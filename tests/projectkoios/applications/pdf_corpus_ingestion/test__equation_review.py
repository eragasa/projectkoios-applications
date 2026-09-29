from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

import pytest

from projectkoios.applications.pdf_corpus_ingestion import (
    AssistedEquationAttempt,
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
_REVIEWED_AT = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _document_root(
    tmp_path: Path,
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
                            "kind": "display",
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
        "schema_version": 1,
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
    reviewed_at: datetime = _REVIEWED_AT,
    expected_previous_revision: int = 0,
) -> HumanEquationRevisionRequest:
    return HumanEquationRevisionRequest(
        binding=binding,
        disposition=disposition,
        assistance_proposal_sha256=proposal_sha256,
        note=note,
        reviewed_at_utc=reviewed_at,
        expected_previous_revision=expected_previous_revision,
    )


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
    replay = append_human_equation_revision(request, document_root=root)
    review_root = _review_root(tmp_path)
    decision = json.loads(
        (review_root / "human/revision-0001/decision.json").read_text()
    )
    assistance = json.loads(
        (review_root / "assisted/attempt-0001/manifest.json").read_text()
    )

    assert first.action is EquationReviewPublicationAction.CREATE
    assert replay.action is EquationReviewPublicationAction.UNCHANGED
    assert first.revision == replay.revision
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
    assert decision["updated_at_utc"] == "2026-09-28T12:00:00.000000Z"
    assert assistance["status"] == "automated_unreviewed"


def test_human_revisions_are_monotonic_and_preserve_prior_bytes(
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
            reviewed_at=_REVIEWED_AT + timedelta(minutes=1),
            expected_previous_revision=1,
        ),
        document_root=root,
    )

    assert first.revision.revision == 1
    assert second.revision.revision == 2
    assert (
        load_latest_human_equation_revision(
            binding,
            document_root=root,
        )
        == second.revision
    )
    assert first_path.read_bytes() == first_bytes
    assert (_review_root(tmp_path) / "human/revision-0002/manifest.json").is_file()


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
            reviewed_at=_REVIEWED_AT + timedelta(minutes=1),
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
                reviewed_at=_REVIEWED_AT + timedelta(minutes=2),
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
        _request(binding, attempt.proposal_sha256, reviewed_at=datetime(2026, 1, 1))
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
        request
        if same_revision
        else _request(
            binding,
            attempt.proposal_sha256,
            note="Different concurrent decision.",
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
