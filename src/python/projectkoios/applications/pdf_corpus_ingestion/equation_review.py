"""Append-only assisted equation attempts and human review revisions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import PurePosixPath

from projectkoios.references import AuthorizedRoot, RootStorageClass

from . import review_tree as _review_tree
from .document_package import (
    DOCUMENT_PACKAGE_CONTRACT_ID,
    DOCUMENT_PACKAGE_MANIFEST,
    DOCUMENT_PACKAGE_SCHEMA_VERSION,
    MAX_DOCUMENT_PACKAGE_ARTIFACTS,
    MAX_DOCUMENT_PACKAGE_BYTES,
)
from .review_tree import (
    MAX_ASSISTED_PROPOSAL_CHARACTERS,
    MAX_EQUATION_REVIEW_NOTE_CHARACTERS,
    MAX_EQUATION_REVIEW_REVISIONS,
    ReviewEvidenceIdentity,
    ReviewTreeValidationError,
    validate_review_tree,
)

EQUATION_REVIEW_CONTRACT_ID = _review_tree.EQUATION_REVIEW_CONTRACT_ID
EQUATION_REVIEW_SCHEMA_VERSION = _review_tree.EQUATION_REVIEW_SCHEMA_VERSION
_MAX_MANIFEST_BYTES = 20_000_000
_MAX_MANIFEST_DEPTH = 32
_MAX_MANIFEST_ITEMS = 200_000
_MAX_MANIFEST_STRING_BYTES = 1_100_000
_MAX_SOURCE_BYTES = 128_000_000
_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DOCUMENT_PACKAGE_STAGES = {
    "assisted": "not-started",
    "equation_detection": "deterministic-complete",
    "human_review": "not-started",
    "ingestion": "deterministic-complete",
    "transcript": "not-started",
}


class EquationReviewError(ValueError):
    """An equation-review value is malformed or inconsistent."""


class EquationReviewEvidenceMismatch(EquationReviewError):
    """The requested append is stale relative to immutable source evidence."""


class EquationReviewStaleRevision(EquationReviewError):
    """The expected previous human revision is no longer current."""


class EquationReviewConcurrencyError(RuntimeError):
    """Another writer won the same exclusive append position."""


class EquationReviewPublicationError(RuntimeError):
    """An append-only review artifact is partial, unsafe, or different."""


class EquationReviewPublicationAction(StrEnum):
    """Result of exact immutable artifact publication."""

    CREATE = "create"
    UNCHANGED = "unchanged"


class EquationReviewDisposition(StrEnum):
    """Explicit human disposition projected by the equation-review API."""

    ACCEPT_TRANSCRIPTION = "ACCEPT_TRANSCRIPTION"
    REJECT_CANDIDATE = "REJECT_CANDIDATE"
    REVISION_REQUIRED = "REVISION_REQUIRED"


@dataclass(frozen=True, slots=True)
class _InventoryEntry:
    relative_path: PurePosixPath
    media_type: str
    byte_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class EquationReviewEvidenceBinding:
    """Exact immutable evidence identities required by every review record."""

    document_id: str
    candidate_id: str
    source_sha256: str
    candidate_evidence_sha256: str
    region_image_sha256: str

    def __post_init__(self) -> None:
        _opaque_id(self.document_id, "document_id")
        _opaque_id(self.candidate_id, "candidate_id")
        _digest(self.source_sha256, "source_sha256")
        _digest(
            self.candidate_evidence_sha256,
            "candidate_evidence_sha256",
        )
        _digest(self.region_image_sha256, "region_image_sha256")


@dataclass(frozen=True, slots=True)
class AssistedEquationAttempt:
    """One immutable automated, unreviewed assisted proposal."""

    binding: EquationReviewEvidenceBinding
    method: str
    proposed_latex: str
    proposal_sha256: str
    attempt_id: str
    attempt: int = 1
    status: str = "automated_unreviewed"

    @classmethod
    def create(
        cls,
        *,
        binding: EquationReviewEvidenceBinding,
        method: str,
        proposed_latex: str,
    ) -> AssistedEquationAttempt:
        if not isinstance(binding, EquationReviewEvidenceBinding):
            raise TypeError("binding must be EquationReviewEvidenceBinding")
        valid_method = _bounded_text(
            method,
            "method",
            maximum=500,
            empty=False,
        )
        proposal = _bounded_text(
            proposed_latex,
            "proposed_latex",
            maximum=MAX_ASSISTED_PROPOSAL_CHARACTERS,
            empty=False,
        )
        proposal_sha256 = hashlib.sha256(proposal.encode("utf-8")).hexdigest()
        identity = _assisted_identity(
            binding=binding,
            method=valid_method,
            proposal_sha256=proposal_sha256,
        )
        return cls(
            binding=binding,
            method=valid_method,
            proposed_latex=proposal,
            proposal_sha256=proposal_sha256,
            attempt_id=_id("equation-assisted-attempt", identity),
        )

    def __post_init__(self) -> None:
        if not isinstance(self.binding, EquationReviewEvidenceBinding):
            raise TypeError("binding must be EquationReviewEvidenceBinding")
        if self.attempt != 1 or self.status != "automated_unreviewed":
            raise EquationReviewError(
                "only automated_unreviewed attempt 1 is supported"
            )
        _bounded_text(self.method, "method", maximum=500, empty=False)
        proposal = _bounded_text(
            self.proposed_latex,
            "proposed_latex",
            maximum=MAX_ASSISTED_PROPOSAL_CHARACTERS,
            empty=False,
        )
        expected_hash = hashlib.sha256(proposal.encode("utf-8")).hexdigest()
        if self.proposal_sha256 != expected_hash:
            raise EquationReviewError("assisted proposal SHA-256 is inconsistent")
        expected_id = _id(
            "equation-assisted-attempt",
            _assisted_identity(
                binding=self.binding,
                method=self.method,
                proposal_sha256=self.proposal_sha256,
            ),
        )
        if self.attempt_id != expected_id:
            raise EquationReviewError("assisted attempt identity is inconsistent")


@dataclass(frozen=True, slots=True)
class HumanEquationRevisionRequest:
    """Caller-owned inputs for one optimistic append operation."""

    binding: EquationReviewEvidenceBinding
    disposition: EquationReviewDisposition
    assistance_proposal_sha256: str | None
    note: str
    reviewed_at_utc: datetime
    expected_previous_revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.binding, EquationReviewEvidenceBinding):
            raise TypeError("binding must be EquationReviewEvidenceBinding")
        if not isinstance(self.disposition, EquationReviewDisposition):
            raise EquationReviewError("human disposition is invalid")
        if self.assistance_proposal_sha256 is not None:
            _digest(
                self.assistance_proposal_sha256,
                "assistance_proposal_sha256",
            )
        if (
            self.disposition is EquationReviewDisposition.ACCEPT_TRANSCRIPTION
            and self.assistance_proposal_sha256 is None
        ):
            raise EquationReviewError(
                "accepted transcription requires an assisted proposal SHA-256"
            )
        _bounded_text(
            self.note,
            "note",
            maximum=MAX_EQUATION_REVIEW_NOTE_CHARACTERS,
            empty=True,
        )
        _utc_text(self.reviewed_at_utc)
        if (
            type(self.expected_previous_revision) is not int
            or not 0 <= self.expected_previous_revision < MAX_EQUATION_REVIEW_REVISIONS
        ):
            raise EquationReviewError("expected_previous_revision is invalid")


@dataclass(frozen=True, slots=True)
class HumanEquationRevision:
    """One immutable, evidence-bound human review revision."""

    binding: EquationReviewEvidenceBinding
    disposition: EquationReviewDisposition
    assistance_proposal_sha256: str | None
    note: str
    revision: int
    updated_at_utc: datetime
    revision_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.binding, EquationReviewEvidenceBinding):
            raise TypeError("binding must be EquationReviewEvidenceBinding")
        if not isinstance(self.disposition, EquationReviewDisposition):
            raise EquationReviewError("human disposition is invalid")
        if self.assistance_proposal_sha256 is not None:
            _digest(
                self.assistance_proposal_sha256,
                "assistance_proposal_sha256",
            )
        if (
            self.disposition is EquationReviewDisposition.ACCEPT_TRANSCRIPTION
            and self.assistance_proposal_sha256 is None
        ):
            raise EquationReviewError(
                "accepted transcription requires an assisted proposal SHA-256"
            )
        _bounded_text(
            self.note,
            "note",
            maximum=MAX_EQUATION_REVIEW_NOTE_CHARACTERS,
            empty=True,
        )
        if (
            type(self.revision) is not int
            or not 1 <= self.revision <= MAX_EQUATION_REVIEW_REVISIONS
        ):
            raise EquationReviewError("human revision number is invalid")
        expected_id = _id(
            "equation-human-revision",
            _human_identity(
                binding=self.binding,
                disposition=self.disposition,
                assistance_proposal_sha256=self.assistance_proposal_sha256,
                note=self.note,
                revision=self.revision,
                updated_at_utc=self.updated_at_utc,
            ),
        )
        if self.revision_id != expected_id:
            raise EquationReviewError("human revision identity is inconsistent")

    @property
    def updated_at_utc_text(self) -> str:
        return _utc_text(self.updated_at_utc)


@dataclass(frozen=True, slots=True)
class HumanEquationRevisionAppendResult:
    """Stored revision plus idempotent publication action."""

    revision: HumanEquationRevision
    action: EquationReviewPublicationAction

    def __post_init__(self) -> None:
        if not isinstance(self.revision, HumanEquationRevision):
            raise TypeError("revision must be HumanEquationRevision")
        if not isinstance(self.action, EquationReviewPublicationAction):
            raise TypeError("action must be EquationReviewPublicationAction")


def equation_candidate_artifact_key(candidate_id: str) -> str:
    """Return the path-free application key for one opaque candidate ID."""
    valid = _opaque_id(candidate_id, "candidate_id")
    stable_prefix = "equation-candidate:sha256:"
    if valid.startswith(stable_prefix):
        digest = valid.removeprefix(stable_prefix)
        if _SHA256.fullmatch(digest) is None:
            raise EquationReviewError(
                "equation candidate stable identity has an invalid digest"
            )
        return digest
    return hashlib.sha256(valid.encode("utf-8")).hexdigest()


def publish_assisted_equation_attempt(
    attempt: AssistedEquationAttempt,
    *,
    document_root: AuthorizedRoot,
) -> EquationReviewPublicationAction:
    """Exclusively publish immutable attempt 0001 with its manifest last."""
    if not isinstance(attempt, AssistedEquationAttempt):
        raise TypeError("attempt must be AssistedEquationAttempt")
    _authorized_root(document_root)
    _validate_evidence(document_root, attempt.binding)
    root = _candidate_root(attempt.binding.candidate_id)
    relative = root / "assisted/attempt-0001"
    expected = _assisted_artifacts(attempt)
    state = document_root.state(relative)
    if state == "directory":
        existing = _existing_child(document_root, relative, "assisted attempt")
        _verify_exact_files(existing, expected)
        return EquationReviewPublicationAction.UNCHANGED
    if state != "missing":
        raise EquationReviewPublicationError(
            "assisted attempt target is not a directory"
        )
    _ensure_parents(document_root, relative)
    try:
        destination = document_root.create_directory(relative)
    except FileExistsError as error:
        raise EquationReviewConcurrencyError(
            "assisted attempt append lost an exclusive-create race"
        ) from error
    _write_artifacts(destination, expected)
    _verify_exact_files(destination, expected)
    return EquationReviewPublicationAction.CREATE


def load_latest_human_equation_revision(
    binding: EquationReviewEvidenceBinding,
    *,
    document_root: AuthorizedRoot,
) -> HumanEquationRevision | None:
    """Load the latest complete revision after revalidating bound evidence."""
    if not isinstance(binding, EquationReviewEvidenceBinding):
        raise TypeError("binding must be EquationReviewEvidenceBinding")
    _authorized_root(document_root)
    _validate_evidence(document_root, binding)
    revisions = _existing_revisions(
        document_root,
        _candidate_root(binding.candidate_id) / "human",
        binding,
    )
    if not revisions:
        return None
    return revisions[-1]


def append_human_equation_revision(
    request: HumanEquationRevisionRequest,
    *,
    document_root: AuthorizedRoot,
) -> HumanEquationRevisionAppendResult:
    """Append one monotonic human revision with optimistic concurrency."""
    if not isinstance(request, HumanEquationRevisionRequest):
        raise TypeError("request must be HumanEquationRevisionRequest")
    _authorized_root(document_root)
    _validate_evidence(document_root, request.binding)
    human_root = _candidate_root(request.binding.candidate_id) / "human"
    revisions = _existing_revisions(
        document_root,
        human_root,
        request.binding,
    )
    if request.assistance_proposal_sha256 is not None:
        _validate_assisted_proposal(
            document_root,
            request.binding,
            request.assistance_proposal_sha256,
        )
    current = revisions[-1].revision if revisions else 0
    expected = request.expected_previous_revision
    if current != expected:
        if current == expected + 1:
            replay = _human_revision(request, revision=current)
            existing = _existing_child(
                document_root,
                human_root / f"revision-{current:04d}",
                "human equation revision",
            )
            try:
                _verify_exact_files(existing, _human_artifacts(replay))
            except EquationReviewPublicationError as error:
                raise EquationReviewStaleRevision(
                    "human revision advanced with different evidence"
                ) from error
            return HumanEquationRevisionAppendResult(
                replay,
                EquationReviewPublicationAction.UNCHANGED,
            )
        raise EquationReviewStaleRevision("expected previous human revision is stale")

    revision_number = current + 1
    revision = _human_revision(request, revision=revision_number)
    relative = human_root / f"revision-{revision_number:04d}"
    if document_root.state(relative) != "missing":
        return _classify_revision_collision(
            request,
            revision,
            document_root=document_root,
            human_root=human_root,
        )
    _ensure_parents(document_root, relative)
    try:
        destination = document_root.create_directory(relative)
    except FileExistsError:
        return _classify_revision_collision(
            request,
            revision,
            document_root=document_root,
            human_root=human_root,
        )
    artifacts = _human_artifacts(revision)
    _write_artifacts(destination, artifacts)
    _verify_exact_files(destination, artifacts)
    return HumanEquationRevisionAppendResult(
        revision,
        EquationReviewPublicationAction.CREATE,
    )


def _classify_revision_collision(
    request: HumanEquationRevisionRequest,
    attempted: HumanEquationRevision,
    *,
    document_root: AuthorizedRoot,
    human_root: PurePosixPath,
) -> HumanEquationRevisionAppendResult:
    revisions = _existing_revisions(
        document_root,
        human_root,
        request.binding,
    )
    if not revisions or revisions[-1].revision < attempted.revision:
        raise EquationReviewPublicationError(
            "concurrent human revision output is partial or malformed"
        )
    latest = revisions[-1]
    if latest.revision > attempted.revision:
        raise EquationReviewStaleRevision("human revisions advanced during append")
    if latest == attempted:
        return HumanEquationRevisionAppendResult(
            latest,
            EquationReviewPublicationAction.UNCHANGED,
        )
    raise EquationReviewConcurrencyError(
        "human revision append lost to different concurrent evidence"
    )


def _human_revision(
    request: HumanEquationRevisionRequest,
    *,
    revision: int,
) -> HumanEquationRevision:
    identity = _human_identity(
        binding=request.binding,
        disposition=request.disposition,
        assistance_proposal_sha256=request.assistance_proposal_sha256,
        note=request.note,
        revision=revision,
        updated_at_utc=request.reviewed_at_utc,
    )
    return HumanEquationRevision(
        binding=request.binding,
        disposition=request.disposition,
        assistance_proposal_sha256=request.assistance_proposal_sha256,
        note=request.note,
        revision=revision,
        updated_at_utc=request.reviewed_at_utc,
        revision_id=_id("equation-human-revision", identity),
    )


def _assisted_artifacts(
    attempt: AssistedEquationAttempt,
) -> tuple[tuple[PurePosixPath, bytes], ...]:
    proposal = attempt.proposed_latex.encode("utf-8")
    identity = {
        **_assisted_identity(
            binding=attempt.binding,
            method=attempt.method,
            proposal_sha256=attempt.proposal_sha256,
        ),
        "attempt_id": attempt.attempt_id,
    }
    manifest = {
        **identity,
        "artifact_files": [
            {
                "byte_size": len(proposal),
                "relative_path": "proposal.txt",
                "sha256": attempt.proposal_sha256,
            }
        ],
    }
    return (
        (PurePosixPath("proposal.txt"), proposal),
        (PurePosixPath("manifest.json"), _canonical(manifest)),
    )


def _human_artifacts(
    revision: HumanEquationRevision,
) -> tuple[tuple[PurePosixPath, bytes], ...]:
    decision_value = {
        **_binding_value(revision.binding),
        "assistance_proposal_sha256": revision.assistance_proposal_sha256,
        "contract_id": EQUATION_REVIEW_CONTRACT_ID,
        "disposition": revision.disposition.value,
        "note": revision.note,
        "revision": revision.revision,
        "revision_id": revision.revision_id,
        "schema_version": EQUATION_REVIEW_SCHEMA_VERSION,
        "updated_at_utc": revision.updated_at_utc_text,
    }
    decision = _canonical(decision_value)
    manifest = {
        **decision_value,
        "artifact_files": [
            {
                "byte_size": len(decision),
                "relative_path": "decision.json",
                "sha256": hashlib.sha256(decision).hexdigest(),
            }
        ],
        "status": "human-reviewed",
    }
    return (
        (PurePosixPath("decision.json"), decision),
        (PurePosixPath("manifest.json"), _canonical(manifest)),
    )


def _human_identity(
    *,
    binding: EquationReviewEvidenceBinding,
    disposition: EquationReviewDisposition,
    assistance_proposal_sha256: str | None,
    note: str,
    revision: int,
    updated_at_utc: datetime,
) -> dict[str, object]:
    return {
        **_binding_value(binding),
        "assistance_proposal_sha256": assistance_proposal_sha256,
        "contract_id": EQUATION_REVIEW_CONTRACT_ID,
        "disposition": disposition.value,
        "note": note,
        "revision": revision,
        "schema_version": EQUATION_REVIEW_SCHEMA_VERSION,
        "updated_at_utc": _utc_text(updated_at_utc),
    }


def _assisted_identity(
    *,
    binding: EquationReviewEvidenceBinding,
    method: str,
    proposal_sha256: str,
) -> dict[str, object]:
    return {
        **_binding_value(binding),
        "attempt": 1,
        "contract_id": EQUATION_REVIEW_CONTRACT_ID,
        "method": method,
        "proposal_path": "proposal.txt",
        "proposal_sha256": proposal_sha256,
        "schema_version": EQUATION_REVIEW_SCHEMA_VERSION,
        "status": "automated_unreviewed",
    }


def _binding_value(binding: EquationReviewEvidenceBinding) -> dict[str, object]:
    return {
        "candidate_evidence_sha256": binding.candidate_evidence_sha256,
        "candidate_id": binding.candidate_id,
        "document_id": binding.document_id,
        "region_image_sha256": binding.region_image_sha256,
        "source_sha256": binding.source_sha256,
    }


def _candidate_root(candidate_id: str) -> PurePosixPath:
    return PurePosixPath("content/equations/regions") / equation_candidate_artifact_key(
        candidate_id
    )


def _validate_evidence(
    root: AuthorizedRoot,
    binding: EquationReviewEvidenceBinding,
) -> None:
    document = _read_json(root, DOCUMENT_PACKAGE_MANIFEST)
    inventory = _document_package_inventory(document, binding)
    _verify_inventoried_files(root, inventory)

    source_path = PurePosixPath("source/document.pdf")
    source_manifest_path = PurePosixPath("source/manifest.json")
    index_path = PurePosixPath("content/equations/index.json")
    candidate_root = _candidate_root(binding.candidate_id)
    image_path = candidate_root / "source/image.png"
    candidate_source_path = candidate_root / "source/manifest.json"
    deterministic_path = candidate_root / "deterministic/manifest.json"

    _require_inventory_entry(
        inventory,
        source_path,
        media_type="application/pdf",
        sha256=binding.source_sha256,
    )
    _require_inventory_entry(
        inventory,
        source_manifest_path,
        media_type="application/json",
    )
    _require_inventory_entry(
        inventory,
        index_path,
        media_type="application/json",
    )
    _require_inventory_entry(
        inventory,
        image_path,
        media_type="image/png",
        sha256=binding.region_image_sha256,
    )
    _require_inventory_entry(
        inventory,
        candidate_source_path,
        media_type="application/json",
    )
    _require_inventory_entry(
        inventory,
        deterministic_path,
        media_type="application/json",
        sha256=binding.candidate_evidence_sha256,
    )

    source_manifest = _read_json(root, source_manifest_path)
    candidate_source = _read_json(root, candidate_source_path)
    deterministic = _read_json(root, deterministic_path)
    index = _read_json(root, index_path)
    candidates = index.get("candidates")
    if not isinstance(candidates, list):
        raise EquationReviewEvidenceMismatch("equation candidate index is malformed")
    indexed = [
        item
        for item in candidates
        if isinstance(item, dict) and item.get("candidate_id") == binding.candidate_id
    ]
    candidate = deterministic.get("candidate")
    rendered = candidate.get("rendered_region") if isinstance(candidate, dict) else None
    if (
        len(indexed) != 1
        or source_manifest.get("document_key") != binding.document_id
        or source_manifest.get("source_path") != source_path.as_posix()
        or source_manifest.get("source_sha256") != binding.source_sha256
        or source_manifest.get("source_byte_size") != inventory[source_path].byte_size
        or source_manifest.get("status") != "immutable-source"
        or candidate_source.get("candidate_id") != binding.candidate_id
        or candidate_source.get("document_key") != binding.document_id
        or candidate_source.get("source_sha256") != binding.source_sha256
        or candidate_source.get("image_path") != image_path.as_posix()
        or candidate_source.get("image_sha256") != binding.region_image_sha256
        or candidate_source.get("status") != "immutable-source-evidence"
        or not isinstance(candidate, dict)
        or candidate.get("candidate_id") != binding.candidate_id
        or not isinstance(rendered, dict)
        or rendered.get("content_sha256") != binding.region_image_sha256
        or deterministic.get("document_key") != binding.document_id
        or deterministic.get("detection_result_id")
        != document.get("equation_detection_result_id")
        or deterministic.get("status") != "deterministic-proposal"
        or index.get("document_key") != binding.document_id
        or index.get("source_sha256") != binding.source_sha256
        or index.get("detection_result_id")
        != document.get("equation_detection_result_id")
        or index.get("status") != "deterministic-unreviewed"
    ):
        raise EquationReviewEvidenceMismatch("document or candidate evidence is stale")
    index_record = indexed[0]
    if (
        set(index_record)
        != {
            "candidate_id",
            "deterministic_manifest",
            "evidence_status",
            "image_path",
            "image_sha256",
            "kind",
            "source_manifest",
        }
        or index_record.get("deterministic_manifest") != deterministic_path.as_posix()
        or index_record.get("image_path") != image_path.as_posix()
        or index_record.get("image_sha256") != binding.region_image_sha256
        or index_record.get("source_manifest") != candidate_source_path.as_posix()
    ):
        raise EquationReviewEvidenceMismatch(
            "candidate is not exactly listed by the deterministic package"
        )


def _document_package_inventory(
    document: dict[str, object],
    binding: EquationReviewEvidenceBinding,
) -> dict[PurePosixPath, _InventoryEntry]:
    expected_keys = {
        "artifact_files",
        "contract_id",
        "document_key",
        "equation_detection_result_id",
        "extraction_bundle_id",
        "package_id",
        "schema_version",
        "source_byte_size",
        "source_sha256",
        "stages",
        "status",
    }
    identity = dict(document)
    package_id = identity.pop("package_id", None)
    source_byte_size = document.get("source_byte_size")
    if (
        set(document) != expected_keys
        or document.get("contract_id") != DOCUMENT_PACKAGE_CONTRACT_ID
        or document.get("schema_version") != DOCUMENT_PACKAGE_SCHEMA_VERSION
        or document.get("document_key") != binding.document_id
        or document.get("source_sha256") != binding.source_sha256
        or document.get("stages") != _DOCUMENT_PACKAGE_STAGES
        or document.get("status") != "deterministic-complete"
        or type(source_byte_size) is not int
        or not 1 <= source_byte_size <= _MAX_SOURCE_BYTES
        or not _stable_identity(
            document.get("equation_detection_result_id"),
            "equation-detection-result",
        )
        or not _stable_identity(
            document.get("extraction_bundle_id"),
            "pdf-extraction-artifact-bundle",
        )
        or package_id != _id("document-processing-package", identity)
    ):
        raise EquationReviewEvidenceMismatch(
            "document completion manifest is forged or inconsistent"
        )
    raw_inventory = document.get("artifact_files")
    if (
        not isinstance(raw_inventory, list)
        or not 1 <= len(raw_inventory) <= MAX_DOCUMENT_PACKAGE_ARTIFACTS
    ):
        raise EquationReviewEvidenceMismatch(
            "document completion inventory is malformed"
        )
    inventory: dict[PurePosixPath, _InventoryEntry] = {}
    total_bytes = 0
    for value in raw_inventory:
        if not isinstance(value, dict) or set(value) != {
            "byte_size",
            "media_type",
            "relative_path",
            "sha256",
        }:
            raise EquationReviewEvidenceMismatch(
                "document completion inventory is malformed"
            )
        raw_path = value.get("relative_path")
        media_type = value.get("media_type")
        byte_size = value.get("byte_size")
        sha256 = value.get("sha256")
        if not isinstance(raw_path, str):
            raise EquationReviewEvidenceMismatch(
                "document completion inventory path is malformed"
            )
        path = PurePosixPath(raw_path)
        if (
            not _safe_relative(path)
            or raw_path != path.as_posix()
            or "\\" in raw_path
            or path == DOCUMENT_PACKAGE_MANIFEST
            or "assisted" in path.parts
            or "human" in path.parts
            or not isinstance(media_type, str)
            or not 1 <= len(media_type) <= 256
            or any(ord(character) < 32 for character in media_type)
            or type(byte_size) is not int
            or not 0 <= byte_size <= _MAX_SOURCE_BYTES
            or not isinstance(sha256, str)
            or _SHA256.fullmatch(sha256) is None
            or path in inventory
        ):
            raise EquationReviewEvidenceMismatch(
                "document completion inventory entry is invalid"
            )
        entry = _InventoryEntry(path, media_type, byte_size, sha256)
        inventory[path] = entry
        total_bytes += byte_size
    if total_bytes > MAX_DOCUMENT_PACKAGE_BYTES:
        raise EquationReviewEvidenceMismatch(
            "document completion inventory exceeds its byte bound"
        )
    source = inventory.get(PurePosixPath("source/document.pdf"))
    required_paths = {
        PurePosixPath("source/document.pdf"),
        PurePosixPath("source/manifest.json"),
        PurePosixPath("ingestion/extraction.json"),
        PurePosixPath("ingestion/manifest.json"),
        PurePosixPath("content/equations/deterministic/detection.json"),
        PurePosixPath("content/equations/index.json"),
        PurePosixPath("content/equations/manifest.json"),
    }
    if (
        source is None
        or source.media_type != "application/pdf"
        or source.byte_size != source_byte_size
        or source.sha256 != binding.source_sha256
        or not required_paths.issubset(inventory)
    ):
        raise EquationReviewEvidenceMismatch(
            "completed deterministic package inventory is incomplete"
        )
    return inventory


def _verify_inventoried_files(
    root: AuthorizedRoot,
    inventory: dict[PurePosixPath, _InventoryEntry],
) -> None:
    for path, entry in inventory.items():
        try:
            observed = root.observe_file(path, max_bytes=entry.byte_size)
        except (OSError, ValueError) as error:
            raise EquationReviewPublicationError(
                "document-package inventory is incomplete"
            ) from error
        if observed.byte_size != entry.byte_size or observed.sha256 != entry.sha256:
            raise EquationReviewEvidenceMismatch(
                "document-package inventoried bytes are stale"
            )


def _require_inventory_entry(
    inventory: dict[PurePosixPath, _InventoryEntry],
    path: PurePosixPath,
    *,
    media_type: str,
    sha256: str | None = None,
) -> _InventoryEntry:
    entry = inventory.get(path)
    if (
        entry is None
        or entry.media_type != media_type
        or (sha256 is not None and entry.sha256 != sha256)
    ):
        raise EquationReviewEvidenceMismatch(
            f"required evidence is absent from package inventory: {path}"
        )
    return entry


def _validate_assisted_proposal(
    root: AuthorizedRoot,
    binding: EquationReviewEvidenceBinding,
    proposal_sha256: str,
) -> None:
    try:
        tree = validate_review_tree(
            root,
            candidate_root=_candidate_root(binding.candidate_id),
            binding=_review_binding(binding),
        )
    except ReviewTreeValidationError as error:
        raise EquationReviewEvidenceMismatch(
            "referenced assisted proposal is stale or different"
        ) from error
    if tree.assisted is None or tree.assisted.proposal_sha256 != proposal_sha256:
        raise EquationReviewEvidenceMismatch(
            "referenced assisted proposal is unavailable"
        )


def _existing_revisions(
    root: AuthorizedRoot,
    human_root: PurePosixPath,
    binding: EquationReviewEvidenceBinding,
) -> tuple[HumanEquationRevision, ...]:
    try:
        tree = validate_review_tree(
            root,
            candidate_root=human_root.parent,
            binding=_review_binding(binding),
        )
        return tuple(
            HumanEquationRevision(
                binding=binding,
                disposition=EquationReviewDisposition(item.disposition),
                assistance_proposal_sha256=item.assistance_proposal_sha256,
                note=item.note,
                revision=item.revision,
                updated_at_utc=item.updated_at_utc,
                revision_id=item.revision_id,
            )
            for item in tree.revisions
        )
    except ValueError as error:
        raise EquationReviewPublicationError(
            "equation review history is partial or malformed"
        ) from error


def _review_binding(
    binding: EquationReviewEvidenceBinding,
) -> ReviewEvidenceIdentity:
    return ReviewEvidenceIdentity(
        document_id=binding.document_id,
        candidate_id=binding.candidate_id,
        source_sha256=binding.source_sha256,
        candidate_evidence_sha256=binding.candidate_evidence_sha256,
        region_image_sha256=binding.region_image_sha256,
    )


def _write_artifacts(
    root: AuthorizedRoot,
    artifacts: tuple[tuple[PurePosixPath, bytes], ...],
) -> None:
    for path, content in artifacts:
        root.write_bytes(path, content, replace=False)


def _verify_exact_files(
    root: AuthorizedRoot,
    artifacts: tuple[tuple[PurePosixPath, bytes], ...],
) -> None:
    expected = {path: content for path, content in artifacts}
    try:
        paths = root.iter_files(
            suffix="",
            recursive=True,
            max_files=len(expected),
            max_entries=len(expected),
            max_depth=1,
        )
    except (OSError, ValueError) as error:
        raise EquationReviewPublicationError(
            "equation review artifact inventory is unsafe"
        ) from error
    if (
        not artifacts
        or artifacts[-1][0] != PurePosixPath("manifest.json")
        or set(paths) != set(expected)
        or root.state(PurePosixPath("manifest.json")) != "regular"
    ):
        raise EquationReviewPublicationError(
            "equation review artifact is partial or different"
        )
    for path, content in expected.items():
        try:
            observed = root.observe_file(
                path,
                max_bytes=_MAX_MANIFEST_BYTES,
            )
        except (OSError, ValueError) as error:
            raise EquationReviewPublicationError(
                "equation review artifact bytes are unavailable"
            ) from error
        if observed.byte_size != len(content) or observed.sha256 != (
            hashlib.sha256(content).hexdigest()
        ):
            raise EquationReviewPublicationError(
                "equation review artifact bytes are different"
            )


def _read_json(root: AuthorizedRoot, path: PurePosixPath) -> dict[str, object]:
    try:
        text = root.read_text(path, max_bytes=_MAX_MANIFEST_BYTES)
        _validate_json_envelope(text)
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
        _validate_json_value(value)
        if text.encode("utf-8") != _canonical(value):
            raise ValueError("JSON evidence is not canonical")
    except (OSError, OverflowError, RecursionError, ValueError) as error:
        raise EquationReviewPublicationError(
            "equation review evidence JSON is unavailable"
        ) from error
    if not isinstance(value, dict):
        raise EquationReviewPublicationError(
            "equation review evidence JSON is malformed"
        )
    return value


def _validate_json_envelope(text: str) -> None:
    if len(text.encode("utf-8")) > _MAX_MANIFEST_BYTES:
        raise ValueError("JSON evidence exceeds its byte limit")
    depth = 0
    in_string = False
    escaped = False
    string_bytes = 0
    for character in text:
        if in_string:
            string_bytes += len(character.encode("utf-8"))
            if string_bytes > _MAX_MANIFEST_STRING_BYTES:
                raise ValueError("JSON evidence string exceeds its byte limit")
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
            string_bytes = 0
        elif character in "[{":
            depth += 1
            if depth > _MAX_MANIFEST_DEPTH:
                raise ValueError("JSON evidence exceeds its depth limit")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("JSON evidence nesting is malformed")
    if depth != 0 or in_string:
        raise ValueError("JSON evidence nesting is malformed")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON evidence contains duplicate keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"JSON evidence contains non-finite number: {value}")


def _validate_json_value(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    items = 0
    while stack:
        current, depth = stack.pop()
        if depth > _MAX_MANIFEST_DEPTH:
            raise ValueError("JSON evidence exceeds its depth limit")
        if isinstance(current, dict):
            items += len(current)
            stack.extend((key, depth + 1) for key in current)
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            items += len(current)
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str):
            if len(current.encode("utf-8")) > _MAX_MANIFEST_STRING_BYTES:
                raise ValueError("JSON evidence string exceeds its byte limit")
        elif current is not None and not isinstance(current, bool | int | float):
            raise ValueError("JSON evidence has an unsupported value")
        if items > _MAX_MANIFEST_ITEMS:
            raise ValueError("JSON evidence exceeds its item limit")


def _ensure_parents(root: AuthorizedRoot, relative: PurePosixPath) -> None:
    current = PurePosixPath()
    for part in relative.parts[:-1]:
        current /= part
        state = root.state(current)
        if state == "directory":
            continue
        if state != "missing":
            raise EquationReviewPublicationError(
                "equation review parent is not a directory"
            )
        try:
            root.create_directory(current)
        except FileExistsError:
            if root.state(current) != "directory":
                raise EquationReviewPublicationError(
                    "equation review parent creation raced with a non-directory"
                ) from None


def _existing_child(
    root: AuthorizedRoot,
    relative: PurePosixPath,
    label: str,
) -> AuthorizedRoot:
    try:
        return AuthorizedRoot.existing(
            root.child_path(relative),
            label=label,
            root_alias=root.preflight_evidence.root_alias,
            storage_class=RootStorageClass.LOCAL,
        )
    except (OSError, ValueError) as error:
        raise EquationReviewPublicationError(
            f"{label} cannot be safely bound"
        ) from error


def _authorized_root(value: object) -> AuthorizedRoot:
    if not isinstance(value, AuthorizedRoot):
        raise TypeError("document_root must be an AuthorizedRoot")
    if value.preflight_evidence.storage_class is not RootStorageClass.LOCAL:
        raise EquationReviewPublicationError(
            "equation review publication requires a local authorized root"
        )
    return value


def _safe_relative(value: PurePosixPath) -> bool:
    return (
        not value.is_absolute()
        and value.as_posix() not in {"", "."}
        and len(value.as_posix()) <= 4_096
        and all(part not in {"", ".", ".."} for part in value.parts)
    )


def _stable_identity(value: object, namespace: str) -> bool:
    prefix = f"{namespace}:sha256:"
    return (
        isinstance(value, str)
        and value.startswith(prefix)
        and _SHA256.fullmatch(value[len(prefix) :]) is not None
    )


def _opaque_id(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or _OPAQUE_ID.fullmatch(value) is None
        or ".." in value
        or (len(value) >= 2 and value[0].isalpha() and value[1] == ":")
    ):
        raise EquationReviewError(f"{field} must be a bounded path-free identity")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise EquationReviewError(f"{field} must be a lowercase SHA-256")
    return value


def _bounded_text(
    value: object,
    field: str,
    *,
    maximum: int,
    empty: bool,
) -> str:
    if not isinstance(value, str):
        raise EquationReviewError(f"{field} must be text")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise EquationReviewError(f"{field} must be valid UTF-8") from error
    if len(value) > maximum or (not empty and not value):
        raise EquationReviewError(f"{field} exceeds its character bound")
    return value


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise EquationReviewError("reviewed_at_utc must be a datetime")
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise EquationReviewError("reviewed_at_utc must be timezone-aware UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _id(namespace: str, value: object) -> str:
    return f"{namespace}:sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8", errors="strict")
