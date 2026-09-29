from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import pytest

from projectkoios.applications.pdf_corpus_ingestion import (
    ASSISTED_EQUATION_ATTEMPT_SCHEMA_VERSION,
    DOCUMENT_PACKAGE_SCHEMA_VERSION,
    AssistedEquationAttempt,
    EquationDisplayMode,
    EquationRenderConfirmation,
    EquationReviewConcurrencyError,
    EquationReviewDisposition,
    EquationReviewError,
    EquationReviewEvidenceBinding,
    EquationReviewEvidenceMismatch,
    EquationReviewPublicationAction,
    EquationReviewPublicationError,
    EquationReviewStaleRevision,
    HumanEquationRevisionRequest,
    append_human_equation_revision,
    load_latest_human_equation_revision,
    publish_assisted_equation_attempt,
)
from projectkoios.applications.pdf_corpus_ingestion.equation_review import (
    equation_candidate_artifact_key,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass

_DOCUMENT = "pizzi2020"
_CANDIDATE = "pizzi2020:eq:001"
_RECORDED_AT = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _document_root(
    tmp_path: Path,
    *,
    candidate_kind: str = "display",
) -> tuple[AuthorizedRoot, EquationReviewEvidenceBinding]:
    document = tmp_path / _DOCUMENT
    candidate_key = equation_candidate_artifact_key(_CANDIDATE)
    candidate_root = f"content/equations/regions/{candidate_key}"
    image_path = f"{candidate_root}/source/image.png"
    candidate_source_path = f"{candidate_root}/source/manifest.json"
    deterministic_path = f"{candidate_root}/deterministic/manifest.json"

    source = b"%PDF-1.4\nsynthetic bytes only\n"
    image = b"\x89PNG\r\n\x1a\nsynthetic-region"
    source_sha256 = hashlib.sha256(source).hexdigest()
    image_sha256 = hashlib.sha256(image).hexdigest()
    detection_id = f"equation-detection-result:sha256:{'d' * 64}"
    extraction_id = f"pdf-extraction-artifact-bundle:sha256:{'e' * 64}"
    deterministic = _canonical(
        {
            "candidate": {
                "candidate_id": _CANDIDATE,
                "rendered_region": {"content_sha256": image_sha256},
            },
            "detection_result_id": detection_id,
            "document_key": _DOCUMENT,
            "schema_version": 1,
            "status": "deterministic-proposal",
        }
    )
    evidence_sha256 = hashlib.sha256(deterministic).hexdigest()
    files: dict[str, tuple[bytes, str]] = {
        "source/document.pdf": (source, "application/pdf"),
        "source/manifest.json": (
            _canonical(
                {
                    "document_key": _DOCUMENT,
                    "schema_version": 1,
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
        image_path: (image, "image/png"),
        candidate_source_path: (
            _canonical(
                {
                    "candidate_id": _CANDIDATE,
                    "document_key": _DOCUMENT,
                    "image_path": image_path,
                    "image_sha256": image_sha256,
                    "schema_version": 1,
                    "source_sha256": source_sha256,
                    "status": "immutable-source-evidence",
                }
            ),
            "application/json",
        ),
        deterministic_path: (deterministic, "application/json"),
        "content/equations/index.json": (
            _canonical(
                {
                    "candidates": [
                        {
                            "candidate_id": _CANDIDATE,
                            "deterministic_manifest": deterministic_path,
                            "evidence_status": "proposed",
                            "image_path": image_path,
                            "image_sha256": image_sha256,
                            "kind": candidate_kind,
                            "source_manifest": candidate_source_path,
                        }
                    ],
                    "detection_artifact": (
                        "content/equations/deterministic/detection.json"
                    ),
                    "detection_result_id": detection_id,
                    "document_key": _DOCUMENT,
                    "schema_version": 1,
                    "source_sha256": source_sha256,
                    "status": "deterministic-unreviewed",
                }
            ),
            "application/json",
        ),
        "content/equations/manifest.json": (
            _canonical({"status": "deterministic-unreviewed"}),
            "application/json",
        ),
    }
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
        "document_key": _DOCUMENT,
        "equation_detection_result_id": detection_id,
        "extraction_bundle_id": extraction_id,
        "schema_version": DOCUMENT_PACKAGE_SCHEMA_VERSION,
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
    completion = {
        **completion_identity,
        "package_id": (
            "document-processing-package:sha256:"
            f"{hashlib.sha256(_canonical(completion_identity)).hexdigest()}"
        ),
    }
    files["document-manifest.json"] = (_canonical(completion), "application/json")
    for relative, (content, _) in files.items():
        target = document / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    root = AuthorizedRoot.existing(
        document,
        label="synthetic document package",
        root_alias="synthetic-document-package",
        storage_class=RootStorageClass.LOCAL,
    )
    return root, EquationReviewEvidenceBinding(
        document_id=_DOCUMENT,
        candidate_id=_CANDIDATE,
        source_sha256=source_sha256,
        candidate_evidence_sha256=evidence_sha256,
        region_image_sha256=image_sha256,
    )


def _attempt(binding: EquationReviewEvidenceBinding) -> AssistedEquationAttempt:
    return AssistedEquationAttempt.create(
        binding=binding,
        method="local-equation-assistance-v1",
        proposed_latex=r"E = mc^2",
    )


def _replace_assisted_attempt(
    tmp_path: Path,
    binding: EquationReviewEvidenceBinding,
    *,
    proposal: bytes,
    method: str,
) -> str:
    proposal_sha256 = hashlib.sha256(proposal).hexdigest()
    identity = {
        "attempt": 1,
        "candidate_evidence_sha256": binding.candidate_evidence_sha256,
        "candidate_id": binding.candidate_id,
        "contract_id": ("projectkoios.applications.pdf-corpus-equation-review"),
        "document_id": binding.document_id,
        "method": method,
        "proposal_path": "proposal.txt",
        "proposal_sha256": proposal_sha256,
        "region_image_sha256": binding.region_image_sha256,
        "schema_version": ASSISTED_EQUATION_ATTEMPT_SCHEMA_VERSION,
        "source_sha256": binding.source_sha256,
        "status": "automated_unreviewed",
    }
    manifest = {
        **identity,
        "artifact_files": [
            {
                "byte_size": len(proposal),
                "relative_path": "proposal.txt",
                "sha256": proposal_sha256,
            }
        ],
        "attempt_id": (
            "equation-assisted-attempt:sha256:"
            f"{hashlib.sha256(_canonical(identity)).hexdigest()}"
        ),
    }
    attempt_root = _review_root(tmp_path) / "assisted/attempt-0001"
    (attempt_root / "proposal.txt").write_bytes(proposal)
    (attempt_root / "manifest.json").write_bytes(_canonical(manifest))
    return proposal_sha256


def _request(
    binding: EquationReviewEvidenceBinding,
    proposal_sha256: str | None,
    *,
    disposition: EquationReviewDisposition = (
        EquationReviewDisposition.ACCEPT_TRANSCRIPTION
    ),
    note: str = "Checked against the exact displayed region.",
    recorded_at: datetime = _RECORDED_AT,
    expected_previous_revision: int = 0,
    reviewer_latex: str = r"E = mc^2",
    display_mode: EquationDisplayMode = EquationDisplayMode.DISPLAY,
    render_confirmation: EquationRenderConfirmation | None = None,
) -> HumanEquationRevisionRequest:
    accepting = disposition is EquationReviewDisposition.ACCEPT_TRANSCRIPTION
    confirmation = render_confirmation
    if accepting and confirmation is None:
        confirmation = EquationRenderConfirmation.create(
            renderer_id="mathjax",
            renderer_version="3.2.2",
            reviewer_latex=reviewer_latex,
            display_mode=display_mode,
        )
    return HumanEquationRevisionRequest(
        binding=binding,
        disposition=disposition,
        assistance_proposal_sha256=proposal_sha256,
        note=note,
        recorded_at_utc=recorded_at,
        expected_previous_revision=expected_previous_revision,
        reviewer_latex=reviewer_latex if accepting else None,
        display_mode=display_mode if accepting else None,
        render_confirmation=confirmation if accepting else None,
    )


def _write_legacy_schema_2_revision(
    tmp_path: Path,
    binding: EquationReviewEvidenceBinding,
    proposal_sha256: str,
) -> tuple[bytes, bytes]:
    identity = {
        "assistance_proposal_sha256": proposal_sha256,
        "candidate_evidence_sha256": binding.candidate_evidence_sha256,
        "candidate_id": binding.candidate_id,
        "contract_id": "projectkoios.applications.pdf-corpus-equation-review",
        "disposition": "ACCEPT_TRANSCRIPTION",
        "document_id": binding.document_id,
        "note": "Immutable schema-2 acceptance.",
        "region_image_sha256": binding.region_image_sha256,
        "revision": 1,
        "schema_version": 2,
        "source_sha256": binding.source_sha256,
    }
    decision = _canonical(
        {
            **identity,
            "recorded_at_utc": "2026-09-28T12:00:00.000000Z",
            "revision_id": (
                "equation-human-revision:sha256:"
                f"{hashlib.sha256(_canonical(identity)).hexdigest()}"
            ),
        }
    )
    decision_value = json.loads(decision)
    manifest = _canonical(
        {
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
    )
    revision_root = _review_root(tmp_path) / "human/revision-0001"
    revision_root.mkdir(parents=True)
    (revision_root / "decision.json").write_bytes(decision)
    (revision_root / "manifest.json").write_bytes(manifest)
    return decision, manifest


def _review_root(tmp_path: Path) -> Path:
    return (
        tmp_path
        / _DOCUMENT
        / "content/equations/regions"
        / equation_candidate_artifact_key(_CANDIDATE)
    )


def test_assisted_attempt_is_immutable_automated_unreviewed(
    tmp_path: Path,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)

    first = publish_assisted_equation_attempt(attempt, document_root=root)
    replay = publish_assisted_equation_attempt(attempt, document_root=root)
    attempt_root = _review_root(tmp_path) / "assisted/attempt-0001"
    manifest = json.loads((attempt_root / "manifest.json").read_text())

    assert first is EquationReviewPublicationAction.CREATE
    assert replay is EquationReviewPublicationAction.UNCHANGED
    assert (attempt_root / "proposal.txt").read_text() == r"E = mc^2"
    assert manifest["status"] == "automated_unreviewed"
    assert manifest["proposal_sha256"] == attempt.proposal_sha256
    assert manifest["candidate_evidence_sha256"] == (binding.candidate_evidence_sha256)
    with pytest.raises(EquationReviewError, match="automated_unreviewed"):
        replace(attempt, status="accepted")


def test_human_acceptance_is_a_separate_exactly_bound_revision(
    tmp_path: Path,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)
    request = _request(binding, attempt.proposal_sha256)

    assert load_latest_human_equation_revision(binding, document_root=root) is None
    first = append_human_equation_revision(request, document_root=root)
    retry = _request(
        binding,
        attempt.proposal_sha256,
        recorded_at=_RECORDED_AT + timedelta(hours=1),
    )
    replay = append_human_equation_revision(retry, document_root=root)
    review_root = _review_root(tmp_path)
    decision = json.loads(
        (review_root / "human/revision-0001/decision.json").read_text()
    )
    assistance = json.loads(
        (review_root / "assisted/attempt-0001/manifest.json").read_text()
    )
    revision_manifest = json.loads(
        (review_root / "human/revision-0001/manifest.json").read_text()
    )

    assert first.action is EquationReviewPublicationAction.CREATE
    assert replay.action is EquationReviewPublicationAction.UNCHANGED
    assert first.revision == replay.revision
    assert replay.revision.recorded_at_utc == _RECORDED_AT
    assert replay.revision.recorded_at_utc != retry.recorded_at_utc
    assert (
        load_latest_human_equation_revision(
            binding,
            document_root=root,
        )
        == first.revision
    )
    assert decision["revision"] == 1
    assert decision["disposition"] == "ACCEPT_TRANSCRIPTION"
    assert decision["assistance_proposal_sha256"] == attempt.proposal_sha256
    assert decision["source_sha256"] == binding.source_sha256
    assert decision["candidate_evidence_sha256"] == (binding.candidate_evidence_sha256)
    assert decision["region_image_sha256"] == binding.region_image_sha256
    assert decision["note"] == request.note
    assert decision["recorded_at_utc"] == "2026-09-28T12:00:00.000000Z"
    assert decision["display_mode"] == "DISPLAY"
    assert decision["reviewer_latex_sha256"] == attempt.proposal_sha256
    assert first.revision.reviewer_latex == attempt.proposed_latex
    assert first.revision.obsidian_markdown == "$$\nE = mc^2\n$$"
    assert (
        review_root / "human/revision-0001/reviewer-latex.txt"
    ).read_bytes() == b"E = mc^2"
    assert (
        review_root / "human/revision-0001/obsidian-markdown.md"
    ).read_bytes() == b"$$\nE = mc^2\n$$"
    assert [item["relative_path"] for item in revision_manifest["artifact_files"]] == [
        "decision.json",
        "obsidian-markdown.md",
        "reviewer-latex.txt",
    ]
    assert "mathml" not in json.dumps(revision_manifest).lower()
    assert assistance["status"] == "automated_unreviewed"


def test_inline_candidate_uses_inline_obsidian_wrapper(tmp_path: Path) -> None:
    root, binding = _document_root(tmp_path, candidate_kind="inline")
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)

    accepted = append_human_equation_revision(
        _request(
            binding,
            attempt.proposal_sha256,
            display_mode=EquationDisplayMode.INLINE,
        ),
        document_root=root,
    )

    assert accepted.revision.obsidian_markdown == "$E = mc^2$"
    assert "$$" not in accepted.revision.obsidian_markdown
    assert (
        _review_root(tmp_path) / "human/revision-0001/obsidian-markdown.md"
    ).read_bytes() == b"$E = mc^2$"


def test_acceptance_rejects_wrapper_different_from_candidate_kind(
    tmp_path: Path,
) -> None:
    root, binding = _document_root(tmp_path, candidate_kind="inline")
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)

    with pytest.raises(EquationReviewEvidenceMismatch, match="display mode"):
        append_human_equation_revision(
            _request(binding, attempt.proposal_sha256),
            document_root=root,
        )


def test_reads_schema_2_then_appends_corrected_schema_3_revision(
    tmp_path: Path,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)
    legacy_decision, legacy_manifest = _write_legacy_schema_2_revision(
        tmp_path,
        binding,
        attempt.proposal_sha256,
    )

    legacy = load_latest_human_equation_revision(binding, document_root=root)
    assert legacy is not None
    assert legacy.schema_version == 2
    assert legacy.reviewer_latex is None

    corrected = r"E = mc^{2}"
    appended = append_human_equation_revision(
        _request(
            binding,
            attempt.proposal_sha256,
            note="Accepted after editing and rendering the correction.",
            expected_previous_revision=1,
            reviewer_latex=corrected,
        ),
        document_root=root,
    )

    assert appended.revision.revision == 2
    assert appended.revision.schema_version == 3
    assert appended.revision.reviewer_latex == corrected
    assert appended.revision.reviewer_latex != attempt.proposed_latex
    assert appended.revision.assistance_proposal_sha256 == attempt.proposal_sha256
    assert appended.revision.obsidian_markdown == f"$$\n{corrected}\n$$"
    assert (
        _review_root(tmp_path) / "human/revision-0001/decision.json"
    ).read_bytes() == legacy_decision
    assert (
        _review_root(tmp_path) / "human/revision-0001/manifest.json"
    ).read_bytes() == legacy_manifest


def test_delimited_proposal_remains_immutable_but_only_body_can_be_accepted(
    tmp_path: Path,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = AssistedEquationAttempt.create(
        binding=binding,
        method="actual-proposal-shape-fixture",
        proposed_latex=r"$E = mc^2$",
    )
    publish_assisted_equation_attempt(attempt, document_root=root)
    legacy_decision, legacy_manifest = _write_legacy_schema_2_revision(
        tmp_path,
        binding,
        attempt.proposal_sha256,
    )

    legacy = load_latest_human_equation_revision(binding, document_root=root)
    assert legacy is not None
    assert legacy.schema_version == 2
    with pytest.raises(EquationReviewError, match="canonical math body"):
        _request(
            binding,
            attempt.proposal_sha256,
            expected_previous_revision=1,
            reviewer_latex=attempt.proposed_latex,
        )

    accepted = append_human_equation_revision(
        _request(
            binding,
            attempt.proposal_sha256,
            expected_previous_revision=1,
            reviewer_latex=r"E = mc^2",
        ),
        document_root=root,
    )

    assert accepted.revision.obsidian_markdown == "$$\nE = mc^2\n$$"
    assert "$$\n$" not in accepted.revision.obsidian_markdown
    assert (
        _review_root(tmp_path) / "assisted/attempt-0001/proposal.txt"
    ).read_text() == (r"$E = mc^2$")
    assert (
        _review_root(tmp_path) / "human/revision-0001/decision.json"
    ).read_bytes() == legacy_decision
    assert (
        _review_root(tmp_path) / "human/revision-0001/manifest.json"
    ).read_bytes() == legacy_manifest


@pytest.mark.parametrize(
    "reviewer_latex",
    (
        "",
        "x" * 100_001,
        "\ud800",
        " E = mc^2",
        "E = mc^2 ",
        "E\r+1",
        "E\r\n+1",
        "e\u0301 = 1",
        "$E = mc^2$",
        "$$E = mc^2$$",
    ),
)
def test_acceptance_rejects_invalid_reviewer_latex(
    tmp_path: Path,
    reviewer_latex: str,
) -> None:
    _, binding = _document_root(tmp_path)

    with pytest.raises(EquationReviewError):
        EquationRenderConfirmation.create(
            renderer_id="mathjax",
            renderer_version="3.2.2",
            reviewer_latex=reviewer_latex,
            display_mode=EquationDisplayMode.DISPLAY,
        )


def test_canonical_body_preserves_internal_whitespace_newlines_and_escaped_dollar(
    tmp_path: Path,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)
    body = "\\text{coût: \\$5}  +\n x"

    result = append_human_equation_revision(
        _request(
            binding,
            attempt.proposal_sha256,
            reviewer_latex=body,
        ),
        document_root=root,
    )

    assert result.revision.reviewer_latex == body
    assert result.revision.obsidian_markdown == f"$$\n{body}\n$$"
    assert (
        load_latest_human_equation_revision(
            binding,
            document_root=root,
        )
        == result.revision
    )


def test_acceptance_rejects_text_changed_after_render(tmp_path: Path) -> None:
    _, binding = _document_root(tmp_path)
    rendered = EquationRenderConfirmation.create(
        renderer_id="mathjax",
        renderer_version="3.2.2",
        reviewer_latex=r"E = mc^2",
        display_mode=EquationDisplayMode.DISPLAY,
    )

    with pytest.raises(EquationReviewError, match="changed after render"):
        _request(
            binding,
            "a" * 64,
            reviewer_latex=r"E = mc^{2}",
            render_confirmation=rendered,
        )


def test_malformed_accepted_representation_fails_closed(tmp_path: Path) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)
    append_human_equation_revision(
        _request(binding, attempt.proposal_sha256),
        document_root=root,
    )
    markdown = _review_root(tmp_path) / "human/revision-0001/obsidian-markdown.md"
    markdown.write_text("$silently divergent$", encoding="utf-8")

    with pytest.raises(EquationReviewPublicationError, match="history"):
        load_latest_human_equation_revision(binding, document_root=root)
    with pytest.raises(EquationReviewPublicationError, match="history"):
        append_human_equation_revision(
            _request(
                binding,
                None,
                disposition=EquationReviewDisposition.REJECT_CANDIDATE,
                expected_previous_revision=1,
            ),
            document_root=root,
        )


def test_replay_rejects_internally_consistent_delimited_reviewer_source(
    tmp_path: Path,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)
    append_human_equation_revision(
        _request(binding, attempt.proposal_sha256),
        document_root=root,
    )
    revision_root = _review_root(tmp_path) / "human/revision-0001"
    reviewer_latex = b"$E = mc^2$"
    obsidian_markdown = b"$$\n$E = mc^2$\n$$"
    reviewer_sha256 = hashlib.sha256(reviewer_latex).hexdigest()
    markdown_sha256 = hashlib.sha256(obsidian_markdown).hexdigest()
    decision_value = json.loads((revision_root / "decision.json").read_bytes())
    decision_value["reviewer_latex_sha256"] = reviewer_sha256
    decision_value["obsidian_markdown_sha256"] = markdown_sha256
    decision_value["render_confirmation"]["rendered_reviewer_latex_sha256"] = (
        reviewer_sha256
    )
    decision_value["render_confirmation"]["rendered_obsidian_markdown_sha256"] = (
        markdown_sha256
    )
    identity = {
        key: value
        for key, value in decision_value.items()
        if key not in {"recorded_at_utc", "revision_id"}
    }
    decision_value["revision_id"] = (
        "equation-human-revision:sha256:"
        f"{hashlib.sha256(_canonical(identity)).hexdigest()}"
    )
    decision = _canonical(decision_value)
    manifest = _canonical(
        {
            **decision_value,
            "artifact_files": [
                {
                    "byte_size": len(decision),
                    "relative_path": "decision.json",
                    "sha256": hashlib.sha256(decision).hexdigest(),
                },
                {
                    "byte_size": len(obsidian_markdown),
                    "relative_path": "obsidian-markdown.md",
                    "sha256": markdown_sha256,
                },
                {
                    "byte_size": len(reviewer_latex),
                    "relative_path": "reviewer-latex.txt",
                    "sha256": reviewer_sha256,
                },
            ],
            "status": "human-reviewed",
        }
    )
    (revision_root / "reviewer-latex.txt").write_bytes(reviewer_latex)
    (revision_root / "obsidian-markdown.md").write_bytes(obsidian_markdown)
    (revision_root / "decision.json").write_bytes(decision)
    (revision_root / "manifest.json").write_bytes(manifest)

    with pytest.raises(EquationReviewPublicationError, match="history"):
        load_latest_human_equation_revision(binding, document_root=root)


def test_recorded_time_does_not_change_stable_revision_identity(
    tmp_path: Path,
) -> None:
    first_root, first_binding = _document_root(tmp_path / "first")
    second_root, second_binding = _document_root(tmp_path / "second")
    first_attempt = _attempt(first_binding)
    second_attempt = _attempt(second_binding)
    publish_assisted_equation_attempt(first_attempt, document_root=first_root)
    publish_assisted_equation_attempt(second_attempt, document_root=second_root)

    first = append_human_equation_revision(
        _request(first_binding, first_attempt.proposal_sha256),
        document_root=first_root,
    ).revision
    second = append_human_equation_revision(
        _request(
            second_binding,
            second_attempt.proposal_sha256,
            recorded_at=_RECORDED_AT + timedelta(days=1),
        ),
        document_root=second_root,
    ).revision

    assert first.revision_id == second.revision_id
    assert first.recorded_at_utc != second.recorded_at_utc


def test_human_history_orders_by_revision_not_recorded_time(
    tmp_path: Path,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)
    first = append_human_equation_revision(
        _request(binding, attempt.proposal_sha256),
        document_root=root,
    )
    first_path = _review_root(tmp_path) / "human/revision-0001/decision.json"
    first_bytes = first_path.read_bytes()

    second = append_human_equation_revision(
        _request(
            binding,
            None,
            disposition=EquationReviewDisposition.REVISION_REQUIRED,
            note="The displayed region needs a corrected transcription.",
            recorded_at=_RECORDED_AT - timedelta(days=1),
            expected_previous_revision=1,
        ),
        document_root=root,
    )

    assert first.revision.revision == 1
    assert second.revision.revision == 2
    assert second.revision.recorded_at_utc < first.revision.recorded_at_utc
    assert (
        load_latest_human_equation_revision(
            binding,
            document_root=root,
        )
        == second.revision
    )
    assert first_path.read_bytes() == first_bytes
    second_root = _review_root(tmp_path) / "human/revision-0002"
    assert (second_root / "manifest.json").is_file()
    assert not (second_root / "reviewer-latex.txt").exists()
    assert not (second_root / "obsidian-markdown.md").exists()


@pytest.mark.parametrize("mutation", ("delete", "corrupt"))
def test_all_historical_assisted_references_are_revalidated(
    tmp_path: Path,
    mutation: str,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)
    append_human_equation_revision(
        _request(binding, attempt.proposal_sha256),
        document_root=root,
    )
    append_human_equation_revision(
        _request(
            binding,
            None,
            disposition=EquationReviewDisposition.REVISION_REQUIRED,
            note="Later unassisted revision.",
            recorded_at=_RECORDED_AT + timedelta(minutes=1),
            expected_previous_revision=1,
        ),
        document_root=root,
    )
    proposal = _review_root(tmp_path) / "assisted/attempt-0001/proposal.txt"
    if mutation == "delete":
        proposal.unlink()
    else:
        proposal.write_text("corrupt proposal")

    with pytest.raises(EquationReviewPublicationError, match="history"):
        load_latest_human_equation_revision(binding, document_root=root)
    with pytest.raises(EquationReviewPublicationError, match="history"):
        append_human_equation_revision(
            _request(
                binding,
                None,
                disposition=EquationReviewDisposition.REJECT_CANDIDATE,
                note="A third unassisted revision must not hide corruption.",
                recorded_at=_RECORDED_AT + timedelta(minutes=2),
                expected_previous_revision=2,
            ),
            document_root=root,
        )


@pytest.mark.parametrize(
    ("proposal", "method"),
    (
        (b"", "synthetic-method"),
        (b"\xff", "synthetic-method"),
        (b"x" * 100_001, "synthetic-method"),
        (b"x", "m" * 501),
    ),
)
def test_rejects_loaded_assisted_artifacts_outside_creation_contract(
    tmp_path: Path,
    proposal: bytes,
    method: str,
) -> None:
    root, binding = _document_root(tmp_path)
    publish_assisted_equation_attempt(_attempt(binding), document_root=root)
    proposal_sha256 = _replace_assisted_attempt(
        tmp_path,
        binding,
        proposal=proposal,
        method=method,
    )

    with pytest.raises(EquationReviewPublicationError, match="history"):
        append_human_equation_revision(
            _request(binding, proposal_sha256),
            document_root=root,
        )


def test_rejects_stale_evidence_proposal_and_revision(
    tmp_path: Path,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)

    with pytest.raises(EquationReviewEvidenceMismatch):
        append_human_equation_revision(
            _request(binding, "f" * 64),
            document_root=root,
        )
    with pytest.raises(EquationReviewEvidenceMismatch):
        append_human_equation_revision(
            _request(
                replace(binding, candidate_evidence_sha256="e" * 64),
                attempt.proposal_sha256,
            ),
            document_root=root,
        )

    append_human_equation_revision(
        _request(binding, attempt.proposal_sha256),
        document_root=root,
    )
    with pytest.raises(EquationReviewStaleRevision):
        append_human_equation_revision(
            _request(
                binding,
                attempt.proposal_sha256,
                note="Different stale decision.",
            ),
            document_root=root,
        )


def test_rejects_forged_minimal_completion_manifest(tmp_path: Path) -> None:
    root, binding = _document_root(tmp_path)
    (tmp_path / _DOCUMENT / "document-manifest.json").write_bytes(
        _canonical(
            {
                "document_key": binding.document_id,
                "source_sha256": binding.source_sha256,
                "status": "deterministic-complete",
            }
        )
    )

    with pytest.raises(EquationReviewEvidenceMismatch, match="completion manifest"):
        publish_assisted_equation_attempt(_attempt(binding), document_root=root)


def test_rejects_candidate_files_absent_from_package_inventory(
    tmp_path: Path,
) -> None:
    root, binding = _document_root(tmp_path)
    candidate_id = "pizzi2020:eq:unlisted"
    candidate_root = (
        tmp_path
        / _DOCUMENT
        / "content/equations/regions"
        / equation_candidate_artifact_key(candidate_id)
    )
    image = b"\x89PNG\r\n\x1a\nunlisted-region"
    image_sha256 = hashlib.sha256(image).hexdigest()
    deterministic = _canonical(
        {
            "candidate": {
                "candidate_id": candidate_id,
                "rendered_region": {"content_sha256": image_sha256},
            },
            "document_key": _DOCUMENT,
            "status": "deterministic-proposal",
        }
    )
    (candidate_root / "source").mkdir(parents=True)
    (candidate_root / "deterministic").mkdir()
    (candidate_root / "source/image.png").write_bytes(image)
    (candidate_root / "source/manifest.json").write_bytes(
        _canonical({"candidate_id": candidate_id})
    )
    (candidate_root / "deterministic/manifest.json").write_bytes(deterministic)
    unlisted_binding = replace(
        binding,
        candidate_id=candidate_id,
        candidate_evidence_sha256=hashlib.sha256(deterministic).hexdigest(),
        region_image_sha256=image_sha256,
    )

    with pytest.raises(EquationReviewEvidenceMismatch, match="package inventory"):
        publish_assisted_equation_attempt(
            _attempt(unlisted_binding),
            document_root=root,
        )
    assert not (candidate_root / "assisted").exists()


def test_rejects_different_existing_and_partial_outputs(tmp_path: Path) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)

    with pytest.raises(EquationReviewPublicationError, match="different"):
        publish_assisted_equation_attempt(
            AssistedEquationAttempt.create(
                binding=binding,
                method=attempt.method,
                proposed_latex=r"E = m c^2",
            ),
            document_root=root,
        )

    human = _review_root(tmp_path) / "human/revision-0001"
    human.mkdir(parents=True)
    (human / "decision.json").write_text("partial")
    with pytest.raises(EquationReviewPublicationError, match="partial"):
        append_human_equation_revision(
            _request(binding, attempt.proposal_sha256),
            document_root=root,
        )


def test_completion_manifest_is_written_last_and_partial_is_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, binding = _document_root(tmp_path)
    original = AuthorizedRoot.write_bytes

    def failing_manifest_write(
        authorized_root: AuthorizedRoot,
        relative: str | PurePosixPath,
        content: bytes,
        *,
        replace: bool,
    ) -> Path:
        path = PurePosixPath(relative)
        if path == PurePosixPath("manifest.json"):
            assert authorized_root.state("proposal.txt") == "regular"
            raise OSError("synthetic manifest failure")
        return original(authorized_root, path, content, replace=replace)

    monkeypatch.setattr(AuthorizedRoot, "write_bytes", failing_manifest_write)
    with pytest.raises(OSError, match="synthetic manifest failure"):
        publish_assisted_equation_attempt(_attempt(binding), document_root=root)
    monkeypatch.undo()

    attempt_root = _review_root(tmp_path) / "assisted/attempt-0001"
    assert (attempt_root / "proposal.txt").is_file()
    assert not (attempt_root / "manifest.json").exists()
    with pytest.raises(EquationReviewPublicationError, match="partial"):
        publish_assisted_equation_attempt(_attempt(binding), document_root=root)


def test_rejects_invalid_time_and_unbound_acceptance(tmp_path: Path) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)

    with pytest.raises(EquationReviewError, match="timezone-aware UTC"):
        _request(binding, attempt.proposal_sha256, recorded_at=datetime(2026, 1, 1))
    with pytest.raises(EquationReviewError, match="timezone-aware UTC"):
        _request(
            binding,
            attempt.proposal_sha256,
            recorded_at=datetime(
                2026,
                1,
                1,
                tzinfo=timezone(timedelta(hours=1)),
            ),
        )
    with pytest.raises(EquationReviewError, match="requires"):
        _request(binding, None)


@pytest.mark.parametrize("race_window", ("state", "create"))
@pytest.mark.parametrize("same_revision", (True, False))
def test_classifies_completed_revision_races(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    race_window: str,
    same_revision: bool,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)
    request = _request(binding, attempt.proposal_sha256)
    competing = (
        _request(
            binding,
            attempt.proposal_sha256,
            recorded_at=_RECORDED_AT + timedelta(minutes=5),
        )
        if same_revision
        else _request(
            binding,
            attempt.proposal_sha256,
            note="Different concurrent decision.",
            recorded_at=_RECORDED_AT + timedelta(minutes=5),
        )
    )
    triggered = False

    if race_window == "state":
        original_state = AuthorizedRoot.state

        def racing_state(
            authorized_root: AuthorizedRoot,
            relative: str | PurePosixPath,
        ) -> str:
            nonlocal triggered
            path = PurePosixPath(relative)
            if path.name == "revision-0001" and not triggered:
                triggered = True
                append_human_equation_revision(competing, document_root=root)
            return original_state(authorized_root, path)

        monkeypatch.setattr(AuthorizedRoot, "state", racing_state)
    else:
        original_create = AuthorizedRoot.create_directory

        def racing_create(
            authorized_root: AuthorizedRoot,
            relative: str | PurePosixPath,
        ) -> AuthorizedRoot:
            nonlocal triggered
            path = PurePosixPath(relative)
            if path.name == "revision-0001" and not triggered:
                triggered = True
                append_human_equation_revision(competing, document_root=root)
                raise FileExistsError(authorized_root.child_path(path))
            return original_create(authorized_root, path)

        monkeypatch.setattr(AuthorizedRoot, "create_directory", racing_create)

    if same_revision:
        result = append_human_equation_revision(request, document_root=root)
        assert result.action is EquationReviewPublicationAction.UNCHANGED
        assert result.revision.note == request.note
        assert result.revision.recorded_at_utc == competing.recorded_at_utc
        assert result.revision.recorded_at_utc != request.recorded_at_utc
    else:
        with pytest.raises(EquationReviewConcurrencyError, match="different"):
            append_human_equation_revision(request, document_root=root)
    assert triggered


def test_create_race_with_partial_revision_remains_publication_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, binding = _document_root(tmp_path)
    attempt = _attempt(binding)
    publish_assisted_equation_attempt(attempt, document_root=root)
    original = AuthorizedRoot.create_directory

    def racing_create(
        authorized_root: AuthorizedRoot,
        relative: str | PurePosixPath,
    ) -> AuthorizedRoot:
        path = PurePosixPath(relative)
        if path.name == "revision-0001":
            original(authorized_root, path)
            raise FileExistsError(authorized_root.child_path(path))
        return original(authorized_root, path)

    monkeypatch.setattr(AuthorizedRoot, "create_directory", racing_create)
    with pytest.raises(EquationReviewPublicationError, match="partial"):
        append_human_equation_revision(
            _request(binding, attempt.proposal_sha256),
            document_root=root,
        )
    assert not (_review_root(tmp_path) / "human/revision-0001/manifest.json").exists()
