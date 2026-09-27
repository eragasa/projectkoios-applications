from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from dataclasses import asdict
from pathlib import Path
from types import ModuleType

from examples.projectkoios.applications.pw_dft_scf.runner.environment import (
    WorkflowRunnerEnvironment,
)
from examples.projectkoios.applications.pw_dft_scf.runner.render_inputs import (
    InputProjectionRunner,
)

_FIXTURE_SHA256 = "bfc9f867474c86d20359a23563cf3d6277928bcf435a126357fd2bdc4732f57e"


class InputProjectionRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Path(__file__).resolve().parents[6]
        self.example = self.repository / "examples/projectkoios/applications/pw_dft_scf"
        fixture_path = (
            self.repository / "tests/fixtures/pw_dft_scf/campaign-projections.json"
        )
        fixture_bytes = fixture_path.read_bytes()
        self.assertEqual(hashlib.sha256(fixture_bytes).hexdigest(), _FIXTURE_SHA256)
        self.fixture = json.loads(fixture_bytes)

    def test_exact_eight_campaign_matrix_and_rendered_values(self) -> None:
        environment = WorkflowRunnerEnvironment.load(
            self.example / "runner/config/runner.toml"
        )
        expected_paths = {item["path"] for item in self.fixture["campaigns"]}
        discovered_paths = {
            path.relative_to(self.example).as_posix()
            for path in (self.example / "providers").glob(
                "*/Si/primitive/**/campaign.toml"
            )
        }
        self.assertEqual(discovered_paths, expected_paths)

        with tempfile.TemporaryDirectory() as temporary_directory:
            for index, expected in enumerate(self.fixture["campaigns"]):
                campaign_path = self.example / expected["path"]
                declaration = tomllib.loads(campaign_path.read_text(encoding="utf-8"))
                self.assertEqual(declaration["campaign_id"], expected["campaign_id"])
                self.assertEqual(declaration["mode"], expected["mode"])
                self.assertEqual(declaration["integration"], expected["provider"])
                self.assertEqual(declaration["structure_id"], expected["structure_id"])
                self.assertEqual(
                    declaration["sampling_profile"], expected["sampling_profile"]
                )
                self.assertEqual(
                    declaration.get("coordinate_profile"),
                    expected["coordinate_profile"],
                )
                self.assertEqual(
                    declaration.get("policy_profile"), expected["policy_profile"]
                )

                loaded = environment.loader.load(campaign_path)
                recipe = loaded.campaign.recipe
                request = recipe.base_request
                self.assertEqual(type(recipe).__name__, expected["recipe_type"])
                self.assertEqual(recipe.campaign_id, expected["campaign_id"])
                self.assertEqual(
                    loaded.campaign.integration_id.value, expected["provider"]
                )
                self.assertEqual(
                    loaded.projection_profile_id, expected["projection_profile"]
                )
                self.assertEqual(
                    list(request.sampling.kpoint_mesh),
                    expected["sampling"]["kpoint_mesh"],
                )
                self.assertEqual(
                    list(request.sampling.kpoint_shift),
                    expected["sampling"]["kpoint_shift"],
                )
                self.assertEqual(
                    request.sampling.wavefunction_cutoff_ev,
                    expected["sampling"]["wavefunction_cutoff_ev"],
                )
                self.assertEqual(
                    list(getattr(recipe, "mesh_densities", ())) or None,
                    expected["mesh_densities"],
                )
                self.assertEqual(
                    list(getattr(recipe, "wavefunction_cutoffs_ev", ())) or None,
                    expected["wavefunction_cutoffs_ev"],
                )
                policy = getattr(recipe, "policy", None)
                self.assertEqual(
                    asdict(policy) if policy is not None else None, expected["policy"]
                )

                positions = [
                    atom.position_fractional.magnitude.tolist()
                    for atom in request.simulation.unit_cell.atomic_basis.atoms
                ]
                self.assertEqual(positions, [[0.0, 0.0, 0.0], [0.25, 0.25, 0.25]])
                output = Path(temporary_directory) / str(index)
                rendered = InputProjectionRunner(environment).render(
                    campaign_path, output
                )
                actual_hashes = {
                    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in rendered
                }
                self.assertEqual(actual_hashes, expected["rendered_sha256"])
                rendered_text = "\n".join(
                    path.read_text(encoding="ascii")
                    for path in rendered
                    if path.suffix != ".json"
                )
                for fragment in expected["rendered_fragments"]:
                    self.assertIn(fragment, rendered_text)

    def test_operational_provider_graph_is_exact_candidate_graph(self) -> None:
        expected_modules = {
            item["module"]: item["sha256"] for item in self.fixture["provider_modules"]
        }
        projection_module = importlib.import_module(
            "projectkoios.integrations.quantumespresso.pw.scf.projection"
        )
        provider_root = Path(projection_module.__file__ or "").resolve().parents[5]
        paths = [item["path"] for item in self.fixture["campaigns"]]
        script = f"""
import hashlib, json, sys, tempfile
from pathlib import Path
sys.path[:0] = [{str(provider_root)!r}, {str(self.repository / "src/python")!r}, {str(self.repository)!r}]
from examples.projectkoios.applications.pw_dft_scf.runner.environment import WorkflowRunnerEnvironment
from examples.projectkoios.applications.pw_dft_scf.runner.render_inputs import InputProjectionRunner
example = Path({str(self.example)!r})
environment = WorkflowRunnerEnvironment.load(example / 'runner/config/runner.toml')
with tempfile.TemporaryDirectory() as directory:
    for index, relative in enumerate({paths!r}):
        InputProjectionRunner(environment).render(example / relative, Path(directory) / str(index))
prefixes = ('projectkoios.integrations.quantumespresso', 'projectkoios.integrations.vasp')
loaded = {{
    name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    for name, module in sys.modules.items()
    if name.startswith(prefixes) and getattr(module, '__file__', None)
}}
print(json.dumps(loaded, sort_keys=True))
"""
        completed = subprocess.run(
            [sys.executable, "-I", "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), expected_modules)

        simulations_repository = os.environ.get("PROJECTKOIOS_SIMULATIONS_REPOSITORY")
        if simulations_repository is not None:
            tree = subprocess.run(
                [
                    "git",
                    "rev-parse",
                    f"{self.fixture['simulations_commit']}^{{tree}}",
                ],
                cwd=simulations_repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(tree, self.fixture["simulations_tree"])
        for expected in self.fixture["provider_modules"]:
            module = importlib.import_module(expected["module"])
            self._assert_module_hash(module, expected["sha256"])
            if simulations_repository is not None:
                entry = (
                    subprocess.run(
                        [
                            "git",
                            "ls-tree",
                            self.fixture["simulations_commit"],
                            "--",
                            expected["path"],
                        ],
                        cwd=simulations_repository,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    .stdout.strip()
                    .split()
                )
                self.assertEqual(entry[:3], ["100644", "blob", expected["git_blob"]])

    def _assert_module_hash(self, module: ModuleType, expected_sha256: str) -> None:
        module_path = Path(module.__file__ or "")
        self.assertTrue(module_path.is_file())
        self.assertEqual(
            hashlib.sha256(module_path.read_bytes()).hexdigest(), expected_sha256
        )


if __name__ == "__main__":
    unittest.main()
