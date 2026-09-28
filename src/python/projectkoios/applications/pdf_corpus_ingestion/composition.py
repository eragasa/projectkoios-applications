"""Compose references-owned discovery into bounded ingestion work."""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

from projectkoios.references import PdfCorpusDiscoveryPlan, PdfSourceObservation

from .multimodal import PdfCorpusMultimodalPolicy
from .plan import (
    MAX_TRANCHE_ITEMS,
    PdfCorpusIngestionPlan,
    PdfCorpusItemDisposition,
    PdfCorpusLocation,
    PdfCorpusPlanError,
    PdfCorpusPlanItem,
)


def compose_pdf_corpus_ingestion_plan(
    discovery: PdfCorpusDiscoveryPlan,
    *,
    cursor: int = 0,
    tranche_size: int = MAX_TRANCHE_ITEMS,
    maximum_file_bytes: int,
    maximum_pdf_pages: int,
    low_text_threshold: int,
    multimodal_policy: PdfCorpusMultimodalPolicy,
) -> PdfCorpusIngestionPlan:
    """Deduplicate exact bytes and retain selected and deferred content."""
    if not isinstance(discovery, PdfCorpusDiscoveryPlan):
        raise TypeError("discovery must be a PdfCorpusDiscoveryPlan")
    if type(cursor) is not int or cursor < 0:
        raise PdfCorpusPlanError("cursor must be nonnegative")
    if type(tranche_size) is not int or not 1 <= tranche_size <= MAX_TRANCHE_ITEMS:
        raise PdfCorpusPlanError("tranche_size exceeds the ingestion batch bound")
    if type(maximum_file_bytes) is not int or maximum_file_bytes <= 0:
        raise PdfCorpusPlanError("maximum_file_bytes must be positive")
    if any(
        item.byte_size > maximum_file_bytes for item in discovery.processable_sources
    ):
        raise PdfCorpusPlanError(
            "processable discovery source exceeds application policy"
        )

    grouped: dict[str, list[PdfSourceObservation]] = defaultdict(list)
    sizes: dict[str, int] = {}
    for source in discovery.processable_sources:
        previous = sizes.setdefault(source.sha256, source.byte_size)
        if previous != source.byte_size:
            raise PdfCorpusPlanError("one digest has conflicting byte sizes")
        grouped[source.sha256].append(source)

    digests = tuple(sorted(grouped))
    end = min(cursor + tranche_size, len(digests))
    items: list[PdfCorpusPlanItem] = []
    for index, digest in enumerate(digests):
        locations = tuple(
            sorted((_location(item) for item in grouped[digest]), key=_location_key)
        )
        if index < cursor:
            disposition = PdfCorpusItemDisposition.DEFERRED_BEFORE_CURSOR
        elif index < end:
            disposition = PdfCorpusItemDisposition.SELECTED
        else:
            disposition = PdfCorpusItemDisposition.DEFERRED_AFTER_TRANCHE
        items.append(
            PdfCorpusPlanItem(
                content_id=f"pdf-content:sha256:{digest}",
                source_id=f"pdf-corpus:sha256:{digest}",
                sha256=digest,
                byte_size=sizes[digest],
                pdf_header_valid=True,
                locations=locations,
                selected_location=locations[0],
                disposition=disposition,
                staging_path=PurePosixPath(f"objects/{digest[:2]}/{digest}.pdf"),
                output_directory=PurePosixPath(f"objects/{digest[:2]}/{digest}"),
            )
        )
    return PdfCorpusIngestionPlan.create(
        discovery_plan_id=discovery.plan_id,
        discovery_plan_json=discovery.to_json(),
        cursor=cursor,
        tranche_size=tranche_size,
        maximum_file_bytes=maximum_file_bytes,
        maximum_pdf_pages=maximum_pdf_pages,
        low_text_threshold=low_text_threshold,
        multimodal_policy=multimodal_policy,
        items=tuple(items),
    )


def _location(source: PdfSourceObservation) -> PdfCorpusLocation:
    return PdfCorpusLocation(
        root_alias=source.root_alias,
        relative_path=PurePosixPath(source.relative_path),
        storage_class=source.storage_class.value,
        probe_id=source.probe_id,
        observation_id=source.observation_id,
    )


def _location_key(value: PdfCorpusLocation) -> tuple[str, str, str, str, str]:
    return (
        value.root_alias,
        value.relative_path.as_posix(),
        value.storage_class,
        value.probe_id,
        value.observation_id,
    )
