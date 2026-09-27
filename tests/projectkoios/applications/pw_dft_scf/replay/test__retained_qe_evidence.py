from __future__ import annotations

import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path

from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceCoordinate,
    PwDftScfEnergyObservation,
)
from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)
from projectkoios.applications.pw_dft_scf.replay import (
    PwDftScfConvergenceReplayer,
    PwDftScfConvergenceReplayEvidence,
)
from projectkoios.simulations.calculator import CalculatorIntegrationId

_FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "fixtures/pw_dft_scf/qe-retained-convergence-normalized.json"
)
_FIXTURE_SHA256 = "ff751aa7aeccc467886ec74979c7b2a92cdc645c83e4917e460bee36db6361d3"
_SIMULATIONS_COMMIT = "24dffe10c29e60afcd5fe07aaacb84921a41a43d"
_SIMULATIONS_TREE = "b7897a05de39072126e6162ce6e8b8fb25be5f31"
_MANIFEST_SHA256 = "94cfaa284e10731d04c241479be464c92e295291c4bb4f795e9e02f232a5c8fc"


class RetainedQeEvidenceReplayTest(unittest.TestCase):
    def test_replays_provenance_bound_provider_normalized_30_plus_6_dataset(
        self,
    ) -> None:
        payload_bytes = _FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(payload_bytes).hexdigest(), _FIXTURE_SHA256)
        payload = json.loads(payload_bytes)
        self.assertEqual(payload["source"]["commit"], _SIMULATIONS_COMMIT)
        self.assertEqual(payload["source"]["tree"], _SIMULATIONS_TREE)
        self.assertEqual(payload["source"]["manifest_sha256"], _MANIFEST_SHA256)
        initial = self._observations(payload["initial_observations"])
        extension = self._observations(payload["extension_observations"])
        self.assertEqual((len(initial), len(extension)), (30, 6))
        policy = payload["policy"]
        evidence = PwDftScfConvergenceReplayEvidence(
            evidence_id=payload["evidence_id"],
            integration_id=CalculatorIntegrationId(payload["integration_id"]),
            policy=PwDftScfConvergencePolicy(**policy),
            initial_observations=initial,
            extension_observations=extension,
            source_evidence_reference=(
                f"{_SIMULATIONS_COMMIT}:{payload['source']['manifest_path']}"
            ),
        )

        result = PwDftScfConvergenceReplayer().replay(evidence)

        self.assertEqual(result.observation_count, 36)
        self.assertEqual(len(result.initial_extension.coordinates), 6)
        self.assertTrue(result.final_assessment.converged)

    def test_optional_simulations_checkout_rederives_normalized_fixture(self) -> None:
        repository_value = os.environ.get("PROJECTKOIOS_SIMULATIONS_REPOSITORY")
        if repository_value is None:
            self.skipTest(
                "set PROJECTKOIOS_SIMULATIONS_REPOSITORY for provider evidence proof"
            )
        repository = Path(repository_value).resolve()
        tree = subprocess.run(
            ["git", "rev-parse", f"{_SIMULATIONS_COMMIT}^{{tree}}"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(tree, _SIMULATIONS_TREE)
        fixture = json.loads(_FIXTURE.read_bytes())
        manifest_bytes = subprocess.run(
            [
                "git",
                "show",
                f"{_SIMULATIONS_COMMIT}:{fixture['source']['manifest_path']}",
            ],
            cwd=repository,
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(hashlib.sha256(manifest_bytes).hexdigest(), _MANIFEST_SHA256)
        manifest = json.loads(manifest_bytes)
        conversion = 13.605693122994

        def normalize(stage: str) -> list[dict[str, float | int]]:
            return [
                {
                    "mesh_density": item["coordinate"]["mesh_density"],
                    "wavefunction_cutoff_ev": (
                        item["coordinate"]["wavefunction_cutoff_ry"] * conversion
                    ),
                    "total_energy_ev_per_atom": (
                        item["native_observation"]["total_energy_ry"]
                        * conversion
                        / item["native_observation"]["atom_count"]
                    ),
                }
                for item in manifest["observations"]
                if item["stage"] == stage
            ]

        self.assertEqual(fixture["initial_observations"], normalize("initial-grid"))
        self.assertEqual(
            fixture["extension_observations"], normalize("adaptive-extension")
        )

    @staticmethod
    def _observations(
        values: list[dict[str, object]],
    ) -> tuple[PwDftScfEnergyObservation, ...]:
        observations: list[PwDftScfEnergyObservation] = []
        for item in values:
            mesh = item["mesh_density"]
            cutoff = item["wavefunction_cutoff_ev"]
            energy = item["total_energy_ev_per_atom"]
            if (
                type(mesh) is not int
                or type(cutoff) is not float
                or type(energy) is not float
            ):
                raise TypeError("normalized observation has invalid numeric types")
            observations.append(
                PwDftScfEnergyObservation(
                    coordinate=PwDftScfConvergenceCoordinate(mesh, cutoff),
                    total_energy_ev_per_atom=energy,
                )
            )
        return tuple(observations)


if __name__ == "__main__":
    unittest.main()
