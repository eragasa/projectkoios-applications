from __future__ import annotations

import hashlib
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from examples.projectkoios.applications.pw_dft_scf.runner.environment import WorkflowRunnerEnvironment
from examples.projectkoios.applications.pw_dft_scf.runner.render_inputs import InputProjectionRunner

_COMMIT = "24dffe10c29e60afcd5fe07aaacb84921a41a43d"
_TREE = "b7897a05de39072126e6162ce6e8b8fb25be5f31"
_VASP_HASHES = {
    "INCAR": "15703162fd60018469973248d32f51b6d35d1a3e716b3201b25f6c0ce0c1734f",
    "KPOINTS": "37c762ac822ae18c3c1abb39def8c008a1afc3beb75a58971376df313da597cd",
    "POSCAR": "38b718c8c976817ed7fe5824b32de744e8be91166c220eefbb46d2a42109a9c4",
    "input-projection.json": "ed0d358e9e09d4ef9364f359f601d80ab59e03258b93df85ad2d3750de9ae28d",
}
_QE_METADATA_HASH = "8cac4e2f09587da48e26b26e2fe835a25eb9d6d1cbae9c1906b42cb8c6f1d239"
_QE_BASE_HASH = "945e807c6dec6ce7c73f54bc0522ce08b0ebfab62ed6ae77e4663ee3e5e0d459"
_QE_CONVERGENCE_HASH = "e18bb80ced5ea2a373e587146becac309d6ce2210b2cd89a9298dbbd2b7006ab"


class InputProjectionRunnerTest(unittest.TestCase):
    def test_projects_exact_reviewed_vasp_and_qe_campaigns(self) -> None:
        repository = Path(__file__).resolve().parents[6]
        transfer = tomllib.loads((repository / "TRANSFER.toml").read_text())
        simulations = transfer["dependencies"]["simulations"]
        self.assertEqual((simulations["combined_commit"], simulations["combined_tree"]), (_COMMIT, _TREE))
        example = repository / "examples/projectkoios/applications/pw_dft_scf"
        environment = WorkflowRunnerEnvironment.load(example / "runner/config/runner.toml")
        campaigns = sorted((example / "providers").glob("*/Si/primitive/**/campaign.toml"))
        self.assertEqual(len(campaigns), 8)

        with tempfile.TemporaryDirectory() as temporary_directory:
            for index, campaign in enumerate(campaigns):
                loaded = environment.loader.load(campaign)
                request = loaded.campaign.recipe.base_request
                self.assertEqual(request.sampling.kpoint_mesh, (8, 8, 8))
                self.assertEqual(request.sampling.kpoint_shift, (0, 0, 0))
                expected_cutoff = 408.1707936897154 if "quantumespresso/Si/primitive/campaign.toml" in campaign.as_posix() else 400.0
                self.assertEqual(request.sampling.wavefunction_cutoff_ev, expected_cutoff)
                positions = tuple(tuple(atom.position_fractional.magnitude.tolist()) for atom in request.simulation.unit_cell.atomic_basis.atoms)
                self.assertEqual(positions, ((0.0, 0.0, 0.0), (0.25, 0.25, 0.25)))

                output = Path(temporary_directory) / str(index)
                rendered = InputProjectionRunner(environment).render(campaign, output)
                actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in rendered}
                if "/vasp/" in campaign.as_posix():
                    self.assertEqual(actual, _VASP_HASHES)
                else:
                    expected_input = _QE_BASE_HASH if campaign.parent.name == "primitive" else _QE_CONVERGENCE_HASH
                    self.assertEqual(actual, {"pw.in": expected_input, "input-projection.json": _QE_METADATA_HASH})
                metadata = json.loads((output / "input-projection.json").read_text(encoding="ascii"))
                self.assertIn(metadata["integration_id"], {"quantum-espresso", "vasp"})


if __name__ == "__main__":
    unittest.main()
