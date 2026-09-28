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

from .document_package import DOCUMENT_PACKAGE_MANIFEST

EQUATION_REVIEW_CONTRACT_ID = "projectkoios.applications.pdf-corpus-equation-review"
EQUATION_REVIEW_SCHEMA_VERSION = 1
MAX_EQUATION_REVIEW_REVISIONS = 9_999
MAX_EQUATION_REVIEW_NOTE_CHARACTERS = 10_000
MAX_ASSISTED_PROPOSAL_CHARACTERS = 100_000
_MAX_ASSISTED_PROPOSAL_BYTES = 400_000
_MAX_MANIFEST_BYTES = 20_000_000
_MAX_MANIFEST_DEPTH = 32
_MAX_MANIFEST_ITEMS = 200_000
_MAX_MANIFEST_STRING_BYTES = 1_100_000
_MAX_REGION_IMAGE_BYTES = 20_000_000
_MAX_SOURCE_BYTES = 128_000_000
_MAX_REVIEW_FILES = 2 * MAX_EQUATION_REVIEW_REVISIONS
_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION_DIRECTORY = re.compile(r"revision-([0-9]{4})")


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
    latest = revisions[-1]
    if latest.assistance_proposal_sha256 is not None:
        _validate_assisted_proposal(
            document_root,
            binding,
            latest.assistance_proposal_sha256,
        )
    return latest


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
    if request.assistance_proposal_sha256 is not None:
        _validate_assisted_proposal(
            document_root,
            request.binding,
            request.assistance_proposal_sha256,
        )

    human_root = _candidate_root(request.binding.candidate_id) / "human"
    revisions = _existing_revisions(
        document_root,
        human_root,
        request.binding,
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
        raise EquationReviewPublicationError(
            "next human revision output already exists"
        )
    _ensure_parents(document_root, relative)
    try:
        destination = document_root.create_directory(relative)
    except FileExistsError as error:
        raise EquationReviewConcurrencyError(
            "human revision append lost an exclusive-create race"
        ) from error
    artifacts = _human_artifacts(revision)
    _write_artifacts(destination, artifacts)
    _verify_exact_files(destination, artifacts)
    return HumanEquationRevisionAppendResult(
        revision,
        EquationReviewPublicationAction.CREATE,
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
    if (
        document.get("document_key") != binding.document_id
        or document.get("source_sha256") != binding.source_sha256
        or document.get("status") != "deterministic-complete"
    ):
        raise EquationReviewEvidenceMismatch(
            "document identity or source evidence is stale"
        )
    source = root.observe_file(
        PurePosixPath("source/document.pdf"),
        max_bytes=_MAX_SOURCE_BYTES,
    )
    if source.sha256 != binding.source_sha256:
        raise EquationReviewEvidenceMismatch("source PDF bytes are stale")
    candidate_root = _candidate_root(binding.candidate_id)
    source_manifest = _read_json(root, candidate_root / "source/manifest.json")
    deterministic_path = candidate_root / "deterministic/manifest.json"
    deterministic = _read_json(root, deterministic_path)
    candidate = deterministic.get("candidate")
    if (
        source_manifest.get("candidate_id") != binding.candidate_id
        or source_manifest.get("document_key") != binding.document_id
        or source_manifest.get("source_sha256") != binding.source_sha256
        or source_manifest.get("image_sha256") != binding.region_image_sha256
        or not isinstance(candidate, dict)
        or candidate.get("candidate_id") != binding.candidate_id
    ):
        raise EquationReviewEvidenceMismatch("candidate source evidence is stale")
    image = root.observe_file(
        candidate_root / "source/image.png",
        max_bytes=_MAX_REGION_IMAGE_BYTES,
    )
    evidence = root.observe_file(
        deterministic_path,
        max_bytes=_MAX_MANIFEST_BYTES,
    )
    if (
        image.sha256 != binding.region_image_sha256
        or evidence.sha256 != binding.candidate_evidence_sha256
    ):
        raise EquationReviewEvidenceMismatch("candidate evidence bytes are stale")


def _validate_assisted_proposal(
    root: AuthorizedRoot,
    binding: EquationReviewEvidenceBinding,
    proposal_sha256: str,
) -> None:
    relative = _candidate_root(binding.candidate_id) / "assisted/attempt-0001"
    if root.state(relative) != "directory":
        raise EquationReviewEvidenceMismatch(
            "referenced assisted proposal is unavailable"
        )
    attempt_root = _existing_child(root, relative, "assisted attempt")
    manifest = _read_json(attempt_root, PurePosixPath("manifest.json"))
    proposal = attempt_root.observe_file(
        PurePosixPath("proposal.txt"),
        max_bytes=_MAX_ASSISTED_PROPOSAL_BYTES,
    )
    method = manifest.get("method")
    if not isinstance(method, str):
        raise EquationReviewEvidenceMismatch(
            "referenced assisted proposal is stale or different"
        )
    identity = _assisted_identity(
        binding=binding,
        method=method,
        proposal_sha256=proposal_sha256,
    )
    expected = {
        **identity,
        "artifact_files": [
            {
                "byte_size": proposal.byte_size,
                "relative_path": "proposal.txt",
                "sha256": proposal.sha256,
            }
        ],
        "attempt_id": _id("equation-assisted-attempt", identity),
    }
    if proposal.sha256 != proposal_sha256 or manifest != expected:
        raise EquationReviewEvidenceMismatch(
            "referenced assisted proposal is stale or different"
        )


def _existing_revisions(
    root: AuthorizedRoot,
    human_root: PurePosixPath,
    binding: EquationReviewEvidenceBinding,
) -> tuple[HumanEquationRevision, ...]:
    state = root.state(human_root)
    if state == "missing":
        return ()
    if state != "directory":
        raise EquationReviewPublicationError("human review root is not a directory")
    bound = _existing_child(root, human_root, "human equation reviews")
    try:
        paths = bound.iter_files(
            suffix="",
            recursive=True,
            max_files=_MAX_REVIEW_FILES,
            max_entries=_MAX_REVIEW_FILES + MAX_EQUATION_REVIEW_REVISIONS,
            max_depth=2,
        )
    except (OSError, ValueError) as error:
        raise EquationReviewPublicationError(
            "human revision inventory is unsafe"
        ) from error
    grouped: dict[int, set[str]] = {}
    for path in paths:
        if len(path.parts) != 2:
            raise EquationReviewPublicationError(
                "human revision inventory contains an unknown path"
            )
        match = _REVISION_DIRECTORY.fullmatch(path.parts[0])
        if match is None or path.name not in {"decision.json", "manifest.json"}:
            raise EquationReviewPublicationError(
                "human revision inventory contains an unknown path"
            )
        revision = int(match.group(1))
        if not 1 <= revision <= MAX_EQUATION_REVIEW_REVISIONS:
            raise EquationReviewPublicationError("human revision number is invalid")
        grouped.setdefault(revision, set()).add(path.name)
    revisions = tuple(sorted(grouped))
    if revisions != tuple(range(1, len(revisions) + 1)) or any(
        grouped[item] != {"decision.json", "manifest.json"} for item in revisions
    ):
        raise EquationReviewPublicationError(
            "human revisions are partial or non-monotonic"
        )
    records: list[HumanEquationRevision] = []
    for revision in revisions:
        revision_root = PurePosixPath(f"revision-{revision:04d}")
        decision_path = revision_root / "decision.json"
        manifest = _read_json(bound, revision_root / "manifest.json")
        decision = _read_json(bound, decision_path)
        try:
            observed = bound.observe_file(
                decision_path,
                max_bytes=_MAX_MANIFEST_BYTES,
            )
        except (OSError, ValueError) as error:
            raise EquationReviewPublicationError(
                "human revision decision bytes are unavailable"
            ) from error
        core = {
            **_binding_value(binding),
            "assistance_proposal_sha256": manifest.get("assistance_proposal_sha256"),
            "contract_id": EQUATION_REVIEW_CONTRACT_ID,
            "disposition": manifest.get("disposition"),
            "note": manifest.get("note"),
            "revision": revision,
            "schema_version": EQUATION_REVIEW_SCHEMA_VERSION,
            "updated_at_utc": manifest.get("updated_at_utc"),
        }
        revision_id = _id("equation-human-revision", core)
        expected_decision = {**core, "revision_id": revision_id}
        expected_manifest = {
            **expected_decision,
            "artifact_files": [
                {
                    "byte_size": observed.byte_size,
                    "relative_path": "decision.json",
                    "sha256": observed.sha256,
                }
            ],
            "status": "human-reviewed",
        }
        if decision != expected_decision or manifest != expected_manifest:
            raise EquationReviewPublicationError(
                "human revision completion manifest is inconsistent"
            )
        try:
            timestamp = datetime.fromisoformat(str(core["updated_at_utc"]))
            record = HumanEquationRevision(
                binding=binding,
                disposition=EquationReviewDisposition(str(core["disposition"])),
                assistance_proposal_sha256=(
                    None
                    if core["assistance_proposal_sha256"] is None
                    else str(core["assistance_proposal_sha256"])
                ),
                note=str(core["note"]),
                revision=revision,
                updated_at_utc=timestamp,
                revision_id=revision_id,
            )
            if record.updated_at_utc_text != core["updated_at_utc"]:
                raise EquationReviewError("human revision UTC time is not canonical")
        except (TypeError, ValueError) as error:
            raise EquationReviewPublicationError(
                "human revision decision is malformed"
            ) from error
        records.append(record)
    return tuple(records)


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
