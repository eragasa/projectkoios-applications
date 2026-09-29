"""Read-only exact transcript projection for one explicit document package."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from projectkoios.ingestion import (
    RAW_EXTRACTION_MEDIA_TYPE,
    RAW_EXTRACTION_RELATIVE_PATH,
    RAW_PAGE_DIRECTORY,
    RAW_PAGE_TEXT_MEDIA_TYPE,
    IngestionStatus,
    PdfExtractionArtifactIncompleteError,
    PdfExtractionArtifactLimitError,
    PdfExtractionArtifactLimits,
    PdfExtractionArtifactMalformedError,
    PdfExtractionArtifactPayload,
    PdfExtractionConfiguration,
    read_pdf_extraction_transcript,
)
from projectkoios.references import AuthorizedRoot

from .document_package import (
    DOCUMENT_INGESTION_MANIFEST_SCHEMA_VERSION,
    DOCUMENT_PACKAGE_CONTRACT_ID,
    DOCUMENT_PACKAGE_MANIFEST,
    DOCUMENT_PACKAGE_SCHEMA_VERSION,
)
from .equation_review import (
    EquationReviewEvidenceBinding,
    EquationReviewEvidenceMismatch,
    EquationReviewPublicationError,
    _authorized_root,
    _document_package_inventory,
    _id,
    _InventoryEntry,
    _read_json,
    _verify_inventoried_files,
)

DOCUMENT_TRANSCRIPT_CONTRACT_ID = (
    "projectkoios.applications.pdf-corpus-document-transcript"
)
DOCUMENT_TRANSCRIPT_SCHEMA_VERSION = 1
MAX_DOCUMENT_TRANSCRIPT_DISPLAY_NAME_BYTES = 1_024
_INGESTION_MANIFEST = PurePosixPath("ingestion/manifest.json")
_EXTRACTION_ARTIFACT = PurePosixPath("ingestion/extraction.json")
_PAGE_DIRECTORY = PurePosixPath("ingestion/pages")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DOCUMENT_ID = re.compile(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*")


class DocumentTranscriptError(ValueError):
    """An exact transcript cannot be projected from the supplied package."""


class DocumentTranscriptIncompleteError(DocumentTranscriptError):
    """The explicit completed package is missing required evidence."""


class DocumentTranscriptUnavailableError(DocumentTranscriptError):
    """Required package evidence cannot be safely read."""


class DocumentTranscriptMalformedError(DocumentTranscriptError):
    """Package or owner extraction evidence is malformed or inconsistent."""


class DocumentTranscriptUnsupportedPackageError(DocumentTranscriptMalformedError):
    """The package schema cannot safely supply transcript evidence."""


class DocumentTranscriptStatus(StrEnum):
    """Review state of exact machine-extracted text."""

    AUTOMATED_UNREVIEWED = "AUTOMATED_UNREVIEWED"


@dataclass(frozen=True, slots=True)
class DocumentTranscriptPage:
    """One path-free physical page with exact native extracted text."""

    page_id: str
    page_index: int
    physical_page: int
    printed_page_label: str | None
    text: str


@dataclass(frozen=True, slots=True)
class DocumentTranscriptProjection:
    """Bounded immutable display projection for one completed PDF package."""

    contract_id: str
    schema_version: int
    document_id: str
    display_name: str
    status: DocumentTranscriptStatus
    physical_page_count: int
    pages: tuple[DocumentTranscriptPage, ...]
    source_sha256: str
    source_byte_size: int
    media_type: str
    metadata: tuple[tuple[str, str], ...]
    extraction_manifest_id: str
    package_id: str
    projection_id: str


def project_document_transcript(
    *,
    document_root: AuthorizedRoot,
) -> DocumentTranscriptProjection:
    """Verify and project one explicit root without discovery or mutation."""
    if not isinstance(document_root, AuthorizedRoot):
        raise TypeError("document_root must be an AuthorizedRoot")
    try:
        _authorized_root(document_root)
        if document_root.state(DOCUMENT_PACKAGE_MANIFEST) != "regular":
            raise DocumentTranscriptIncompleteError(
                "document completion manifest is unavailable"
            )
        document = _read_json(document_root, DOCUMENT_PACKAGE_MANIFEST)
        schema_version = document.get("schema_version")
        if schema_version != DOCUMENT_PACKAGE_SCHEMA_VERSION:
            raise DocumentTranscriptUnsupportedPackageError(
                "document package schema is unsupported"
            )
        if document.get("contract_id") != DOCUMENT_PACKAGE_CONTRACT_ID:
            raise DocumentTranscriptMalformedError(
                "document package contract is malformed"
            )
        document_id = _document_id(document.get("document_key"))
        source_sha256 = _digest(document.get("source_sha256"), "source SHA-256")
        source_byte_size = _positive_int(
            document.get("source_byte_size"),
            "source byte size",
        )
        binding = EquationReviewEvidenceBinding(
            document_id=document_id,
            candidate_id="document-transcript",
            source_sha256=source_sha256,
            candidate_evidence_sha256="0" * 64,
            region_image_sha256="0" * 64,
        )
        inventory = _document_package_inventory(document, binding)
        for path in inventory:
            if document_root.state(path) != "regular":
                raise DocumentTranscriptIncompleteError(
                    "document completion inventory is incomplete"
                )
        _verify_inventoried_files(document_root, inventory)
        ingestion = _read_json(document_root, _INGESTION_MANIFEST)
        configuration, artifact_limits, artifact_paths = _ingestion_binding(
            ingestion,
            inventory=inventory,
            document_id=document_id,
            source_sha256=source_sha256,
            extraction_bundle_id=document.get("extraction_bundle_id"),
        )
        artifacts = _read_ingestion_artifacts(
            document_root,
            inventory,
            artifact_paths,
        )
        transcript = read_pdf_extraction_transcript(
            artifacts,
            expected_bundle_id=str(document["extraction_bundle_id"]),
            expected_source_sha256=source_sha256,
            expected_source_byte_size=source_byte_size,
            configuration=configuration,
            artifact_limits=artifact_limits,
        )
        if transcript.manifest_id != ingestion.get("extraction_manifest_id"):
            raise DocumentTranscriptMalformedError(
                "ingestion manifest identity is inconsistent"
            )
        if transcript.status is not IngestionStatus.COMPLETED:
            raise DocumentTranscriptMalformedError(
                "only completed extraction evidence can be displayed"
            )
        if transcript.review_status != "automated_unreviewed":
            raise DocumentTranscriptMalformedError(
                "transcript review status is inconsistent"
            )
        pages = tuple(
            DocumentTranscriptPage(
                page_id=page.page_id,
                page_index=page.page_index,
                physical_page=page.page_index + 1,
                printed_page_label=page.printed_page_label,
                text=page.text,
            )
            for page in transcript.pages
        )
        if not pages or tuple(page.page_index for page in pages) != tuple(
            range(len(pages))
        ):
            raise DocumentTranscriptMalformedError(
                "transcript pages are not complete physical-page evidence"
            )
        display_name = _display_name(document_id, transcript.metadata)
        identity: dict[str, object] = {
            "contract_id": DOCUMENT_TRANSCRIPT_CONTRACT_ID,
            "document_id": document_id,
            "display_name": display_name,
            "extraction_manifest_id": transcript.manifest_id,
            "media_type": transcript.media_type,
            "metadata": [list(item) for item in transcript.metadata],
            "package_id": document.get("package_id"),
            "pages": [
                {
                    "page_id": page.page_id,
                    "page_index": page.page_index,
                    "physical_page": page.physical_page,
                    "printed_page_label": page.printed_page_label,
                    "text": page.text,
                }
                for page in pages
            ],
            "physical_page_count": len(pages),
            "schema_version": DOCUMENT_TRANSCRIPT_SCHEMA_VERSION,
            "source_byte_size": transcript.source_byte_size,
            "source_sha256": transcript.source_sha256,
            "status": DocumentTranscriptStatus.AUTOMATED_UNREVIEWED.value,
        }
        return DocumentTranscriptProjection(
            contract_id=DOCUMENT_TRANSCRIPT_CONTRACT_ID,
            schema_version=DOCUMENT_TRANSCRIPT_SCHEMA_VERSION,
            document_id=document_id,
            display_name=display_name,
            status=DocumentTranscriptStatus.AUTOMATED_UNREVIEWED,
            physical_page_count=len(pages),
            pages=pages,
            source_sha256=transcript.source_sha256,
            source_byte_size=transcript.source_byte_size,
            media_type=transcript.media_type,
            metadata=transcript.metadata,
            extraction_manifest_id=transcript.manifest_id,
            package_id=str(document["package_id"]),
            projection_id=_projection_id(identity),
        )
    except DocumentTranscriptError:
        raise
    except PdfExtractionArtifactIncompleteError as error:
        raise DocumentTranscriptIncompleteError(
            "ingestion extraction evidence is incomplete"
        ) from error
    except (
        PdfExtractionArtifactLimitError,
        PdfExtractionArtifactMalformedError,
        EquationReviewEvidenceMismatch,
    ) as error:
        raise DocumentTranscriptMalformedError(
            "document package or ingestion evidence is malformed"
        ) from error
    except EquationReviewPublicationError as error:
        if _caused_by_os_error(error):
            raise DocumentTranscriptUnavailableError(
                "document package evidence is unavailable"
            ) from error
        raise DocumentTranscriptMalformedError(
            "document package evidence is malformed"
        ) from error
    except OSError as error:
        raise DocumentTranscriptUnavailableError(
            "document package evidence is unavailable"
        ) from error
    except (KeyError, TypeError, ValueError) as error:
        raise DocumentTranscriptMalformedError(
            "document transcript projection evidence is malformed"
        ) from error


def _ingestion_binding(
    value: dict[str, object],
    *,
    inventory: dict[PurePosixPath, _InventoryEntry],
    document_id: str,
    source_sha256: str,
    extraction_bundle_id: object,
) -> tuple[
    PdfExtractionConfiguration,
    PdfExtractionArtifactLimits,
    tuple[PurePosixPath, ...],
]:
    expected_keys = {
        "artifact_limits",
        "artifact_paths",
        "document_key",
        "extraction_bundle_id",
        "extraction_configuration",
        "extraction_configuration_digest",
        "extraction_manifest_id",
        "manifest_id",
        "schema_version",
        "source_sha256",
        "status",
    }
    identity = dict(value)
    manifest_id = identity.pop("manifest_id", None)
    if (
        set(value) != expected_keys
        or value.get("schema_version") != DOCUMENT_INGESTION_MANIFEST_SCHEMA_VERSION
        or value.get("document_key") != document_id
        or value.get("source_sha256") != source_sha256
        or value.get("extraction_bundle_id") != extraction_bundle_id
        or value.get("status") != "deterministic-complete"
        or manifest_id != _id("document-ingestion-manifest", identity)
    ):
        raise DocumentTranscriptMalformedError(
            "document ingestion manifest is inconsistent"
        )
    raw_configuration = value.get("extraction_configuration")
    raw_limits = value.get("artifact_limits")
    if not isinstance(raw_configuration, dict) or set(raw_configuration) != {
        "low_text_character_threshold",
        "maximum_pages",
    }:
        raise DocumentTranscriptMalformedError(
            "document extraction configuration is malformed"
        )
    if not isinstance(raw_limits, dict) or set(raw_limits) != {
        "max_artifacts",
        "max_page_text_bytes",
        "max_raw_extraction_bytes",
        "max_total_artifact_bytes",
    }:
        raise DocumentTranscriptMalformedError(
            "document extraction artifact limits are malformed"
        )
    configuration = PdfExtractionConfiguration(
        low_text_character_threshold=_nonnegative_int(
            raw_configuration.get("low_text_character_threshold"),
            "low text character threshold",
        ),
        maximum_pages=_positive_int(
            raw_configuration.get("maximum_pages"),
            "maximum pages",
        ),
    )
    limits = PdfExtractionArtifactLimits(
        max_artifacts=_positive_int(
            raw_limits.get("max_artifacts"),
            "maximum artifact count",
        ),
        max_raw_extraction_bytes=_positive_int(
            raw_limits.get("max_raw_extraction_bytes"),
            "maximum raw extraction bytes",
        ),
        max_page_text_bytes=_positive_int(
            raw_limits.get("max_page_text_bytes"),
            "maximum page text bytes",
        ),
        max_total_artifact_bytes=_positive_int(
            raw_limits.get("max_total_artifact_bytes"),
            "maximum total artifact bytes",
        ),
    )
    if value.get("extraction_configuration_digest") != (
        configuration.configuration_digest
    ):
        raise DocumentTranscriptMalformedError(
            "document extraction configuration digest is inconsistent"
        )
    raw_paths = value.get("artifact_paths")
    if (
        not isinstance(raw_paths, list)
        or not raw_paths
        or any(not isinstance(item, str) for item in raw_paths)
    ):
        raise DocumentTranscriptMalformedError(
            "document ingestion artifact inventory is malformed"
        )
    paths = tuple(PurePosixPath(item) for item in raw_paths)
    expected_paths = {
        path
        for path in inventory
        if path.parts[:1] == ("ingestion",) and path != _INGESTION_MANIFEST
    }
    if (
        len(paths) != len(set(paths))
        or set(paths) != expected_paths
        or not paths
        or paths[0] != _EXTRACTION_ARTIFACT
    ):
        raise DocumentTranscriptMalformedError(
            "document ingestion artifact membership is inconsistent"
        )
    return configuration, limits, paths


def _read_ingestion_artifacts(
    root: AuthorizedRoot,
    inventory: dict[PurePosixPath, _InventoryEntry],
    paths: tuple[PurePosixPath, ...],
) -> tuple[PdfExtractionArtifactPayload, ...]:
    artifacts: list[PdfExtractionArtifactPayload] = []
    for path in paths:
        entry = inventory[path]
        if path == _EXTRACTION_ARTIFACT:
            owner_path = RAW_EXTRACTION_RELATIVE_PATH
            expected_media_type = RAW_EXTRACTION_MEDIA_TYPE
        elif path.parent == _PAGE_DIRECTORY:
            owner_path = f"{RAW_PAGE_DIRECTORY}/{path.name}"
            expected_media_type = RAW_PAGE_TEXT_MEDIA_TYPE
        else:
            raise DocumentTranscriptMalformedError(
                "document ingestion artifact path is unsupported"
            )
        if entry.media_type != expected_media_type:
            raise DocumentTranscriptMalformedError(
                "document ingestion artifact media type is inconsistent"
            )
        content = root.read_bytes(path, max_bytes=entry.byte_size)
        if (
            len(content) != entry.byte_size
            or hashlib.sha256(content).hexdigest() != entry.sha256
        ):
            raise DocumentTranscriptMalformedError(
                "document ingestion artifact bytes changed while reading"
            )
        artifacts.append(
            PdfExtractionArtifactPayload.create(
                relative_path=owner_path,
                media_type=entry.media_type,
                content=content,
            )
        )
    return tuple(artifacts)


def _display_name(
    document_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> str:
    titles = tuple(value for key, value in metadata if key == "title" and value)
    if len(titles) > 1:
        raise DocumentTranscriptMalformedError(
            "document metadata contains duplicate titles"
        )
    value = document_id if not titles else titles[0]
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise DocumentTranscriptMalformedError(
            "document display name is not valid UTF-8"
        ) from error
    if not encoded or len(encoded) > MAX_DOCUMENT_TRANSCRIPT_DISPLAY_NAME_BYTES:
        raise DocumentTranscriptMalformedError(
            "document display name exceeds its bound"
        )
    return value


def _document_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or _DOCUMENT_ID.fullmatch(value) is None
        or len(value.encode("utf-8")) > 128
    ):
        raise DocumentTranscriptMalformedError("document identity is malformed")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise DocumentTranscriptMalformedError(f"{field} is malformed")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise DocumentTranscriptMalformedError(f"{field} is malformed")
    return value


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise DocumentTranscriptMalformedError(f"{field} is malformed")
    return value


def _projection_id(value: object) -> str:
    canonical = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return f"document-transcript:sha256:{hashlib.sha256(canonical).hexdigest()}"


def _caused_by_os_error(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, OSError):
            return True
        current = current.__cause__
    return False
