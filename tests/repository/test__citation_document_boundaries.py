from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

from projectkoios.applications.pdf_corpus_ingestion.citation_document_contracts import (
    CITATION_DOCUMENT_INGESTION_CONTRACT_ID,
    CITATION_DOCUMENT_INGESTION_INTENT_CONTRACT_ID,
    CITATION_DOCUMENT_RECEIPT_CONTRACT_ID,
    CITATION_DOCUMENT_REGISTRY_CONTRACT_ID,
    INGESTION_DOCUMENT_PACKAGE_SOURCE_COMMIT,
    INGESTION_DOCUMENT_PACKAGE_SOURCE_TREE,
    KSDFT_CITATION_TARGET_SOURCE_COMMIT,
    KSDFT_CITATION_TARGET_SOURCE_TREE,
    REFERENCES_CITATION_DOCUMENT_SOURCE_COMMIT,
    REFERENCES_CITATION_DOCUMENT_SOURCE_TREE,
)

_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _ROOT / "src/python/projectkoios/applications/pdf_corpus_ingestion"
_SOURCE_MIRROR = {
    "citation_document_contracts": (
        "CitationDocumentFailureCode",
        "CitationDocumentIngestionIntent",
        "CitationDocumentIngestionRequest",
        "CitationDocumentIngestionResult",
        "CitationDocumentReceipt",
        "CitationDocumentTerminalStatus",
    ),
    "citation_document_custody": (
        "CitationDocumentCustodyError",
        "CitationDocumentCustodyLimitError",
        "PrivatePdfCustody",
    ),
    "citation_document_registry": (
        "CitationDocumentRegistry",
        "CitationDocumentRegistryError",
        "CitationDocumentRegistryLimitError",
        "CitationDocumentRegistryProjection",
    ),
    "citation_document_service": ("CitationDocumentIngestionService",),
}
_COMPONENTS = (
    (
        Path(
            os.environ.get(
                "PROJECTKOIOS_KSDFT_REPOSITORY",
                _ROOT.parent / "ksdft2effmass",
            )
        ),
        KSDFT_CITATION_TARGET_SOURCE_COMMIT,
        KSDFT_CITATION_TARGET_SOURCE_TREE,
    ),
    (
        Path(
            os.environ.get(
                "PROJECTKOIOS_REFERENCES_REPOSITORY",
                _ROOT.parent / "projectkoios-references",
            )
        ),
        REFERENCES_CITATION_DOCUMENT_SOURCE_COMMIT,
        REFERENCES_CITATION_DOCUMENT_SOURCE_TREE,
    ),
    (
        Path(
            os.environ.get(
                "PROJECTKOIOS_INGESTION_REPOSITORY",
                _ROOT.parent / "projectkoios-ingestion",
            )
        ),
        INGESTION_DOCUMENT_PACKAGE_SOURCE_COMMIT,
        INGESTION_DOCUMENT_PACKAGE_SOURCE_TREE,
    ),
)


def test_citation_document_sources_and_public_classes_have_architecture_docs() -> None:
    docs = _ROOT / "docs/architecture/projectkoios/applications/pdf_corpus_ingestion"
    for module, classes in _SOURCE_MIRROR.items():
        module_docs = docs / module
        assert (module_docs / "index.md").is_file(), module
        assert (module_docs / "implementation.md").is_file(), module
        assert (module_docs / "schematic.md").is_file(), module
        for class_name in classes:
            assert (module_docs / class_name / "index.md").is_file(), (
                module,
                class_name,
            )


def test_citation_document_contract_ids_are_canonical_and_unversioned() -> None:
    contract_ids = (
        CITATION_DOCUMENT_RECEIPT_CONTRACT_ID,
        CITATION_DOCUMENT_INGESTION_INTENT_CONTRACT_ID,
        CITATION_DOCUMENT_INGESTION_CONTRACT_ID,
        CITATION_DOCUMENT_REGISTRY_CONTRACT_ID,
    )
    assert len(contract_ids) == len(set(contract_ids))
    assert all(value.startswith("projectkoios.applications.") for value in contract_ids)
    assert all("@" not in value for value in contract_ids)


def test_citation_document_tests_use_canonical_owner_taxonomy_imports() -> None:
    test_path = (
        _ROOT
        / "tests/projectkoios/applications/pdf_corpus_ingestion"
        / "test__citation_document_ingestion.py"
    )
    tree = ast.parse(test_path.read_text(), filename=str(test_path))
    imported_by_module = {
        node.module: {alias.name for alias in node.names}
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert (
        "CitationBibliographyObservationBinding"
        in imported_by_module["projectkoios.references.bibliography"]
    )
    assert {
        "CitationContentIdentity",
        "CitationSourceLocator",
        "CitationTargetBibliographyEntry",
        "CitationTargetGroup",
        "CitationTargetOccurrence",
        "CitationTargetSnapshot",
    }.issubset(imported_by_module["projectkoios.references.citations"])
    assert not {
        "CitationBibliographyObservationBinding",
        "CitationContentIdentity",
        "CitationSourceLocator",
        "CitationTargetBibliographyEntry",
        "CitationTargetGroup",
        "CitationTargetOccurrence",
        "CitationTargetSnapshot",
    }.intersection(imported_by_module["projectkoios.references.citation_document"])


def test_citation_document_slice_uses_only_public_owner_modules() -> None:
    forbidden = {
        "projectkoios.references.citation_document._contract",
        "projectkoios.references.assets",
        "projectkoios.references.provided_intake",
        "projectkoios.ingestion.cache",
        "projectkoios.ingestion.cli",
    }
    violations: list[str] = []
    for path in sorted(_PACKAGE.glob("citation_document_*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        if imported & forbidden:
            violations.append(str(path.relative_to(_ROOT)))
    assert violations == []


@pytest.mark.parametrize(("repository", "commit", "tree"), _COMPONENTS)
def test_citation_document_source_is_an_exact_local_git_object(
    repository: Path,
    commit: str,
    tree: str,
) -> None:
    if not (repository / ".git").exists():
        pytest.skip("bounded sdist environment has no component Git repository")
    subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    observed = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{tree}}"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert observed == tree
