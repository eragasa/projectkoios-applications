"""Path-free contracts for synchronous citation-document ingestion."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import final

from projectkoios.base import (
    DataObjectActionRequest,
    DataObjectActionResult,
    DataObjectModel,
)
from projectkoios.ingestion import (
    PdfExtractionArtifactLimits,
    PdfExtractionConfiguration,
)
from projectkoios.references.citation_document import (
    CITATION_SOURCE_DOCUMENT_LINK_CONTRACT_ID,
    CITATION_SOURCE_DOCUMENT_LINKER_NAME,
    CitationDocumentProjectionResult,
    CitationSourceDocumentDescriptor,
    CitationSourceDocumentLink,
    CitationSourceDocumentLinkRequest,
    CitationSourceDocumentLinkResult,
    CitationSourceDocumentObservation,
)

CITATION_DOCUMENT_RECEIPT_CONTRACT_ID = (
    "projectkoios.applications.citation-document-receipt"
)
CITATION_DOCUMENT_INGESTION_INTENT_CONTRACT_ID = (
    "projectkoios.applications.citation-document-ingestion-intent"
)
CITATION_DOCUMENT_INGESTION_CONTRACT_ID = (
    "projectkoios.applications.citation-document-ingestion"
)
CITATION_DOCUMENT_REGISTRY_CONTRACT_ID = (
    "projectkoios.applications.citation-document-registry"
)

KSDFT_CITATION_TARGET_SOURCE_COMMIT = "3ec21b4318020d700be671a8f220b2149b3d28c7"
KSDFT_CITATION_TARGET_SOURCE_TREE = "9953c0e99a28443426b5093852292f7cfbada2cc"
REFERENCES_CITATION_DOCUMENT_SOURCE_COMMIT = "f1ca7b4aee552af131ff7af7d1408d33dd338c93"
REFERENCES_CITATION_DOCUMENT_SOURCE_TREE = "b37672e36af13014dc25170be725fbf3f909c2d7"
INGESTION_DOCUMENT_PACKAGE_SOURCE_COMMIT = "be60640bec4fe15cc88b24161545eb1027ffbd2e"
INGESTION_DOCUMENT_PACKAGE_SOURCE_TREE = "d386a1744f79463fd7cd0b3087ee5fc361e0f7d5"

_MAX_ID_BYTES = 4_096
_SHA256 = re.compile(r"[0-9a-f]{64}")


class CitationDocumentTerminalStatus(StrEnum):
    """Terminal result of one synchronous request."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


class CitationDocumentFailureCode(StrEnum):
    """Bounded non-sensitive failure classifications."""

    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    PACKAGE_BUILD_FAILED = "PACKAGE_BUILD_FAILED"
    PUBLICATION_FAILED = "PUBLICATION_FAILED"
    PUBLICATION_INDETERMINATE = "PUBLICATION_INDETERMINATE"
    TRANSCRIPT_VERIFICATION_FAILED = "TRANSCRIPT_VERIFICATION_FAILED"


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class CitationDocumentReceipt(DataObjectModel):
    """Technical custody receipt; it grants no rights or processing authority."""

    source_document: CitationSourceDocumentDescriptor
    receipt_id: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate_inputs()
        object.__setattr__(
            self,
            "receipt_id",
            _id("citation-document-receipt", self.identity_payload()),
        )

    def _validate_inputs(self) -> None:
        if type(self.source_document) is not CitationSourceDocumentDescriptor:
            raise TypeError(
                "source_document must be a CitationSourceDocumentDescriptor"
            )
        self.source_document.validate_identity()

    def identity_payload(self) -> dict[str, object]:
        return {
            "contract_id": CITATION_DOCUMENT_RECEIPT_CONTRACT_ID,
            "source_document": self.source_document.record_payload(),
        }

    def validate_identity(self) -> None:
        if type(self) is not CitationDocumentReceipt:
            raise TypeError("receipt must be an exact CitationDocumentReceipt")
        self._validate_inputs()
        rebuilt = CitationDocumentReceipt(source_document=self.source_document)
        if rebuilt != self:
            raise ValueError("citation document receipt does not match replay")

    def observation(
        self,
        *,
        target_snapshot_id: str,
        literal_citekey: str,
    ) -> CitationSourceDocumentObservation:
        """Build explicit positive availability evidence for References."""
        self.validate_identity()
        return CitationSourceDocumentObservation(
            target_snapshot_id=target_snapshot_id,
            literal_citekey=literal_citekey,
            coverage_status="incomplete",
            source_documents=(self.source_document,),
            inaccessible_evidence_ids=(),
            evidence_id=self.receipt_id,
        )


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class CitationDocumentIngestionIntent(DataObjectModel):
    """Deterministic pre-link intent under configured local authority."""

    receipt: CitationDocumentReceipt
    projection_result: CitationDocumentProjectionResult
    projection_item_id: str
    identity_item_id: str
    local_processing_authority_assertion_id: str
    local_processing_admission_decision_id: str
    extraction_configuration: PdfExtractionConfiguration
    artifact_limits: PdfExtractionArtifactLimits
    intent_id: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate_inputs()
        object.__setattr__(
            self,
            "intent_id",
            _id("citation-document-ingestion-intent", self.identity_payload()),
        )
        self._link_request()

    def _validate_inputs(self) -> None:
        if type(self.receipt) is not CitationDocumentReceipt:
            raise TypeError("receipt must be a CitationDocumentReceipt")
        self.receipt.validate_identity()
        if type(self.projection_result) is not CitationDocumentProjectionResult:
            raise TypeError(
                "projection_result must be a CitationDocumentProjectionResult"
            )
        self.projection_result.validate_identity()
        if type(self.extraction_configuration) is not PdfExtractionConfiguration:
            raise TypeError(
                "extraction_configuration must be a PdfExtractionConfiguration"
            )
        if type(self.artifact_limits) is not PdfExtractionArtifactLimits:
            raise TypeError("artifact_limits must be PdfExtractionArtifactLimits")
        _opaque(self.projection_item_id, "projection_item_id")
        _opaque(self.identity_item_id, "identity_item_id")
        _opaque(
            self.local_processing_authority_assertion_id,
            "local_processing_authority_assertion_id",
        )
        _opaque(
            self.local_processing_admission_decision_id,
            "local_processing_admission_decision_id",
        )

    def identity_payload(self) -> dict[str, object]:
        configuration = self.extraction_configuration
        limits = self.artifact_limits
        return {
            "contract_id": CITATION_DOCUMENT_INGESTION_INTENT_CONTRACT_ID,
            "receipt_id": self.receipt.receipt_id,
            "source_document_descriptor_id": (
                self.receipt.source_document.descriptor_id
            ),
            "projection_result_id": self.projection_result.result_id,
            "projection_item_id": self.projection_item_id,
            "identity_item_id": self.identity_item_id,
            "local_processing_authority_assertion_id": (
                self.local_processing_authority_assertion_id
            ),
            "local_processing_admission_decision_id": (
                self.local_processing_admission_decision_id
            ),
            "extraction_configuration": {
                "low_text_character_threshold": (
                    configuration.low_text_character_threshold
                ),
                "maximum_pages": configuration.maximum_pages,
            },
            "artifact_limits": {
                "max_artifacts": limits.max_artifacts,
                "max_raw_extraction_bytes": limits.max_raw_extraction_bytes,
                "max_page_text_bytes": limits.max_page_text_bytes,
                "max_total_artifact_bytes": limits.max_total_artifact_bytes,
            },
        }

    def validate_identity(self) -> None:
        if type(self) is not CitationDocumentIngestionIntent:
            raise TypeError("intent must be an exact CitationDocumentIngestionIntent")
        self._validate_inputs()
        rebuilt = CitationDocumentIngestionIntent(
            receipt=self.receipt,
            projection_result=self.projection_result,
            projection_item_id=self.projection_item_id,
            identity_item_id=self.identity_item_id,
            local_processing_authority_assertion_id=(
                self.local_processing_authority_assertion_id
            ),
            local_processing_admission_decision_id=(
                self.local_processing_admission_decision_id
            ),
            extraction_configuration=self.extraction_configuration,
            artifact_limits=self.artifact_limits,
        )
        if rebuilt != self:
            raise ValueError("citation document intent does not match replay")

    def _link_request(self) -> CitationSourceDocumentLinkRequest:
        return CitationSourceDocumentLinkRequest(
            projection_result=self.projection_result,
            item_id=self.projection_item_id,
            identity_item_id=self.identity_item_id,
            source_document_id=self.receipt.source_document.source_document_id,
            pre_effect_intent_id=self.intent_id,
        )

    def link_request(self) -> CitationSourceDocumentLinkRequest:
        """Return the exact neutral References request bound to this intent."""
        self.validate_identity()
        return self._link_request()


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class CitationDocumentIngestionRequest(DataObjectActionRequest):
    """Exact synchronous effect request after neutral owner linkage."""

    intent: CitationDocumentIngestionIntent
    link_result: CitationSourceDocumentLinkResult
    request_id: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate_inputs()
        object.__setattr__(
            self,
            "request_id",
            _id("citation-document-ingestion-request", self.identity_payload()),
        )

    def _validate_inputs(self) -> None:
        if type(self.intent) is not CitationDocumentIngestionIntent:
            raise TypeError("intent must be a CitationDocumentIngestionIntent")
        self.intent.validate_identity()
        if type(self.link_result) is not CitationSourceDocumentLinkResult:
            raise TypeError("link_result must be a CitationSourceDocumentLinkResult")
        if type(self.link_result.request) is not CitationSourceDocumentLinkRequest:
            raise TypeError("link_result request must use its exact runtime type")
        if type(self.link_result.link) is not CitationSourceDocumentLink:
            raise TypeError("link_result link must use its exact runtime type")
        if (
            type(self.link_result.link.source_document)
            is not CitationSourceDocumentDescriptor
        ):
            raise TypeError("linked source document must use its exact runtime type")
        self.link_result.validate_identity()
        expected = self.intent.link_request()
        if self.link_result.request != expected:
            raise ValueError("link result does not match the exact pre-effect intent")
        link = self.link_result.link
        if (
            link.pre_effect_intent_id != self.intent.intent_id
            or link.source_document != self.intent.receipt.source_document
        ):
            raise ValueError("link result correlation is inconsistent")

    def identity_payload(self) -> dict[str, object]:
        return {
            "contract_id": CITATION_DOCUMENT_INGESTION_CONTRACT_ID,
            "intent_id": self.intent.intent_id,
            "link_result_id": self.link_result.result_id,
            "link_id": self.link_result.link.link_id,
        }

    def validate_identity(self) -> None:
        if type(self) is not CitationDocumentIngestionRequest:
            raise TypeError("request must be an exact CitationDocumentIngestionRequest")
        self._validate_inputs()
        rebuilt = CitationDocumentIngestionRequest(
            intent=self.intent,
            link_result=self.link_result,
        )
        if rebuilt != self:
            raise ValueError("citation document request does not match replay")

    @property
    def document_id(self) -> str:
        return f"citation-document-{_digest_tail(self.request_id)}"


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class CitationDocumentIngestionResult(DataObjectActionResult):
    """Path-free restart-sufficient terminal result retained for replay."""

    request_id: str
    intent_id: str
    link_result_id: str
    source_document_link: CitationSourceDocumentLink
    receipt_id: str
    source_document_descriptor_id: str
    document_id: str
    status: CitationDocumentTerminalStatus
    failure_code: CitationDocumentFailureCode | None = None
    extraction_bundle_id: str | None = None
    package_id: str | None = None
    transcript_projection_id: str | None = None
    physical_page_count: int | None = None
    publication_action: str | None = None
    result_id: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate_inputs()
        object.__setattr__(
            self,
            "result_id",
            _id("citation-document-ingestion-result", self.identity_payload()),
        )

    @property
    def link_id(self) -> str:
        return self.source_document_link.link_id

    @property
    def transcript_ready(self) -> bool:
        return self.status is CitationDocumentTerminalStatus.SUCCEEDED

    def _validate_inputs(self) -> None:
        for value, name in (
            (self.request_id, "request_id"),
            (self.intent_id, "intent_id"),
            (self.link_result_id, "link_result_id"),
            (self.receipt_id, "receipt_id"),
            (self.source_document_descriptor_id, "source_document_descriptor_id"),
            (self.document_id, "document_id"),
        ):
            _opaque(value, name)
        if type(self.source_document_link) is not CitationSourceDocumentLink:
            raise TypeError("source_document_link must be a CitationSourceDocumentLink")
        if (
            type(self.source_document_link.source_document)
            is not CitationSourceDocumentDescriptor
        ):
            raise TypeError("linked source document must use its exact runtime type")
        self.source_document_link.validate_identity()
        expected_link_result_id = _id(
            "citation-source-document-link-result",
            {
                "contract_id": CITATION_SOURCE_DOCUMENT_LINK_CONTRACT_ID,
                "linker": CITATION_SOURCE_DOCUMENT_LINKER_NAME,
                "request_id": self.source_document_link.creating_request_id,
                "link_id": self.source_document_link.link_id,
            },
        )
        expected_receipt_id = CitationDocumentReceipt(
            source_document=self.source_document_link.source_document
        ).receipt_id
        if (
            self.link_result_id != expected_link_result_id
            or self.source_document_link.pre_effect_intent_id != self.intent_id
            or self.source_document_link.source_document.descriptor_id
            != self.source_document_descriptor_id
            or self.receipt_id != expected_receipt_id
            or self.document_id != f"citation-document-{_digest_tail(self.request_id)}"
        ):
            raise ValueError("terminal link lineage is inconsistent")
        if type(self.status) is not CitationDocumentTerminalStatus:
            raise TypeError("status must be a CitationDocumentTerminalStatus")
        success_values = (
            self.extraction_bundle_id,
            self.package_id,
            self.transcript_projection_id,
            self.physical_page_count,
            self.publication_action,
        )
        if self.status is CitationDocumentTerminalStatus.SUCCEEDED:
            if self.failure_code is not None or any(
                value is None for value in success_values
            ):
                raise ValueError("successful result evidence is incomplete")
            assert self.physical_page_count is not None
            if (
                type(self.physical_page_count) is not int
                or self.physical_page_count <= 0
                or self.publication_action not in {"create", "unchanged"}
            ):
                raise ValueError("successful result evidence is invalid")
            for optional_value, name in (
                (self.extraction_bundle_id, "extraction_bundle_id"),
                (self.package_id, "package_id"),
                (self.transcript_projection_id, "transcript_projection_id"),
            ):
                assert optional_value is not None
                _opaque(optional_value, name)
        elif self.failure_code is None or any(
            value is not None for value in success_values
        ):
            raise ValueError(
                "non-success result must carry one code and no readiness evidence"
            )
        elif type(self.failure_code) is not CitationDocumentFailureCode:
            raise TypeError("failure_code must be a CitationDocumentFailureCode")

    def identity_payload(self) -> dict[str, object]:
        return {
            "contract_id": CITATION_DOCUMENT_INGESTION_CONTRACT_ID,
            "request_id": self.request_id,
            "intent_id": self.intent_id,
            "link_result_id": self.link_result_id,
            "source_document_link": _link_record(self.source_document_link),
            "receipt_id": self.receipt_id,
            "source_document_descriptor_id": self.source_document_descriptor_id,
            "document_id": self.document_id,
            "status": self.status.value,
            "failure_code": (
                None if self.failure_code is None else self.failure_code.value
            ),
            "extraction_bundle_id": self.extraction_bundle_id,
            "package_id": self.package_id,
            "transcript_projection_id": self.transcript_projection_id,
            "physical_page_count": self.physical_page_count,
            "publication_action": self.publication_action,
        }

    def validate_identity(self) -> None:
        if type(self) is not CitationDocumentIngestionResult:
            raise TypeError("result must be an exact CitationDocumentIngestionResult")
        self._validate_inputs()
        rebuilt = CitationDocumentIngestionResult(
            request_id=self.request_id,
            intent_id=self.intent_id,
            link_result_id=self.link_result_id,
            source_document_link=self.source_document_link,
            receipt_id=self.receipt_id,
            source_document_descriptor_id=self.source_document_descriptor_id,
            document_id=self.document_id,
            status=self.status,
            failure_code=self.failure_code,
            extraction_bundle_id=self.extraction_bundle_id,
            package_id=self.package_id,
            transcript_projection_id=self.transcript_projection_id,
            physical_page_count=self.physical_page_count,
            publication_action=self.publication_action,
        )
        if rebuilt != self:
            raise ValueError("citation document result does not match replay")

    def validate_request(self, request: CitationDocumentIngestionRequest) -> None:
        if type(request) is not CitationDocumentIngestionRequest:
            raise TypeError("request must be a CitationDocumentIngestionRequest")
        request.validate_identity()
        self.validate_identity()
        expected = (
            request.request_id,
            request.intent.intent_id,
            request.link_result.result_id,
            request.link_result.link,
            request.intent.receipt.receipt_id,
            request.intent.receipt.source_document.descriptor_id,
            request.document_id,
        )
        actual = (
            self.request_id,
            self.intent_id,
            self.link_result_id,
            self.source_document_link,
            self.receipt_id,
            self.source_document_descriptor_id,
            self.document_id,
        )
        if actual != expected:
            raise ValueError("terminal result does not match the exact request")

    def record_payload(self) -> dict[str, object]:
        payload = self.identity_payload()
        payload["result_id"] = self.result_id
        return payload

    @classmethod
    def from_record(cls, value: object) -> CitationDocumentIngestionResult:
        if cls is not CitationDocumentIngestionResult:
            raise TypeError("result replay requires the exact result class")
        if not isinstance(value, dict):
            raise ValueError("ingestion result record must be an object")
        expected = {
            "contract_id",
            "request_id",
            "intent_id",
            "link_result_id",
            "source_document_link",
            "receipt_id",
            "source_document_descriptor_id",
            "document_id",
            "status",
            "failure_code",
            "extraction_bundle_id",
            "package_id",
            "transcript_projection_id",
            "physical_page_count",
            "publication_action",
            "result_id",
        }
        if set(value) != expected or value.get("contract_id") != (
            CITATION_DOCUMENT_INGESTION_CONTRACT_ID
        ):
            raise ValueError("ingestion result record shape is invalid")
        raw_failure = value.get("failure_code")
        result = CitationDocumentIngestionResult(
            request_id=_record_text(value, "request_id"),
            intent_id=_record_text(value, "intent_id"),
            link_result_id=_record_text(value, "link_result_id"),
            source_document_link=_link_from_record(value.get("source_document_link")),
            receipt_id=_record_text(value, "receipt_id"),
            source_document_descriptor_id=_record_text(
                value, "source_document_descriptor_id"
            ),
            document_id=_record_text(value, "document_id"),
            status=CitationDocumentTerminalStatus(_record_text(value, "status")),
            failure_code=(
                None
                if raw_failure is None
                else CitationDocumentFailureCode(_record_text(value, "failure_code"))
            ),
            extraction_bundle_id=_optional_text(value, "extraction_bundle_id"),
            package_id=_optional_text(value, "package_id"),
            transcript_projection_id=_optional_text(value, "transcript_projection_id"),
            physical_page_count=_optional_int(value, "physical_page_count"),
            publication_action=_optional_text(value, "publication_action"),
        )
        if value.get("result_id") != result.result_id:
            raise ValueError("ingestion result identity is invalid")
        result.validate_identity()
        return result


def _link_record(link: CitationSourceDocumentLink) -> dict[str, object]:
    payload = link.identity_payload()
    payload["link_id"] = link.link_id
    return payload


def _link_from_record(value: object) -> CitationSourceDocumentLink:
    if not isinstance(value, dict):
        raise ValueError("source document link record must be an object")
    expected = {
        "contract_id",
        "creating_request_id",
        "prior_projection_id",
        "prior_item_id",
        "target_snapshot_id",
        "identity_projection_id",
        "literal_citekey",
        "identity_item_id",
        "requested_identity_id",
        "source_document",
        "availability_observation_ids",
        "pre_effect_intent_id",
        "linkage_basis",
        "limitations",
        "link_id",
    }
    if set(value) != expected:
        raise ValueError("source document link record shape is invalid")
    descriptor_value = value.get("source_document")
    if not isinstance(descriptor_value, dict) or set(descriptor_value) != {
        "source_document_id",
        "sha256",
        "byte_size",
        "media_type",
        "descriptor_id",
    }:
        raise ValueError("source document descriptor record is invalid")
    byte_size = descriptor_value.get("byte_size")
    if type(byte_size) is not int:
        raise ValueError("source document byte size is invalid")
    descriptor = CitationSourceDocumentDescriptor(
        source_document_id=_record_text(descriptor_value, "source_document_id"),
        sha256=_record_text(descriptor_value, "sha256"),
        byte_size=byte_size,
        media_type=_record_text(descriptor_value, "media_type"),
    )
    if descriptor_value.get("descriptor_id") != descriptor.descriptor_id:
        raise ValueError("source document descriptor identity is invalid")
    link = CitationSourceDocumentLink(
        creating_request_id=_record_text(value, "creating_request_id"),
        prior_projection_id=_record_text(value, "prior_projection_id"),
        prior_item_id=_record_text(value, "prior_item_id"),
        target_snapshot_id=_record_text(value, "target_snapshot_id"),
        identity_projection_id=_record_text(value, "identity_projection_id"),
        literal_citekey=_record_text(value, "literal_citekey"),
        identity_item_id=_record_text(value, "identity_item_id"),
        requested_identity_id=_record_text(value, "requested_identity_id"),
        source_document=descriptor,
        availability_observation_ids=_record_text_tuple(
            value, "availability_observation_ids"
        ),
        pre_effect_intent_id=_record_text(value, "pre_effect_intent_id"),
        linkage_basis=_record_text(value, "linkage_basis"),
        limitations=_record_text_tuple(value, "limitations"),
        link_id=_record_text(value, "link_id"),
    )
    link.validate_identity()
    return link


def _record_text(value: dict[object, object], key: str) -> str:
    item = value.get(key)
    if type(item) is not str:
        raise ValueError(f"record {key} must be text")
    return item


def _record_text_tuple(value: dict[object, object], key: str) -> tuple[str, ...]:
    item = value.get(key)
    if not isinstance(item, list) or any(type(entry) is not str for entry in item):
        raise ValueError(f"record {key} must be a text list")
    return tuple(item)


def _optional_text(value: dict[object, object], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if type(item) is not str:
        raise ValueError(f"record {key} must be text or null")
    return item


def _optional_int(value: dict[object, object], key: str) -> int | None:
    item = value.get(key)
    if item is None:
        return None
    if type(item) is not int:
        raise ValueError(f"record {key} must be an integer or null")
    return item


def _opaque(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > _MAX_ID_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{field_name} is invalid")
    return value


def _digest_tail(value: str) -> str:
    tail = value.rsplit(":", 1)[-1]
    if _SHA256.fullmatch(tail) is None:
        raise ValueError("identity has no canonical SHA-256 suffix")
    return tail


def _id(prefix: str, payload: object) -> str:
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"{prefix}:sha256:{hashlib.sha256(canonical).hexdigest()}"


def canonical_json(value: object) -> bytes:
    """Serialize one bounded identity record canonically."""
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
