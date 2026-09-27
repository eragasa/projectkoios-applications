from __future__ import annotations

import unittest

from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)
from projectkoios.applications.pw_dft_scf.recipe import (
    PwDftScfCutoffConvergenceRecipe,
    PwDftScfGridConvergenceRecipe,
    PwDftScfKpointConvergenceRecipe,
    PwDftScfSingleCalculationRecipe,
)
from tests.projectkoios.applications.pw_dft_scf.support import silicon_scf_request


class PwDftScfRecipeTest(unittest.TestCase):
    def test_supports_all_four_scientific_workflow_modes(self) -> None:
        base = silicon_scf_request()
        policy = PwDftScfConvergencePolicy(cutoff_increment_ev=50.0)
        single = PwDftScfSingleCalculationRecipe("si-single", base)
        kpoint = PwDftScfKpointConvergenceRecipe("si-kpoint", base, (4, 6, 8), policy)
        cutoff = PwDftScfCutoffConvergenceRecipe(
            "si-cutoff", base, (300.0, 350.0, 400.0), policy
        )
        grid = PwDftScfGridConvergenceRecipe(
            "si-grid",
            base,
            (4, 6, 8),
            (300.0, 350.0, 400.0),
            policy,
        )

        self.assertEqual(single.base_request, base)
        self.assertEqual(len(kpoint.coordinates()), 3)
        self.assertEqual(len(cutoff.coordinates()), 3)
        self.assertEqual(len(grid.coordinates()), 9)
        projected = grid.request_for(grid.coordinates()[0], scope="initial")
        self.assertEqual(projected.sampling.kpoint_mesh, (4, 4, 4))
        self.assertEqual(projected.sampling.wavefunction_cutoff_ev, 300.0)


if __name__ == "__main__":
    unittest.main()
