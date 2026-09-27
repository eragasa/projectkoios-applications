"""Deterministic replay of normalized plane-wave SCF convergence evidence."""

from __future__ import annotations

from dataclasses import dataclass

from projectkoios.applications.pw_dft_scf.convergence.assessment import (
    EnergyGridConvergenceAssessmentRequest,
    EnergyGridConvergenceAssessor,
)
from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceAssessment,
    PwDftScfEnergyObservation,
)
from projectkoios.applications.pw_dft_scf.convergence.controller import (
    ExtendPwDftScfConvergence,
    PwDftScfConvergenceAccepted,
    PwDftScfConvergenceController,
)
from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)
from projectkoios.simulations.calculator import CalculatorIntegrationId
from projectkoios.simulations.dft.pw.scf.base import PwDftScfObject


class PwDftScfConvergenceReplayError(ValueError):
    """Report evidence that cannot reproduce its declared policy lifecycle."""


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceReplayEvidence(PwDftScfObject):
    """Carry provider-normalized observations without copying native artifacts."""

    evidence_id: str
    integration_id: CalculatorIntegrationId
    policy: PwDftScfConvergencePolicy
    initial_observations: tuple[PwDftScfEnergyObservation, ...]
    extension_observations: tuple[PwDftScfEnergyObservation, ...]
    source_evidence_reference: str

    def __post_init__(self) -> None:
        for label, value in (
            ("evidence_id", self.evidence_id),
            ("source_evidence_reference", self.source_evidence_reference),
        ):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError(f"{label} must be nonempty and stripped")
        if type(self.integration_id) is not CalculatorIntegrationId:
            raise TypeError("integration_id must be a CalculatorIntegrationId")
        if type(self.policy) is not PwDftScfConvergencePolicy:
            raise TypeError("policy must be a PwDftScfConvergencePolicy")
        self._validate_observations(self.initial_observations, "initial_observations")
        self._validate_observations(
            self.extension_observations,
            "extension_observations",
        )
        initial_coordinates = {
            observation.coordinate for observation in self.initial_observations
        }
        extension_coordinates = {
            observation.coordinate for observation in self.extension_observations
        }
        if initial_coordinates & extension_coordinates:
            raise ValueError("initial and extension coordinates must be disjoint")

    @staticmethod
    def _validate_observations(
        observations: tuple[PwDftScfEnergyObservation, ...],
        label: str,
    ) -> None:
        if type(observations) is not tuple or not observations:
            raise ValueError(f"{label} must be a nonempty tuple")
        if any(type(item) is not PwDftScfEnergyObservation for item in observations):
            raise TypeError(f"{label} must contain PwDftScfEnergyObservation values")
        coordinates = tuple(item.coordinate for item in observations)
        if len(coordinates) != len(set(coordinates)):
            raise ValueError(f"{label} coordinates must be unique")


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceReplayResult(PwDftScfObject):
    """Record the reproduced extension and terminal policy outcomes."""

    evidence_id: str
    integration_id: CalculatorIntegrationId
    observation_count: int
    initial_assessment: PwDftScfConvergenceAssessment
    initial_extension: ExtendPwDftScfConvergence
    final_assessment: PwDftScfConvergenceAssessment
    terminal_outcome: PwDftScfConvergenceAccepted
    source_evidence_reference: str


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceReplayer(PwDftScfObject):
    """Replay normalized evidence without parsing or executing a calculator."""

    def replay(
        self,
        evidence: PwDftScfConvergenceReplayEvidence,
    ) -> PwDftScfConvergenceReplayResult:
        """Require evidence to reproduce one extension followed by acceptance."""
        if type(evidence) is not PwDftScfConvergenceReplayEvidence:
            raise TypeError("evidence must be PwDftScfConvergenceReplayEvidence")
        assessor = EnergyGridConvergenceAssessor()
        controller = PwDftScfConvergenceController()
        initial_assessment = assessor.assess(
            EnergyGridConvergenceAssessmentRequest(
                observations=evidence.initial_observations,
                policy=evidence.policy,
            )
        )
        initial_decision = controller.decide(initial_assessment)
        if type(initial_decision) is not ExtendPwDftScfConvergence:
            raise PwDftScfConvergenceReplayError(
                "initial observations do not reproduce one grid extension"
            )
        requested = set(initial_decision.coordinates)
        retained = {
            observation.coordinate for observation in evidence.extension_observations
        }
        if requested != retained:
            raise PwDftScfConvergenceReplayError(
                "extension observations do not match the requested coordinates"
            )
        observations = evidence.initial_observations + evidence.extension_observations
        final_assessment = assessor.assess(
            EnergyGridConvergenceAssessmentRequest(
                observations=observations,
                policy=evidence.policy,
            )
        )
        terminal_outcome = controller.decide(final_assessment)
        if type(terminal_outcome) is not PwDftScfConvergenceAccepted:
            raise PwDftScfConvergenceReplayError(
                "complete observations do not reproduce policy acceptance"
            )
        return PwDftScfConvergenceReplayResult(
            evidence_id=evidence.evidence_id,
            integration_id=evidence.integration_id,
            observation_count=len(observations),
            initial_assessment=initial_assessment,
            initial_extension=initial_decision,
            final_assessment=final_assessment,
            terminal_outcome=terminal_outcome,
            source_evidence_reference=evidence.source_evidence_reference,
        )
