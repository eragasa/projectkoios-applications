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


def test_capability_has_no_owner_private_cli_or_process_imports() -> None:
    forbidden_modules = {
        "subprocess",
        "socket",
        "requests",
        "openai",
        "anthropic",
        "pytesseract",
        "projectkoios.references.assets",
        "projectkoios.references.provided_intake",
        "projectkoios.ingestion.cli",
    }
    forbidden_names = {
        "CanonicalAssetAuthorization",
        "CanonicalAsset",
        "citekey",
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


def test_transcript_projection_uses_only_the_public_owner_replay_seam() -> None:
    text = (_PACKAGE / "transcript.py").read_text()
    assert "read_pdf_extraction_transcript" in text
    assert "deserialize_extraction_result" not in text
    assert "projectkoios.ingestion.cache" not in text
    assert "os.walk(" not in text
    assert "Path.home(" not in text
    assert "subprocess" not in text
    assert "socket" not in text


def test_document_package_and_transcript_seams_are_unversioned() -> None:
    document_package = (_PACKAGE / "document_package.py").read_text()
    transcript = (_PACKAGE / "transcript.py").read_text()
    public_exports = (_PACKAGE / "__init__.py").read_text()

    assert "schema_version" not in document_package
    assert "schema_version" not in transcript
    assert "DOCUMENT_PACKAGE_SCHEMA_VERSION" not in public_exports
    assert "DOCUMENT_INGESTION_MANIFEST_SCHEMA_VERSION" not in public_exports
    assert "DOCUMENT_TRANSCRIPT_SCHEMA_VERSION" not in public_exports
    assert "DocumentTranscriptUnsupportedPackageError" not in public_exports


def test_runner_uses_bound_filesystem_primitives() -> None:
    text = (_PACKAGE / "runner.py").read_text()
    assert "staged_path.read_bytes(" not in text
    assert "destination.mkdir(" not in text
    assert "destination.open(" not in text
    assert "ingest_pdf_artifacts" not in text
    assert "extract_pdf_bytes_artifacts" in text
    assert "rename_child" not in text
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
