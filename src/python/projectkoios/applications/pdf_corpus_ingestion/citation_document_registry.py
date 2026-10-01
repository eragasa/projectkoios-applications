"""Bounded immutable registry for synchronous citation-document results."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import final

from projectkoios.references import AuthorizedRoot

from .citation_document_contracts import (
    CITATION_DOCUMENT_REGISTRY_CONTRACT_ID,
    CitationDocumentIngestionRequest,
    CitationDocumentIngestionResult,
    CitationDocumentTerminalStatus,
    canonical_json,
)
from .transcript import (
    DocumentTranscriptProjection,
    project_document_transcript,
)

MAX_CITATION_DOCUMENT_REGISTRY_ENTRIES = 10_000
MAX_CITATION_DOCUMENT_REGISTRY_RECORD_BYTES = 64_000
_REGISTRY_NAME = re.compile(r"citation-document-result-([0-9a-f]{64})\.json")
_DOCUMENT_ID = re.compile(r"citation-document-[0-9a-f]{64}")


class CitationDocumentRegistryError(ValueError):
    """The immutable result registry is malformed, conflicting, or unsafe."""


class CitationDocumentRegistryLimitError(CitationDocumentRegistryError):
    """The bounded result registry is full or oversized."""


@final
@dataclass(frozen=True, slots=True)
class CitationDocumentRegistryProjection:
    """Path-free bounded projection of every terminal request result."""

    results: tuple[CitationDocumentIngestionResult, ...]
    successful_document_ids: tuple[str, ...]
    projection_id: str = field(init=False)
    contract_id: str = CITATION_DOCUMENT_REGISTRY_CONTRACT_ID

    def __post_init__(self) -> None:
        if (
            type(self.results) is not tuple
            or len(self.results) > MAX_CITATION_DOCUMENT_REGISTRY_ENTRIES
            or any(
                type(item) is not CitationDocumentIngestionResult
                for item in self.results
            )
        ):
            raise TypeError("registry projection results are invalid")
        if tuple(item.request_id for item in self.results) != tuple(
            sorted({item.request_id for item in self.results})
        ):
            raise ValueError("registry projection results are not canonical")
        expected_documents = tuple(
            sorted(
                item.document_id
                for item in self.results
                if item.status is CitationDocumentTerminalStatus.SUCCEEDED
            )
        )
        if self.successful_document_ids != expected_documents or len(
            expected_documents
        ) != len(set(expected_documents)):
            raise ValueError("registry successful document identities are invalid")
        payload = {
            "contract_id": self.contract_id,
            "result_ids": [item.result_id for item in self.results],
            "successful_document_ids": list(self.successful_document_ids),
        }
        canonical = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        object.__setattr__(
            self,
            "projection_id",
            "citation-document-registry-projection:sha256:"
            + hashlib.sha256(canonical).hexdigest(),
        )


@final
@dataclass(frozen=True, slots=True)
class CitationDocumentRegistry:
    """One local immutable terminal-result repository."""

    root: AuthorizedRoot
    max_entries: int = MAX_CITATION_DOCUMENT_REGISTRY_ENTRIES

    def __post_init__(self) -> None:
        if not isinstance(self.root, AuthorizedRoot):
            raise TypeError("root must be an AuthorizedRoot")
        if (
            type(self.max_entries) is not int
            or not 0 < self.max_entries <= MAX_CITATION_DOCUMENT_REGISTRY_ENTRIES
        ):
            raise ValueError("max_entries is outside the registry bound")

    def lookup(
        self,
        request: CitationDocumentIngestionRequest,
    ) -> CitationDocumentIngestionResult | None:
        """Load and bind one exact terminal replay result."""
        if type(request) is not CitationDocumentIngestionRequest:
            raise TypeError("request must be a CitationDocumentIngestionRequest")
        relative = _record_path(request.request_id)
        state = self.root.state(relative)
        if state == "missing":
            return None
        if state != "regular":
            raise CitationDocumentRegistryError(
                "registry request record is not a regular file"
            )
        result = self._read(relative)
        result.validate_request(request)
        return result

    def record(
        self,
        request: CitationDocumentIngestionRequest,
        result: CitationDocumentIngestionResult,
    ) -> CitationDocumentIngestionResult:
        """Publish one terminal result exactly once, or verify exact replay."""
        if type(result) is not CitationDocumentIngestionResult:
            raise TypeError("result must be a CitationDocumentIngestionResult")
        result.validate_request(request)
        relative = _record_path(request.request_id)
        content = canonical_json(result.record_payload())
        if len(content) > MAX_CITATION_DOCUMENT_REGISTRY_RECORD_BYTES:
            raise CitationDocumentRegistryLimitError(
                "registry record exceeds its byte bound"
            )
        state = self.root.state(relative)
        if state == "regular":
            existing = self._read(relative)
            existing.validate_request(request)
            if existing != result:
                raise CitationDocumentRegistryError(
                    "registry request already has a different terminal result"
                )
            return existing
        if state != "missing":
            raise CitationDocumentRegistryError(
                "registry request destination is unsafe"
            )
        if len(self._paths()) >= self.max_entries:
            raise CitationDocumentRegistryLimitError("registry is full")
        try:
            self.root.write_bytes(relative, content, replace=False)
        except FileExistsError:
            existing = self._read(relative)
            existing.validate_request(request)
            if existing != result:
                raise CitationDocumentRegistryError(
                    "concurrent registry result conflicts"
                ) from None
            return existing
        return self._read(relative)

    def project(self) -> CitationDocumentRegistryProjection:
        """Return all bounded terminal results in canonical request order."""
        results = tuple(self._read(path) for path in self._paths())
        return CitationDocumentRegistryProjection(
            results=results,
            successful_document_ids=tuple(
                sorted(
                    item.document_id
                    for item in results
                    if item.status is CitationDocumentTerminalStatus.SUCCEEDED
                )
            ),
        )

    def lookup_document(
        self,
        document_id: str,
    ) -> CitationDocumentIngestionResult:
        """Return one registered successful document result by exact identity."""
        if type(document_id) is not str or _DOCUMENT_ID.fullmatch(document_id) is None:
            raise CitationDocumentRegistryError("document identity is invalid")
        matches = tuple(
            item
            for item in self.project().results
            if item.status is CitationDocumentTerminalStatus.SUCCEEDED
            and item.document_id == document_id
        )
        if len(matches) != 1:
            raise CitationDocumentRegistryError(
                "registered successful document is absent or ambiguous"
            )
        return matches[0]

    def transcript(
        self,
        *,
        document_id: str,
        package_root: AuthorizedRoot,
    ) -> DocumentTranscriptProjection:
        """Verify and return one registered successful transcript."""
        result = self.lookup_document(document_id)
        transcript = _project_package(package_root, document_id)
        if (
            transcript.package_id != result.package_id
            or transcript.projection_id != result.transcript_projection_id
            or transcript.physical_page_count != result.physical_page_count
        ):
            raise CitationDocumentRegistryError(
                "registered transcript evidence no longer matches"
            )
        return transcript

    def _paths(self) -> tuple[PurePosixPath, ...]:
        try:
            paths = self.root.iter_files(
                suffix="",
                recursive=False,
                reject_directories=True,
                max_files=self.max_entries + 1,
                max_entries=self.max_entries + 1,
                max_depth=1,
            )
        except (OSError, ValueError) as error:
            raise CitationDocumentRegistryLimitError(
                "registry inventory exceeds its bound or is unsafe"
            ) from error
        if len(paths) > self.max_entries or any(
            len(path.parts) != 1 or _REGISTRY_NAME.fullmatch(path.name) is None
            for path in paths
        ):
            raise CitationDocumentRegistryError(
                "registry contains an unsupported entry"
            )
        return paths

    def _read(self, relative: PurePosixPath) -> CitationDocumentIngestionResult:
        try:
            content = self.root.read_bytes(
                relative,
                max_bytes=MAX_CITATION_DOCUMENT_REGISTRY_RECORD_BYTES,
            )
            value = json.loads(content)
            result = CitationDocumentIngestionResult.from_record(value)
        except CitationDocumentRegistryError:
            raise
        except (
            OSError,
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
        ) as error:
            raise CitationDocumentRegistryError(
                "registry record is malformed or unavailable"
            ) from error
        if relative != _record_path(result.request_id):
            raise CitationDocumentRegistryError(
                "registry record path does not match its request identity"
            )
        return result


def _record_path(request_id: str) -> PurePosixPath:
    tail = request_id.rsplit(":", 1)[-1]
    if re.fullmatch(r"[0-9a-f]{64}", tail) is None:
        raise CitationDocumentRegistryError("request identity is invalid")
    return PurePosixPath(f"citation-document-result-{tail}.json")


def _project_package(
    package_root: AuthorizedRoot,
    document_id: str,
) -> DocumentTranscriptProjection:
    if not isinstance(package_root, AuthorizedRoot):
        raise TypeError("package_root must be an AuthorizedRoot")
    if package_root.state(document_id) != "directory":
        raise CitationDocumentRegistryError(
            "registered document package is unavailable"
        )
    document_root = AuthorizedRoot.existing(
        package_root.child_path(document_id),
        label=f"registered citation document {document_id}",
        root_alias=package_root.preflight_evidence.root_alias,
        storage_class=package_root.preflight_evidence.storage_class,
        placeholder_probe=package_root.placeholder_probe,
    )
    return project_document_transcript(document_root=document_root)
