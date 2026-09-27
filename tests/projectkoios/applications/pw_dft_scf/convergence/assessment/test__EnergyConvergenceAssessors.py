from __future__ import annotations

import unittest

from projectkoios.applications.pw_dft_scf.convergence.assessment import (
    EnergyAxisConvergenceAssessmentRequest,
    EnergyAxisConvergenceAssessor,
    EnergyGridConvergenceAssessmentRequest,
    EnergyGridConvergenceAssessor,
)
from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceAxis,
    PwDftScfConvergenceCoordinate,
    PwDftScfEnergyObservation,
)
from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)


class EnergyConvergenceAssessorsTest(unittest.TestCase):
    def test_axis_assessor_is_reused_for_kpoint_and_cutoff_convergence(self) -> None:
        policy = PwDftScfConvergencePolicy(cutoff_increment_ev=50.0)
        kpoint = EnergyAxisConvergenceAssessor().assess(
            EnergyAxisConvergenceAssessmentRequest(
                PwDftScfConvergenceAxis.kpoint,
                _observations(
                    {
                        (4, 400.0): -5.000000,
                        (6, 400.0): -5.000500,
                        (8, 400.0): -5.000800,
                    }
                ),
                policy,
            )
        )
        cutoff = EnergyAxisConvergenceAssessor().assess(
            EnergyAxisConvergenceAssessmentRequest(
                PwDftScfConvergenceAxis.wavefunction_cutoff,
                _observations(
                    {
                        (8, 300.0): -5.000000,
                        (8, 350.0): -5.000500,
                        (8, 400.0): -5.000800,
                    }
                ),
                policy,
            )
        )

        self.assertTrue(kpoint.converged)
        self.assertTrue(cutoff.converged)

    def test_grid_assessor_requires_both_high_edges(self) -> None:
        assessment = EnergyGridConvergenceAssessor().assess(
            EnergyGridConvergenceAssessmentRequest(
                _observations(
                    {
                        (4, 300.0): -4.9800,
                        (4, 350.0): -4.9810,
                        (4, 400.0): -4.9820,
                        (6, 300.0): -4.9900,
                        (6, 350.0): -4.9910,
                        (6, 400.0): -4.9920,
                        (8, 300.0): -5.0000,
                        (8, 350.0): -5.0005,
                        (8, 400.0): -5.0008,
                    }
                ),
                PwDftScfConvergencePolicy(cutoff_increment_ev=50.0),
            )
        )

        self.assertFalse(assessment.converged)
        self.assertTrue(assessment.can_extend)
        self.assertEqual(
            assessment.requested_points,
            tuple(
                PwDftScfConvergenceCoordinate(mesh, cutoff)
                for mesh in (10, 12)
                for cutoff in (300.0, 350.0, 400.0)
            ),
        )


def _observations(
    energies: dict[tuple[int, float], float],
) -> tuple[PwDftScfEnergyObservation, ...]:
    return tuple(
        PwDftScfEnergyObservation(
            PwDftScfConvergenceCoordinate(mesh, cutoff),
            energy,
        )
        for (mesh, cutoff), energy in sorted(energies.items())
    )


if __name__ == "__main__":
    unittest.main()
