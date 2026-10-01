"""Synchronous citation-document composition and exact terminal replay."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import final

from projectkoios.base import DataObjectActionizer
from projectkoios.ingestion import (
    PdfExtractionArtifactBundle,
    extract_pdf_bytes_artifacts,
)
from projectkoios.references import AuthorizedRoot
from projectkoios.references.citation_document import (
    CitationSourceDocumentLinker,
)

from .citation_document_contracts import (
    CitationDocumentFailureCode,
    CitationDocumentIngestionIntent,
    CitationDocumentIngestionRequest,
    CitationDocumentIngestionResult,
    CitationDocumentTerminalStatus,
)
from .citation_document_custody import (
    PrivatePdfCustody,
    _require_mode_0600_files,
    _require_private_root,
)
from .citation_document_registry import (
    CitationDocumentRegistry,
    CitationDocumentRegistryError,
)
from .document_package import (
    DeterministicDocumentPackage,
    DocumentPackagePublicationAction,
    build_deterministic_document_package,
    publish_deterministic_document_package,
)
from .transcript import (
    DocumentTranscriptProjection,
    project_document_transcript,
)

_Extractor = Callable[..., PdfExtractionArtifactBundle]
_PackageBuilder = Callable[..., DeterministicDocumentPackage]
_PackagePublisher = Callable[..., DocumentPackagePublicationAction]
_TranscriptProjector = Callable[..., DocumentTranscriptProjection]


@final
@dataclass(frozen=True, slots=True)
class CitationDocumentIngestionService(
    DataObjectActionizer[
        CitationDocumentIngestionRequest,
        CitationDocumentIngestionResult,
    ]
):
    """Perform one bounded synchronous effect and retain its terminal result."""

    custody: PrivatePdfCustody
    package_root: AuthorizedRoot
    registry: CitationDocumentRegistry
    extractor: _Extractor = extract_pdf_bytes_artifacts
    package_builder: _PackageBuilder = build_deterministic_document_package
    package_publisher: _PackagePublisher = publish_deterministic_document_package
    transcript_projector: _TranscriptProjector = project_document_transcript

    def __post_init__(self) -> None:
        if type(self.custody) is not PrivatePdfCustody:
            raise TypeError("custody must be an exact PrivatePdfCustody")
        if type(self.registry) is not CitationDocumentRegistry:
            raise TypeError("registry must be an exact CitationDocumentRegistry")
        self._validate_roots()
        for dependency, name in (
            (self.extractor, "extractor"),
            (self.package_builder, "package_builder"),
            (self.package_publisher, "package_publisher"),
            (self.transcript_projector, "transcript_projector"),
        ):
            if not callable(dependency):
                raise TypeError(f"{name} must be callable")

    def _validate_roots(self) -> None:
        _require_private_root(self.custody.root, field_name="custody root")
        _require_private_root(self.package_root, field_name="package root")
        _require_private_root(self.registry.root, field_name="registry root")
        roots = (
            ("custody root", self.custody.root.path),
            ("package root", self.package_root.path),
            ("registry root", self.registry.root.path),
        )
        for index, (left_name, left) in enumerate(roots):
            for right_name, right in roots[index + 1 :]:
                if (
                    left == right
                    or left.is_relative_to(right)
                    or right.is_relative_to(left)
                ):
                    raise ValueError(
                        f"{left_name} and {right_name} must be disjoint and non-nested"
                    )

    def request(
        self,
        intent: CitationDocumentIngestionIntent,
    ) -> CitationDocumentIngestionRequest:
        """Create the owner link Result and downstream synchronous request."""
        if type(self) is not CitationDocumentIngestionService:
            raise TypeError("service must be an exact CitationDocumentIngestionService")
        self._validate_roots()
        if type(intent) is not CitationDocumentIngestionIntent:
            raise TypeError("intent must be a CitationDocumentIngestionIntent")
        intent.validate_identity()
        link_result = CitationSourceDocumentLinker().link(request=intent.link_request())
        return CitationDocumentIngestionRequest(
            intent=intent,
            link_result=link_result,
        )

    def action(
        self,
        *,
        request: CitationDocumentIngestionRequest,
    ) -> CitationDocumentIngestionResult:
        """Execute synchronously or return the exact retained terminal replay."""
        if type(self) is not CitationDocumentIngestionService:
            raise TypeError("service must be an exact CitationDocumentIngestionService")
        self._validate_roots()
        if type(request) is not CitationDocumentIngestionRequest:
            raise TypeError("request must be a CitationDocumentIngestionRequest")
        request.validate_identity()
        return self._execute(request)

    def ingest(
        self,
        request: CitationDocumentIngestionRequest,
    ) -> CitationDocumentIngestionResult:
        """Compatibility spelling routed through the sole action path."""
        return self.action(request=request)

    def _execute(
        self,
        request: CitationDocumentIngestionRequest,
    ) -> CitationDocumentIngestionResult:
        existing = self.registry.lookup(request)
        if existing is not None:
            if existing.status is CitationDocumentTerminalStatus.SUCCEEDED:
                self._verify_success(request, existing)
            return existing

        state = self.package_root.state(request.document_id)
        if state != "missing":
            return self._retain(
                request,
                self._failure(
                    request,
                    CitationDocumentTerminalStatus.INDETERMINATE,
                    CitationDocumentFailureCode.PUBLICATION_INDETERMINATE,
                ),
            )

        try:
            content = self.custody.read_for_ingestion(request.intent.receipt)
            descriptor = request.intent.receipt.source_document
            configuration = request.intent.extraction_configuration
            extraction = self.extractor(
                content,
                source_id=descriptor.source_document_id,
                locator=f"private-custody-receipt:{request.intent.receipt.receipt_id}",
                low_text_character_threshold=(
                    configuration.low_text_character_threshold
                ),
                expected_source_sha256=descriptor.sha256,
                expected_source_byte_size=descriptor.byte_size,
                maximum_pages=configuration.maximum_pages,
                artifact_limits=request.intent.artifact_limits,
            )
        except Exception:
            return self._retain(
                request,
                self._failure(
                    request,
                    CitationDocumentTerminalStatus.FAILED,
                    CitationDocumentFailureCode.EXTRACTION_FAILED,
                ),
            )

        try:
            package = self.package_builder(
                document_key=request.document_id,
                source_pdf=content,
                extraction=extraction,
            )
        except Exception:
            return self._retain(
                request,
                self._failure(
                    request,
                    CitationDocumentTerminalStatus.FAILED,
                    CitationDocumentFailureCode.PACKAGE_BUILD_FAILED,
                ),
            )

        try:
            publication_action = self.package_publisher(
                package,
                output_root=self.package_root,
            )
        except Exception:
            state_after: str
            try:
                state_after = self.package_root.state(request.document_id)
            except Exception:
                state_after = "unknown"
            status = (
                CitationDocumentTerminalStatus.FAILED
                if state_after == "missing"
                else CitationDocumentTerminalStatus.INDETERMINATE
            )
            code = (
                CitationDocumentFailureCode.PUBLICATION_FAILED
                if status is CitationDocumentTerminalStatus.FAILED
                else CitationDocumentFailureCode.PUBLICATION_INDETERMINATE
            )
            return self._retain(request, self._failure(request, status, code))

        try:
            transcript = self._project(request.document_id)
            self._require_transcript_source(request, transcript)
            if (
                transcript.package_id != package.package_id
                or package.extraction_bundle_id != extraction.bundle_id
            ):
                raise ValueError("published package identity changed")
        except Exception:
            return self._retain(
                request,
                self._failure(
                    request,
                    CitationDocumentTerminalStatus.INDETERMINATE,
                    CitationDocumentFailureCode.TRANSCRIPT_VERIFICATION_FAILED,
                ),
            )

        result = self._success(
            request,
            extraction_bundle_id=extraction.bundle_id,
            package_id=package.package_id,
            transcript=transcript,
            publication_action=publication_action.value,
        )
        return self._retain(request, result)

    def _verify_success(
        self,
        request: CitationDocumentIngestionRequest,
        result: CitationDocumentIngestionResult,
    ) -> None:
        try:
            transcript = self._project(request.document_id)
            self._require_transcript_source(request, transcript)
        except Exception as error:
            raise CitationDocumentRegistryError(
                "retained successful transcript can no longer be verified"
            ) from error
        if (
            transcript.package_id != result.package_id
            or transcript.projection_id != result.transcript_projection_id
            or transcript.physical_page_count != result.physical_page_count
        ):
            raise CitationDocumentRegistryError(
                "retained successful result conflicts with transcript"
            )

    def _project(self, document_id: str) -> DocumentTranscriptProjection:
        return self.transcript_projector(document_root=self._document_root(document_id))

    def _document_root(self, document_id: str) -> AuthorizedRoot:
        if self.package_root.state(document_id) != "directory":
            raise ValueError("document package is not a directory")
        document_root = AuthorizedRoot.existing(
            self.package_root.child_path(document_id),
            label=f"citation document package {document_id}",
            root_alias=self.package_root.preflight_evidence.root_alias,
            storage_class=self.package_root.preflight_evidence.storage_class,
            placeholder_probe=self.package_root.placeholder_probe,
        )
        _require_mode_0600_files(
            document_root,
            field_name="document package root",
        )
        return document_root

    @staticmethod
    def _require_transcript_source(
        request: CitationDocumentIngestionRequest,
        transcript: DocumentTranscriptProjection,
    ) -> None:
        descriptor = request.intent.receipt.source_document
        if (
            transcript.document_id != request.document_id
            or transcript.source_sha256 != descriptor.sha256
            or transcript.source_byte_size != descriptor.byte_size
            or transcript.media_type != descriptor.media_type
        ):
            raise ValueError("transcript source does not match the custody receipt")

    @staticmethod
    def _success(
        request: CitationDocumentIngestionRequest,
        *,
        extraction_bundle_id: str,
        package_id: str,
        transcript: DocumentTranscriptProjection,
        publication_action: str,
    ) -> CitationDocumentIngestionResult:
        return CitationDocumentIngestionResult(
            request_id=request.request_id,
            intent_id=request.intent.intent_id,
            link_result_id=request.link_result.result_id,
            source_document_link=request.link_result.link,
            receipt_id=request.intent.receipt.receipt_id,
            source_document_descriptor_id=(
                request.intent.receipt.source_document.descriptor_id
            ),
            document_id=request.document_id,
            status=CitationDocumentTerminalStatus.SUCCEEDED,
            extraction_bundle_id=extraction_bundle_id,
            package_id=package_id,
            transcript_projection_id=transcript.projection_id,
            physical_page_count=transcript.physical_page_count,
            publication_action=publication_action,
        )

    @staticmethod
    def _failure(
        request: CitationDocumentIngestionRequest,
        status: CitationDocumentTerminalStatus,
        code: CitationDocumentFailureCode,
    ) -> CitationDocumentIngestionResult:
        return CitationDocumentIngestionResult(
            request_id=request.request_id,
            intent_id=request.intent.intent_id,
            link_result_id=request.link_result.result_id,
            source_document_link=request.link_result.link,
            receipt_id=request.intent.receipt.receipt_id,
            source_document_descriptor_id=(
                request.intent.receipt.source_document.descriptor_id
            ),
            document_id=request.document_id,
            status=status,
            failure_code=code,
        )

    def _retain(
        self,
        request: CitationDocumentIngestionRequest,
        result: CitationDocumentIngestionResult,
    ) -> CitationDocumentIngestionResult:
        return self.registry.record(request, result)
