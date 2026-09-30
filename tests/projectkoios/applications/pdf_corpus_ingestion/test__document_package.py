from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import cast

import pymupdf
import pytest

from projectkoios.applications.pdf_corpus_ingestion import (
    AssistedEquationAttempt,
    EquationDisplayMode,
    EquationRenderConfirmation,
    EquationReviewDisposition,
    EquationReviewEvidenceBinding,
    HumanEquationRevisionRequest,
    append_human_equation_revision,
    project_equation_review_queue,
    publish_assisted_equation_attempt,
)
from projectkoios.applications.pdf_corpus_ingestion.document_package import (
    DOCUMENT_PACKAGE_MANIFEST,
    DeterministicDocumentPackage,
    DocumentPackageArtifact,
    DocumentPackageError,
    DocumentPackagePublicationAction,
    DocumentPackagePublicationError,
    build_deterministic_document_package,
    publish_deterministic_document_package,
)
from projectkoios.ingestion import (
    PdfExtractionArtifactBundle,
    extract_pdf_bytes_artifacts,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass


def _pdf(*, equation: bool = True) -> bytes:
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    page = document.new_page(width=300, height=300)
    text = "E = mc^2 (1)" if equation else "A plain sentence without mathematics."
    page.insert_text((50, 100), text, fontsize=14)
    content = document.tobytes()  # type: ignore[no-untyped-call]
    document.close()  # type: ignore[no-untyped-call]
    return cast(bytes, content)


def _package(
    *, equation: bool = True
) -> tuple[bytes, PdfExtractionArtifactBundle, DeterministicDocumentPackage]:
    content = _pdf(equation=equation)
    extraction = extract_pdf_bytes_artifacts(
        content,
        source_id="reference:pizzi2020",
        locator="corpus:pizzi2020.pdf",
        low_text_character_threshold=0,
        expected_source_sha256=hashlib.sha256(content).hexdigest(),
        expected_source_byte_size=len(content),
        maximum_pages=10,
    )
    package = build_deterministic_document_package(
        document_key="pizzi2020",
        source_pdf=content,
        extraction=extraction,
    )
    return content, extraction, package


def test_builds_document_centric_deterministic_equation_package() -> None:
    content, extraction, package = _package()
    artifacts = {item.relative_path: item for item in package.artifacts}

    assert package.artifacts[-1].relative_path == DOCUMENT_PACKAGE_MANIFEST
    assert artifacts[PurePosixPath("source/document.pdf")].content == content
    assert PurePosixPath("source/manifest.json") in artifacts
    assert PurePosixPath("ingestion/extraction.json") in artifacts
    assert PurePosixPath("ingestion/pages/page-0001.txt") in artifacts
    assert PurePosixPath("ingestion/manifest.json") in artifacts
    ingestion_manifest = json.loads(
        artifacts[PurePosixPath("ingestion/manifest.json")].content
    )
    assert "schema_version" not in ingestion_manifest
    assert ingestion_manifest["extraction_configuration"] == {
        "low_text_character_threshold": 0,
        "maximum_pages": 10,
    }
    assert ingestion_manifest["artifact_limits"] == {
        "max_artifacts": extraction.artifact_limits.max_artifacts,
        "max_page_text_bytes": extraction.artifact_limits.max_page_text_bytes,
        "max_raw_extraction_bytes": (
            extraction.artifact_limits.max_raw_extraction_bytes
        ),
        "max_total_artifact_bytes": (
            extraction.artifact_limits.max_total_artifact_bytes
        ),
    }
    assert PurePosixPath("content/equations/deterministic/detection.json") in artifacts
    assert PurePosixPath("content/equations/index.json") in artifacts
    assert PurePosixPath("content/equations/manifest.json") in artifacts

    index = json.loads(artifacts[PurePosixPath("content/equations/index.json")].content)
    assert len(index["candidates"]) == 1
    candidate = index["candidates"][0]
    assert candidate["kind"] == "display"
    assert candidate["evidence_status"] in {"proposed", "ambiguous"}
    image = artifacts[PurePosixPath(candidate["image_path"])]
    assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert image.sha256 == candidate["image_sha256"]

    completion = json.loads(package.artifacts[-1].content)
    assert completion["status"] == "deterministic-complete"
    assert "schema_version" not in completion
    assert completion["stages"] == {
        "assisted": "not-started",
        "equation_detection": "deterministic-complete",
        "human_review": "not-started",
        "ingestion": "deterministic-complete",
        "transcript": "not-started",
    }
    assert completion["extraction_bundle_id"] == extraction.bundle_id
    assert completion["package_id"] == package.package_id
    assert len(completion["artifact_files"]) == len(package.artifacts) - 1
    application_manifests = (
        PurePosixPath("source/manifest.json"),
        PurePosixPath("ingestion/manifest.json"),
        PurePosixPath("content/equations/index.json"),
        PurePosixPath("content/equations/manifest.json"),
        DOCUMENT_PACKAGE_MANIFEST,
        PurePosixPath(candidate["source_manifest"]),
        PurePosixPath(candidate["deterministic_manifest"]),
    )
    assert all(
        "schema_version" not in json.loads(artifacts[path].content)
        for path in application_manifests
    )
    assert not any(
        "assisted" in item.relative_path.parts
        or "human" in item.relative_path.parts
        or "transcript" in item.relative_path.parts
        for item in package.artifacts
    )


def test_package_projection_is_exactly_repeatable_for_one_extraction() -> None:
    content, extraction, first = _package()

    second = build_deterministic_document_package(
        document_key="pizzi2020",
        source_pdf=content,
        extraction=extraction,
    )

    assert second == first


def test_publishes_document_directory_and_verifies_exact_replay(
    tmp_path: Path,
) -> None:
    _, _, package = _package()
    output = tmp_path / "wannier-seven"
    output.mkdir(mode=0o700)
    root = AuthorizedRoot.existing(
        output,
        label="test corpus output",
        root_alias="test-corpus-output",
        storage_class=RootStorageClass.LOCAL,
    )

    first = publish_deterministic_document_package(package, output_root=root)
    second = publish_deterministic_document_package(package, output_root=root)

    assert first is DocumentPackagePublicationAction.CREATE
    assert second is DocumentPackagePublicationAction.UNCHANGED
    document_root = output / "pizzi2020"
    assert (document_root / "source/document.pdf").is_file()
    assert (document_root / "ingestion/extraction.json").is_file()
    assert (document_root / "content/equations/index.json").is_file()
    assert (document_root / "document-manifest.json").is_file()
    queue = project_equation_review_queue(
        document_root=AuthorizedRoot.existing(
            document_root,
            label="published document package",
            root_alias="test-corpus-output",
            storage_class=RootStorageClass.LOCAL,
        )
    )
    assert len(queue.items) == 1
    assert queue.items[0].display_mode == "DISPLAY"
    assert queue.items[0].native_evidence.raw_text == "E = mc^2 (1)"


def test_review_append_preserves_exact_deterministic_package_replay(
    tmp_path: Path,
) -> None:
    _, _, package = _package()
    artifacts = {item.relative_path: item for item in package.artifacts}
    index = json.loads(artifacts[PurePosixPath("content/equations/index.json")].content)
    candidate = index["candidates"][0]
    candidate_id = candidate["candidate_id"]
    deterministic_path = PurePosixPath(candidate["deterministic_manifest"])
    binding = EquationReviewEvidenceBinding(
        document_id=package.document_key,
        candidate_id=candidate_id,
        source_sha256=package.source_sha256,
        candidate_evidence_sha256=artifacts[deterministic_path].sha256,
        region_image_sha256=candidate["image_sha256"],
    )
    output = tmp_path / "wannier-seven"
    output.mkdir(mode=0o700)
    output_root = AuthorizedRoot.existing(
        output,
        label="test corpus output",
        root_alias="test-corpus-output",
        storage_class=RootStorageClass.LOCAL,
    )
    assert (
        publish_deterministic_document_package(
            package,
            output_root=output_root,
        )
        is DocumentPackagePublicationAction.CREATE
    )
    document_root = AuthorizedRoot.existing(
        output / package.document_key,
        label="published document package",
        root_alias="test-corpus-output",
        storage_class=RootStorageClass.LOCAL,
    )
    attempt = AssistedEquationAttempt.create(
        binding=binding,
        method="synthetic-assistance-v1",
        proposed_latex=r"E = mc^2",
    )
    publish_assisted_equation_attempt(attempt, document_root=document_root)
    append_human_equation_revision(
        HumanEquationRevisionRequest(
            binding=binding,
            disposition=EquationReviewDisposition.ACCEPT_TRANSCRIPTION,
            assistance_proposal_sha256=attempt.proposal_sha256,
            note="Synthetic review fixture.",
            recorded_at_utc=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
            expected_previous_revision=0,
            reviewer_latex=attempt.proposed_latex,
            display_mode=EquationDisplayMode.DISPLAY,
            render_confirmation=EquationRenderConfirmation.create(
                renderer_id="mathjax",
                renderer_version="3.2.2",
                reviewer_latex=attempt.proposed_latex,
                display_mode=EquationDisplayMode.DISPLAY,
            ),
        ),
        document_root=document_root,
    )

    assert (
        publish_deterministic_document_package(
            package,
            output_root=output_root,
        )
        is DocumentPackagePublicationAction.UNCHANGED
    )


def test_deterministic_replay_rejects_named_review_garbage(
    tmp_path: Path,
) -> None:
    _, _, package = _package()
    artifacts = {item.relative_path: item for item in package.artifacts}
    index = json.loads(artifacts[PurePosixPath("content/equations/index.json")].content)
    candidate = index["candidates"][0]
    candidate_root = PurePosixPath(candidate["deterministic_manifest"]).parent.parent
    output = tmp_path / "wannier-seven"
    output.mkdir(mode=0o700)
    output_root = AuthorizedRoot.existing(
        output,
        label="test corpus output",
        root_alias="test-corpus-output",
        storage_class=RootStorageClass.LOCAL,
    )
    publish_deterministic_document_package(package, output_root=output_root)
    attempt_root = (
        output / package.document_key / candidate_root / "assisted/attempt-0001"
    )
    attempt_root.mkdir(parents=True)
    (attempt_root / "proposal.txt").write_bytes(b"not-a-valid-proposal-manifest")
    (attempt_root / "manifest.json").write_bytes(b"not-json")

    with pytest.raises(DocumentPackagePublicationError, match="review extension"):
        publish_deterministic_document_package(package, output_root=output_root)


def test_partial_document_directory_fails_closed(
    tmp_path: Path,
) -> None:
    _, _, package = _package()
    output = tmp_path / "wannier-seven"
    output.mkdir(mode=0o700)
    partial = output / "pizzi2020"
    partial.mkdir(mode=0o700)
    (partial / "partial.txt").write_text("partial")
    root = AuthorizedRoot.existing(
        output,
        label="test corpus output",
        root_alias="test-corpus-output",
        storage_class=RootStorageClass.LOCAL,
    )

    with pytest.raises(DocumentPackagePublicationError, match="incomplete"):
        publish_deterministic_document_package(package, output_root=root)

    assert (partial / "partial.txt").read_text() == "partial"


def test_plain_document_retains_empty_equation_index() -> None:
    _, _, package = _package(equation=False)
    artifacts = {item.relative_path: item for item in package.artifacts}
    index = json.loads(artifacts[PurePosixPath("content/equations/index.json")].content)
    manifest = json.loads(
        artifacts[PurePosixPath("content/equations/manifest.json")].content
    )

    assert index["candidates"] == []
    assert manifest["candidate_count"] == 0
    assert not any("regions" in item.relative_path.parts for item in package.artifacts)


@pytest.mark.parametrize(
    "document_key",
    ("", "../escape", "pizzi 2020", "/absolute", "pizzi2020/other"),
)
def test_rejects_unsafe_document_keys(document_key: str) -> None:
    content, extraction, _ = _package()

    with pytest.raises(DocumentPackageError, match="document_key"):
        build_deterministic_document_package(
            document_key=document_key,
            source_pdf=content,
            extraction=extraction,
        )


def test_rejects_source_bytes_that_do_not_match_extraction() -> None:
    content, extraction, _ = _package()

    with pytest.raises(DocumentPackageError, match="do not match"):
        build_deterministic_document_package(
            document_key="pizzi2020",
            source_pdf=content + b"changed",
            extraction=extraction,
        )


def test_artifact_rejects_path_escape_and_mutable_content() -> None:
    with pytest.raises(DocumentPackageError, match="safe relative"):
        DocumentPackageArtifact.create(
            relative_path="../escape",
            media_type="application/json",
            content=b"{}\n",
        )
    with pytest.raises(TypeError, match="immutable bytes"):
        DocumentPackageArtifact.create(
            relative_path="safe.json",
            media_type="application/json",
            content=bytearray(b"{}\n"),  # type: ignore[arg-type]
        )
