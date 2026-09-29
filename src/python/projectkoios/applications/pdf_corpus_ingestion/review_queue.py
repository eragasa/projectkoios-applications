"""Read-only deterministic projection of one document's equation review queue."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from projectkoios.references import AuthorizedRoot

from .document_package import (
    DOCUMENT_PACKAGE_MANIFEST,
    MAX_DOCUMENT_PACKAGE_ARTIFACTS,
)
from .equation_review import (
    EquationReviewDisposition,
    EquationReviewEvidenceBinding,
    EquationReviewPublicationError,
    _authorized_root,
    _document_package_inventory,
    _id,
    _InventoryEntry,
    _read_json,
    _verify_inventoried_files,
    equation_candidate_artifact_key,
)
from .review_tree import (
    MAX_REVIEW_ARTIFACTS,
    ReviewEvidenceIdentity,
    ReviewTreeValidationError,
    ValidatedHumanRevision,
    ValidatedReviewTree,
    validate_review_tree,
)

EQUATION_REVIEW_QUEUE_CONTRACT_ID = (
    "projectkoios.applications.pdf-corpus-equation-review-queue"
)
EQUATION_REVIEW_QUEUE_SCHEMA_VERSION = 1
MAX_EQUATION_REVIEW_QUEUE_CANDIDATES = 256
_SHA256 = re.compile(r"[0-9a-f]{64}")
_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
_INDEX_PATH = PurePosixPath("content/equations/index.json")
_DETECTION_PATH = PurePosixPath("content/equations/deterministic/detection.json")
_INDEX_KEYS = {
    "candidates",
    "detection_artifact",
    "detection_result_id",
    "document_key",
    "schema_version",
    "source_sha256",
    "status",
}
_INDEX_RECORD_KEYS = {
    "candidate_id",
    "deterministic_manifest",
    "evidence_status",
    "image_path",
    "image_sha256",
    "kind",
    "source_manifest",
}


class EquationReviewQueueError(ValueError):
    """A deterministic review queue cannot be projected."""


class EquationReviewQueueIncompleteError(EquationReviewQueueError):
    """The explicit document package is incomplete."""


class EquationReviewQueueMalformedError(EquationReviewQueueError):
    """The package, candidate evidence, or review tree is malformed."""


class EquationReviewQueueAssistanceStatus(StrEnum):
    """Presence of a complete immutable assisted attempt."""

    NOT_STARTED = "NOT_STARTED"
    AUTOMATED_UNREVIEWED = "AUTOMATED_UNREVIEWED"


class EquationReviewQueueDecisionStatus(StrEnum):
    """Latest validated human-review state."""

    NOT_REVIEWED = "NOT_REVIEWED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    REVISION_REQUIRED = "REVISION_REQUIRED"


@dataclass(frozen=True, slots=True)
class EquationReviewQueueNativeEvidence:
    """Path-free deterministic native evidence retained for reviewer context."""

    raw_text: str
    source_label: str | None
    confidence: float
    evidence_status: str
    source_block_id: str
    detection_input_id: str
    warning_ids: tuple[str, ...]
    processor_name: str
    processor_version: str
    configuration_digest: str
    candidate_sha256: str


@dataclass(frozen=True, slots=True)
class EquationReviewQueueAssistance:
    """Optional complete assisted attempt projected without artifact paths."""

    status: EquationReviewQueueAssistanceStatus
    attempt_id: str | None
    method: str | None
    proposal: str | None
    proposal_sha256: str | None


@dataclass(frozen=True, slots=True)
class EquationReviewQueueLatestDecision:
    """Optional latest validated schema-2 or schema-3 human revision."""

    status: EquationReviewQueueDecisionStatus
    revision: int
    schema_version: int
    revision_id: str
    disposition: EquationReviewDisposition
    assistance_proposal_sha256: str | None
    note: str
    recorded_at_utc: str
    reviewer_latex: str | None
    reviewer_latex_sha256: str | None
    obsidian_markdown: str | None
    obsidian_markdown_sha256: str | None
    display_mode: str | None
    renderer_id: str | None
    renderer_version: str | None
    rendered_reviewer_latex_sha256: str | None
    rendered_obsidian_markdown_sha256: str | None


@dataclass(frozen=True, slots=True)
class EquationReviewQueueItem:
    """One path-free eligible proposed display-equation review item."""

    document_id: str
    candidate_id: str
    page_index: int
    physical_page_number: int
    printed_page_label: str | None
    bounding_box: tuple[float, float, float, float]
    display_mode: str
    source_sha256: str
    candidate_evidence_sha256: str
    region_image_sha256: str
    native_evidence: EquationReviewQueueNativeEvidence
    assistance: EquationReviewQueueAssistance
    decision_status: EquationReviewQueueDecisionStatus
    latest_decision: EquationReviewQueueLatestDecision | None


@dataclass(frozen=True, slots=True)
class EquationReviewQueueProjection:
    """Stable content-derived queue for one explicit completed document root."""

    contract_id: str
    schema_version: int
    document_id: str
    source_sha256: str
    package_id: str
    items: tuple[EquationReviewQueueItem, ...]
    projection_id: str


def project_equation_review_queue(
    *,
    document_root: AuthorizedRoot,
) -> EquationReviewQueueProjection:
    """Project all eligible candidates without writes, image reads, or model use."""
    try:
        _authorized_root(document_root)
        if document_root.state(DOCUMENT_PACKAGE_MANIFEST) != "regular":
            raise EquationReviewQueueIncompleteError(
                "document completion manifest is unavailable"
            )
        return _project(document_root)
    except EquationReviewQueueError:
        raise
    except ReviewTreeValidationError as error:
        raise EquationReviewQueueMalformedError(
            "equation review tree is partial or malformed"
        ) from error
    except EquationReviewPublicationError as error:
        raise EquationReviewQueueMalformedError(
            "document package evidence is unavailable or malformed"
        ) from error
    except OSError as error:
        raise EquationReviewQueueIncompleteError(
            "document package evidence is unavailable"
        ) from error
    except (KeyError, TypeError, ValueError) as error:
        raise EquationReviewQueueMalformedError(
            "document package projection evidence is malformed"
        ) from error


def _project(root: AuthorizedRoot) -> EquationReviewQueueProjection:
    document = _read_json(root, DOCUMENT_PACKAGE_MANIFEST)
    document_id = _bounded_id(document.get("document_key"), "document ID")
    source_sha256 = _digest(document.get("source_sha256"), "source SHA-256")
    binding_for_inventory = EquationReviewEvidenceBinding(
        document_id=document_id,
        candidate_id="review-queue-inventory",
        source_sha256=source_sha256,
        candidate_evidence_sha256="0" * 64,
        region_image_sha256="0" * 64,
    )
    inventory = _document_package_inventory(
        document,
        binding_for_inventory,
    )
    for path in inventory:
        if root.state(path) != "regular":
            raise EquationReviewQueueIncompleteError(
                "document completion inventory is incomplete"
            )
    _verify_inventoried_files(root, inventory)
    index = _read_json(root, _INDEX_PATH)
    raw_candidates = _validate_index(
        index,
        document_id=document_id,
        source_sha256=source_sha256,
        detection_result_id=document.get("equation_detection_result_id"),
    )
    if len(raw_candidates) > MAX_EQUATION_REVIEW_QUEUE_CANDIDATES:
        raise EquationReviewQueueMalformedError(
            "equation candidate index exceeds the queue bound"
        )

    candidates: list[_CandidateProjection] = []
    bindings: dict[str, ReviewEvidenceIdentity] = {}
    seen_ids: set[str] = set()
    for value in raw_candidates:
        candidate = _validate_candidate(
            root,
            inventory,
            value,
            document_id=document_id,
            source_sha256=source_sha256,
            detection_result_id=document.get("equation_detection_result_id"),
        )
        if candidate.binding.candidate_id in seen_ids:
            raise EquationReviewQueueMalformedError(
                "equation candidate index contains duplicate identities"
            )
        seen_ids.add(candidate.binding.candidate_id)
        candidate_key = equation_candidate_artifact_key(candidate.binding.candidate_id)
        if candidate_key in bindings:
            raise EquationReviewQueueMalformedError(
                "equation candidate index contains duplicate artifact keys"
            )
        bindings[candidate_key] = candidate.binding
        candidates.append(candidate)

    extra_paths = _review_extension_paths(root, set(inventory))
    grouped = _group_review_paths(extra_paths, bindings)
    trees: dict[str, ValidatedReviewTree] = {}
    for candidate in candidates:
        candidate_key = equation_candidate_artifact_key(candidate.binding.candidate_id)
        trees[candidate_key] = validate_review_tree(
            root,
            candidate_root=(PurePosixPath("content/equations/regions") / candidate_key),
            binding=candidate.binding,
            expected_paths=grouped.get(candidate_key, set()),
        )

    items = tuple(
        sorted(
            (
                _queue_item(
                    candidate,
                    trees[
                        equation_candidate_artifact_key(candidate.binding.candidate_id)
                    ],
                )
                for candidate in candidates
                if candidate.kind == "display"
                and candidate.evidence_status == "proposed"
            ),
            key=_queue_sort_key,
        )
    )
    identity = {
        "contract_id": EQUATION_REVIEW_QUEUE_CONTRACT_ID,
        "document_id": document_id,
        "items": [_item_value(item) for item in items],
        "package_id": _bounded_text(document.get("package_id"), "package ID"),
        "schema_version": EQUATION_REVIEW_QUEUE_SCHEMA_VERSION,
        "source_sha256": source_sha256,
    }
    return EquationReviewQueueProjection(
        contract_id=EQUATION_REVIEW_QUEUE_CONTRACT_ID,
        schema_version=EQUATION_REVIEW_QUEUE_SCHEMA_VERSION,
        document_id=document_id,
        source_sha256=source_sha256,
        package_id=str(document["package_id"]),
        items=items,
        projection_id=_queue_id(identity),
    )


@dataclass(frozen=True, slots=True)
class _CandidateProjection:
    binding: ReviewEvidenceIdentity
    page_index: int
    printed_page_label: str | None
    bounding_box: tuple[float, float, float, float]
    kind: str
    evidence_status: str
    native_evidence: EquationReviewQueueNativeEvidence


def _validate_index(
    index: dict[str, object],
    *,
    document_id: str,
    source_sha256: str,
    detection_result_id: object,
) -> list[object]:
    candidates = index.get("candidates")
    if (
        set(index) != _INDEX_KEYS
        or index.get("detection_artifact") != _DETECTION_PATH.as_posix()
        or index.get("detection_result_id") != detection_result_id
        or index.get("document_key") != document_id
        or index.get("schema_version") != 1
        or index.get("source_sha256") != source_sha256
        or index.get("status") != "deterministic-unreviewed"
        or not isinstance(candidates, list)
    ):
        raise EquationReviewQueueMalformedError(
            "equation candidate index is inconsistent"
        )
    return candidates


def _validate_candidate(
    root: AuthorizedRoot,
    inventory: dict[PurePosixPath, _InventoryEntry],
    index_value: object,
    *,
    document_id: str,
    source_sha256: str,
    detection_result_id: object,
) -> _CandidateProjection:
    if not isinstance(index_value, dict) or set(index_value) != _INDEX_RECORD_KEYS:
        raise EquationReviewQueueMalformedError(
            "equation candidate index record is malformed"
        )
    candidate_id = _bounded_id(index_value.get("candidate_id"), "candidate ID")
    candidate_key = equation_candidate_artifact_key(candidate_id)
    candidate_root = PurePosixPath("content/equations/regions") / candidate_key
    image_path = candidate_root / "source/image.png"
    source_manifest_path = candidate_root / "source/manifest.json"
    deterministic_path = candidate_root / "deterministic/manifest.json"
    image_sha256 = _digest(index_value.get("image_sha256"), "region image SHA-256")
    if (
        index_value.get("image_path") != image_path.as_posix()
        or index_value.get("source_manifest") != source_manifest_path.as_posix()
        or index_value.get("deterministic_manifest") != deterministic_path.as_posix()
        or index_value.get("kind") not in {"display", "inline"}
        or index_value.get("evidence_status") not in {"proposed", "ambiguous"}
    ):
        raise EquationReviewQueueMalformedError(
            "equation candidate index membership is inconsistent"
        )
    image_entry = _inventory_entry(inventory, image_path, "image/png")
    _inventory_entry(
        inventory,
        source_manifest_path,
        "application/json",
    )
    deterministic_entry = _inventory_entry(
        inventory,
        deterministic_path,
        "application/json",
    )
    if image_entry.sha256 != image_sha256:
        raise EquationReviewQueueMalformedError(
            "region image index hash is inconsistent"
        )
    source_manifest = _read_json(root, source_manifest_path)
    deterministic = _read_json(root, deterministic_path)
    source_identity = dict(source_manifest)
    source_manifest_id = source_identity.pop("manifest_id", None)
    deterministic_identity = dict(deterministic)
    deterministic_manifest_id = deterministic_identity.pop("manifest_id", None)
    candidate = deterministic.get("candidate")
    if not isinstance(candidate, dict):
        raise EquationReviewQueueMalformedError(
            "deterministic candidate evidence is malformed"
        )
    rendered = candidate.get("rendered_region")
    region = source_manifest.get("region")
    if (
        source_manifest_id != _id("equation-region-source-manifest", source_identity)
        or deterministic_manifest_id
        != _id("equation-deterministic-manifest", deterministic_identity)
        or source_manifest.get("candidate_id") != candidate_id
        or source_manifest.get("document_key") != document_id
        or source_manifest.get("image_path") != image_path.as_posix()
        or source_manifest.get("image_sha256") != image_sha256
        or source_manifest.get("schema_version") != 1
        or source_manifest.get("source_sha256") != source_sha256
        or source_manifest.get("status") != "immutable-source-evidence"
        or deterministic.get("detection_result_id") != detection_result_id
        or deterministic.get("document_key") != document_id
        or deterministic.get("schema_version") != 1
        or deterministic.get("status") != "deterministic-proposal"
        or candidate.get("candidate_id") != candidate_id
        or candidate.get("kind") != index_value.get("kind")
        or candidate.get("evidence_status") != index_value.get("evidence_status")
        or not isinstance(rendered, dict)
        or rendered != region
        or rendered.get("content_sha256") != image_sha256
        or rendered.get("source_content_hash") != source_sha256
    ):
        raise EquationReviewQueueMalformedError(
            "candidate evidence binding is inconsistent"
        )
    page_index = rendered.get("page_index")
    printed_page_label = rendered.get("printed_page_label")
    bounding_box = _bounding_box(rendered.get("source_bounding_box"))
    if (
        type(page_index) is not int
        or page_index < 0
        or (printed_page_label is not None and not isinstance(printed_page_label, str))
    ):
        raise EquationReviewQueueMalformedError("candidate page evidence is malformed")
    native = _native_evidence(candidate)
    return _CandidateProjection(
        binding=ReviewEvidenceIdentity(
            document_id=document_id,
            candidate_id=candidate_id,
            source_sha256=source_sha256,
            candidate_evidence_sha256=deterministic_entry.sha256,
            region_image_sha256=image_sha256,
        ),
        page_index=page_index,
        printed_page_label=printed_page_label,
        bounding_box=bounding_box,
        kind=str(index_value["kind"]),
        evidence_status=str(index_value["evidence_status"]),
        native_evidence=native,
    )


def _native_evidence(candidate: dict[str, object]) -> EquationReviewQueueNativeEvidence:
    raw_text = _bounded_text(candidate.get("raw_text"), "native equation text")
    source_label = candidate.get("source_label")
    confidence = candidate.get("confidence")
    warning_ids = candidate.get("warning_ids")
    if (
        source_label is not None
        and not isinstance(source_label, str)
        or isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not math.isfinite(float(confidence))
        or not 0.0 <= float(confidence) <= 1.0
        or not isinstance(warning_ids, list)
        or len(warning_ids) > 1_000
        or any(not isinstance(value, str) for value in warning_ids)
    ):
        raise EquationReviewQueueMalformedError("native equation evidence is malformed")
    valid_source_label = (
        None if source_label is None else _bounded_text(source_label, "source label")
    )
    valid_warning_ids = tuple(
        _bounded_text(value, "warning ID") for value in warning_ids
    )
    return EquationReviewQueueNativeEvidence(
        raw_text=raw_text,
        source_label=valid_source_label,
        confidence=float(confidence),
        evidence_status=_bounded_text(
            candidate.get("evidence_status"),
            "native evidence status",
        ),
        source_block_id=_bounded_text(
            candidate.get("source_block_id"),
            "source block ID",
        ),
        detection_input_id=_bounded_text(
            candidate.get("detection_input_id"),
            "detection input ID",
        ),
        warning_ids=valid_warning_ids,
        processor_name=_bounded_text(
            candidate.get("processor_name"),
            "processor name",
        ),
        processor_version=_bounded_text(
            candidate.get("processor_version"),
            "processor version",
        ),
        configuration_digest=_bounded_text(
            candidate.get("configuration_digest"),
            "configuration digest",
        ),
        candidate_sha256=hashlib.sha256(_canonical(candidate)).hexdigest(),
    )


def _review_extension_paths(
    root: AuthorizedRoot,
    deterministic_paths: set[PurePosixPath],
) -> set[PurePosixPath]:
    expected = deterministic_paths | {DOCUMENT_PACKAGE_MANIFEST}
    try:
        observed = set(
            root.iter_files(
                suffix="",
                recursive=True,
                max_files=(MAX_DOCUMENT_PACKAGE_ARTIFACTS + MAX_REVIEW_ARTIFACTS + 1),
                max_entries=(MAX_DOCUMENT_PACKAGE_ARTIFACTS + MAX_REVIEW_ARTIFACTS + 1),
                max_depth=8,
            )
        )
    except (OSError, ValueError) as error:
        raise EquationReviewQueueMalformedError(
            "document package inventory is unsafe"
        ) from error
    if not expected.issubset(observed):
        raise EquationReviewQueueIncompleteError(
            "document package inventory is incomplete"
        )
    return observed - expected


def _group_review_paths(
    paths: set[PurePosixPath],
    bindings: dict[str, ReviewEvidenceIdentity],
) -> dict[str, set[PurePosixPath]]:
    grouped: dict[str, set[PurePosixPath]] = {}
    for path in paths:
        if (
            len(path.parts) < 5
            or path.parts[:3] != ("content", "equations", "regions")
            or path.parts[3] not in bindings
        ):
            raise EquationReviewQueueMalformedError(
                "document package contains an unknown artifact"
            )
        grouped.setdefault(path.parts[3], set()).add(path)
    return grouped


def _queue_item(
    candidate: _CandidateProjection,
    tree: ValidatedReviewTree,
) -> EquationReviewQueueItem:
    assisted = tree.assisted
    assistance = EquationReviewQueueAssistance(
        status=(
            EquationReviewQueueAssistanceStatus.NOT_STARTED
            if assisted is None
            else EquationReviewQueueAssistanceStatus.AUTOMATED_UNREVIEWED
        ),
        attempt_id=None if assisted is None else assisted.attempt_id,
        method=None if assisted is None else assisted.method,
        proposal=None if assisted is None else assisted.proposed_latex,
        proposal_sha256=None if assisted is None else assisted.proposal_sha256,
    )
    latest = None if not tree.revisions else tree.revisions[-1]
    decision = None if latest is None else _latest_decision(latest)
    return EquationReviewQueueItem(
        document_id=candidate.binding.document_id,
        candidate_id=candidate.binding.candidate_id,
        page_index=candidate.page_index,
        physical_page_number=candidate.page_index + 1,
        printed_page_label=candidate.printed_page_label,
        bounding_box=candidate.bounding_box,
        display_mode="DISPLAY",
        source_sha256=candidate.binding.source_sha256,
        candidate_evidence_sha256=candidate.binding.candidate_evidence_sha256,
        region_image_sha256=candidate.binding.region_image_sha256,
        native_evidence=candidate.native_evidence,
        assistance=assistance,
        decision_status=(
            EquationReviewQueueDecisionStatus.NOT_REVIEWED
            if decision is None
            else decision.status
        ),
        latest_decision=decision,
    )


def _latest_decision(
    revision: ValidatedHumanRevision,
) -> EquationReviewQueueLatestDecision:
    disposition = EquationReviewDisposition(revision.disposition)
    status = {
        EquationReviewDisposition.ACCEPT_TRANSCRIPTION: (
            EquationReviewQueueDecisionStatus.ACCEPTED
        ),
        EquationReviewDisposition.REJECT_CANDIDATE: (
            EquationReviewQueueDecisionStatus.REJECTED
        ),
        EquationReviewDisposition.REVISION_REQUIRED: (
            EquationReviewQueueDecisionStatus.REVISION_REQUIRED
        ),
    }[disposition]
    render = revision.render_confirmation
    return EquationReviewQueueLatestDecision(
        status=status,
        revision=revision.revision,
        schema_version=revision.schema_version,
        revision_id=revision.revision_id,
        disposition=disposition,
        assistance_proposal_sha256=revision.assistance_proposal_sha256,
        note=revision.note,
        recorded_at_utc=revision.recorded_at_utc.isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        reviewer_latex=revision.reviewer_latex,
        reviewer_latex_sha256=revision.reviewer_latex_sha256,
        obsidian_markdown=revision.obsidian_markdown,
        obsidian_markdown_sha256=revision.obsidian_markdown_sha256,
        display_mode=revision.display_mode,
        renderer_id=None if render is None else render.renderer_id,
        renderer_version=None if render is None else render.renderer_version,
        rendered_reviewer_latex_sha256=(
            None if render is None else render.rendered_reviewer_latex_sha256
        ),
        rendered_obsidian_markdown_sha256=(
            None if render is None else render.rendered_obsidian_markdown_sha256
        ),
    )


def _queue_sort_key(item: EquationReviewQueueItem) -> tuple[object, ...]:
    x0, y0, x1, y1 = item.bounding_box
    return (item.page_index, y0, x0, y1, x1, item.candidate_id)


def _item_value(item: EquationReviewQueueItem) -> dict[str, object]:
    native = item.native_evidence
    assistance = item.assistance
    decision = item.latest_decision
    return {
        "assistance": {
            "attempt_id": assistance.attempt_id,
            "method": assistance.method,
            "proposal": assistance.proposal,
            "proposal_sha256": assistance.proposal_sha256,
            "status": assistance.status.value,
        },
        "bounding_box": list(item.bounding_box),
        "candidate_evidence_sha256": item.candidate_evidence_sha256,
        "candidate_id": item.candidate_id,
        "decision_status": item.decision_status.value,
        "display_mode": item.display_mode,
        "document_id": item.document_id,
        "latest_decision": None if decision is None else _decision_value(decision),
        "native_evidence": {
            "candidate_sha256": native.candidate_sha256,
            "confidence": native.confidence,
            "configuration_digest": native.configuration_digest,
            "detection_input_id": native.detection_input_id,
            "evidence_status": native.evidence_status,
            "processor_name": native.processor_name,
            "processor_version": native.processor_version,
            "raw_text": native.raw_text,
            "source_block_id": native.source_block_id,
            "source_label": native.source_label,
            "warning_ids": list(native.warning_ids),
        },
        "page_index": item.page_index,
        "physical_page_number": item.physical_page_number,
        "printed_page_label": item.printed_page_label,
        "region_image_sha256": item.region_image_sha256,
        "source_sha256": item.source_sha256,
    }


def _decision_value(value: EquationReviewQueueLatestDecision) -> dict[str, object]:
    return {
        "assistance_proposal_sha256": value.assistance_proposal_sha256,
        "display_mode": value.display_mode,
        "disposition": value.disposition.value,
        "note": value.note,
        "obsidian_markdown": value.obsidian_markdown,
        "obsidian_markdown_sha256": value.obsidian_markdown_sha256,
        "recorded_at_utc": value.recorded_at_utc,
        "renderer_id": value.renderer_id,
        "renderer_version": value.renderer_version,
        "rendered_obsidian_markdown_sha256": (value.rendered_obsidian_markdown_sha256),
        "rendered_reviewer_latex_sha256": value.rendered_reviewer_latex_sha256,
        "reviewer_latex": value.reviewer_latex,
        "reviewer_latex_sha256": value.reviewer_latex_sha256,
        "revision": value.revision,
        "revision_id": value.revision_id,
        "schema_version": value.schema_version,
        "status": value.status.value,
    }


def _inventory_entry(
    inventory: dict[PurePosixPath, _InventoryEntry],
    path: PurePosixPath,
    media_type: str,
) -> _InventoryEntry:
    entry = inventory.get(path)
    if entry is None or entry.media_type != media_type:
        raise EquationReviewQueueMalformedError(
            "candidate evidence is absent from completion inventory"
        )
    return entry


def _bounding_box(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise EquationReviewQueueMalformedError("candidate bounding box is malformed")
    if any(
        isinstance(item, bool) or not isinstance(item, int | float) for item in value
    ):
        raise EquationReviewQueueMalformedError("candidate bounding box is malformed")
    box = (
        float(value[0]),
        float(value[1]),
        float(value[2]),
        float(value[3]),
    )
    x0, y0, x1, y1 = box
    if not all(math.isfinite(item) for item in box) or x1 < x0 or y1 < y0:
        raise EquationReviewQueueMalformedError("candidate bounding box is malformed")
    return box


def _bounded_id(value: object, field: str) -> str:
    if not isinstance(value, str) or _OPAQUE_ID.fullmatch(value) is None:
        raise EquationReviewQueueMalformedError(f"{field} is malformed")
    return value


def _bounded_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1_000_000:
        raise EquationReviewQueueMalformedError(f"{field} is malformed")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise EquationReviewQueueMalformedError(f"{field} is malformed") from error
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise EquationReviewQueueMalformedError(f"{field} is malformed")
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _queue_id(value: object) -> str:
    return (
        f"equation-review-queue:sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"
    )
