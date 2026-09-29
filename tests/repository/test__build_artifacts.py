from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from email.parser import BytesParser
from pathlib import Path

import physkit

import projectkoios.chunking
import projectkoios.ingestion
import projectkoios.references
import projectkoios.simulations

_ROOT = Path(__file__).resolve().parents[2]
_EPOCH = "1758931200"
_SDIST_INVENTORY = _ROOT / "tests/fixtures/artifacts/sdist-inventory.txt"
_SDIST_INVENTORY_SHA256 = (
    "262c72ec770f778df096c2b9c7630508a0abf5b6777eb5429e77f7abb2310a15"
)
_WHEEL_INVENTORY = (
    "projectkoios/applications/__init__.py",
    "projectkoios/applications/_optional_dependencies.py",
    "projectkoios/applications/py.typed",
    "projectkoios/applications/pdf_corpus_ingestion/__init__.py",
    "projectkoios/applications/pdf_corpus_ingestion/cli.py",
    "projectkoios/applications/pdf_corpus_ingestion/composition.py",
    "projectkoios/applications/pdf_corpus_ingestion/document_package.py",
    "projectkoios/applications/pdf_corpus_ingestion/equation_review.py",
    "projectkoios/applications/pdf_corpus_ingestion/multimodal.py",
    "projectkoios/applications/pdf_corpus_ingestion/plan.py",
    "projectkoios/applications/pdf_corpus_ingestion/review_tree.py",
    "projectkoios/applications/pdf_corpus_ingestion/roots.py",
    "projectkoios/applications/pdf_corpus_ingestion/runner.py",
    "projectkoios/applications/pw_dft_relaxation/__init__.py",
    "projectkoios/applications/pw_dft_relaxation/composition.py",
    "projectkoios/applications/pw_dft_relaxation/workflow/__init__.py",
    "projectkoios/applications/pw_dft_relaxation/workflow/base.py",
    "projectkoios/applications/pw_dft_relaxation/workflow/definition.py",
    "projectkoios/applications/pw_dft_scf/__init__.py",
    "projectkoios/applications/pw_dft_scf/comparison.py",
    "projectkoios/applications/pw_dft_scf/configuration.py",
    "projectkoios/applications/pw_dft_scf/recipe.py",
    "projectkoios/applications/pw_dft_scf/replay.py",
    "projectkoios/applications/pw_dft_scf/convergence/__init__.py",
    "projectkoios/applications/pw_dft_scf/convergence/assessment.py",
    "projectkoios/applications/pw_dft_scf/convergence/base.py",
    "projectkoios/applications/pw_dft_scf/convergence/comparison.py",
    "projectkoios/applications/pw_dft_scf/convergence/controller.py",
    "projectkoios/applications/pw_dft_scf/convergence/policy.py",
    "projectkoios/applications/pw_dft_scf/workflow/__init__.py",
    "projectkoios/applications/pw_dft_scf/workflow/base.py",
    "projectkoios/applications/pw_dft_scf/workflow/definition.py",
    "projectkoios/applications/pw_dft_scf/workflow/facade.py",
    "projectkoios_applications-0.1.0.dev0.dist-info/licenses/LICENSE",
    "projectkoios_applications-0.1.0.dev0.dist-info/licenses/NOTICE",
    "projectkoios_applications-0.1.0.dev0.dist-info/licenses/THIRD_PARTY_NOTICES.md",
    "projectkoios_applications-0.1.0.dev0.dist-info/METADATA",
    "projectkoios_applications-0.1.0.dev0.dist-info/WHEEL",
    "projectkoios_applications-0.1.0.dev0.dist-info/entry_points.txt",
    "projectkoios_applications-0.1.0.dev0.dist-info/top_level.txt",
    "projectkoios_applications-0.1.0.dev0.dist-info/RECORD",
)


class BuildArtifactTest(unittest.TestCase):
    def test_reproducible_complete_artifacts_and_sdist_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = self._source_copy(base / "first")
            second = self._source_copy(base / "second")
            first_wheel, first_sdist = self._build(first, "--sdist", "--wheel")
            second_wheel, second_sdist = self._build(second, "--sdist", "--wheel")
            assert first_sdist is not None and second_sdist is not None
            self.assertEqual(self._sha(first_wheel), self._sha(second_wheel))
            self.assertEqual(self._sha(first_sdist), self._sha(second_sdist))
            self._assert_wheel(first_wheel)
            self._assert_sdist(first_sdist)

            extracted = base / "from-sdist"
            extracted.mkdir()
            with tarfile.open(first_sdist, "r:gz") as archive:
                archive.extractall(extracted, filter="data")
            source = next(extracted.iterdir())
            round_trip_wheel, _ = self._build(source, "--wheel")
            self.assertEqual(self._sha(first_wheel), self._sha(round_trip_wheel))
            self._assert_isolated_import(round_trip_wheel)
            self._assert_pdf_corpus_minimal_import(round_trip_wheel)

    @staticmethod
    def _source_copy(destination: Path) -> Path:
        if (_ROOT / ".git").exists():
            subprocess.run(["git", "diff", "--quiet", "--"], cwd=_ROOT, check=True)
            archive = subprocess.run(
                ["git", "archive", "HEAD"],
                cwd=_ROOT,
                check=True,
                capture_output=True,
            ).stdout
            destination.mkdir()
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
                tar.extractall(destination, filter="data")
            staged_patch = subprocess.run(
                ["git", "diff", "--cached", "--binary", "HEAD"],
                cwd=_ROOT,
                check=True,
                capture_output=True,
            ).stdout
            if staged_patch:
                subprocess.run(
                    ["git", "apply", "--binary", "-"],
                    cwd=destination,
                    input=staged_patch,
                    check=True,
                )
        else:
            shutil.copytree(
                _ROOT,
                destination,
                ignore=shutil.ignore_patterns(
                    ".git",
                    "build",
                    "dist",
                    "*.egg-info",
                    "__pycache__",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                ),
            )
        return destination

    @staticmethod
    def _build(source: Path, *kinds: str) -> tuple[Path, Path | None]:
        environment = os.environ.copy()
        environment["SOURCE_DATE_EPOCH"] = _EPOCH
        subprocess.run(
            [sys.executable, "-m", "build", "--no-isolation", *kinds],
            cwd=source,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        wheel = next((source / "dist").glob("*.whl"))
        sdists = tuple((source / "dist").glob("*.tar.gz"))
        return wheel, sdists[0] if sdists else None

    def _assert_wheel(self, wheel: Path) -> None:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            metadata = BytesParser().parsebytes(
                archive.read("projectkoios_applications-0.1.0.dev0.dist-info/METADATA")
            )
        self.assertEqual(len(names), len(set(names)), "wheel has duplicate members")
        self.assertEqual(names, list(_WHEEL_INVENTORY))
        requirements = metadata.get_all("Requires-Dist") or []
        self.assertTrue(requirements)
        self.assertTrue(all("; extra ==" in value for value in requirements))
        pdf_requirements = {
            value.split(";", 1)[0].strip()
            for value in requirements
            if 'extra == "pdf-corpus"' in value
        }
        self.assertEqual(
            pdf_requirements,
            {
                "projectkoios-ingestion[pdf]==0.0.0",
                "projectkoios-references==0.0.0",
            },
        )
        self.assertFalse(
            any(
                "projectkoios-simulations" in value or "physkit" in value.lower()
                for value in requirements
                if 'extra == "pdf-corpus"' in value
            )
        )
        self.assertIn("simulations", metadata.get_all("Provides-Extra") or [])
        self.assertTrue(
            any(
                value.startswith("projectkoios-simulations")
                and 'extra == "simulations"' in value
                for value in requirements
            )
        )

    def _assert_sdist(self, sdist: Path | None) -> None:
        assert sdist is not None
        inventory_bytes = _SDIST_INVENTORY.read_bytes()
        self.assertEqual(
            hashlib.sha256(inventory_bytes).hexdigest(),
            _SDIST_INVENTORY_SHA256,
        )
        expected = inventory_bytes.decode("utf-8").splitlines()
        self.assertEqual(len(expected), len(set(expected)))
        with tarfile.open(sdist, "r:gz") as archive:
            raw_names = archive.getnames()
        self.assertEqual(
            len(raw_names), len(set(raw_names)), "sdist has duplicate members"
        )
        roots = {name.split("/", 1)[0] for name in raw_names}
        self.assertEqual(roots, {"projectkoios_applications-0.1.0.dev0"})
        relative_names = [name.split("/", 1)[1] for name in raw_names if "/" in name]
        self.assertEqual(
            len(relative_names),
            len(set(relative_names)),
            "sdist has duplicate relative paths",
        )
        self.assertEqual(raw_names, expected)

    def _assert_isolated_import(self, wheel: Path) -> None:
        simulations = str(
            Path(next(iter(projectkoios.simulations.__path__))).parents[1]
        )
        physkit_root = str(Path(physkit.__file__).resolve().parents[1])
        references = str(Path(next(iter(projectkoios.references.__path__))).parents[1])
        ingestion = str(Path(next(iter(projectkoios.ingestion.__path__))).parents[1])
        core = str(Path(next(iter(projectkoios.chunking.__path__))).parents[1])
        script = f"""
import sys, zipfile, tempfile
with tempfile.TemporaryDirectory() as directory:
    zipfile.ZipFile({str(wheel)!r}).extractall(directory)
    sys.path[:0] = [
        directory,
        {simulations!r},
        {physkit_root!r},
        {references!r},
        {ingestion!r},
        {core!r},
    ]
    from projectkoios.applications.pdf_corpus_ingestion import (
        EquationReviewEvidenceBinding,
        PdfCorpusIngestionPlan,
    )
    from projectkoios.applications.pw_dft_scf.replay import PwDftScfConvergenceReplayer
    from projectkoios.applications.pw_dft_relaxation.composition import (
        PwDftRelaxationComposer,
    )
    assert (
        EquationReviewEvidenceBinding
        and PdfCorpusIngestionPlan
        and PwDftScfConvergenceReplayer
        and PwDftRelaxationComposer
    )
"""
        subprocess.run(
            [sys.executable, "-I", "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )

    def _assert_pdf_corpus_minimal_import(self, wheel: Path) -> None:
        references = str(Path(next(iter(projectkoios.references.__path__))).parents[1])
        ingestion = str(Path(next(iter(projectkoios.ingestion.__path__))).parents[1])
        core = str(Path(next(iter(projectkoios.chunking.__path__))).parents[1])
        script = f"""
import importlib
import importlib.abc
import sys, zipfile, tempfile

class BlockScientificImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "physkit" or fullname.startswith("physkit."):
            raise ModuleNotFoundError(fullname)
        if fullname == "projectkoios.simulations" or fullname.startswith(
            "projectkoios.simulations."
        ):
            raise ModuleNotFoundError(fullname)
        return None

with tempfile.TemporaryDirectory() as directory:
    zipfile.ZipFile({str(wheel)!r}).extractall(directory)
    sys.path[:0] = [
        directory,
        {references!r},
        {ingestion!r},
        {core!r},
    ]
    sys.meta_path.insert(0, BlockScientificImports())
    from projectkoios.applications.pdf_corpus_ingestion import (
        EquationReviewEvidenceBinding,
        PdfCorpusIngestionPlan,
    )
    assert EquationReviewEvidenceBinding and PdfCorpusIngestionPlan
    assert "projectkoios.simulations" not in sys.modules
    assert "physkit" not in sys.modules
    for capability in (
        "projectkoios.applications.pw_dft_scf",
        "projectkoios.applications.pw_dft_relaxation",
    ):
        try:
            importlib.import_module(capability)
        except ImportError as error:
            assert "projectkoios-applications[simulations]" in str(error)
        else:
            raise AssertionError("simulation capability imported without its extra")
"""
        subprocess.run(
            [sys.executable, "-I", "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
