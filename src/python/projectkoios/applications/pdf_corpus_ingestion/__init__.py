"""Bounded PDF-corpus discovery and ingestion application composition."""

from .composition import compose_pdf_corpus_ingestion_plan
from .multimodal import PdfCorpusMultimodalPolicy
from .plan import (
    MAX_APPLICATION_PDF_BYTES,
    MAX_TRANCHE_ITEMS,
    PdfCorpusIngestionPlan,
    PdfCorpusItemDisposition,
    PdfCorpusLocation,
    PdfCorpusPlanError,
    PdfCorpusPlanItem,
)

__all__ = [
    "MAX_APPLICATION_PDF_BYTES",
    "MAX_TRANCHE_ITEMS",
    "PdfCorpusIngestionPlan",
    "PdfCorpusItemDisposition",
    "PdfCorpusLocation",
    "PdfCorpusMultimodalPolicy",
    "PdfCorpusPlanError",
    "PdfCorpusPlanItem",
    "compose_pdf_corpus_ingestion_plan",
]
