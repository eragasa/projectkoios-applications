"""Qualified comparison of calculator-neutral SCF convergence tests."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum

from projectkoios.applications.pw_dft_scf.convergence.assessment import (
    EnergyAxisConvergenceAssessmentRequest,
    EnergyAxisConvergenceAssessor,
    EnergyGridConvergenceAssessmentRequest,
    EnergyGridConvergenceAssessor,
)
from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceAssessment,
    PwDftScfConvergenceAxis,
    PwDftScfConvergenceCoordinate,
    PwDftScfEnergyObservation,
)
from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)
from projectkoios.simulations.calculator import CalculatorIntegrationId
from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfObject,
)

_IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class PwDftScfConvergenceTestKind(StrEnum):
    """Identify the coordinate set varied by one convergence test."""

    K_POINTS = "k-points"
    WAVEFUNCTION_CUTOFF = "wavefunction-cutoff"
    CROSS = "cross"


class PwDftScfConvergenceComparisonInterpretation(StrEnum):
    """Bound a comparison to descriptive relative-energy convergence evidence."""

    RELATIVE_ENERGY_DESCRIPTIVE = "relative-energy-descriptive"


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceTest(PwDftScfObject):
    """Bind one backend's convergence observations to policy and evidence."""

    test_id: str
    integration_id: CalculatorIntegrationId
    kind: PwDftScfConvergenceTestKind
    observations: tuple[PwDftScfEnergyObservation, ...]
    policy: PwDftScfConvergencePolicy
    evidence_id: str

    def __post_init__(self) -> None:
        if type(self.test_id) is not str or not _IDENTIFIER.fullmatch(self.test_id):
            raise ValueError("test_id must be a lowercase slug")
        if type(self.integration_id) is not CalculatorIntegrationId:
            raise TypeError("integration_id must be a CalculatorIntegrationId")
        if type(self.kind) is not PwDftScfConvergenceTestKind:
            raise TypeError("kind must be a PwDftScfConvergenceTestKind")
        if type(self.observations) is not tuple or not self.observations:
            raise ValueError("observations must be a nonempty tuple")
        if any(
            type(item) is not PwDftScfEnergyObservation for item in self.observations
        ):
            raise TypeError(
                "observations must contain PwDftScfEnergyObservation values"
            )
        coordinates = tuple(item.coordinate for item in self.observations)
        if len(coordinates) != len(set(coordinates)):
            raise ValueError("convergence-test coordinates must be unique")
        if type(self.policy) is not PwDftScfConvergencePolicy:
            raise TypeError("policy must be a PwDftScfConvergencePolicy")
        if (
            type(self.evidence_id) is not str
            or not self.evidence_id
            or self.evidence_id != self.evidence_id.strip()
        ):
            raise ValueError("evidence_id must be nonempty and stripped")


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceComparisonRequest(PwDftScfObject):
    """Order two like-for-like convergence tests and cite input alignment."""

    comparison_id: str
    input_alignment_id: str
    left: PwDftScfConvergenceTest
    right: PwDftScfConvergenceTest

    def __post_init__(self) -> None:
        for label, value in (
            ("comparison_id", self.comparison_id),
            ("input_alignment_id", self.input_alignment_id),
        ):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError(f"{label} must be nonempty and stripped")
        if type(self.left) is not PwDftScfConvergenceTest:
            raise TypeError("left must be a PwDftScfConvergenceTest")
        if type(self.right) is not PwDftScfConvergenceTest:
            raise TypeError("right must be a PwDftScfConvergenceTest")
        if self.left.kind is not self.right.kind:
            raise ValueError("comparison requires matching convergence-test kinds")
        if self.left.policy != self.right.policy:
            raise ValueError("comparison requires the same convergence policy")
        if self.left.evidence_id == self.right.evidence_id:
            raise ValueError("comparison requires distinct evidence identifiers")


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceComparisonAnalysis(PwDftScfObject):
    """Report two assessments and their descriptive tail-delta differences."""

    request: PwDftScfConvergenceComparisonRequest
    interpretation: PwDftScfConvergenceComparisonInterpretation
    left_assessment: PwDftScfConvergenceAssessment
    right_assessment: PwDftScfConvergenceAssessment
    convergence_outcomes_match: bool
    common_coordinates: tuple[PwDftScfConvergenceCoordinate, ...]
    kpoint_tail_delta_left_minus_right_mev_per_atom: tuple[float, ...] | None
    cutoff_tail_delta_left_minus_right_mev_per_atom: tuple[float, ...] | None
    qualifications: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.request) is not PwDftScfConvergenceComparisonRequest:
            raise TypeError("request must be a PwDftScfConvergenceComparisonRequest")
        if type(self.interpretation) is not PwDftScfConvergenceComparisonInterpretation:
            raise TypeError("interpretation has the wrong type")
        for assessment in (self.left_assessment, self.right_assessment):
            if type(assessment) is not PwDftScfConvergenceAssessment:
                raise TypeError("assessments must be PwDftScfConvergenceAssessment")
        if type(self.convergence_outcomes_match) is not bool:
            raise TypeError("convergence_outcomes_match must be a boolean")
        if type(self.common_coordinates) is not tuple or any(
            type(coordinate) is not PwDftScfConvergenceCoordinate
            for coordinate in self.common_coordinates
        ):
            raise TypeError(
                "common_coordinates must contain PwDftScfConvergenceCoordinate values"
            )
        if len(self.common_coordinates) != len(set(self.common_coordinates)):
            raise ValueError("common_coordinates must be unique")
        for label, values in (
            (
                "kpoint_tail_delta_left_minus_right_mev_per_atom",
                self.kpoint_tail_delta_left_minus_right_mev_per_atom,
            ),
            (
                "cutoff_tail_delta_left_minus_right_mev_per_atom",
                self.cutoff_tail_delta_left_minus_right_mev_per_atom,
            ),
        ):
            if values is not None and (
                type(values) is not tuple
                or any(
                    type(value) is not float or not math.isfinite(value)
                    for value in values
                )
            ):
                raise TypeError(f"{label} must be a finite-float tuple or None")
        if type(self.qualifications) is not tuple or not self.qualifications:
            raise ValueError("qualifications must be a nonempty tuple")
        if any(
            type(value) is not str or not value or value != value.strip()
            for value in self.qualifications
        ):
            raise ValueError("qualifications must contain nonempty stripped strings")


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceComparator(PwDftScfObject):
    """Compare convergence behavior without comparing absolute energy zeros."""

    def compare(
        self,
        request: PwDftScfConvergenceComparisonRequest,
    ) -> PwDftScfConvergenceComparisonAnalysis:
        """Reassess both tests and report qualified descriptive differences."""
        if type(request) is not PwDftScfConvergenceComparisonRequest:
            raise TypeError("request must be a PwDftScfConvergenceComparisonRequest")
        left_assessment = self._assess(request.left)
        right_assessment = self._assess(request.right)
        left_coordinates = {
            observation.coordinate for observation in request.left.observations
        }
        right_coordinates = {
            observation.coordinate for observation in request.right.observations
        }
        common_coordinates = tuple(
            sorted(
                left_coordinates & right_coordinates,
                key=lambda coordinate: (
                    coordinate.mesh_density,
                    coordinate.wavefunction_cutoff_ev,
                ),
            )
        )
        return PwDftScfConvergenceComparisonAnalysis(
            request=request,
            interpretation=(
                PwDftScfConvergenceComparisonInterpretation.RELATIVE_ENERGY_DESCRIPTIVE
            ),
            left_assessment=left_assessment,
            right_assessment=right_assessment,
            convergence_outcomes_match=(
                left_assessment.converged == right_assessment.converged
            ),
            common_coordinates=common_coordinates,
            kpoint_tail_delta_left_minus_right_mev_per_atom=self._delta_difference(
                left_assessment.kpoint_tail_deltas_mev_per_atom,
                right_assessment.kpoint_tail_deltas_mev_per_atom,
            ),
            cutoff_tail_delta_left_minus_right_mev_per_atom=self._delta_difference(
                left_assessment.cutoff_tail_deltas_mev_per_atom,
                right_assessment.cutoff_tail_deltas_mev_per_atom,
            ),
            qualifications=(
                "The comparison uses neighboring relative-energy changes, not "
                "calculator-native absolute total energies.",
                "Matching convergence outcomes do not establish equivalent "
                "pseudopotentials, basis quality, or scientific accuracy.",
                "Cutoff coordinates retain backend- and pseudopotential-specific "
                "basis meanings even when expressed in the same energy unit.",
            ),
        )

    @staticmethod
    def _assess(
        test: PwDftScfConvergenceTest,
    ) -> PwDftScfConvergenceAssessment:
        """Dispatch one declared test to its calculator-neutral assessor."""
        if test.kind is PwDftScfConvergenceTestKind.CROSS:
            return EnergyGridConvergenceAssessor().assess(
                EnergyGridConvergenceAssessmentRequest(
                    observations=test.observations,
                    policy=test.policy,
                )
            )
        axis = (
            PwDftScfConvergenceAxis.kpoint
            if test.kind is PwDftScfConvergenceTestKind.K_POINTS
            else PwDftScfConvergenceAxis.wavefunction_cutoff
        )
        return EnergyAxisConvergenceAssessor().assess(
            EnergyAxisConvergenceAssessmentRequest(
                axis=axis,
                observations=test.observations,
                policy=test.policy,
            )
        )

    @staticmethod
    def _delta_difference(
        left: tuple[float, ...],
        right: tuple[float, ...],
    ) -> tuple[float, ...] | None:
        """Subtract equally shaped tail-delta evidence or report no comparison."""
        if not left and not right:
            return None
        if len(left) != len(right):
            return None
        return tuple(
            left_value - right_value
            for left_value, right_value in zip(left, right, strict=True)
        )
