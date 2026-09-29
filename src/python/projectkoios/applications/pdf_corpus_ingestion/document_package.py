"""Document-centric deterministic PDF processing artifacts.

This module builds immutable payloads only. Filesystem authorization and
publication remain application-runner concerns.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import PurePosixPath
from typing import BinaryIO, Protocol

from projectkoios.ingestion import (
    DeterministicEquationCandidateDetector,
    EquationDetectionResult,
    ExtractedDocument,
    PdfExtractionArtifactBundle,
    contract_dict,
    serialize_contract,
)
from projectkoios.references import AuthorizedRoot

from .review_tree import (
    MAX_REVIEW_ARTIFACTS,
    ReviewEvidenceIdentity,
    ReviewTreeValidationError,
    validate_review_tree,
)

DOCUMENT_PACKAGE_CONTRACT_ID = "projectkoios.applications.pdf-corpus-document-package"
DOCUMENT_PACKAGE_SCHEMA_VERSION = 1
DOCUMENT_PACKAGE_MANIFEST = PurePosixPath("document-manifest.json")
MAX_DOCUMENT_PACKAGE_ARTIFACTS = 10_000
MAX_DOCUMENT_PACKAGE_BYTES = 512_000_000
MAX_DOCUMENT_PACKAGE_REVIEW_ARTIFACTS = MAX_REVIEW_ARTIFACTS
_MAX_ARTIFACT_BYTES = 128_000_000
_DOCUMENT_KEY = re.compile(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class DocumentPackageError(ValueError):
    """A deterministic document package is malformed or exceeds its bounds."""


class DocumentPackagePublicationError(RuntimeError):
    """Document publication is unsafe, partial, or different."""


class DocumentPackagePublicationAction(StrEnum):
    """Result of one exact document-package publication."""

    CREATE = "create"
    UNCHANGED = "unchanged"


class _EquationDetector(Protocol):
    def detect(
        self,
        document: ExtractedDocument,
        content: BinaryIO,
    ) -> EquationDetectionResult: ...


@dataclass(frozen=True, slots=True)
class DocumentPackageArtifact:
    """One exact, bounded payload at a package-relative path."""

    relative_path: PurePosixPath
    media_type: str
    byte_size: int
    sha256: str
    content: bytes

    @classmethod
    def create(
        cls,
        *,
        relative_path: str | PurePosixPath,
        media_type: str,
        content: bytes,
    ) -> DocumentPackageArtifact:
        path = PurePosixPath(relative_path)
        if not isinstance(content, bytes):
            raise TypeError("document-package content must be immutable bytes")
        return cls(
            relative_path=path,
            media_type=media_type,
            byte_size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            content=content,
        )

    def __post_init__(self) -> None:
        _relative(self.relative_path, "artifact path")
        _text(self.media_type, "artifact media type", maximum=256)
        if not isinstance(self.content, bytes):
            raise TypeError("document-package content must be immutable bytes")
        if (
            type(self.byte_size) is not int
            or self.byte_size < 0
            or self.byte_size > _MAX_ARTIFACT_BYTES
            or self.byte_size != len(self.content)
        ):
            raise DocumentPackageError("artifact byte size is invalid")
        if (
            not isinstance(self.sha256, str)
            or _DIGEST.fullmatch(self.sha256) is None
            or hashlib.sha256(self.content).hexdigest() != self.sha256
        ):
            raise DocumentPackageError("artifact SHA-256 is invalid")


@dataclass(frozen=True, slots=True)
class DeterministicDocumentPackage:
    """A complete source, ingestion, and equation-detection package."""

    document_key: str
    package_id: str
    source_sha256: str
    source_byte_size: int
    extraction_bundle_id: str
    equation_detection_result_id: str
    artifacts: tuple[DocumentPackageArtifact, ...]
    contract_id: str = DOCUMENT_PACKAGE_CONTRACT_ID
    schema_version: int = DOCUMENT_PACKAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _document_key(self.document_key)
        if (
            self.contract_id != DOCUMENT_PACKAGE_CONTRACT_ID
            or self.schema_version != DOCUMENT_PACKAGE_SCHEMA_VERSION
        ):
            raise DocumentPackageError("unsupported document-package contract")
        _stable_id(self.package_id, "document-processing-package")
        _digest(self.source_sha256, "source_sha256")
        if type(self.source_byte_size) is not int or self.source_byte_size <= 0:
            raise DocumentPackageError("source_byte_size must be positive")
        _stable_id(self.extraction_bundle_id, "pdf-extraction-artifact-bundle")
        _stable_id(
            self.equation_detection_result_id,
            "equation-detection-result",
        )
        if (
            not isinstance(self.artifacts, tuple)
            or not self.artifacts
            or len(self.artifacts) > MAX_DOCUMENT_PACKAGE_ARTIFACTS
            or any(
                not isinstance(item, DocumentPackageArtifact) for item in self.artifacts
            )
        ):
            raise DocumentPackageError("document-package artifacts are invalid")
        paths = tuple(item.relative_path for item in self.artifacts)
        if len(set(paths)) != len(paths):
            raise DocumentPackageError("document-package paths must be unique")
        if paths[-1] != DOCUMENT_PACKAGE_MANIFEST:
            raise DocumentPackageError("document manifest must be written last")
        if PurePosixPath("source/document.pdf") not in paths:
            raise DocumentPackageError("document package has no exact source PDF")
        if any(
            path.parts[0] in {"assisted", "human", "transcript"}
            or "assisted" in path.parts
            or "human" in path.parts
            for path in paths
        ):
            raise DocumentPackageError(
                "deterministic package cannot contain assisted or human artifacts"
            )
        if sum(item.byte_size for item in self.artifacts) > (
            MAX_DOCUMENT_PACKAGE_BYTES
        ):
            raise DocumentPackageError("document package exceeds its byte limit")
        source = next(
            item
            for item in self.artifacts
            if item.relative_path == PurePosixPath("source/document.pdf")
        )
        if (
            source.sha256 != self.source_sha256
            or source.byte_size != self.source_byte_size
            or source.media_type != "application/pdf"
        ):
            raise DocumentPackageError("source artifact identity is inconsistent")
        manifest = self.artifacts[-1]
        if manifest.media_type != "application/json":
            raise DocumentPackageError("document manifest media type is invalid")
        try:
            manifest_value = json.loads(manifest.content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DocumentPackageError("document manifest is malformed") from error
        if (
            not isinstance(manifest_value, dict)
            or manifest_value.get("package_id") != self.package_id
            or manifest_value.get("document_key") != self.document_key
            or manifest_value.get("source_sha256") != self.source_sha256
            or manifest_value.get("status") != "deterministic-complete"
        ):
            raise DocumentPackageError("document manifest is inconsistent")


def build_deterministic_document_package(
    *,
    document_key: str,
    source_pdf: bytes,
    extraction: PdfExtractionArtifactBundle,
    equation_detector: _EquationDetector | None = None,
) -> DeterministicDocumentPackage:
    """Build one bounded document package without filesystem mutation."""
    _document_key(document_key)
    if not isinstance(source_pdf, bytes):
        raise TypeError("source_pdf must be exact immutable bytes")
    if not isinstance(extraction, PdfExtractionArtifactBundle):
        raise TypeError("extraction must be a PdfExtractionArtifactBundle")
    source = extraction.result.document.source
    source_sha256 = hashlib.sha256(source_pdf).hexdigest()
    if (
        not source_pdf.startswith(b"%PDF-")
        or source_sha256 != source.content_hash
        or len(source_pdf) != source.byte_length
    ):
        raise DocumentPackageError("source PDF bytes do not match extraction evidence")

    artifacts: list[DocumentPackageArtifact] = []
    artifacts.append(
        DocumentPackageArtifact.create(
            relative_path="source/document.pdf",
            media_type="application/pdf",
            content=source_pdf,
        )
    )
    artifacts.append(
        _json_artifact(
            "source/manifest.json",
            _identified(
                "document-source-manifest",
                {
                    "document_key": document_key,
                    "locator": source.locator,
                    "media_type": source.media_type,
                    "schema_version": 1,
                    "source_blob_id": source.blob_id,
                    "source_byte_size": source.byte_length,
                    "source_id": source.source_id,
                    "source_path": "source/document.pdf",
                    "source_sha256": source.content_hash,
                    "status": "immutable-source",
                },
            ),
        )
    )

    ingestion_paths: list[str] = []
    for owner_artifact in extraction.artifacts:
        target = _ingestion_path(owner_artifact.relative_path)
        artifacts.append(
            DocumentPackageArtifact.create(
                relative_path=target,
                media_type=owner_artifact.media_type,
                content=owner_artifact.content,
            )
        )
        ingestion_paths.append(target.as_posix())
    artifacts.append(
        _json_artifact(
            "ingestion/manifest.json",
            _identified(
                "document-ingestion-manifest",
                {
                    "artifact_paths": ingestion_paths,
                    "document_key": document_key,
                    "extraction_bundle_id": extraction.bundle_id,
                    "extraction_configuration_digest": (
                        extraction.configuration.configuration_digest
                    ),
                    "extraction_manifest_id": (extraction.result.manifest.manifest_id),
                    "schema_version": 1,
                    "source_sha256": source.content_hash,
                    "status": "deterministic-complete",
                },
            ),
        )
    )

    detector = equation_detector or DeterministicEquationCandidateDetector()
    detection = detector.detect(extraction.result.document, BytesIO(source_pdf))
    detection_path = PurePosixPath("content/equations/deterministic/detection.json")
    artifacts.append(
        DocumentPackageArtifact.create(
            relative_path=detection_path,
            media_type=(
                "application/vnd.projectkoios.ingestion.equation-detection+json"
            ),
            content=(serialize_contract(detection) + "\n").encode("utf-8"),
        )
    )

    index_records: list[dict[str, object]] = []
    for candidate in detection.candidates:
        candidate_digest = _stable_id_digest(
            candidate.candidate_id,
            "equation-candidate",
        )
        root = PurePosixPath("content/equations/regions") / candidate_digest
        image_path = root / "source/image.png"
        source_manifest_path = root / "source/manifest.json"
        deterministic_manifest_path = root / "deterministic/manifest.json"
        region = candidate.rendered_region
        artifacts.append(
            DocumentPackageArtifact.create(
                relative_path=image_path,
                media_type="image/png",
                content=region.content,
            )
        )
        region_value = contract_dict(region)
        region_value.pop("content")
        artifacts.append(
            _json_artifact(
                source_manifest_path,
                _identified(
                    "equation-region-source-manifest",
                    {
                        "candidate_id": candidate.candidate_id,
                        "document_key": document_key,
                        "image_path": image_path.as_posix(),
                        "image_sha256": region.content_sha256,
                        "region": region_value,
                        "schema_version": 1,
                        "source_sha256": source.content_hash,
                        "status": "immutable-source-evidence",
                    },
                ),
            )
        )
        candidate_value = contract_dict(candidate)
        rendered = candidate_value.get("rendered_region")
        if not isinstance(rendered, dict):
            raise DocumentPackageError("candidate region projection is malformed")
        rendered.pop("content", None)
        artifacts.append(
            _json_artifact(
                deterministic_manifest_path,
                _identified(
                    "equation-deterministic-manifest",
                    {
                        "candidate": candidate_value,
                        "detection_result_id": detection.result_id,
                        "document_key": document_key,
                        "schema_version": 1,
                        "status": "deterministic-proposal",
                    },
                ),
            )
        )
        index_records.append(
            {
                "candidate_id": candidate.candidate_id,
                "deterministic_manifest": (deterministic_manifest_path.as_posix()),
                "evidence_status": candidate.evidence_status.value,
                "image_path": image_path.as_posix(),
                "image_sha256": region.content_sha256,
                "kind": candidate.kind.value,
                "source_manifest": source_manifest_path.as_posix(),
            }
        )

    index_path = PurePosixPath("content/equations/index.json")
    artifacts.append(
        _json_artifact(
            index_path,
            {
                "candidates": index_records,
                "detection_artifact": detection_path.as_posix(),
                "detection_result_id": detection.result_id,
                "document_key": document_key,
                "schema_version": 1,
                "source_sha256": source.content_hash,
                "status": "deterministic-unreviewed",
            },
        )
    )
    equation_artifact_paths = [
        item.relative_path.as_posix()
        for item in artifacts
        if item.relative_path.parts[:2] == ("content", "equations")
    ]
    artifacts.append(
        _json_artifact(
            "content/equations/manifest.json",
            _identified(
                "document-equation-manifest",
                {
                    "artifact_paths": equation_artifact_paths,
                    "candidate_count": len(detection.candidates),
                    "detection_result_id": detection.result_id,
                    "document_key": document_key,
                    "schema_version": 1,
                    "source_sha256": source.content_hash,
                    "status": "deterministic-unreviewed",
                    "warning_count": len(detection.warnings),
                },
            ),
        )
    )

    inventory = [_inventory_item(item) for item in artifacts]
    completion_identity: dict[str, object] = {
        "artifact_files": inventory,
        "contract_id": DOCUMENT_PACKAGE_CONTRACT_ID,
        "document_key": document_key,
        "equation_detection_result_id": detection.result_id,
        "extraction_bundle_id": extraction.bundle_id,
        "schema_version": DOCUMENT_PACKAGE_SCHEMA_VERSION,
        "source_byte_size": source.byte_length,
        "source_sha256": source.content_hash,
        "stages": {
            "assisted": "not-started",
            "equation_detection": "deterministic-complete",
            "human_review": "not-started",
            "ingestion": "deterministic-complete",
            "transcript": "not-started",
        },
        "status": "deterministic-complete",
    }
    package_id = _id("document-processing-package", completion_identity)
    completion = dict(completion_identity)
    completion["package_id"] = package_id
    artifacts.append(_json_artifact(DOCUMENT_PACKAGE_MANIFEST, completion))

    return DeterministicDocumentPackage(
        document_key=document_key,
        package_id=package_id,
        source_sha256=source.content_hash,
        source_byte_size=source.byte_length,
        extraction_bundle_id=extraction.bundle_id,
        equation_detection_result_id=detection.result_id,
        artifacts=tuple(artifacts),
    )


def publish_deterministic_document_package(
    package: DeterministicDocumentPackage,
    *,
    output_root: AuthorizedRoot,
) -> DocumentPackagePublicationAction:
    """Exclusively publish one document directory or verify exact replay."""
    if not isinstance(package, DeterministicDocumentPackage):
        raise TypeError("package must be a DeterministicDocumentPackage")
    if not isinstance(output_root, AuthorizedRoot):
        raise TypeError("output_root must be an AuthorizedRoot")
    relative = PurePosixPath(package.document_key)
    state = output_root.state(relative)
    if state == "regular":
        raise DocumentPackagePublicationError(
            "document-package target is not a directory"
        )
    if state == "directory":
        existing = AuthorizedRoot.existing(
            output_root.child_path(relative),
            label=f"existing document package {package.document_key}",
            root_alias=output_root.preflight_evidence.root_alias,
            storage_class=output_root.preflight_evidence.storage_class,
            placeholder_probe=output_root.placeholder_probe,
        )
        _verify_publication(existing, package)
        return DocumentPackagePublicationAction.UNCHANGED

    destination = output_root.create_directory(relative)
    for artifact in package.artifacts:
        _create_parents(destination, artifact.relative_path)
        destination.write_bytes(
            artifact.relative_path,
            artifact.content,
            replace=False,
        )
    _verify_publication(destination, package)
    return DocumentPackagePublicationAction.CREATE


def _verify_publication(
    root: AuthorizedRoot,
    package: DeterministicDocumentPackage,
) -> None:
    expected = {item.relative_path: item for item in package.artifacts}
    try:
        paths = root.iter_files(
            suffix="",
            recursive=True,
            max_files=(
                MAX_DOCUMENT_PACKAGE_ARTIFACTS + MAX_DOCUMENT_PACKAGE_REVIEW_ARTIFACTS
            ),
            max_entries=(
                MAX_DOCUMENT_PACKAGE_ARTIFACTS
                + MAX_DOCUMENT_PACKAGE_REVIEW_ARTIFACTS
                + 10_000
            ),
            max_depth=8,
        )
    except (OSError, ValueError) as error:
        raise DocumentPackagePublicationError(
            "document-package inventory is unsafe"
        ) from error
    observed_paths = set(paths)
    expected_paths = set(expected)
    if (
        not expected_paths.issubset(observed_paths)
        or root.state(DOCUMENT_PACKAGE_MANIFEST) != "regular"
    ):
        raise DocumentPackagePublicationError(
            "document-package publication is incomplete or different"
        )
    _verify_review_extensions(
        root,
        observed_paths - expected_paths,
        package,
        expected,
    )
    for path, artifact in expected.items():
        try:
            observed = root.observe_file(
                path,
                max_bytes=_MAX_ARTIFACT_BYTES,
            )
        except (OSError, ValueError) as error:
            raise DocumentPackagePublicationError(
                "document-package artifact cannot be verified"
            ) from error
        if (
            observed.byte_size != artifact.byte_size
            or observed.sha256 != artifact.sha256
        ):
            raise DocumentPackagePublicationError(
                "document-package artifact bytes are different"
            )


def _verify_review_extensions(
    root: AuthorizedRoot,
    paths: set[PurePosixPath],
    package: DeterministicDocumentPackage,
    deterministic: dict[PurePosixPath, DocumentPackageArtifact],
) -> None:
    if not paths:
        return
    index_artifact = deterministic.get(PurePosixPath("content/equations/index.json"))
    if index_artifact is None:
        raise DocumentPackagePublicationError(
            "document-package equation index is unavailable"
        )
    try:
        index = json.loads(index_artifact.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DocumentPackagePublicationError(
            "document-package equation index is malformed"
        ) from error
    candidates = index.get("candidates") if isinstance(index, dict) else None
    if not isinstance(candidates, list):
        raise DocumentPackagePublicationError(
            "document-package equation index is malformed"
        )
    bindings: dict[str, ReviewEvidenceIdentity] = {}
    for value in candidates:
        if not isinstance(value, dict):
            raise DocumentPackagePublicationError(
                "document-package equation index is malformed"
            )
        candidate_id = value.get("candidate_id")
        deterministic_path_value = value.get("deterministic_manifest")
        image_path_value = value.get("image_path")
        image_sha256 = value.get("image_sha256")
        source_manifest_value = value.get("source_manifest")
        if (
            not isinstance(candidate_id, str)
            or not isinstance(deterministic_path_value, str)
            or not isinstance(image_path_value, str)
            or not isinstance(image_sha256, str)
            or not isinstance(source_manifest_value, str)
        ):
            raise DocumentPackagePublicationError(
                "document-package equation index is malformed"
            )
        deterministic_path = PurePosixPath(deterministic_path_value)
        image_path = PurePosixPath(image_path_value)
        source_manifest = PurePosixPath(source_manifest_value)
        parts = deterministic_path.parts
        if (
            len(parts) != 6
            or parts[:3] != ("content", "equations", "regions")
            or _DIGEST.fullmatch(parts[3]) is None
            or parts[4:] != ("deterministic", "manifest.json")
            or deterministic_path not in deterministic
            or image_path not in deterministic
            or source_manifest not in deterministic
            or deterministic[image_path].sha256 != image_sha256
            or parts[3] in bindings
        ):
            raise DocumentPackagePublicationError(
                "document-package equation index is inconsistent"
            )
        bindings[parts[3]] = ReviewEvidenceIdentity(
            document_id=package.document_key,
            candidate_id=candidate_id,
            source_sha256=package.source_sha256,
            candidate_evidence_sha256=deterministic[deterministic_path].sha256,
            region_image_sha256=image_sha256,
        )
    grouped: dict[str, set[PurePosixPath]] = {}
    for path in paths:
        if (
            len(path.parts) < 5
            or path.parts[:3] != ("content", "equations", "regions")
            or path.parts[3] not in bindings
        ):
            raise DocumentPackagePublicationError(
                "document-package publication contains an unknown artifact"
            )
        grouped.setdefault(path.parts[3], set()).add(path)
    for candidate_key, candidate_paths in grouped.items():
        try:
            validate_review_tree(
                root,
                candidate_root=(
                    PurePosixPath("content/equations/regions") / candidate_key
                ),
                binding=bindings[candidate_key],
                expected_paths=candidate_paths,
            )
        except ReviewTreeValidationError as error:
            raise DocumentPackagePublicationError(
                "document-package review extension is malformed"
            ) from error


def _create_parents(root: AuthorizedRoot, relative: PurePosixPath) -> None:
    current = PurePosixPath()
    for part in relative.parts[:-1]:
        current /= part
        state = root.state(current)
        if state == "missing":
            root.create_directory(current)
        elif state != "directory":
            raise DocumentPackagePublicationError(
                "document-package parent is not a directory"
            )


def _ingestion_path(value: str) -> PurePosixPath:
    source = PurePosixPath(value)
    if source == PurePosixPath("raw-extraction.json"):
        return PurePosixPath("ingestion/extraction.json")
    if source.parts[:1] == ("raw-pages",) and len(source.parts) == 2:
        return PurePosixPath("ingestion/pages") / source.name
    raise DocumentPackageError("unsupported owner extraction artifact path")


def _json_artifact(
    path: str | PurePosixPath,
    value: object,
) -> DocumentPackageArtifact:
    return DocumentPackageArtifact.create(
        relative_path=path,
        media_type="application/json",
        content=_canonical(value).encode("utf-8"),
    )


def _identified(namespace: str, value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    result["manifest_id"] = _id(namespace, value)
    return result


def _inventory_item(value: DocumentPackageArtifact) -> dict[str, object]:
    return {
        "byte_size": value.byte_size,
        "media_type": value.media_type,
        "relative_path": value.relative_path.as_posix(),
        "sha256": value.sha256,
    }


def _id(namespace: str, value: object) -> str:
    digest = hashlib.sha256(_canonical(value).encode()).hexdigest()
    return f"{namespace}:sha256:{digest}"


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _document_key(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value.encode("utf-8")) <= 128
        or _DOCUMENT_KEY.fullmatch(value) is None
    ):
        raise DocumentPackageError("document_key must be a portable identifier")
    return value


def _relative(value: PurePosixPath, field: str) -> None:
    if (
        not isinstance(value, PurePosixPath)
        or value.is_absolute()
        or value.as_posix() in {"", "."}
        or any(part in {"", ".", ".."} for part in value.parts)
    ):
        raise DocumentPackageError(f"{field} must be a safe relative path")


def _text(value: object, field: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise DocumentPackageError(f"{field} must be bounded text")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise DocumentPackageError(f"{field} must be a lowercase SHA-256")
    return value


def _stable_id(value: object, namespace: str) -> str:
    if not isinstance(value, str):
        raise DocumentPackageError(f"{namespace} identity must be text")
    prefix = f"{namespace}:sha256:"
    if not value.startswith(prefix) or _DIGEST.fullmatch(value[len(prefix) :]) is None:
        raise DocumentPackageError(f"{namespace} identity is invalid")
    return value


def _stable_id_digest(value: object, namespace: str) -> str:
    valid = _stable_id(value, namespace)
    return valid.rsplit(":", 1)[1]
