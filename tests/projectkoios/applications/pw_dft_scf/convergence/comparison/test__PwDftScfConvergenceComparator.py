from __future__ import annotations

import unittest
from typing import TypedDict

from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceCoordinate,
    PwDftScfEnergyObservation,
)
from projectkoios.applications.pw_dft_scf.convergence.comparison import (
    PwDftScfConvergenceComparator,
    PwDftScfConvergenceComparisonAnalysis,
    PwDftScfConvergenceComparisonInterpretation,
    PwDftScfConvergenceComparisonRequest,
    PwDftScfConvergenceTest,
    PwDftScfConvergenceTestKind,
)
from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)
from projectkoios.simulations.calculator import CalculatorIntegrationId


class _PolicyKwargs(TypedDict):
    tolerance_mev_per_atom: float
    required_consecutive_deltas: int
    mesh_increment: int
    cutoff_increment_ev: float
    extension_steps: int
    maximum_mesh_density: int
    maximum_cutoff_ev: float
    maximum_grid_points: int


_POLICY_KWARGS: _PolicyKwargs = {
    "tolerance_mev_per_atom": 1.0,
    "required_consecutive_deltas": 2,
    "mesh_increment": 2,
    "cutoff_increment_ev": 50.0,
    "extension_steps": 2,
    "maximum_mesh_density": 12,
    "maximum_cutoff_ev": 600.0,
    "maximum_grid_points": 40,
}
_KPOINT_COORDINATES = ((4, 400.0), (6, 400.0), (8, 400.0))
_CUTOFF_COORDINATES = ((8, 300.0), (8, 350.0), (8, 400.0))
_LEFT_AXIS_ENERGIES = (-5.0, -5.0005, -5.0007)
_RIGHT_AXIS_ENERGIES = (-150.0, -150.0004, -150.0005)
_MESH_COMPONENTS = (0.0, 0.0005, 0.0007)
_CUTOFF_COMPONENTS = (0.0, 0.0004, 0.0008)
_RIGHT_MESH_COMPONENTS = (0.0, 0.0004, 0.0005)
_RIGHT_CUTOFF_COMPONENTS = (0.0, 0.0003, 0.0005)


class PwDftScfConvergenceComparatorTest(unittest.TestCase):
    def test_compares_kpoint_convergence_without_absolute_energies(self) -> None:
        analysis = _compare_axis(
            kind=PwDftScfConvergenceTestKind.K_POINTS,
            coordinates=_KPOINT_COORDINATES,
        )

        self.assertTrue(analysis.left_assessment.converged)
        self.assertTrue(analysis.right_assessment.converged)
        self.assertTrue(analysis.convergence_outcomes_match)
        self.assertEqual(len(analysis.common_coordinates), 3)
        _assert_deltas(
            self,
            analysis.kpoint_tail_delta_left_minus_right_mev_per_atom,
            (0.1, 0.1),
        )
        self.assertIsNone(analysis.cutoff_tail_delta_left_minus_right_mev_per_atom)

    def test_compares_cutoff_convergence_without_equating_basis_quality(self) -> None:
        analysis = _compare_axis(
            kind=PwDftScfConvergenceTestKind.WAVEFUNCTION_CUTOFF,
            coordinates=_CUTOFF_COORDINATES,
        )

        self.assertTrue(analysis.convergence_outcomes_match)
        _assert_deltas(
            self,
            analysis.cutoff_tail_delta_left_minus_right_mev_per_atom,
            (0.1, 0.1),
        )
        self.assertIn(
            "Cutoff coordinates retain backend- and pseudopotential-specific "
            "basis meanings even when expressed in the same energy unit.",
            analysis.qualifications,
        )

    def test_compares_cross_convergence_on_both_grid_edges(self) -> None:
        coordinates = tuple(
            (mesh, cutoff) for mesh in (4, 6, 8) for cutoff in (300.0, 350.0, 400.0)
        )
        left_energies = tuple(
            -5.0 - _MESH_COMPONENTS[mesh_index] - _CUTOFF_COMPONENTS[cutoff_index]
            for mesh_index in range(3)
            for cutoff_index in range(3)
        )
        right_energies = tuple(
            -150.0
            - _RIGHT_MESH_COMPONENTS[mesh_index]
            - _RIGHT_CUTOFF_COMPONENTS[cutoff_index]
            for mesh_index in range(3)
            for cutoff_index in range(3)
        )
        analysis = _compare(
            kind=PwDftScfConvergenceTestKind.CROSS,
            coordinates=coordinates,
            left_energies=left_energies,
            right_energies=right_energies,
        )

        self.assertEqual(
            analysis.interpretation,
            PwDftScfConvergenceComparisonInterpretation.RELATIVE_ENERGY_DESCRIPTIVE,
        )
        self.assertTrue(analysis.left_assessment.converged)
        self.assertTrue(analysis.right_assessment.converged)
        self.assertEqual(len(analysis.common_coordinates), 9)
        self.assertIsNotNone(analysis.kpoint_tail_delta_left_minus_right_mev_per_atom)
        self.assertIsNotNone(analysis.cutoff_tail_delta_left_minus_right_mev_per_atom)

    def test_rejects_comparison_under_different_policies(self) -> None:
        left = _test(
            test_id="left-kpoints",
            integration_id="vasp",
            kind=PwDftScfConvergenceTestKind.K_POINTS,
            evidence_id="left-evidence",
            coordinates=_KPOINT_COORDINATES,
            energies=_LEFT_AXIS_ENERGIES,
            policy=PwDftScfConvergencePolicy(**_POLICY_KWARGS),
        )
        right_policy_kwargs: _PolicyKwargs = {
            **_POLICY_KWARGS,
            "tolerance_mev_per_atom": 2.0,
        }
        right = _test(
            test_id="right-kpoints",
            integration_id="quantum-espresso",
            kind=PwDftScfConvergenceTestKind.K_POINTS,
            evidence_id="right-evidence",
            coordinates=_KPOINT_COORDINATES,
            energies=_RIGHT_AXIS_ENERGIES,
            policy=PwDftScfConvergencePolicy(**right_policy_kwargs),
        )

        with self.assertRaisesRegex(ValueError, "same convergence policy"):
            PwDftScfConvergenceComparisonRequest(
                comparison_id="mismatched-policy",
                input_alignment_id="silicon-input-alignment",
                left=left,
                right=right,
            )


def _compare_axis(
    *,
    kind: PwDftScfConvergenceTestKind,
    coordinates: tuple[tuple[int, float], ...],
) -> PwDftScfConvergenceComparisonAnalysis:
    return _compare(
        kind=kind,
        coordinates=coordinates,
        left_energies=_LEFT_AXIS_ENERGIES,
        right_energies=_RIGHT_AXIS_ENERGIES,
    )


def _compare(
    *,
    kind: PwDftScfConvergenceTestKind,
    coordinates: tuple[tuple[int, float], ...],
    left_energies: tuple[float, ...],
    right_energies: tuple[float, ...],
) -> PwDftScfConvergenceComparisonAnalysis:
    policy = PwDftScfConvergencePolicy(**_POLICY_KWARGS)
    request = PwDftScfConvergenceComparisonRequest(
        comparison_id=f"silicon-{kind.value}-comparison",
        input_alignment_id="silicon-scf-input-alignment-v1",
        left=_test(
            test_id=f"vasp-{kind.value}",
            integration_id="vasp",
            kind=kind,
            evidence_id=f"vasp-{kind.value}-evidence",
            coordinates=coordinates,
            energies=left_energies,
            policy=policy,
        ),
        right=_test(
            test_id=f"qe-{kind.value}",
            integration_id="quantum-espresso",
            kind=kind,
            evidence_id=f"qe-{kind.value}-evidence",
            coordinates=coordinates,
            energies=right_energies,
            policy=policy,
        ),
    )
    return PwDftScfConvergenceComparator().compare(request)


def _test(
    *,
    test_id: str,
    integration_id: str,
    kind: PwDftScfConvergenceTestKind,
    evidence_id: str,
    coordinates: tuple[tuple[int, float], ...],
    energies: tuple[float, ...],
    policy: PwDftScfConvergencePolicy,
) -> PwDftScfConvergenceTest:
    return PwDftScfConvergenceTest(
        test_id=test_id,
        integration_id=CalculatorIntegrationId(value=integration_id),
        kind=kind,
        observations=tuple(
            PwDftScfEnergyObservation(
                coordinate=PwDftScfConvergenceCoordinate(
                    mesh_density=mesh,
                    wavefunction_cutoff_ev=cutoff,
                ),
                total_energy_ev_per_atom=energy,
            )
            for (mesh, cutoff), energy in zip(coordinates, energies, strict=True)
        ),
        policy=policy,
        evidence_id=evidence_id,
    )


def _assert_deltas(
    case: unittest.TestCase,
    actual: tuple[float, ...] | None,
    expected: tuple[float, ...],
) -> None:
    case.assertIsNotNone(actual)
    assert actual is not None
    case.assertEqual(len(actual), len(expected))
    for actual_value, expected_value in zip(actual, expected, strict=True):
        case.assertAlmostEqual(actual_value, expected_value)


if __name__ == "__main__":
    unittest.main()
