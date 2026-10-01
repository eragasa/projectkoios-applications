from __future__ import annotations

import ast
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
_COMPONENTS = (
    (
        Path("/Users/eugene/repos/ksdft2effmass"),
        KSDFT_CITATION_TARGET_SOURCE_COMMIT,
        KSDFT_CITATION_TARGET_SOURCE_TREE,
    ),
    (
        Path("/Users/eugene/repos/projectkoios-references"),
        REFERENCES_CITATION_DOCUMENT_SOURCE_COMMIT,
        REFERENCES_CITATION_DOCUMENT_SOURCE_TREE,
    ),
    (
        Path("/Users/eugene/repos/projectkoios-ingestion"),
        INGESTION_DOCUMENT_PACKAGE_SOURCE_COMMIT,
        INGESTION_DOCUMENT_PACKAGE_SOURCE_TREE,
    ),
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
