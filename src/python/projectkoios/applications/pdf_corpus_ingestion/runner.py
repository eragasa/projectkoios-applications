"""Fail-closed execution for one bounded PDF-corpus tranche."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Protocol

from projectkoios.ingestion import (
    OllamaMultimodalLimitError,
    OllamaMultimodalRegionProcessor,
    OllamaMultimodalRequest,
    OllamaMultimodalResultStatus,
    OllamaMultimodalSelection,
    OllamaTransport,
    PageRegionSelection,
    PdfDependencyUnavailableError,
    PdfRegionRenderLimitError,
    RenderedRegion,
    contract_dict,
    serialize_contract,
)
from projectkoios.ingestion.cli import ingest_pdf_artifacts
from projectkoios.ingestion.models import ExtractionResult
from projectkoios.references import (
    AuthorizedRoot,
    PdfCorpusDiscoveryPlan,
    PdfCorpusRoot,
    PdfSourceObservation,
    RootStorageClass,
    rebind_pdf_source,
)

from .multimodal import PdfCorpusMultimodalPolicy
from .plan import PdfCorpusIngestionPlan, PdfCorpusPlanItem

_MANIFEST = "pdf-corpus-ingestion-manifest.json"
_MAX_OUTPUT_FILES = 10_000
_MAX_MANIFEST_BYTES = 10_000_000
_MAX_MANIFEST_DEPTH = 32
_MAX_MANIFEST_ITEMS = 100_000
_MAX_MANIFEST_STRUCTURAL_TOKENS = 250_000
_MAX_MANIFEST_STRING_BYTES = 8_192


class PdfCorpusRunError(RuntimeError):
    """A tranche failed without concealing already published raw evidence."""

    def __init__(
        self,
        message: str,
        *,
        raw_published_content_ids: tuple[str, ...] = (),
        pending_content_ids: tuple[str, ...] = (),
        temporary_output: str | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_published_content_ids = raw_published_content_ids
        self.pending_content_ids = pending_content_ids
        self.temporary_output = temporary_output


class PdfCorpusRunAction(StrEnum):
    CREATE = "create"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class PdfCorpusPreflightItem:
    content_id: str
    staging_action: PdfCorpusRunAction
    output_action: PdfCorpusRunAction
    existing_multimodal_status: str | None


@dataclass(frozen=True, slots=True)
class PdfCorpusRunReport:
    plan_id: str
    applied: bool
    items: tuple[PdfCorpusPreflightItem, ...]
    raw_published_content_ids: tuple[str, ...]
    raw_complete: bool
    multimodal_complete: bool
    corpus_coverage_status: str
    deferred_content_count: int
    next_cursor: int | None

    def to_json(self) -> str:
        return _canonical(
            {
                "applied": self.applied,
                "corpus_coverage_status": self.corpus_coverage_status,
                "deferred_content_count": self.deferred_content_count,
                "items": [
                    {
                        "content_id": item.content_id,
                        "existing_multimodal_status": (item.existing_multimodal_status),
                        "output_action": item.output_action.value,
                        "staging_action": item.staging_action.value,
                    }
                    for item in self.items
                ],
                "multimodal_complete": self.multimodal_complete,
                "next_cursor": self.next_cursor,
                "plan_id": self.plan_id,
                "raw_complete": self.raw_complete,
                "raw_published_content_ids": list(self.raw_published_content_ids),
            }
        )


@dataclass(frozen=True, slots=True)
class _Prepared:
    item: PdfCorpusPlanItem
    source: PdfSourceObservation
    source_root: AuthorizedRoot
    source_relative: PurePosixPath
    staging_action: PdfCorpusRunAction
    output_action: PdfCorpusRunAction
    existing_status: str | None


class _Ingester(Protocol):
    def __call__(
        self,
        pdf: Path,
        *,
        source_id: str,
        output: Path,
        raw_text_directory: Path | None = None,
        cache_root: Path | None = None,
        locator: str | None = None,
        low_text_threshold: int = 40,
        expected_source_sha256: str | None = None,
        expected_source_byte_size: int | None = None,
    ) -> ExtractionResult: ...


def preflight_pdf_corpus_run(
    plan: PdfCorpusIngestionPlan,
    *,
    roots: tuple[PdfCorpusRoot, ...],
    staging_root_path: Path,
    output_root_path: Path,
) -> tuple[
    tuple[_Prepared, ...],
    AuthorizedRoot,
    AuthorizedRoot,
    PdfCorpusDiscoveryPlan,
]:
    """Rebind all selected sources and inspect all targets without writes."""
    discovery = PdfCorpusDiscoveryPlan.from_json(plan.discovery_plan_json)
    expected_roots = tuple(
        (item.root_alias, item.storage_class.value)
        for item in discovery.root_preflights
    )
    actual_roots = tuple(
        sorted((item.alias, item.storage_class.value) for item in roots)
    )
    if actual_roots != expected_roots:
        raise PdfCorpusRunError("runtime roots do not exactly rebind discovery")

    staging = _local_root(staging_root_path, "PDF corpus staging")
    output = _local_root(output_root_path, "PDF corpus output")
    _require_private(staging.path)
    _require_disjoint(roots, staging, output)
    sources = {item.observation_id: item for item in discovery.processable_sources}
    prepared: list[_Prepared] = []
    for item in plan.selected_items:
        source = sources.get(item.selected_location.observation_id)
        if source is None:
            raise PdfCorpusRunError("selected source is absent from discovery")
        rebound = rebind_pdf_source(source, roots)
        if (source.sha256, source.byte_size) != (item.sha256, item.byte_size):
            raise PdfCorpusRunError("selected source conflicts with plan")
        stage_action = _stage_action(staging, plan, item)
        output_action, status = _output_action(output, plan, item)
        prepared.append(
            _Prepared(
                item,
                source,
                rebound.root,
                rebound.relative_path,
                stage_action,
                output_action,
                status,
            )
        )
    return tuple(prepared), staging, output, discovery


def run_pdf_corpus_ingestion(
    plan: PdfCorpusIngestionPlan,
    *,
    roots: tuple[PdfCorpusRoot, ...],
    staging_root_path: Path,
    output_root_path: Path,
    apply: bool,
    ollama_endpoint: str | None = None,
    ollama_transport: OllamaTransport | None = None,
    ingester: _Ingester = ingest_pdf_artifacts,
) -> PdfCorpusRunReport:
    """Dry-run full preflight or apply one exact bounded tranche."""
    prepared, staging, output, discovery = preflight_pdf_corpus_run(
        plan,
        roots=roots,
        staging_root_path=staging_root_path,
        output_root_path=output_root_path,
    )
    public = tuple(
        PdfCorpusPreflightItem(
            value.item.content_id,
            value.staging_action,
            value.output_action,
            value.existing_status,
        )
        for value in prepared
    )
    deferred_content = len(plan.items) - len(plan.selected_items)
    existing = tuple(
        value.item.content_id
        for value in prepared
        if value.output_action is PdfCorpusRunAction.UNCHANGED
    )
    if not apply:
        return PdfCorpusRunReport(
            plan.plan_id,
            False,
            public,
            existing,
            False,
            False,
            discovery.coverage_status,
            deferred_content,
            plan.next_cursor,
        )

    # No mutation occurs before every source and target passes preflight.
    for value in prepared:
        if value.staging_action is PdfCorpusRunAction.CREATE:
            _parents(staging, value.item.staging_path)
            staging.copy_file_from(
                value.source_root,
                value.source_relative,
                value.item.staging_path,
                max_bytes=plan.maximum_file_bytes,
                expected_sha256=value.item.sha256,
                expected_size=value.item.byte_size,
            )

    published: list[str] = []
    statuses: list[str] = []
    page_budget = plan.multimodal_policy.maximum_pages_per_tranche
    for index, value in enumerate(prepared):
        if value.output_action is PdfCorpusRunAction.UNCHANGED:
            published.append(value.item.content_id)
            statuses.append(value.existing_status or "failed")
            continue
        temporary = _temporary(plan, value.item)
        try:
            status, consumed = _publish(
                plan,
                value,
                staging,
                output,
                page_budget,
                ollama_endpoint,
                ollama_transport,
                ingester,
                discovery.coverage_status,
                deferred_content,
            )
        except Exception as error:
            raise PdfCorpusRunError(
                f"tranche failed after {len(published)} raw publications",
                raw_published_content_ids=tuple(published),
                pending_content_ids=tuple(
                    candidate.item.content_id for candidate in prepared[index:]
                ),
                temporary_output=temporary.as_posix(),
            ) from error
        page_budget -= consumed
        published.append(value.item.content_id)
        statuses.append(status)

    return PdfCorpusRunReport(
        plan.plan_id,
        True,
        public,
        tuple(published),
        len(published) == len(prepared),
        all(status in {"complete", "not-required"} for status in statuses),
        discovery.coverage_status,
        deferred_content,
        plan.next_cursor,
    )


def _publish(
    plan: PdfCorpusIngestionPlan,
    prepared: _Prepared,
    staging: AuthorizedRoot,
    output: AuthorizedRoot,
    page_budget: int,
    endpoint: str | None,
    transport: OllamaTransport | None,
    ingester: _Ingester,
    coverage: str,
    deferred_content: int,
) -> tuple[str, int]:
    item = prepared.item
    _parents(output, item.output_directory)
    temporary_relative = _temporary(plan, item)
    temporary = output.create_directory(temporary_relative)
    _require_private(temporary.path)
    staged_path = staging.child_path(item.staging_path)
    extraction = ingester(
        staged_path,
        source_id=item.source_id,
        output=temporary.path / "raw-extraction.json",
        raw_text_directory=temporary.path / "raw-pages",
        cache_root=None,
        locator=(
            f"{item.selected_location.root_alias}:"
            f"{item.selected_location.relative_path.as_posix()}"
        ),
        low_text_threshold=plan.low_text_threshold,
        expected_source_sha256=item.sha256,
        expected_source_byte_size=item.byte_size,
    )
    unresolved = _unresolved(extraction, plan.multimodal_policy)
    selected = unresolved[: plan.multimodal_policy.maximum_pages_per_document]
    deferred_document = unresolved[len(selected) :]
    selected_for_tranche = selected[:page_budget]
    deferred_tranche = selected[len(selected_for_tranche) :]
    resolution = _resolve(
        plan,
        item,
        staging,
        temporary,
        extraction,
        selected_for_tranche,
        deferred_document,
        deferred_tranche,
        endpoint,
        transport,
    )
    manifest = _manifest_value(
        plan,
        item,
        temporary,
        extraction,
        resolution,
        coverage,
        deferred_content,
    )
    temporary.write_bytes(
        _MANIFEST,
        _canonical(manifest).encode(),
        replace=False,
    )
    output.rename_child(temporary_relative, item.output_directory)
    return str(resolution["status"]), len(selected_for_tranche)


def _resolve(
    plan: PdfCorpusIngestionPlan,
    item: PdfCorpusPlanItem,
    staging: AuthorizedRoot,
    temporary: AuthorizedRoot,
    extraction: ExtractionResult,
    selected: tuple[int, ...],
    deferred_document: tuple[int, ...],
    deferred_tranche: tuple[int, ...],
    endpoint: str | None,
    transport: OllamaTransport | None,
) -> dict[str, object]:
    deferred = bool(deferred_document or deferred_tranche)
    if not selected:
        return _resolution(
            "deferred" if deferred else "not-required",
            selected,
            deferred_document,
            deferred_tranche,
            (),
            (),
            (),
            None,
            None,
        )

    payload = staging.read_bytes(
        item.staging_path,
        max_bytes=plan.maximum_file_bytes,
    )
    renderer = plan.multimodal_policy.renderer()
    regions: list[dict[str, object]] = []
    selections: list[OllamaMultimodalSelection] = []
    failures: list[dict[str, object]] = []
    for page in selected:
        try:
            region = renderer.render(
                extraction.document.source,
                BytesIO(payload),
                (PageRegionSelection.for_full_page(extraction.document.source, page),),
            )[0]
            selection = OllamaMultimodalSelection.from_rendered_region(region)
        except (
            OllamaMultimodalLimitError,
            PdfDependencyUnavailableError,
            PdfRegionRenderLimitError,
            TypeError,
            ValueError,
        ) as error:
            failures.append(
                {
                    "code": _render_failure(error),
                    "exception_class": type(error).__name__,
                    "page_index": page,
                }
            )
            continue
        stem = f"page-{page + 1:04d}-{region.content_sha256}"
        png = PurePosixPath(f"multimodal/regions/{stem}.png")
        evidence = PurePosixPath(f"multimodal/regions/{stem}.json")
        _write(temporary, png, region.content)
        _write(
            temporary,
            evidence,
            _canonical(_region_evidence(region)).encode(),
        )
        regions.append(
            {
                "byte_length": region.byte_length,
                "metadata_file": evidence.as_posix(),
                "page_index": page,
                "png_file": png.as_posix(),
                "png_sha256": region.content_sha256,
                "region_id": region.region_id,
            }
        )
        selections.append(selection)

    if endpoint is None:
        return _resolution(
            "failed" if failures else "pending",
            selected,
            deferred_document,
            deferred_tranche,
            tuple(regions),
            (),
            tuple(failures),
            "render-failed" if failures else "ollama-unconfigured",
            None,
        )

    configuration = plan.multimodal_policy.ollama_configuration(endpoint)
    processor = OllamaMultimodalRegionProcessor(
        configuration=configuration,
        transport=transport,
    )
    result_records: list[dict[str, object]] = []
    complete = not failures
    for index, batch in enumerate(
        _batches(tuple(selections), plan.multimodal_policy), start=1
    ):
        request = OllamaMultimodalRequest.create(batch)
        result = processor.process(request)
        relative = PurePosixPath(f"multimodal/result-{index:04d}.json")
        _write(
            temporary,
            relative,
            (serialize_contract(result) + "\n").encode(),
        )
        result_records.append(
            {
                "cacheable": result.cacheable,
                "file": relative.as_posix(),
                "request_id": request.request_id,
                "result_id": result.result_id,
                "status": result.status.value,
            }
        )
        complete = complete and result.status is OllamaMultimodalResultStatus.COMPLETE
    status = "failed" if not complete else "deferred" if deferred else "complete"
    return _resolution(
        status,
        selected,
        deferred_document,
        deferred_tranche,
        tuple(regions),
        tuple(result_records),
        tuple(failures),
        None if complete else "ollama-result-failed",
        configuration.configuration_digest,
    )


def _resolution(
    status: str,
    selected: tuple[int, ...],
    deferred_document: tuple[int, ...],
    deferred_tranche: tuple[int, ...],
    regions: tuple[dict[str, object], ...],
    results: tuple[dict[str, object], ...],
    failures: tuple[dict[str, object], ...],
    failure_code: str | None,
    configuration_digest: str | None,
) -> dict[str, object]:
    return {
        "configuration_digest": configuration_digest,
        "deferred_document_page_indices": list(deferred_document),
        "deferred_tranche_page_indices": list(deferred_tranche),
        "failure_code": failure_code,
        "regions": list(regions),
        "render_failures": list(failures),
        "results": list(results),
        "selected_page_indices": list(selected),
        "status": status,
        "terminal_incomplete": status not in {"complete", "not-required"},
    }


def _manifest_value(
    plan: PdfCorpusIngestionPlan,
    item: PdfCorpusPlanItem,
    root: AuthorizedRoot,
    extraction: ExtractionResult,
    resolution: dict[str, object],
    coverage: str,
    deferred_content: int,
) -> dict[str, object]:
    identity: dict[str, object] = {
        "artifact_files": _inventory(root, plan.maximum_file_bytes),
        "content_id": item.content_id,
        "corpus_coverage_status": coverage,
        "deferred_content_count": deferred_content,
        "multimodal": resolution,
        "plan_id": plan.plan_id,
        "raw_evidence": {
            "document_id": extraction.document.document_id,
            "manifest_id": extraction.manifest.manifest_id,
            "status": extraction.manifest.status.value,
        },
        "raw_extraction_status": "complete",
        "schema_version": 1,
        "source_byte_size": item.byte_size,
        "source_sha256": item.sha256,
    }
    identity["manifest_id"] = (
        "pdf-corpus-output-manifest:sha256:"
        + hashlib.sha256(_canonical(identity).encode()).hexdigest()
    )
    return identity


def _load_application_manifest(
    root: AuthorizedRoot,
) -> tuple[str, object]:
    try:
        text = root.read_text(_MANIFEST, max_bytes=_MAX_MANIFEST_BYTES)
        _validate_manifest_envelope(text)
        value = json.loads(
            text,
            object_pairs_hook=_unique_manifest_object,
            parse_constant=_reject_json_constant,
        )
        _validate_manifest_value(value)
    except (OverflowError, RecursionError, ValueError) as error:
        raise PdfCorpusRunError("existing output manifest is malformed") from error
    return text, value


def _validate_manifest_envelope(text: str) -> None:
    if len(text.encode("utf-8")) > _MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds its byte limit")
    depth = 0
    structural_tokens = 0
    string_bytes = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            string_bytes += len(character.encode("utf-8"))
            if string_bytes > _MAX_MANIFEST_STRING_BYTES:
                raise ValueError("manifest string exceeds its byte limit")
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
            structural_tokens += 1
            if depth > _MAX_MANIFEST_DEPTH:
                raise ValueError("manifest exceeds its nesting limit")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("manifest nesting is malformed")
        elif character in ",:":
            structural_tokens += 1
        if structural_tokens > _MAX_MANIFEST_STRUCTURAL_TOKENS:
            raise ValueError("manifest exceeds its item limit")
    if depth != 0 or in_string:
        raise ValueError("manifest nesting is malformed")


def _unique_manifest_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("manifest contains duplicate object keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"manifest contains non-finite number: {value}")


def _validate_manifest_value(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    items = 0
    while stack:
        current, depth = stack.pop()
        if depth > _MAX_MANIFEST_DEPTH:
            raise ValueError("manifest exceeds its nesting limit")
        if isinstance(current, dict):
            items += len(current)
            stack.extend((item, depth + 1) for item in current.values())
            stack.extend((key, depth + 1) for key in current)
        elif isinstance(current, list):
            items += len(current)
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str):
            if len(current.encode("utf-8")) > _MAX_MANIFEST_STRING_BYTES:
                raise ValueError("manifest string exceeds its byte limit")
        elif current is not None and not isinstance(current, bool | int | float):
            raise ValueError("manifest contains an unsupported JSON value")
        if items > _MAX_MANIFEST_ITEMS:
            raise ValueError("manifest exceeds its item limit")


def _verify_output(
    root: AuthorizedRoot,
    plan: PdfCorpusIngestionPlan,
    item: PdfCorpusPlanItem,
) -> str:
    if root.state(_MANIFEST) != "regular":
        raise PdfCorpusRunError("existing output has no complete manifest")
    text, value = _load_application_manifest(root)
    expected = {
        "artifact_files",
        "content_id",
        "corpus_coverage_status",
        "deferred_content_count",
        "manifest_id",
        "multimodal",
        "plan_id",
        "raw_evidence",
        "raw_extraction_status",
        "schema_version",
        "source_byte_size",
        "source_sha256",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise PdfCorpusRunError("existing output manifest fields are invalid")
    if text != _canonical(value):
        raise PdfCorpusRunError("existing output manifest is noncanonical")
    identity = dict(value)
    recorded_id = identity.pop("manifest_id")
    expected_id = (
        "pdf-corpus-output-manifest:sha256:"
        + hashlib.sha256(_canonical(identity).encode()).hexdigest()
    )
    if (
        recorded_id != expected_id
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["plan_id"] != plan.plan_id
        or value["content_id"] != item.content_id
        or value["source_sha256"] != item.sha256
        or value["source_byte_size"] != item.byte_size
        or value["raw_extraction_status"] != "complete"
        or value["corpus_coverage_status"]
        != PdfCorpusDiscoveryPlan.from_json(plan.discovery_plan_json).coverage_status
        or type(value["deferred_content_count"]) is not int
        or value["deferred_content_count"] != len(plan.items) - len(plan.selected_items)
        or value["artifact_files"] != _inventory(root, plan.maximum_file_bytes)
    ):
        raise PdfCorpusRunError("existing output is incomplete or different")
    raw = value["raw_evidence"]
    if (
        not isinstance(raw, dict)
        or set(raw) != {"document_id", "manifest_id", "status"}
        or not all(isinstance(raw[name], str) and raw[name] for name in raw)
        or raw["status"] != "completed"
    ):
        raise PdfCorpusRunError("existing raw-evidence summary is invalid")
    resolution = value["multimodal"]
    if not isinstance(resolution, dict) or set(resolution) != {
        "configuration_digest",
        "deferred_document_page_indices",
        "deferred_tranche_page_indices",
        "failure_code",
        "regions",
        "render_failures",
        "results",
        "selected_page_indices",
        "status",
        "terminal_incomplete",
    }:
        raise PdfCorpusRunError("existing resolution summary is invalid")
    status = resolution["status"]
    if not isinstance(status, str) or status not in {
        "complete",
        "deferred",
        "failed",
        "pending",
        "not-required",
    }:
        raise PdfCorpusRunError("existing resolution status is invalid")
    if type(resolution["terminal_incomplete"]) is not bool or resolution[
        "terminal_incomplete"
    ] != (status not in {"complete", "not-required"}):
        raise PdfCorpusRunError("existing resolution completion is inconsistent")
    _verify_resolution_summary(plan, item, resolution, value["artifact_files"])
    return str(status)


def _verify_resolution_summary(
    plan: PdfCorpusIngestionPlan,
    item: PdfCorpusPlanItem,
    value: dict[str, object],
    artifacts: object,
) -> None:
    if item not in plan.selected_items:
        raise PdfCorpusRunError("resolution item is outside the selected tranche")
    inventory = _artifact_inventory(artifacts)
    selected = _indices(value["selected_page_indices"])
    deferred_document = _indices(value["deferred_document_page_indices"])
    deferred_tranche = _indices(value["deferred_tranche_page_indices"])
    pages = selected + deferred_tranche + deferred_document
    policy = plan.multimodal_policy
    if (
        pages != tuple(sorted(set(pages)))
        or len(selected) > policy.maximum_pages_per_tranche
        or len(selected) + len(deferred_tranche) > policy.maximum_pages_per_document
        or (
            deferred_document
            and len(selected) + len(deferred_tranche)
            != policy.maximum_pages_per_document
        )
    ):
        raise PdfCorpusRunError("resolution page partitions exceed policy")

    failures = value["render_failures"]
    regions = value["regions"]
    results = value["results"]
    if (
        not isinstance(failures, list)
        or not isinstance(regions, list)
        or not isinstance(results, list)
    ):
        raise PdfCorpusRunError("resolution evidence lists are invalid")
    region_pages = _verify_regions(regions, inventory)
    failure_pages = _verify_render_failures(failures)
    if region_pages & failure_pages or tuple(sorted(region_pages | failure_pages)) != (
        selected
    ):
        raise PdfCorpusRunError("selected pages are not exactly covered once")
    result_states = _verify_result_summaries(results, inventory)
    if len(result_states) > len(region_pages):
        raise PdfCorpusRunError("Ollama result count exceeds rendered regions")

    status = value["status"]
    failure_code = value["failure_code"]
    configuration = value["configuration_digest"]
    has_deferred = bool(deferred_document or deferred_tranche)
    complete_results = bool(result_states) and all(
        result_status == "complete" and cacheable
        for result_status, cacheable in result_states
    )
    no_evidence = not regions and not failures and not results
    configured = _stable_id(configuration, "ollama-multimodal-configuration")
    if status == "not-required":
        consistent = not pages and no_evidence and configuration is None
        consistent = consistent and failure_code is None
    elif status == "pending":
        consistent = (
            bool(selected)
            and bool(regions)
            and not failures
            and not results
            and configuration is None
            and failure_code == "ollama-unconfigured"
        )
    elif status == "complete":
        consistent = (
            bool(selected)
            and not has_deferred
            and not failures
            and configured
            and complete_results
            and failure_code is None
        )
    elif status == "deferred":
        consistent = has_deferred and not failures and failure_code is None
        if selected:
            consistent = consistent and configured and complete_results
        else:
            consistent = consistent and no_evidence and configuration is None
    else:  # failed
        bad_result = any(
            result_status != "complete" or not cacheable
            for result_status, cacheable in result_states
        )
        render_only = (
            failure_code == "render-failed"
            and bool(failures)
            and not results
            and configuration is None
        )
        processed = (
            failure_code == "ollama-result-failed"
            and configured
            and (bool(failures) or bad_result)
        )
        consistent = bool(selected) and (render_only or processed)
    if not consistent:
        raise PdfCorpusRunError("resolution status and evidence are inconsistent")


def _artifact_inventory(artifacts: object) -> dict[str, dict[str, object]]:
    if not isinstance(artifacts, list):
        raise PdfCorpusRunError("artifact inventory is invalid")
    result: dict[str, dict[str, object]] = {}
    for artifact in artifacts:
        if (
            not isinstance(artifact, dict)
            or set(artifact) != {"byte_size", "relative_path", "sha256"}
            or not isinstance(artifact["relative_path"], str)
            or not _relative_artifact_path(artifact["relative_path"])
            or type(artifact["byte_size"]) is not int
            or artifact["byte_size"] < 0
            or not _digest(artifact["sha256"])
            or artifact["relative_path"] in result
        ):
            raise PdfCorpusRunError("artifact inventory entry is invalid")
        result[artifact["relative_path"]] = artifact
    return result


def _verify_regions(
    values: list[object],
    inventory: dict[str, dict[str, object]],
) -> set[int]:
    pages: list[int] = []
    for region in values:
        expected = {
            "byte_length",
            "metadata_file",
            "page_index",
            "png_file",
            "png_sha256",
            "region_id",
        }
        if not isinstance(region, dict) or set(region) != expected:
            raise PdfCorpusRunError("region summary is invalid")
        page = region["page_index"]
        digest = region["png_sha256"]
        if type(page) is not int or page < 0 or not _digest(digest):
            raise PdfCorpusRunError("region page or digest is invalid")
        stem = f"multimodal/regions/page-{page + 1:04d}-{digest}"
        png = inventory.get(f"{stem}.png")
        metadata = inventory.get(f"{stem}.json")
        if (
            region["png_file"] != f"{stem}.png"
            or region["metadata_file"] != f"{stem}.json"
            or png is None
            or metadata is None
            or type(region["byte_length"]) is not int
            or region["byte_length"] <= 0
            or png["byte_size"] != region["byte_length"]
            or png["sha256"] != digest
            or not _stable_id(region["region_id"], "rendered-region")
        ):
            raise PdfCorpusRunError("region artifact summary is inconsistent")
        pages.append(page)
    if pages != sorted(set(pages)):
        raise PdfCorpusRunError("region summaries are noncanonical")
    return set(pages)


def _verify_render_failures(values: list[object]) -> set[int]:
    pages: list[int] = []
    allowed_codes = {
        "ollama-selection-limit",
        "render-evidence-invalid",
        "render-limit",
        "render-type-invalid",
        "renderer-unavailable",
    }
    for failure in values:
        if not isinstance(failure, dict) or set(failure) != {
            "code",
            "exception_class",
            "page_index",
        }:
            raise PdfCorpusRunError("render-failure summary is invalid")
        page = failure["page_index"]
        exception = failure["exception_class"]
        if (
            type(page) is not int
            or page < 0
            or not isinstance(failure["code"], str)
            or failure["code"] not in allowed_codes
            or not isinstance(exception, str)
            or not 1 <= len(exception) <= 128
            or not exception.replace("_", "a").isalnum()
        ):
            raise PdfCorpusRunError("render-failure summary is invalid")
        pages.append(page)
    if pages != sorted(set(pages)):
        raise PdfCorpusRunError("render-failure summaries are noncanonical")
    return set(pages)


def _verify_result_summaries(
    values: list[object],
    inventory: dict[str, dict[str, object]],
) -> tuple[tuple[str, bool], ...]:
    states: list[tuple[str, bool]] = []
    request_ids: set[str] = set()
    result_ids: set[str] = set()
    for index, result in enumerate(values, start=1):
        relative = f"multimodal/result-{index:04d}.json"
        if (
            not isinstance(result, dict)
            or set(result) != {"cacheable", "file", "request_id", "result_id", "status"}
            or result["file"] != relative
            or relative not in inventory
            or not isinstance(result["status"], str)
            or result["status"] not in {"complete", "failed"}
            or type(result["cacheable"]) is not bool
            or not _stable_id(result["request_id"], "ollama-multimodal-request")
            or not _stable_id(result["result_id"], "ollama-multimodal-result")
            or result["request_id"] in request_ids
            or result["result_id"] in result_ids
        ):
            raise PdfCorpusRunError("Ollama result summary is invalid")
        request_ids.add(result["request_id"])
        result_ids.add(result["result_id"])
        states.append((result["status"], result["cacheable"]))
    return tuple(states)


def _indices(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or any(
        type(item) is not int or item < 0 for item in value
    ):
        raise PdfCorpusRunError("page-index summary is invalid")
    result = tuple(value)
    if result != tuple(sorted(set(result))):
        raise PdfCorpusRunError("page-index summary is noncanonical")
    return result


def _relative_artifact_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _stable_id(value: object, namespace: str) -> bool:
    if not isinstance(value, str):
        return False
    prefix = f"{namespace}:sha256:"
    return value.startswith(prefix) and _digest(value[len(prefix) :])


def _stage_action(
    root: AuthorizedRoot,
    plan: PdfCorpusIngestionPlan,
    item: PdfCorpusPlanItem,
) -> PdfCorpusRunAction:
    state = root.state(item.staging_path)
    if state == "missing":
        return PdfCorpusRunAction.CREATE
    if state != "regular":
        raise PdfCorpusRunError("staging target is not a regular file")
    observed = root.observe_file(
        item.staging_path,
        max_bytes=plan.maximum_file_bytes,
        prefix_bytes=5,
    )
    if (
        observed.sha256 != item.sha256
        or observed.byte_size != item.byte_size
        or observed.prefix != b"%PDF-"
    ):
        raise PdfCorpusRunError("staging target is incomplete or different")
    return PdfCorpusRunAction.UNCHANGED


def _output_action(
    root: AuthorizedRoot,
    plan: PdfCorpusIngestionPlan,
    item: PdfCorpusPlanItem,
) -> tuple[PdfCorpusRunAction, str | None]:
    state = root.state(item.output_directory)
    if state == "missing":
        if root.state(_temporary(plan, item)) != "missing":
            raise PdfCorpusRunError("incomplete temporary output already exists")
        return PdfCorpusRunAction.CREATE, None
    if state != "directory":
        raise PdfCorpusRunError("output target is not a directory")
    child = _local_root(root.child_path(item.output_directory), "existing output")
    return PdfCorpusRunAction.UNCHANGED, _verify_output(child, plan, item)


def _unresolved(
    result: ExtractionResult,
    policy: PdfCorpusMultimodalPolicy,
) -> tuple[int, ...]:
    return tuple(
        sorted(
            {
                span.page_index
                for warning in result.warnings
                if warning.code == policy.selection_warning_code
                for span in warning.source_spans
            }
        )
    )


def _batches(
    selections: tuple[OllamaMultimodalSelection, ...],
    policy: PdfCorpusMultimodalPolicy,
) -> tuple[tuple[OllamaMultimodalSelection, ...], ...]:
    result: list[tuple[OllamaMultimodalSelection, ...]] = []
    current: list[OllamaMultimodalSelection] = []
    byte_count = 0
    pixel_count = 0
    for selection in selections:
        pixels = selection.width_pixels * selection.height_pixels
        if current and (
            len(current) >= policy.request_max_selections
            or byte_count + selection.png_byte_length > policy.max_total_image_bytes
            or pixel_count + pixels > policy.max_total_pixels
        ):
            result.append(tuple(current))
            current, byte_count, pixel_count = [], 0, 0
        current.append(selection)
        byte_count += selection.png_byte_length
        pixel_count += pixels
    if current:
        result.append(tuple(current))
    return tuple(result)


def _region_evidence(region: RenderedRegion) -> dict[str, object]:
    value = contract_dict(region)
    value.pop("content")
    return value


def _render_failure(error: Exception) -> str:
    if isinstance(error, PdfRegionRenderLimitError):
        return "render-limit"
    if isinstance(error, OllamaMultimodalLimitError):
        return "ollama-selection-limit"
    if isinstance(error, PdfDependencyUnavailableError):
        return "renderer-unavailable"
    if isinstance(error, TypeError):
        return "render-type-invalid"
    return "render-evidence-invalid"


def _inventory(root: AuthorizedRoot, max_bytes: int) -> list[dict[str, object]]:
    paths = root.iter_files(
        suffix="",
        recursive=True,
        max_files=_MAX_OUTPUT_FILES,
        max_entries=_MAX_OUTPUT_FILES,
        max_depth=8,
    )
    result: list[dict[str, object]] = []
    for path in paths:
        if path.as_posix() == _MANIFEST:
            continue
        observed = root.observe_file(path, max_bytes=max_bytes)
        result.append(
            {
                "byte_size": observed.byte_size,
                "relative_path": path.as_posix(),
                "sha256": observed.sha256,
            }
        )
    return result


def _write(root: AuthorizedRoot, relative: PurePosixPath, content: bytes) -> None:
    _parents(root, relative)
    root.write_bytes(relative, content, replace=False)


def _parents(root: AuthorizedRoot, relative: PurePosixPath) -> None:
    current = PurePosixPath()
    for part in relative.parts[:-1]:
        current /= part
        state = root.state(current)
        if state == "missing":
            root.create_directory(current)
        elif state != "directory":
            raise PdfCorpusRunError("target parent is not a directory")


def _temporary(
    plan: PdfCorpusIngestionPlan,
    item: PdfCorpusPlanItem,
) -> PurePosixPath:
    plan_digest = plan.plan_id.rsplit(":", 1)[-1]
    return item.output_directory.with_name(f".koios-{item.sha256}-{plan_digest}.tmp")


def _local_root(path: Path, label: str) -> AuthorizedRoot:
    return AuthorizedRoot.existing(
        path,
        label=label,
        root_alias="pdf-corpus-local-runtime",
        storage_class=RootStorageClass.LOCAL,
    )


def _require_private(path: Path) -> None:
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PdfCorpusRunError("staging/temp root must be mode 0700 or stricter")


def _require_disjoint(
    sources: tuple[PdfCorpusRoot, ...],
    staging: AuthorizedRoot,
    output: AuthorizedRoot,
) -> None:
    values = tuple((item.alias, item.path.resolve()) for item in sources) + (
        ("staging", staging.path),
        ("output", output.path),
    )
    for index, (left_name, left) in enumerate(values):
        for right_name, right in values[index + 1 :]:
            if (
                left == right
                or left.is_relative_to(right)
                or right.is_relative_to(left)
            ):
                raise PdfCorpusRunError(
                    f"runtime roots overlap or nest: {left_name!r}, {right_name!r}"
                )


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
