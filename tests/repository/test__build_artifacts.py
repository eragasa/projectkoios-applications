from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

import physkit

import projectkoios.simulations

_ROOT = Path(__file__).resolve().parents[2]
_EPOCH = "1758931200"


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

    @staticmethod
    def _source_copy(destination: Path) -> Path:
        shutil.copytree(
            _ROOT,
            destination,
            ignore=shutil.ignore_patterns(
                ".git",
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
            names = set(archive.namelist())
            for filename in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
                self.assertTrue(
                    any(name.endswith(f"licenses/{filename}") for name in names)
                )
            self.assertIn("projectkoios/applications/pw_dft_scf/replay.py", names)
            self.assertIn(
                "projectkoios/applications/pw_dft_relaxation/composition.py", names
            )
            self.assertFalse(
                any(name.startswith("projectkoios/integrations/") for name in names)
            )
            self.assertFalse(
                any(name.startswith(("tests/", "build_backend/")) for name in names)
            )

    def _assert_sdist(self, sdist: Path | None) -> None:
        assert sdist is not None
        with tarfile.open(sdist, "r:gz") as archive:
            names = archive.getnames()
        for suffix in (
            "/LICENSE",
            "/NOTICE",
            "/THIRD_PARTY_NOTICES.md",
            "/build_backend/projectkoios_build.py",
            "/tests/repository/test__build_artifacts.py",
            "/tests/fixtures/pw_dft_scf/qe-retained-convergence-normalized.json",
        ):
            self.assertTrue(any(name.endswith(suffix) for name in names), suffix)

    def _assert_isolated_import(self, wheel: Path) -> None:
        simulations = str(
            Path(next(iter(projectkoios.simulations.__path__))).parents[1]
        )
        physkit_root = str(Path(physkit.__file__).resolve().parents[1])
        script = f"""
import sys, zipfile, tempfile
with tempfile.TemporaryDirectory() as directory:
    zipfile.ZipFile({str(wheel)!r}).extractall(directory)
    sys.path[:0] = [directory, {simulations!r}, {physkit_root!r}]
    from projectkoios.applications.pw_dft_scf.replay import PwDftScfConvergenceReplayer
    from projectkoios.applications.pw_dft_relaxation.composition import (
        PwDftRelaxationComposer,
    )
    assert PwDftScfConvergenceReplayer and PwDftRelaxationComposer
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
