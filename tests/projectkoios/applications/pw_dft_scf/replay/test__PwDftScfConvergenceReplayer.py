from __future__ import annotations

import unittest

import pytest

from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceCoordinate,
    PwDftScfEnergyObservation,
)
from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)
from projectkoios.applications.pw_dft_scf.replay import (
    PwDftScfConvergenceReplayer,
    PwDftScfConvergenceReplayError,
    PwDftScfConvergenceReplayEvidence,
)
from projectkoios.simulations.calculator import CalculatorIntegrationId

_MESH_COMPONENTS = {4: 0.0, 6: 0.0100, 8: 0.0200, 10: 0.0205, 12: 0.0207}
_CUTOFF_COMPONENTS = {
    300.0: 0.0,
    350.0: 0.0100,
    400.0: 0.0200,
    450.0: 0.0204,
    500.0: 0.0206,
}
_INITIAL_COORDINATES = tuple(
    (mesh, cutoff) for mesh in (4, 6, 8) for cutoff in (300.0, 350.0, 400.0)
)
_EXTENSION_COORDINATES = tuple(
    (mesh, cutoff)
    for mesh in (4, 6, 8, 10, 12)
    for cutoff in (300.0, 350.0, 400.0, 450.0, 500.0)
    if (mesh, cutoff) not in _INITIAL_COORDINATES
)


class PwDftScfConvergenceReplayerTest(unittest.TestCase):
    @pytest.mark.property
    def test_replays_extension_then_acceptance_deterministically(self) -> None:
        forward = PwDftScfConvergenceReplayer().replay(_evidence())
        reversed_order = PwDftScfConvergenceReplayer().replay(_evidence(reverse=True))

        self.assertEqual(forward.observation_count, 25)
        self.assertEqual(
            set(forward.initial_extension.coordinates),
            set(reversed_order.initial_extension.coordinates),
        )
        self.assertEqual(forward.final_assessment, reversed_order.final_assessment)
        self.assertTrue(forward.final_assessment.converged)

    @pytest.mark.adversarial
    def test_rejects_extension_that_does_not_match_policy_request(self) -> None:
        evidence = _evidence()
        incomplete = PwDftScfConvergenceReplayEvidence(
            evidence_id=evidence.evidence_id,
            integration_id=evidence.integration_id,
            policy=evidence.policy,
            initial_observations=evidence.initial_observations,
            extension_observations=evidence.extension_observations[:-1],
            source_evidence_reference=evidence.source_evidence_reference,
        )

        with self.assertRaisesRegex(
            PwDftScfConvergenceReplayError,
            "do not match",
        ):
            PwDftScfConvergenceReplayer().replay(incomplete)

    @pytest.mark.adversarial
    def test_rejects_overlapping_initial_and_extension_coordinates(self) -> None:
        evidence = _evidence()
        with self.assertRaisesRegex(ValueError, "must be disjoint"):
            PwDftScfConvergenceReplayEvidence(
                evidence_id=evidence.evidence_id,
                integration_id=evidence.integration_id,
                policy=evidence.policy,
                initial_observations=evidence.initial_observations,
                extension_observations=(evidence.initial_observations[0],),
                source_evidence_reference=evidence.source_evidence_reference,
            )


def _evidence(*, reverse: bool = False) -> PwDftScfConvergenceReplayEvidence:
    initial = _observations(_INITIAL_COORDINATES)
    extension = _observations(_EXTENSION_COORDINATES)
    if reverse:
        initial = tuple(reversed(initial))
        extension = tuple(reversed(extension))
    return PwDftScfConvergenceReplayEvidence(
        evidence_id="synthetic-qe-grid-replay",
        integration_id=CalculatorIntegrationId("quantum-espresso"),
        policy=PwDftScfConvergencePolicy(
            tolerance_mev_per_atom=1.0,
            required_consecutive_deltas=2,
            mesh_increment=2,
            cutoff_increment_ev=50.0,
            extension_steps=2,
            maximum_mesh_density=12,
            maximum_cutoff_ev=500.0,
            maximum_grid_points=25,
        ),
        initial_observations=initial,
        extension_observations=extension,
        source_evidence_reference="provider-evidence:synthetic-software-verification",
    )


def _observations(
    coordinates: tuple[tuple[int, float], ...],
) -> tuple[PwDftScfEnergyObservation, ...]:
    return tuple(
        PwDftScfEnergyObservation(
            coordinate=PwDftScfConvergenceCoordinate(mesh, cutoff),
            total_energy_ev_per_atom=(
                -5.0 - _MESH_COMPONENTS[mesh] - _CUTOFF_COMPONENTS[cutoff]
            ),
        )
        for mesh, cutoff in coordinates
    )


if __name__ == "__main__":
    unittest.main()
