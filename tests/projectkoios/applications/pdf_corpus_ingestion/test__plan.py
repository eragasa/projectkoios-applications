from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from projectkoios.applications.pdf_corpus_ingestion import (
    MAX_APPLICATION_PDF_BYTES,
    MAX_APPLICATION_PDF_PAGES,
    PdfCorpusIngestionPlan,
    PdfCorpusItemDisposition,
    PdfCorpusMultimodalPolicy,
    PdfCorpusPlanError,
    compose_pdf_corpus_ingestion_plan,
)
from projectkoios.references import (
    PDF_CORPUS_DISCOVERY_IO_LIMITS,
    PdfCorpusDiscoveryPlan,
    PdfCorpusRoot,
    RootStorageClass,
    discover_pdf_corpus,
)


def _discover(root: Path) -> PdfCorpusDiscoveryPlan:
    return discover_pdf_corpus((PdfCorpusRoot("corpus", root, RootStorageClass.LOCAL),))


def _compose(
    discovery: PdfCorpusDiscoveryPlan,
    *,
    cursor: int = 0,
    tranche_size: int = 256,
) -> PdfCorpusIngestionPlan:
    maximum = PDF_CORPUS_DISCOVERY_IO_LIMITS.max_file_bytes
    assert maximum is not None and maximum >= MAX_APPLICATION_PDF_BYTES
    policy = PdfCorpusMultimodalPolicy.create(
        native_text_character_threshold=40,
        maximum_pages_per_document=16,
        maximum_pages_per_tranche=64,
        request_max_selections=8,
        expected_ollama_version="0.12.3",
        model_name="example-vision:latest",
        expected_model_digest="1" * 64,
    )
    return compose_pdf_corpus_ingestion_plan(
        discovery,
        cursor=cursor,
        tranche_size=tranche_size,
        maximum_file_bytes=MAX_APPLICATION_PDF_BYTES,
        maximum_pdf_pages=100,
        low_text_threshold=40,
        multimodal_policy=policy,
    )


def test_empty_plan_is_canonical_and_contains_no_absolute_root(
    tmp_path: Path,
) -> None:
    plan = _compose(_discover(tmp_path))

    assert plan.items == ()
    assert plan.selected_items == ()
    assert plan.next_cursor is None
    assert plan.maximum_pdf_pages == 100
    assert str(tmp_path) not in plan.to_json()
    assert PdfCorpusIngestionPlan.from_json(plan.to_json()) == plan


def test_invalid_pdf_header_is_retained_only_in_discovery(
    tmp_path: Path,
) -> None:
    (tmp_path / "invalid.pdf").write_bytes(b"not-a-pdf")
    discovery = _discover(tmp_path)

    plan = _compose(discovery)

    assert len(discovery.source_observations) == 1
    assert discovery.source_observations[0].pdf_header_valid is False
    assert plan.items == ()


def test_identical_bytes_are_deduplicated_with_all_locations(
    tmp_path: Path,
) -> None:
    content = b"%PDF-1.4\nidentical\n"
    (tmp_path / "a.pdf").write_bytes(content)
    (tmp_path / "b.pdf").write_bytes(content)

    plan = _compose(_discover(tmp_path))

    assert len(plan.items) == 1
    assert tuple(
        location.relative_path.as_posix() for location in plan.items[0].locations
    ) == (
        "a.pdf",
        "b.pdf",
    )
    assert plan.items[0].selected_location.relative_path.as_posix() == "a.pdf"


def test_tranche_retains_before_and_after_cursor(
    tmp_path: Path,
) -> None:
    for index in range(4):
        (tmp_path / f"{index}.pdf").write_bytes(b"%PDF-1.4\n" + bytes([index]))

    plan = _compose(_discover(tmp_path), cursor=1, tranche_size=2)

    assert len(plan.items) == 4
    assert (
        tuple(item.disposition for item in plan.items).count(
            PdfCorpusItemDisposition.SELECTED
        )
        == 2
    )
    assert (
        tuple(item.disposition for item in plan.items).count(
            PdfCorpusItemDisposition.DEFERRED_BEFORE_CURSOR
        )
        == 1
    )
    assert (
        tuple(item.disposition for item in plan.items).count(
            PdfCorpusItemDisposition.DEFERRED_AFTER_TRANCHE
        )
        == 1
    )
    assert plan.next_cursor == 3


def test_pdf_page_bound_is_plan_owned_and_bounded(tmp_path: Path) -> None:
    plan = _compose(_discover(tmp_path))

    with pytest.raises(PdfCorpusPlanError, match="maximum_pdf_pages"):
        replace(plan, maximum_pdf_pages=MAX_APPLICATION_PDF_PAGES + 1)
    with pytest.raises(PdfCorpusPlanError, match="output-file ceiling"):
        replace(plan, maximum_pdf_pages=10)


def test_noncanonical_json_is_rejected(tmp_path: Path) -> None:
    plan = _compose(_discover(tmp_path))

    with pytest.raises(PdfCorpusPlanError):
        PdfCorpusIngestionPlan.from_json(plan.to_json().replace("  ", "    "))


def test_self_consistent_invented_location_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "source.pdf").write_bytes(b"%PDF-1.4\nsource\n")
    value = json.loads(_compose(_discover(tmp_path)).to_json())
    value["items"][0]["locations"][0]["relative_path"] = "invented.pdf"
    value["items"][0]["selected_location"]["relative_path"] = "invented.pdf"
    identity = dict(value)
    del identity["plan_id"]
    canonical_identity = (
        json.dumps(identity, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    value["plan_id"] = (
        "pdf-corpus-ingestion-plan:sha256:"
        + hashlib.sha256(canonical_identity.encode("utf-8")).hexdigest()
    )
    malicious = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    with pytest.raises(PdfCorpusPlanError, match="exactly compose"):
        PdfCorpusIngestionPlan.from_json(malicious)


def test_unknown_nested_field_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "source.pdf").write_bytes(b"%PDF-1.4\nsource\n")
    value = json.loads(_compose(_discover(tmp_path)).to_json())
    value["items"][0]["unexpected"] = True

    with pytest.raises(PdfCorpusPlanError, match="unknown"):
        PdfCorpusIngestionPlan.from_json(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
