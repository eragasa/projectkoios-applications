from __future__ import annotations

import unittest

from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceAssessment,
    PwDftScfConvergenceCoordinate,
)
from projectkoios.applications.pw_dft_scf.convergence.controller import (
    ExtendPwDftScfConvergence,
    PwDftScfConvergenceAccepted,
    PwDftScfConvergenceBudgetExhausted,
    PwDftScfConvergenceController,
)


class PwDftScfConvergenceControllerTest(unittest.TestCase):
    def test_routes_the_three_fixed_controller_outcomes(self) -> None:
        point = PwDftScfConvergenceCoordinate(10, 400.0)
        controller = PwDftScfConvergenceController()

        accepted = controller.decide(_assessment(converged=True, can_extend=False))
        extended = controller.decide(
            _assessment(
                converged=False,
                can_extend=True,
                requested_points=(point,),
            )
        )
        exhausted = controller.decide(_assessment(converged=False, can_extend=False))

        self.assertIsInstance(accepted, PwDftScfConvergenceAccepted)
        self.assertIsInstance(extended, ExtendPwDftScfConvergence)
        self.assertIsInstance(exhausted, PwDftScfConvergenceBudgetExhausted)


def _assessment(
    *,
    converged: bool,
    can_extend: bool,
    requested_points: tuple[PwDftScfConvergenceCoordinate, ...] = (),
) -> PwDftScfConvergenceAssessment:
    return PwDftScfConvergenceAssessment(
        converged=converged,
        can_extend=can_extend,
        kpoint_tail_deltas_mev_per_atom=(),
        cutoff_tail_deltas_mev_per_atom=(),
        requested_points=requested_points,
        reason="test",
    )


if __name__ == "__main__":
    unittest.main()
