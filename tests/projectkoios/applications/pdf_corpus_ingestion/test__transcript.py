from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
from typing import cast

import pymupdf
import pytest

from projectkoios.applications.pdf_corpus_ingestion import (
    DOCUMENT_PACKAGE_SCHEMA_VERSION,
    DocumentTranscriptIncompleteError,
    DocumentTranscriptMalformedError,
    DocumentTranscriptStatus,
    DocumentTranscriptUnsupportedPackageError,
    build_deterministic_document_package,
    project_document_transcript,
    publish_deterministic_document_package,
)
from projectkoios.ingestion import extract_pdf_bytes_artifacts
from projectkoios.references import AuthorizedRoot, RootStorageClass

_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures/pdf_corpus_ingestion/document-transcript-cases.json"
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _stable_id(namespace: str, value: object) -> str:
    return f"{namespace}:sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


def _fixture() -> dict[str, object]:
    return cast(dict[str, object], json.loads(_FIXTURE.read_bytes()))


def _pdf(*, title: str | None = "Synthetic Transcript Display") -> bytes:
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    if title is not None:
        document.set_metadata({"title": title})
    first = document.new_page(width=300, height=300)
    first.insert_text((50, 100), "First page exact text.", fontsize=12)
    document.new_page(width=300, height=300)
    third = document.new_page(width=300, height=300)
    third.insert_text((50, 100), "Third page exact text.", fontsize=12)
    third.insert_text((50, 240), "Second native block.", fontsize=12)
    content = document.tobytes()  # type: ignore[no-untyped-call]
    document.close()  # type: ignore[no-untyped-call]
    return cast(bytes, content)


def _document_root(
    tmp_path: Path,
    *,
    title: str | None = "Synthetic Transcript Display",
) -> tuple[AuthorizedRoot, Path]:
    content = _pdf(title=title)
    extraction = extract_pdf_bytes_artifacts(
        content,
        source_id="fixture:synthetic-transcript",
        locator="fixture/synthetic-transcript.pdf",
        low_text_character_threshold=0,
        expected_source_sha256=hashlib.sha256(content).hexdigest(),
        expected_source_byte_size=len(content),
        maximum_pages=3,
    )
    package = build_deterministic_document_package(
        document_key="synthetic-transcript",
        source_pdf=content,
        extraction=extraction,
    )
    output = tmp_path / "document-packages"
    output.mkdir(parents=True)
    output_root = AuthorizedRoot.existing(
        output,
        label="sanitized transcript fixtures",
        root_alias="sanitized-transcript-fixtures",
        storage_class=RootStorageClass.LOCAL,
    )
    publish_deterministic_document_package(package, output_root=output_root)
    document_path = output / package.document_key
    return (
        AuthorizedRoot.existing(
            document_path,
            label="sanitized transcript fixture",
            root_alias="sanitized-transcript-fixture",
            storage_class=RootStorageClass.LOCAL,
        ),
        document_path,
    )


def _rewrite_completion(document: Path) -> None:
    completion_path = document / "document-manifest.json"
    completion = json.loads(completion_path.read_bytes())
    identity = dict(completion)
    identity.pop("package_id")
    completion["package_id"] = _stable_id(
        "document-processing-package",
        identity,
    )
    completion_path.write_bytes(_canonical(completion))


def _rewrite_inventory_entry(document: Path, relative_path: str) -> None:
    completion_path = document / "document-manifest.json"
    completion = json.loads(completion_path.read_bytes())
    content = (document / relative_path).read_bytes()
    for entry in completion["artifact_files"]:
        if entry["relative_path"] == relative_path:
            entry["byte_size"] = len(content)
            entry["sha256"] = hashlib.sha256(content).hexdigest()
            break
    else:
        raise AssertionError(f"missing fixture inventory entry: {relative_path}")
    identity = dict(completion)
    identity.pop("package_id")
    completion["package_id"] = _stable_id(
        "document-processing-package",
        identity,
    )
    completion_path.write_bytes(_canonical(completion))


def test_projects_complete_exact_path_free_automated_transcript(
    tmp_path: Path,
) -> None:
    root, _ = _document_root(tmp_path)
    expected = cast(dict[str, object], _fixture()["complete"])

    first = project_document_transcript(document_root=root)
    second = project_document_transcript(document_root=root)

    assert first == second
    assert first.projection_id == second.projection_id
    assert first.projection_id.startswith("document-transcript:sha256:")
    assert first.document_id == expected["document_id"]
    assert first.display_name == expected["display_name"]
    assert first.status is DocumentTranscriptStatus.AUTOMATED_UNREVIEWED
    assert first.physical_page_count == 3
    assert [page.page_index for page in first.pages] == [0, 1, 2]
    assert [page.physical_page for page in first.pages] == [1, 2, 3]
    assert [page.text for page in first.pages] == expected["page_texts"]
    assert all(page.page_id for page in first.pages)
    assert len({page.page_id for page in first.pages}) == 3
    assert ("title", "Synthetic Transcript Display") in first.metadata
    assert first.metadata == tuple(sorted(first.metadata))
    serialized = json.dumps(asdict(first), ensure_ascii=False, sort_keys=True)
    assert "manifest.json" not in serialized
    assert "ingestion/pages" not in serialized
    assert str(tmp_path) not in serialized
    with pytest.raises(FrozenInstanceError):
        first.pages[0].text = "changed"  # type: ignore[misc]


def test_preserves_exact_empty_physical_page(tmp_path: Path) -> None:
    root, _ = _document_root(tmp_path)

    projection = project_document_transcript(document_root=root)

    assert projection.pages[1].text == ""
    assert projection.pages[1].page_index == 1
    assert projection.pages[1].physical_page == 2


def test_display_name_falls_back_to_document_identity(tmp_path: Path) -> None:
    root, _ = _document_root(tmp_path, title=None)

    projection = project_document_transcript(document_root=root)

    assert projection.display_name == projection.document_id


def test_missing_owner_artifact_is_typed_incomplete_evidence(
    tmp_path: Path,
) -> None:
    root, document = _document_root(tmp_path)
    incomplete = cast(dict[str, str], _fixture()["incomplete"])
    removed = incomplete["remove_artifact"]
    ingestion_path = document / "ingestion/manifest.json"
    ingestion = json.loads(ingestion_path.read_bytes())
    ingestion["artifact_paths"].remove(removed)
    identity = dict(ingestion)
    identity.pop("manifest_id")
    ingestion["manifest_id"] = _stable_id("document-ingestion-manifest", identity)
    ingestion_path.write_bytes(_canonical(ingestion))
    completion_path = document / "document-manifest.json"
    completion = json.loads(completion_path.read_bytes())
    completion["artifact_files"] = [
        entry
        for entry in completion["artifact_files"]
        if entry["relative_path"] != removed
    ]
    (document / removed).unlink()
    ingestion_bytes = ingestion_path.read_bytes()
    for entry in completion["artifact_files"]:
        if entry["relative_path"] == "ingestion/manifest.json":
            entry["byte_size"] = len(ingestion_bytes)
            entry["sha256"] = hashlib.sha256(ingestion_bytes).hexdigest()
    identity = dict(completion)
    identity.pop("package_id")
    completion["package_id"] = _stable_id(
        "document-processing-package",
        identity,
    )
    completion_path.write_bytes(_canonical(completion))

    with pytest.raises(DocumentTranscriptIncompleteError):
        project_document_transcript(document_root=root)


def test_owner_json_is_never_reinterpreted_when_malformed(
    tmp_path: Path,
) -> None:
    root, document = _document_root(tmp_path)
    malformed = cast(dict[str, str], _fixture()["malformed"])
    target = document / malformed["replace_artifact"]
    target.write_bytes(b"{}\n")
    _rewrite_inventory_entry(document, malformed["replace_artifact"])

    with pytest.raises(DocumentTranscriptMalformedError):
        project_document_transcript(document_root=root)


def test_configuration_binding_and_stale_package_bytes_fail_closed(
    tmp_path: Path,
) -> None:
    root, document = _document_root(tmp_path)
    ingestion_path = document / "ingestion/manifest.json"
    ingestion = json.loads(ingestion_path.read_bytes())
    ingestion["extraction_configuration"]["maximum_pages"] = 4
    identity = dict(ingestion)
    identity.pop("manifest_id")
    ingestion["manifest_id"] = _stable_id("document-ingestion-manifest", identity)
    ingestion_path.write_bytes(_canonical(ingestion))
    _rewrite_inventory_entry(document, "ingestion/manifest.json")

    with pytest.raises(DocumentTranscriptMalformedError):
        project_document_transcript(document_root=root)

    fresh_root, fresh_document = _document_root(tmp_path / "fresh")
    page = fresh_document / "ingestion/pages/page-0001.txt"
    page.write_bytes(page.read_bytes() + b"drift")
    with pytest.raises(DocumentTranscriptMalformedError):
        project_document_transcript(document_root=fresh_root)


def test_schema_one_package_is_explicitly_unsupported(tmp_path: Path) -> None:
    root, document = _document_root(tmp_path)
    unsupported = cast(dict[str, int], _fixture()["unsupported"])
    completion_path = document / "document-manifest.json"
    completion = json.loads(completion_path.read_bytes())
    assert completion["schema_version"] == DOCUMENT_PACKAGE_SCHEMA_VERSION
    completion["schema_version"] = unsupported["package_schema_version"]
    completion_path.write_bytes(_canonical(completion))
    _rewrite_completion(document)

    with pytest.raises(DocumentTranscriptUnsupportedPackageError):
        project_document_transcript(document_root=root)


def test_missing_completion_manifest_is_typed_incomplete(tmp_path: Path) -> None:
    root, document = _document_root(tmp_path)
    (document / "document-manifest.json").unlink()

    with pytest.raises(DocumentTranscriptIncompleteError):
        project_document_transcript(document_root=root)
