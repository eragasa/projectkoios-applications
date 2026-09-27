from __future__ import annotations

import unittest

from projectkoios.applications.pw_dft_scf.comparison import (
    PwDftScfComparator,
    PwDftScfComparisonInterpretation,
    PwDftScfComparisonRequest,
    PwDftScfEnergyAlignment,
    PwDftScfEnergyAlignmentDeclaration,
    PwDftScfEnergyAlignmentKind,
)
from projectkoios.simulations.calculator import CalculatorIntegrationId
from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfNativeArtifact,
    PwDftScfObservation,
    PwDftScfResult,
)


class PwDftScfComparatorTest(unittest.TestCase):
    def test_binds_a_predeclared_reference_to_a_successful_result(self) -> None:
        result = _result("left", "left.out", "a" * 64, -2.0, 3, 300.0)
        declaration = PwDftScfEnergyAlignmentDeclaration(
            kind=PwDftScfEnergyAlignmentKind.EXPLICIT_REFERENCE,
            reference_energy_ev_per_atom=-0.25,
            reference_id="reference-evidence",
            qualification="Explicit test reference.",
        )

        alignment = declaration.bind(result)

        self.assertIs(alignment.result, result)
        self.assertEqual(alignment.aligned_energy_ev_per_atom, -0.75)

    def test_reproduces_the_qualified_retained_silicon_difference(self) -> None:
        qe = _result(
            integration_id="quantum-espresso",
            artifact_id="qe/pw.out",
            sha256="e" * 64,
            total_energy_ev=-310.74456218311093,
            iterations=5,
            cutoff_ev=408.17079368982,
        )
        vasp = _result(
            integration_id="vasp",
            artifact_id="vasp/OUTCAR",
            sha256="1" * 64,
            total_energy_ev=-10.84056782,
            iterations=11,
            cutoff_ev=400.0,
        )
        request = PwDftScfComparisonRequest(
            comparison_id="silicon-qe-minus-vasp",
            input_alignment_id="silicon-scf-input-alignment-v1",
            left=PwDftScfEnergyAlignment(
                result=qe,
                kind=PwDftScfEnergyAlignmentKind.EXPLICIT_REFERENCE,
                reference_energy_ev_per_atom=-149.96614065567152,
                reference_id="qe-upf-total-psenergy",
                qualification=(
                    "QE UPF-header reference; not a matched isolated-atom result."
                ),
            ),
            right=PwDftScfEnergyAlignment(result=vasp),
        )

        analysis = PwDftScfComparator().compare(request)

        self.assertEqual(
            analysis.interpretation,
            PwDftScfComparisonInterpretation.EXPLICIT_REFERENCE_ALIGNED,
        )
        self.assertAlmostEqual(
            analysis.aligned_left_minus_right_mev_per_atom,
            14.143474116059096,
        )
        self.assertAlmostEqual(
            analysis.native_left_minus_right_mev_per_atom,
            -149951.99718155546,
        )
        self.assertTrue(analysis.irreducible_kpoint_counts_match)
        self.assertAlmostEqual(
            analysis.wavefunction_cutoff_left_minus_right_ev or 0.0,
            8.17079368982,
        )
        self.assertIn(
            "Explicit reference-zero alignment is not a substitute for matched "
            "relative-energy calculations.",
            analysis.qualifications,
        )

    def test_native_comparison_is_descriptive_only(self) -> None:
        request = PwDftScfComparisonRequest(
            comparison_id="native-comparison",
            input_alignment_id="aligned-inputs",
            left=PwDftScfEnergyAlignment(
                _result("left", "left.out", "a" * 64, -2.0, 3, None)
            ),
            right=PwDftScfEnergyAlignment(
                _result("right", "right.out", "b" * 64, -1.0, 4, None)
            ),
        )

        analysis = PwDftScfComparator().compare(request)

        self.assertEqual(
            analysis.interpretation,
            PwDftScfComparisonInterpretation.NATIVE_DESCRIPTIVE,
        )
        self.assertEqual(analysis.native_left_minus_right_mev_per_atom, -500.0)
        self.assertEqual(
            analysis.native_left_minus_right_mev_per_atom,
            analysis.aligned_left_minus_right_mev_per_atom,
        )
        self.assertIsNone(analysis.wavefunction_cutoff_left_minus_right_ev)

    def test_rejects_an_unconverged_result(self) -> None:
        result = _result(
            "left",
            "left.out",
            "a" * 64,
            -2.0,
            3,
            300.0,
            converged=False,
        )

        with self.assertRaisesRegex(ValueError, "completed, converged"):
            PwDftScfEnergyAlignment(result)

    def test_rejects_two_paths_to_the_same_integration_artifact_bytes(self) -> None:
        left = _result("vasp", "first/OUTCAR", "a" * 64, -2.0, 3, 300.0)
        right = _result("vasp", "second/OUTCAR", "a" * 64, -2.0, 3, 300.0)

        with self.assertRaisesRegex(ValueError, "distinct native artifacts"):
            PwDftScfComparisonRequest(
                "comparison",
                "alignment",
                PwDftScfEnergyAlignment(left),
                PwDftScfEnergyAlignment(right),
            )

    def test_rejects_mismatched_atom_counts(self) -> None:
        left = _result("left", "left.out", "a" * 64, -2.0, 3, 300.0)
        right = _result("right", "right.out", "b" * 64, -1.0, 4, 300.0, atom_count=1)

        with self.assertRaisesRegex(ValueError, "equal atom counts"):
            PwDftScfComparisonRequest(
                "comparison",
                "alignment",
                PwDftScfEnergyAlignment(left),
                PwDftScfEnergyAlignment(right),
            )


def _result(
    integration_id: str,
    artifact_id: str,
    sha256: str,
    total_energy_ev: float,
    iterations: int,
    cutoff_ev: float | None,
    *,
    atom_count: int = 2,
    converged: bool = True,
) -> PwDftScfResult:
    return PwDftScfResult(
        evaluation_id="silicon-scf",
        task_id=f"{integration_id}-task",
        observation=PwDftScfObservation(
            total_energy_ev=total_energy_ev,
            atom_count=atom_count,
            electronic_iteration_count=iterations,
            converged=converged,
            completed=True,
            native_artifact=PwDftScfNativeArtifact(
                integration_id=CalculatorIntegrationId(integration_id),
                artifact_id=artifact_id,
                sha256=sha256,
                byte_size=100,
            ),
            program_version="test",
            irreducible_kpoint_count=29,
            wavefunction_cutoff_ev=cutoff_ev,
        ),
    )


if __name__ == "__main__":
    unittest.main()
