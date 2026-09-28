from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from projectkoios.applications.pdf_corpus_ingestion.roots import (
    PdfCorpusRootSpecificationError,
    parse_pdf_corpus_roots,
)
from projectkoios.references import (
    PdfSkipReason,
    PlaceholderProbeSupport,
    PlaceholderStatus,
    RootStorageClass,
    discover_pdf_corpus,
)


class _Probe:
    probe_id = "test-cloud-metadata-v1"

    def support(self, *, root_alias: str) -> PlaceholderProbeSupport:
        del root_alias
        return PlaceholderProbeSupport.SUPPORTED

    def observe(
        self,
        *,
        root_alias: str,
        relative_path: PurePosixPath,
    ) -> PlaceholderStatus:
        del root_alias, relative_path
        return PlaceholderStatus.ORDINARY_FILE


def test_local_root_requires_explicit_class_and_absolute_path(
    tmp_path: Path,
) -> None:
    roots = parse_pdf_corpus_roots((f"local:papers={tmp_path}",))
    assert roots[0].storage_class is RootStorageClass.LOCAL
    assert roots[0].placeholder_probe is None

    with pytest.raises(PdfCorpusRootSpecificationError, match="absolute"):
        parse_pdf_corpus_roots(("local:papers=relative",))


def test_cloud_root_off_darwin_yields_incomplete_evidence_without_touch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_was_constructed = False

    def forbidden_probe(path: Path) -> _Probe:
        nonlocal probe_was_constructed
        probe_was_constructed = True
        raise AssertionError(f"probe touched {path}")

    def forbidden_stat(*args: object, **kwargs: object) -> object:
        raise AssertionError(f"path touched: {args!r} {kwargs!r}")

    monkeypatch.setattr(
        "projectkoios.references.pdf_corpus.os.stat",
        forbidden_stat,
    )
    root = parse_pdf_corpus_roots(
        (f"cloud-backed:papers={tmp_path / 'must-not-be-touched'}",),
        platform="linux",
        probe_factory=forbidden_probe,
    )[0]
    plan = discover_pdf_corpus((root,))

    assert not probe_was_constructed
    assert root.placeholder_probe is None
    assert plan.coverage_status == "incomplete"
    assert plan.source_observations == ()
    assert tuple(item.reason for item in plan.skipped_observations) == (
        PdfSkipReason.UNSUPPORTED_PLATFORM,
    )

    with pytest.raises(PdfCorpusRootSpecificationError, match="cloud-backed"):
        parse_pdf_corpus_roots((f"cloud:papers={tmp_path}",), platform="darwin")


def test_nested_local_and_cloud_roots_fail_before_probe(
    tmp_path: Path,
) -> None:
    probe_was_constructed = False

    def forbidden_probe(path: Path) -> _Probe:
        nonlocal probe_was_constructed
        probe_was_constructed = True
        return _Probe()

    nested = tmp_path / "Library" / "CloudStorage"
    with pytest.raises(PdfCorpusRootSpecificationError, match="overlap or nest"):
        parse_pdf_corpus_roots(
            (
                f"local:home={tmp_path}",
                f"cloud-backed:cloud={nested}",
            ),
            platform="darwin",
            probe_factory=forbidden_probe,
        )
    assert not probe_was_constructed
    assert not nested.exists()


def test_cloud_root_uses_explicit_probe_on_darwin(tmp_path: Path) -> None:
    roots = parse_pdf_corpus_roots(
        (f"cloud-backed:papers={tmp_path}",),
        platform="darwin",
        probe_factory=lambda path: _Probe(),
    )
    assert roots[0].storage_class is RootStorageClass.CLOUD_BACKED
    assert roots[0].placeholder_probe is not None
