"""Reusable convergence-controller actions and terminal outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceAssessment,
    PwDftScfConvergenceCoordinate,
)
from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfAction,
    PwDftScfWorkflowOutcome,
)


@dataclass(frozen=True, slots=True)
class ExtendPwDftScfConvergence(PwDftScfAction):
    """Request child workflows for newly proposed convergence coordinates."""

    coordinates: tuple[PwDftScfConvergenceCoordinate, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceAccepted(PwDftScfWorkflowOutcome):
    """Terminate a campaign after its declared criterion is satisfied."""

    assessment: PwDftScfConvergenceAssessment


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceBudgetExhausted(PwDftScfWorkflowOutcome):
    """Terminate a campaign that cannot extend within its declared bounds."""

    assessment: PwDftScfConvergenceAssessment


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceController:
    """Route any calculator-neutral assessment to extend, accept, or exhaust."""

    def decide(
        self,
        assessment: PwDftScfConvergenceAssessment,
    ) -> (
        ExtendPwDftScfConvergence
        | PwDftScfConvergenceAccepted
        | PwDftScfConvergenceBudgetExhausted
    ):
        """Return the unique deterministic next action or terminal outcome."""
        if assessment.converged:
            return PwDftScfConvergenceAccepted(assessment)
        if assessment.can_extend:
            return ExtendPwDftScfConvergence(
                assessment.requested_points,
                assessment.reason,
            )
        return PwDftScfConvergenceBudgetExhausted(assessment)
