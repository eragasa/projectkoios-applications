from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from projectkoios.applications.pdf_corpus_ingestion.plan import (
    INGESTION_SOURCE_COMMIT,
    INGESTION_SOURCE_TREE,
    REFERENCES_SOURCE_COMMIT,
    REFERENCES_SOURCE_TREE,
)

_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _ROOT / "src/python/projectkoios/applications/pdf_corpus_ingestion"
_COMPONENTS = (
    (
        Path("/Users/eugene/repos/projectkoios-references"),
        REFERENCES_SOURCE_COMMIT,
        REFERENCES_SOURCE_TREE,
    ),
    (
        Path("/Users/eugene/repos/projectkoios-ingestion"),
        INGESTION_SOURCE_COMMIT,
        INGESTION_SOURCE_TREE,
    ),
)


def test_capability_has_no_acceptance_private_cli_or_process_imports() -> None:
    forbidden_modules = {
        "subprocess",
        "socket",
        "requests",
        "openai",
        "anthropic",
        "pytesseract",
        "projectkoios.references.assets",
        "projectkoios.references.provided_intake",
    }
    forbidden_names = {
        "CanonicalAssetAuthorization",
        "CanonicalAsset",
        "citekey",
        "acceptance",
        "_resolve_items",
    }
    for path in sorted(_PACKAGE.glob("*.py")):
        text = path.read_text()
        tree = ast.parse(text, filename=str(path))
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
        assert not (imported & forbidden_modules), path
        assert not any(name in text for name in forbidden_names), path


def test_runner_uses_bound_filesystem_primitives() -> None:
    text = (_PACKAGE / "runner.py").read_text()
    assert "staged_path.read_bytes(" not in text
    assert "destination.mkdir(" not in text
    assert "destination.open(" not in text
    assert "ingest_pdf_artifacts(" not in text
    assert "subprocess" not in text


def test_tests_do_not_scan_home_or_filesystem_root() -> None:
    tests = _ROOT / "tests/projectkoios/applications/pdf_corpus_ingestion"
    text = "\n".join(path.read_text() for path in sorted(tests.glob("*.py")))
    assert "Path.home(" not in text
    assert "expanduser(" not in text
    assert "os.walk(" not in text
    assert "Path('/')" not in text
    assert 'Path("/")' not in text


@pytest.mark.parametrize(("repository", "commit", "tree"), _COMPONENTS)
def test_component_provenance_is_an_exact_local_git_object(
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
