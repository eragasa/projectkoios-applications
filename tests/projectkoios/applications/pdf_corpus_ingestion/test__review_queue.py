from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from projectkoios.applications.pdf_corpus_ingestion import (
    AssistedEquationAttempt,
    EquationDisplayMode,
    EquationRenderConfirmation,
    EquationReviewDisposition,
    EquationReviewEvidenceBinding,
    EquationReviewQueueAssistanceStatus,
    EquationReviewQueueDecisionStatus,
    EquationReviewQueueIncompleteError,
    EquationReviewQueueMalformedError,
    HumanEquationRevisionRequest,
    append_human_equation_revision,
    project_equation_review_queue,
    publish_assisted_equation_attempt,
)
from projectkoios.applications.pdf_corpus_ingestion.equation_review import (
    equation_candidate_artifact_key,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass

_RECORDED_AT = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class _Candidate:
    candidate_id: str
    page_index: int
    box: tuple[float, float, float, float]
    kind: str = "display"
    evidence_status: str = "proposed"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _stable_id(namespace: str, value: object) -> str:
    return f"{namespace}:sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


def _document_root(
    tmp_path: Path,
    candidates: tuple[_Candidate, ...],
) -> tuple[AuthorizedRoot, dict[str, EquationReviewEvidenceBinding]]:
    document_id = "pizzi2020"
    document = tmp_path / document_id
    source = b"%PDF-1.4\nsynthetic review queue fixture\n"
    source_sha256 = hashlib.sha256(source).hexdigest()
    detection_id = f"equation-detection-result:sha256:{'d' * 64}"
    extraction_id = f"pdf-extraction-artifact-bundle:sha256:{'e' * 64}"
    files: dict[str, tuple[bytes, str]] = {
        "source/document.pdf": (source, "application/pdf"),
        "source/manifest.json": (
            _canonical(
                {
                    "document_key": document_id,
                    "source_byte_size": len(source),
                    "source_path": "source/document.pdf",
                    "source_sha256": source_sha256,
                    "status": "immutable-source",
                }
            ),
            "application/json",
        ),
        "ingestion/extraction.json": (
            _canonical({"synthetic": True}),
            "application/json",
        ),
        "ingestion/manifest.json": (
            _canonical({"status": "deterministic-complete"}),
            "application/json",
        ),
        "content/equations/deterministic/detection.json": (
            _canonical({"result_id": detection_id}),
            "application/json",
        ),
        "content/equations/manifest.json": (
            _canonical({"status": "deterministic-unreviewed"}),
            "application/json",
        ),
    }
    index_records: list[dict[str, object]] = []
    bindings: dict[str, EquationReviewEvidenceBinding] = {}
    for ordinal, specification in enumerate(candidates, start=1):
        key = equation_candidate_artifact_key(specification.candidate_id)
        root = f"content/equations/regions/{key}"
        image_path = f"{root}/source/image.png"
        source_path = f"{root}/source/manifest.json"
        deterministic_path = f"{root}/deterministic/manifest.json"
        image = b"\x89PNG\r\n\x1a\n" + specification.candidate_id.encode()
        image_sha256 = hashlib.sha256(image).hexdigest()
        region = {
            "content_sha256": image_sha256,
            "page_index": specification.page_index,
            "printed_page_label": str(specification.page_index + 1),
            "source_bounding_box": list(specification.box),
            "source_content_hash": source_sha256,
        }
        source_identity = {
            "candidate_id": specification.candidate_id,
            "document_key": document_id,
            "image_path": image_path,
            "image_sha256": image_sha256,
            "region": region,
            "schema_version": 1,
            "source_sha256": source_sha256,
            "status": "immutable-source-evidence",
        }
        source_manifest = {
            **source_identity,
            "manifest_id": _stable_id(
                "equation-region-source-manifest",
                source_identity,
            ),
        }
        candidate = {
            "candidate_id": specification.candidate_id,
            "confidence": 0.9,
            "configuration_digest": f"configuration:sha256:{ordinal:064x}",
            "detection_input_id": f"equation-detection-input:sha256:{ordinal:064x}",
            "evidence": [["fixture", "synthetic"]],
            "evidence_status": specification.evidence_status,
            "kind": specification.kind,
            "processor_name": "synthetic-detector",
            "processor_version": "1.0",
            "raw_text": f"E_{{{ordinal}}} = mc^2",
            "rendered_region": region,
            "source_block_id": f"block:{ordinal}",
            "source_label": f"({ordinal})",
            "source_spans": [],
            "warning_ids": [],
        }
        deterministic_identity = {
            "candidate": candidate,
            "detection_result_id": detection_id,
            "document_key": document_id,
            "schema_version": 1,
            "status": "deterministic-proposal",
        }
        deterministic = _canonical(
            {
                **deterministic_identity,
                "manifest_id": _stable_id(
                    "equation-deterministic-manifest",
                    deterministic_identity,
                ),
            }
        )
        files[image_path] = (image, "image/png")
        files[source_path] = (_canonical(source_manifest), "application/json")
        files[deterministic_path] = (deterministic, "application/json")
        index_records.append(
            {
                "candidate_id": specification.candidate_id,
                "deterministic_manifest": deterministic_path,
                "evidence_status": specification.evidence_status,
                "image_path": image_path,
                "image_sha256": image_sha256,
                "kind": specification.kind,
                "source_manifest": source_path,
            }
        )
        bindings[specification.candidate_id] = EquationReviewEvidenceBinding(
            document_id=document_id,
            candidate_id=specification.candidate_id,
            source_sha256=source_sha256,
            candidate_evidence_sha256=hashlib.sha256(deterministic).hexdigest(),
            region_image_sha256=image_sha256,
        )
    files["content/equations/index.json"] = (
        _canonical(
            {
                "candidates": index_records,
                "detection_artifact": (
                    "content/equations/deterministic/detection.json"
                ),
                "detection_result_id": detection_id,
                "document_key": document_id,
                "schema_version": 1,
                "source_sha256": source_sha256,
                "status": "deterministic-unreviewed",
            }
        ),
        "application/json",
    )
    inventory = [
        {
            "byte_size": len(content),
            "media_type": media_type,
            "relative_path": path,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path, (content, media_type) in files.items()
    ]
    completion_identity = {
        "artifact_files": inventory,
        "contract_id": "projectkoios.applications.pdf-corpus-document-package",
        "document_key": document_id,
        "equation_detection_result_id": detection_id,
        "extraction_bundle_id": extraction_id,
        "schema_version": 1,
        "source_byte_size": len(source),
        "source_sha256": source_sha256,
        "stages": {
            "assisted": "not-started",
            "equation_detection": "deterministic-complete",
            "human_review": "not-started",
            "ingestion": "deterministic-complete",
            "transcript": "not-started",
        },
        "status": "deterministic-complete",
    }
    files["document-manifest.json"] = (
        _canonical(
            {
                **completion_identity,
                "package_id": _stable_id(
                    "document-processing-package",
                    completion_identity,
                ),
            }
        ),
        "application/json",
    )
    for relative, (content, _) in files.items():
        target = document / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return (
        AuthorizedRoot.existing(
            document,
            label="synthetic review queue package",
            root_alias="synthetic-review-queue",
            storage_class=RootStorageClass.LOCAL,
        ),
        bindings,
    )


def _attempt(binding: EquationReviewEvidenceBinding) -> AssistedEquationAttempt:
    return AssistedEquationAttempt.create(
        binding=binding,
        method="synthetic-assistance",
        proposed_latex=r"E = mc^2",
    )


def _legacy_revision(
    root_path: Path,
    binding: EquationReviewEvidenceBinding,
    proposal_sha256: str,
) -> None:
    identity = {
        "assistance_proposal_sha256": proposal_sha256,
        "candidate_evidence_sha256": binding.candidate_evidence_sha256,
        "candidate_id": binding.candidate_id,
        "contract_id": "projectkoios.applications.pdf-corpus-equation-review",
        "disposition": "ACCEPT_TRANSCRIPTION",
        "document_id": binding.document_id,
        "note": "Legacy accepted review.",
        "region_image_sha256": binding.region_image_sha256,
        "revision": 1,
        "schema_version": 2,
        "source_sha256": binding.source_sha256,
    }
    decision_value = {
        **identity,
        "recorded_at_utc": "2026-09-29T12:00:00.000000Z",
        "revision_id": _stable_id("equation-human-revision", identity),
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
    candidate_key = equation_candidate_artifact_key(binding.candidate_id)
    target = (
        root_path / "content/equations/regions" / candidate_key / "human/revision-0001"
    )
    target.mkdir(parents=True)
    (target / "decision.json").write_bytes(decision)
    (target / "manifest.json").write_bytes(_canonical(manifest))


def _accept_request(
    binding: EquationReviewEvidenceBinding,
    proposal_sha256: str,
    *,
    previous: int,
    latex: str,
) -> HumanEquationRevisionRequest:
    return HumanEquationRevisionRequest(
        binding=binding,
        disposition=EquationReviewDisposition.ACCEPT_TRANSCRIPTION,
        assistance_proposal_sha256=proposal_sha256,
        note="Rendered and accepted.",
        recorded_at_utc=_RECORDED_AT,
        expected_previous_revision=previous,
        reviewer_latex=latex,
        display_mode=EquationDisplayMode.DISPLAY,
        render_confirmation=EquationRenderConfirmation.create(
            renderer_id="mathjax",
            renderer_version="3.2.2",
            reviewer_latex=latex,
            display_mode=EquationDisplayMode.DISPLAY,
        ),
    )


def _replace_index_and_completion(document: Path, index: dict[str, object]) -> None:
    index_path = document / "content/equations/index.json"
    index_bytes = _canonical(index)
    index_path.write_bytes(index_bytes)
    completion_path = document / "document-manifest.json"
    completion = json.loads(completion_path.read_bytes())
    for entry in completion["artifact_files"]:
        if entry["relative_path"] == "content/equations/index.json":
            entry["byte_size"] = len(index_bytes)
            entry["sha256"] = hashlib.sha256(index_bytes).hexdigest()
            break
    identity = dict(completion)
    identity.pop("package_id")
    completion["package_id"] = _stable_id(
        "document-processing-package",
        identity,
    )
    completion_path.write_bytes(_canonical(completion))


def _candidate_specs() -> tuple[_Candidate, ...]:
    return (
        _Candidate("pizzi:eq:assisted", 1, (10, 40, 90, 60)),
        _Candidate("pizzi:eq:rejected", 2, (10, 10, 90, 30)),
        _Candidate("pizzi:eq:unassisted", 0, (50, 30, 100, 50)),
        _Candidate("pizzi:eq:legacy", 0, (10, 10, 80, 20)),
        _Candidate("pizzi:eq:superseded", 0, (20, 30, 70, 40)),
        _Candidate("pizzi:eq:inline", 0, (1, 1, 2, 2), kind="inline"),
        _Candidate(
            "pizzi:eq:ambiguous",
            0,
            (2, 2, 3, 3),
            evidence_status="ambiguous",
        ),
    )


def test_projects_stable_ordered_queue_with_all_review_lifecycle_shapes(
    tmp_path: Path,
) -> None:
    root, bindings = _document_root(tmp_path, _candidate_specs())
    document = tmp_path / "pizzi2020"
    initial = project_equation_review_queue(document_root=root)

    assisted = _attempt(bindings["pizzi:eq:assisted"])
    publish_assisted_equation_attempt(assisted, document_root=root)

    legacy_attempt = _attempt(bindings["pizzi:eq:legacy"])
    publish_assisted_equation_attempt(legacy_attempt, document_root=root)
    _legacy_revision(
        document, bindings["pizzi:eq:legacy"], legacy_attempt.proposal_sha256
    )

    superseded_attempt = _attempt(bindings["pizzi:eq:superseded"])
    publish_assisted_equation_attempt(superseded_attempt, document_root=root)
    _legacy_revision(
        document,
        bindings["pizzi:eq:superseded"],
        superseded_attempt.proposal_sha256,
    )
    append_human_equation_revision(
        _accept_request(
            bindings["pizzi:eq:superseded"],
            superseded_attempt.proposal_sha256,
            previous=1,
            latex=r"E = mc^{2}",
        ),
        document_root=root,
    )

    append_human_equation_revision(
        HumanEquationRevisionRequest(
            binding=bindings["pizzi:eq:rejected"],
            disposition=EquationReviewDisposition.REJECT_CANDIDATE,
            assistance_proposal_sha256=None,
            note="Not an equation.",
            recorded_at_utc=_RECORDED_AT,
            expected_previous_revision=0,
        ),
        document_root=root,
    )

    first = project_equation_review_queue(document_root=root)
    second = project_equation_review_queue(document_root=root)

    assert first == second
    assert first.projection_id == second.projection_id
    assert first.projection_id != initial.projection_id
    assert first.projection_id.startswith("equation-review-queue:sha256:")
    assert [item.candidate_id for item in first.items] == [
        "pizzi:eq:legacy",
        "pizzi:eq:superseded",
        "pizzi:eq:unassisted",
        "pizzi:eq:assisted",
        "pizzi:eq:rejected",
    ]
    by_id = {item.candidate_id: item for item in first.items}
    assert by_id["pizzi:eq:unassisted"].assistance.status is (
        EquationReviewQueueAssistanceStatus.NOT_STARTED
    )
    assert by_id["pizzi:eq:unassisted"].decision_status is (
        EquationReviewQueueDecisionStatus.NOT_REVIEWED
    )
    assisted_item = by_id["pizzi:eq:assisted"]
    assert assisted_item.assistance.status is (
        EquationReviewQueueAssistanceStatus.AUTOMATED_UNREVIEWED
    )
    assert assisted_item.assistance.proposal == r"E = mc^2"
    assert assisted_item.assistance.proposal_sha256 == assisted.proposal_sha256
    legacy = by_id["pizzi:eq:legacy"].latest_decision
    assert legacy is not None
    assert legacy.schema_version == 2
    assert legacy.status is EquationReviewQueueDecisionStatus.ACCEPTED
    assert legacy.reviewer_latex is None
    superseded = by_id["pizzi:eq:superseded"].latest_decision
    assert superseded is not None
    assert superseded.revision == 2
    assert superseded.schema_version == 3
    assert superseded.reviewer_latex == r"E = mc^{2}"
    assert superseded.obsidian_markdown == "$$\nE = mc^{2}\n$$"
    assert superseded.reviewer_latex_sha256 == hashlib.sha256(b"E = mc^{2}").hexdigest()
    assert (
        superseded.obsidian_markdown_sha256
        == hashlib.sha256(b"$$\nE = mc^{2}\n$$").hexdigest()
    )
    assert superseded.renderer_id == "mathjax"
    rejected = by_id["pizzi:eq:rejected"].latest_decision
    assert rejected is not None
    assert rejected.status is EquationReviewQueueDecisionStatus.REJECTED
    assert rejected.reviewer_latex is None
    assert by_id["pizzi:eq:legacy"].physical_page_number == 1
    assert by_id["pizzi:eq:legacy"].bounding_box == (10.0, 10.0, 80.0, 20.0)
    assert by_id["pizzi:eq:legacy"].native_evidence.raw_text == "E_{4} = mc^2"
    serialized = json.dumps(asdict(first), ensure_ascii=False, sort_keys=True)
    assert "image_path" not in serialized
    assert "manifest.json" not in serialized
    assert not any(
        isinstance(value, bytes)
        for item in first.items
        for value in asdict(item).values()
    )


def test_partial_review_and_missing_inventory_are_typed_failures(
    tmp_path: Path,
) -> None:
    root, bindings = _document_root(
        tmp_path / "partial",
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    key = equation_candidate_artifact_key("pizzi:eq:one")
    partial = (
        tmp_path
        / "partial/pizzi2020/content/equations/regions"
        / key
        / "assisted/attempt-0001"
    )
    partial.mkdir(parents=True)
    (partial / "proposal.txt").write_text("E = mc^2")
    with pytest.raises(EquationReviewQueueMalformedError):
        project_equation_review_queue(document_root=root)

    missing_root, _ = _document_root(
        tmp_path / "missing",
        (_Candidate("pizzi:eq:two", 0, (1, 2, 3, 4)),),
    )
    (tmp_path / "missing/pizzi2020/source/document.pdf").unlink()
    with pytest.raises(EquationReviewQueueIncompleteError):
        project_equation_review_queue(document_root=missing_root)
    assert bindings


@pytest.mark.parametrize("mutation", ("duplicate", "path-mismatch", "bound"))
def test_duplicate_mismatched_and_over_bound_indexes_fail_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    root, _ = _document_root(
        tmp_path,
        (_Candidate("pizzi:eq:one", 0, (1, 2, 3, 4)),),
    )
    document = tmp_path / "pizzi2020"
    index_path = document / "content/equations/index.json"
    index = json.loads(index_path.read_bytes())
    record = index["candidates"][0]
    if mutation == "duplicate":
        index["candidates"].append(dict(record))
    elif mutation == "path-mismatch":
        record["image_path"] = "content/equations/regions/wrong/source/image.png"
    else:
        index["candidates"] = [dict(record) for _ in range(257)]
    _replace_index_and_completion(document, index)

    with pytest.raises(EquationReviewQueueMalformedError):
        project_equation_review_queue(document_root=root)
