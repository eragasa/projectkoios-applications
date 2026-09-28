"""Bounded PDF-corpus discovery and ingestion application composition."""

from .composition import compose_pdf_corpus_ingestion_plan
from .document_package import (
    DOCUMENT_PACKAGE_CONTRACT_ID,
    DOCUMENT_PACKAGE_MANIFEST,
    DOCUMENT_PACKAGE_SCHEMA_VERSION,
    DeterministicDocumentPackage,
    DocumentPackageArtifact,
    DocumentPackageError,
    DocumentPackagePublicationAction,
    DocumentPackagePublicationError,
    build_deterministic_document_package,
    publish_deterministic_document_package,
)
from .multimodal import PdfCorpusMultimodalPolicy
from .plan import (
    MAX_APPLICATION_PDF_BYTES,
    MAX_APPLICATION_PDF_PAGES,
    MAX_TRANCHE_ITEMS,
    PdfCorpusIngestionPlan,
    PdfCorpusItemDisposition,
    PdfCorpusLocation,
    PdfCorpusPlanError,
    PdfCorpusPlanItem,
)

__all__ = [
    "DOCUMENT_PACKAGE_CONTRACT_ID",
    "DOCUMENT_PACKAGE_MANIFEST",
    "DOCUMENT_PACKAGE_SCHEMA_VERSION",
    "MAX_APPLICATION_PDF_BYTES",
    "MAX_APPLICATION_PDF_PAGES",
    "MAX_TRANCHE_ITEMS",
    "DeterministicDocumentPackage",
    "DocumentPackageArtifact",
    "DocumentPackageError",
    "DocumentPackagePublicationAction",
    "DocumentPackagePublicationError",
    "PdfCorpusIngestionPlan",
    "PdfCorpusItemDisposition",
    "PdfCorpusLocation",
    "PdfCorpusMultimodalPolicy",
    "PdfCorpusPlanError",
    "PdfCorpusPlanItem",
    "build_deterministic_document_package",
    "compose_pdf_corpus_ingestion_plan",
    "publish_deterministic_document_package",
]
