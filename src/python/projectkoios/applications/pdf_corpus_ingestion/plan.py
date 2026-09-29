"""Canonical bounded plans for PDF-corpus discovery and ingestion."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any

from projectkoios.references import (
    PDF_CORPUS_DISCOVERY_IO_LIMITS,
    PdfCorpusDiscoveryPlan,
)

from .multimodal import PdfCorpusMultimodalPolicy

PLAN_CONTRACT_ID = "projectkoios.applications.pdf-corpus-ingestion-plan"
PLAN_CONTRACT_VERSION = "0.2.0"
PLAN_SCHEMA_VERSION = 2
PLAN_PRODUCER = "projectkoios-applications==0.1.0.dev0"
REFERENCES_COMPONENT = "projectkoios-references==0.0.0"
REFERENCES_SOURCE_COMMIT = "b7581cb5f8a619883ecd73ed1d9354b85e5f57fd"
REFERENCES_SOURCE_TREE = "41c0165e2d4cb73ca41e2bb2acace1b77b7544d9"
INGESTION_COMPONENT = "projectkoios-ingestion==0.0.0"
INGESTION_SOURCE_COMMIT = "be60640bec4fe15cc88b24161545eb1027ffbd2e"
INGESTION_SOURCE_TREE = "d386a1744f79463fd7cd0b3087ee5fc361e0f7d5"
MAX_TRANCHE_ITEMS = 256
MAX_APPLICATION_PDF_PAGES = 9_000
MAX_OUTPUT_ARTIFACT_FILES = 10_000
MAX_DISCOVERY_PLAN_BYTES = 16_777_216
MAX_APPLICATION_PLAN_BYTES = 20_971_520
MAX_APPLICATION_PDF_BYTES = 50_000_000
MAX_JSON_NESTING = 32
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SLUG = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")


class PdfCorpusPlanError(ValueError):
    """Report malformed or inconsistent application plans."""


class PdfCorpusItemDisposition(StrEnum):
    """Explain whether one deduplicated content identity is in this tranche."""

    DEFERRED_BEFORE_CURSOR = "deferred-before-cursor"
    SELECTED = "selected"
    DEFERRED_AFTER_TRANCHE = "deferred-after-tranche"


@dataclass(frozen=True, slots=True)
class PdfCorpusLocation:
    """Retain one privacy-reduced location for identical PDF bytes."""

    root_alias: str
    relative_path: PurePosixPath
    storage_class: str
    probe_id: str
    observation_id: str

    def __post_init__(self) -> None:
        _text(self.root_alias, "root_alias")
        _relative(self.relative_path, "relative_path")
        if self.storage_class not in {"local", "cloud-backed"}:
            raise PdfCorpusPlanError("storage_class must be explicit")
        _text(self.probe_id, "probe_id")
        _text(self.observation_id, "observation_id")


@dataclass(frozen=True, slots=True)
class PdfCorpusPlanItem:
    """Bind one unique PDF content identity to every observed location."""

    content_id: str
    source_id: str
    sha256: str
    byte_size: int
    pdf_header_valid: bool
    locations: tuple[PdfCorpusLocation, ...]
    selected_location: PdfCorpusLocation
    disposition: PdfCorpusItemDisposition
    staging_path: PurePosixPath
    output_directory: PurePosixPath

    def __post_init__(self) -> None:
        digest = _digest(self.sha256, "sha256")
        if self.content_id != f"pdf-content:sha256:{digest}":
            raise PdfCorpusPlanError("content_id does not match sha256")
        if self.source_id != f"pdf-corpus:sha256:{digest}":
            raise PdfCorpusPlanError("source_id does not match sha256")
        if type(self.byte_size) is not int or self.byte_size <= 0:
            raise PdfCorpusPlanError("byte_size must be positive")
        if self.pdf_header_valid is not True:
            raise PdfCorpusPlanError("processable content must have a PDF header")
        if (
            not self.locations
            or tuple(sorted(self.locations, key=_location_key)) != self.locations
        ):
            raise PdfCorpusPlanError("locations must be nonempty and sorted")
        if len({_location_key(item) for item in self.locations}) != len(self.locations):
            raise PdfCorpusPlanError("locations must be unique")
        if self.selected_location != self.locations[0]:
            raise PdfCorpusPlanError("selected_location must be deterministic")
        if not isinstance(self.disposition, PdfCorpusItemDisposition):
            raise PdfCorpusPlanError("item disposition is invalid")
        _relative(self.staging_path, "staging_path")
        _relative(self.output_directory, "output_directory")
        if self.staging_path.as_posix() != f"objects/{digest[:2]}/{digest}.pdf":
            raise PdfCorpusPlanError("staging_path is not content addressed")
        if self.output_directory.as_posix() != f"objects/{digest[:2]}/{digest}":
            raise PdfCorpusPlanError("output_directory is not content addressed")


@dataclass(frozen=True, slots=True)
class PdfCorpusIngestionPlan:
    """Embed discovery evidence and select one bounded deterministic tranche."""

    plan_id: str
    discovery_plan_id: str
    discovery_plan_sha256: str
    discovery_plan_json: str
    cursor: int
    tranche_size: int
    next_cursor: int | None
    maximum_file_bytes: int
    maximum_pdf_pages: int
    low_text_threshold: int
    multimodal_policy: PdfCorpusMultimodalPolicy
    items: tuple[PdfCorpusPlanItem, ...]
    contract_id: str = PLAN_CONTRACT_ID
    contract_version: str = PLAN_CONTRACT_VERSION
    schema_version: int = PLAN_SCHEMA_VERSION
    producer: str = PLAN_PRODUCER
    references_component: str = REFERENCES_COMPONENT
    references_source_commit: str = REFERENCES_SOURCE_COMMIT
    references_source_tree: str = REFERENCES_SOURCE_TREE
    ingestion_component: str = INGESTION_COMPONENT
    ingestion_source_commit: str = INGESTION_SOURCE_COMMIT
    ingestion_source_tree: str = INGESTION_SOURCE_TREE

    def __post_init__(self) -> None:
        if (
            self.contract_id != PLAN_CONTRACT_ID
            or self.contract_version != PLAN_CONTRACT_VERSION
            or self.schema_version != PLAN_SCHEMA_VERSION
            or self.producer != PLAN_PRODUCER
            or self.references_component != REFERENCES_COMPONENT
            or self.references_source_commit != REFERENCES_SOURCE_COMMIT
            or self.references_source_tree != REFERENCES_SOURCE_TREE
            or self.ingestion_component != INGESTION_COMPONENT
            or self.ingestion_source_commit != INGESTION_SOURCE_COMMIT
            or self.ingestion_source_tree != INGESTION_SOURCE_TREE
        ):
            raise PdfCorpusPlanError("unsupported plan contract or producer")
        _text(self.discovery_plan_id, "discovery_plan_id")
        encoded = self.discovery_plan_json.encode("utf-8")
        if not encoded or len(encoded) > MAX_DISCOVERY_PLAN_BYTES:
            raise PdfCorpusPlanError("embedded discovery plan is empty or too large")
        if hashlib.sha256(encoded).hexdigest() != _digest(
            self.discovery_plan_sha256, "discovery_plan_sha256"
        ):
            raise PdfCorpusPlanError("discovery plan digest is inconsistent")
        try:
            discovery = PdfCorpusDiscoveryPlan.from_json(self.discovery_plan_json)
        except (TypeError, ValueError) as error:
            raise PdfCorpusPlanError(
                "embedded discovery plan is invalid or noncanonical"
            ) from error
        if discovery.plan_id != self.discovery_plan_id:
            raise PdfCorpusPlanError("discovery_plan_id is inconsistent")
        if type(self.cursor) is not int or self.cursor < 0:
            raise PdfCorpusPlanError("cursor must be nonnegative")
        if (
            type(self.tranche_size) is not int
            or not 1 <= self.tranche_size <= MAX_TRANCHE_ITEMS
        ):
            raise PdfCorpusPlanError("tranche_size exceeds the ingestion batch bound")
        discovery_maximum = PDF_CORPUS_DISCOVERY_IO_LIMITS.max_file_bytes
        if (
            type(self.maximum_file_bytes) is not int
            or self.maximum_file_bytes <= 0
            or discovery_maximum is None
            or self.maximum_file_bytes > discovery_maximum
            or self.maximum_file_bytes > MAX_APPLICATION_PDF_BYTES
        ):
            raise PdfCorpusPlanError(
                "maximum_file_bytes exceeds the discovery contract ceiling"
            )
        if (
            type(self.maximum_pdf_pages) is not int
            or not 1 <= self.maximum_pdf_pages <= MAX_APPLICATION_PDF_PAGES
        ):
            raise PdfCorpusPlanError("maximum_pdf_pages exceeds the application bound")
        if type(self.low_text_threshold) is not int or self.low_text_threshold < 0:
            raise PdfCorpusPlanError("low_text_threshold must be nonnegative")
        if (
            not isinstance(self.multimodal_policy, PdfCorpusMultimodalPolicy)
            or self.multimodal_policy.native_text_character_threshold
            != self.low_text_threshold
        ):
            raise PdfCorpusPlanError(
                "multimodal selection threshold must match raw extraction"
            )
        if (
            self.multimodal_policy.maximum_pages_per_document > self.maximum_pdf_pages
            or self.maximum_pdf_pages
            + 3 * self.multimodal_policy.maximum_pages_per_document
            + 2
            > MAX_OUTPUT_ARTIFACT_FILES
        ):
            raise PdfCorpusPlanError(
                "PDF and multimodal page bounds exceed the output-file ceiling"
            )
        if tuple(sorted(self.items, key=lambda item: item.sha256)) != self.items:
            raise PdfCorpusPlanError("items must be sorted by content identity")
        if len({item.sha256 for item in self.items}) != len(self.items):
            raise PdfCorpusPlanError("items must be content-deduplicated")
        selected = tuple(
            index
            for index, item in enumerate(self.items)
            if item.disposition is PdfCorpusItemDisposition.SELECTED
        )
        expected_end = min(self.cursor + self.tranche_size, len(self.items))
        if selected != tuple(range(min(self.cursor, len(self.items)), expected_end)):
            raise PdfCorpusPlanError("selected tranche does not match cursor policy")
        expected_next = expected_end if expected_end < len(self.items) else None
        if self.next_cursor != expected_next:
            raise PdfCorpusPlanError("next_cursor is inconsistent")
        if self.plan_id != _plan_id(self._identity_dict()):
            raise PdfCorpusPlanError("plan_id is inconsistent")
        _validate_discovery_composition(self, discovery)

    @property
    def selected_items(self) -> tuple[PdfCorpusPlanItem, ...]:
        return tuple(
            item
            for item in self.items
            if item.disposition is PdfCorpusItemDisposition.SELECTED
        )

    @classmethod
    def create(
        cls,
        *,
        discovery_plan_id: str,
        discovery_plan_json: str,
        cursor: int,
        tranche_size: int,
        maximum_file_bytes: int,
        maximum_pdf_pages: int,
        low_text_threshold: int,
        multimodal_policy: PdfCorpusMultimodalPolicy,
        items: tuple[PdfCorpusPlanItem, ...],
    ) -> PdfCorpusIngestionPlan:
        digest = hashlib.sha256(discovery_plan_json.encode("utf-8")).hexdigest()
        values: dict[str, object] = {
            "contract_id": PLAN_CONTRACT_ID,
            "contract_version": PLAN_CONTRACT_VERSION,
            "schema_version": PLAN_SCHEMA_VERSION,
            "producer": PLAN_PRODUCER,
            "references_component": REFERENCES_COMPONENT,
            "references_source_commit": REFERENCES_SOURCE_COMMIT,
            "references_source_tree": REFERENCES_SOURCE_TREE,
            "ingestion_component": INGESTION_COMPONENT,
            "ingestion_source_commit": INGESTION_SOURCE_COMMIT,
            "ingestion_source_tree": INGESTION_SOURCE_TREE,
            "discovery_plan_id": discovery_plan_id,
            "discovery_plan_sha256": digest,
            "discovery_plan_json": discovery_plan_json,
            "cursor": cursor,
            "tranche_size": tranche_size,
            "next_cursor": min(cursor + tranche_size, len(items))
            if cursor + tranche_size < len(items)
            else None,
            "maximum_file_bytes": maximum_file_bytes,
            "maximum_pdf_pages": maximum_pdf_pages,
            "low_text_threshold": low_text_threshold,
            "multimodal_policy": multimodal_policy,
            "items": items,
        }
        return cls(plan_id=_plan_id(_identity_value(values)), **values)  # type: ignore[arg-type]

    def _identity_dict(self) -> dict[str, object]:
        return _identity_value(
            {
                "contract_id": self.contract_id,
                "contract_version": self.contract_version,
                "schema_version": self.schema_version,
                "producer": self.producer,
                "references_component": self.references_component,
                "references_source_commit": self.references_source_commit,
                "references_source_tree": self.references_source_tree,
                "ingestion_component": self.ingestion_component,
                "ingestion_source_commit": self.ingestion_source_commit,
                "ingestion_source_tree": self.ingestion_source_tree,
                "discovery_plan_id": self.discovery_plan_id,
                "discovery_plan_sha256": self.discovery_plan_sha256,
                "discovery_plan_json": self.discovery_plan_json,
                "cursor": self.cursor,
                "tranche_size": self.tranche_size,
                "next_cursor": self.next_cursor,
                "maximum_file_bytes": self.maximum_file_bytes,
                "maximum_pdf_pages": self.maximum_pdf_pages,
                "low_text_threshold": self.low_text_threshold,
                "multimodal_policy": self.multimodal_policy,
                "items": self.items,
            }
        )

    def to_json(self) -> str:
        value = self._identity_dict()
        value["plan_id"] = self.plan_id
        return _canonical(value)

    @classmethod
    def from_json(cls, text: str) -> PdfCorpusIngestionPlan:
        _validate_json_envelope(text)
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise PdfCorpusPlanError("plan JSON is malformed") from error
        expected = {
            "contract_id",
            "contract_version",
            "schema_version",
            "producer",
            "references_component",
            "references_source_commit",
            "references_source_tree",
            "ingestion_component",
            "ingestion_source_commit",
            "ingestion_source_tree",
            "discovery_plan_id",
            "discovery_plan_sha256",
            "discovery_plan_json",
            "cursor",
            "tranche_size",
            "next_cursor",
            "maximum_file_bytes",
            "maximum_pdf_pages",
            "low_text_threshold",
            "multimodal_policy",
            "items",
            "plan_id",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise PdfCorpusPlanError("plan fields are incomplete or unknown")
        raw_items = value["items"]
        maximum_sources = PDF_CORPUS_DISCOVERY_IO_LIMITS.max_files
        if (
            not isinstance(raw_items, list)
            or maximum_sources is None
            or len(raw_items) > maximum_sources
        ):
            raise PdfCorpusPlanError("items exceed the discovery source bound")
        location_count = sum(
            len(item.get("locations", ()))
            for item in raw_items
            if isinstance(item, dict) and isinstance(item.get("locations"), list)
        )
        if location_count > maximum_sources:
            raise PdfCorpusPlanError("locations exceed the discovery source bound")
        items = tuple(_item_from_dict(item) for item in raw_items)
        try:
            policy = PdfCorpusMultimodalPolicy.from_dict(value["multimodal_policy"])
        except (TypeError, ValueError) as error:
            raise PdfCorpusPlanError("multimodal policy is invalid") from error
        plan = cls(
            items=items,
            multimodal_policy=policy,
            **{key: value[key] for key in expected - {"items", "multimodal_policy"}},
        )
        if text != plan.to_json():
            raise PdfCorpusPlanError("plan JSON is not canonical")
        return plan


def _location_key(value: PdfCorpusLocation) -> tuple[str, str, str, str, str]:
    return (
        value.root_alias,
        value.relative_path.as_posix(),
        value.storage_class,
        value.probe_id,
        value.observation_id,
    )


def _identity_value(value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    items = result.get("items")
    if isinstance(items, tuple):
        result["items"] = [_item_dict(item) for item in items]
    policy = result.get("multimodal_policy")
    if isinstance(policy, PdfCorpusMultimodalPolicy):
        result["multimodal_policy"] = policy.to_dict()
    return result


def _item_dict(item: PdfCorpusPlanItem) -> dict[str, object]:
    return {
        "byte_size": item.byte_size,
        "content_id": item.content_id,
        "disposition": item.disposition.value,
        "locations": [
            {
                "observation_id": value.observation_id,
                "probe_id": value.probe_id,
                "relative_path": value.relative_path.as_posix(),
                "root_alias": value.root_alias,
                "storage_class": value.storage_class,
            }
            for value in item.locations
        ],
        "output_directory": item.output_directory.as_posix(),
        "pdf_header_valid": item.pdf_header_valid,
        "selected_location": {
            "observation_id": item.selected_location.observation_id,
            "probe_id": item.selected_location.probe_id,
            "relative_path": item.selected_location.relative_path.as_posix(),
            "root_alias": item.selected_location.root_alias,
            "storage_class": item.selected_location.storage_class,
        },
        "sha256": item.sha256,
        "source_id": item.source_id,
        "staging_path": item.staging_path.as_posix(),
    }


def _item_from_dict(value: object) -> PdfCorpusPlanItem:
    expected = {
        "byte_size",
        "content_id",
        "disposition",
        "locations",
        "output_directory",
        "pdf_header_valid",
        "selected_location",
        "sha256",
        "source_id",
        "staging_path",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise PdfCorpusPlanError("item fields are incomplete or unknown")
    locations = value.get("locations")
    selected = value.get("selected_location")
    if not isinstance(locations, list) or not isinstance(selected, dict):
        raise PdfCorpusPlanError("item locations are malformed")
    return PdfCorpusPlanItem(
        content_id=_string(value, "content_id"),
        source_id=_string(value, "source_id"),
        sha256=_string(value, "sha256"),
        byte_size=_integer(value, "byte_size"),
        pdf_header_valid=_boolean(value, "pdf_header_valid"),
        locations=tuple(_location_from_dict(item) for item in locations),
        selected_location=_location_from_dict(selected),
        disposition=PdfCorpusItemDisposition(_string(value, "disposition")),
        staging_path=PurePosixPath(_string(value, "staging_path")),
        output_directory=PurePosixPath(_string(value, "output_directory")),
    )


def _location_from_dict(value: object) -> PdfCorpusLocation:
    expected = {
        "observation_id",
        "probe_id",
        "relative_path",
        "root_alias",
        "storage_class",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise PdfCorpusPlanError("location fields are incomplete or unknown")
    return PdfCorpusLocation(
        root_alias=_string(value, "root_alias"),
        relative_path=PurePosixPath(_string(value, "relative_path")),
        storage_class=_string(value, "storage_class"),
        probe_id=_string(value, "probe_id"),
        observation_id=_string(value, "observation_id"),
    )


def _validate_discovery_composition(
    plan: PdfCorpusIngestionPlan,
    discovery: PdfCorpusDiscoveryPlan,
) -> None:
    grouped: dict[str, list[PdfCorpusLocation]] = {}
    sizes: dict[str, int] = {}
    for source in discovery.processable_sources:
        previous = sizes.setdefault(source.sha256, source.byte_size)
        if previous != source.byte_size:
            raise PdfCorpusPlanError("discovery digest has conflicting sizes")
        grouped.setdefault(source.sha256, []).append(
            PdfCorpusLocation(
                root_alias=source.root_alias,
                relative_path=PurePosixPath(source.relative_path),
                storage_class=source.storage_class.value,
                probe_id=source.probe_id,
                observation_id=source.observation_id,
            )
        )
    digests = tuple(sorted(grouped))
    if tuple(item.sha256 for item in plan.items) != digests:
        raise PdfCorpusPlanError("items do not exactly compose discovery sources")
    end = min(plan.cursor + plan.tranche_size, len(digests))
    for index, item in enumerate(plan.items):
        locations = tuple(sorted(grouped[item.sha256], key=_location_key))
        disposition = (
            PdfCorpusItemDisposition.DEFERRED_BEFORE_CURSOR
            if index < plan.cursor
            else PdfCorpusItemDisposition.SELECTED
            if index < end
            else PdfCorpusItemDisposition.DEFERRED_AFTER_TRANCHE
        )
        if (
            item.byte_size != sizes[item.sha256]
            or item.byte_size > plan.maximum_file_bytes
            or item.locations != locations
            or item.selected_location != locations[0]
            or item.disposition is not disposition
        ):
            raise PdfCorpusPlanError(
                "item does not exactly compose discovery evidence and policy"
            )


def _validate_json_envelope(text: str) -> None:
    if not isinstance(text, str):
        raise PdfCorpusPlanError("plan JSON must be text")
    if len(text.encode("utf-8")) > MAX_APPLICATION_PLAN_BYTES:
        raise PdfCorpusPlanError("plan JSON exceeds its byte limit")
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_NESTING:
                raise PdfCorpusPlanError("plan JSON exceeds its nesting limit")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise PdfCorpusPlanError("plan JSON nesting is malformed")
    if depth != 0 or in_string:
        raise PdfCorpusPlanError("plan JSON nesting is malformed")


def _plan_id(value: dict[str, object]) -> str:
    return (
        "pdf-corpus-ingestion-plan:sha256:"
        + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
    )


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _relative(value: PurePosixPath, name: str) -> None:
    if (
        not isinstance(value, PurePosixPath)
        or value.is_absolute()
        or ".." in value.parts
        or value.as_posix() in {"", "."}
    ):
        raise PdfCorpusPlanError(f"{name} must be a safe relative path")


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PdfCorpusPlanError(f"{name} must be a lowercase SHA-256")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 4096:
        raise PdfCorpusPlanError(f"{name} must be bounded nonempty text")
    return value


def _string(mapping: dict[str, Any], key: str) -> str:
    return _text(mapping.get(key), key)


def _integer(mapping: dict[str, Any], key: str) -> int:
    value = mapping.get(key)
    if type(value) is not int:
        raise PdfCorpusPlanError(f"{key} must be an integer")
    return value


def _boolean(mapping: dict[str, Any], key: str) -> bool:
    value = mapping.get(key)
    if type(value) is not bool:
        raise PdfCorpusPlanError(f"{key} must be a boolean")
    return value
