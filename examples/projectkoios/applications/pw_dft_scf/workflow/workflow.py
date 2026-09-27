"""Example-only SNAKES implementation of the common SCF workflow façade."""

from __future__ import annotations

from typing import cast

from projectkoios.applications.pw_dft_scf.configuration import (
    PwDftScfRuntimeConfiguration,
)
from projectkoios.applications.pw_dft_scf.workflow.base import (
    PwDftScfWorkflowStatus,
)
from projectkoios.applications.pw_dft_scf.workflow.facade import (
    PwDftScfWorkflowFacade,
)
from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfAction,
    PwDftScfEvent,
    PwDftScfWorkflowOutcome,
)
from projectkoios.simulations.dft.pw.scf.events import (
    PwDftScfOutputAnalyzed,
    PwDftScfTaskCompleted,
    PwDftScfTaskFailed,
    PwDftScfTaskRegistered,
    PwDftScfTaskSubmitted,
)

from .net import build_dft_pw_scf_net
from .runtime import LocalSnakesRun

_EVENT_PLACES = {
    PwDftScfTaskRegistered: "task_registered",
    PwDftScfTaskSubmitted: "task_submitted",
    PwDftScfTaskCompleted: "task_completed",
    PwDftScfTaskFailed: "task_failed",
    PwDftScfOutputAnalyzed: "output_analyzed",
}
_ACTION_PLACES = ("registration_action", "submission_action", "analysis_action")


class LocalPwDftScfWorkflow(PwDftScfWorkflowFacade):
    """Drive a private SNAKES net through calculator-neutral domain values."""

    __slots__ = ("_runtime",)

    def __init__(
        self,
        evaluation_id: str,
        runtime: PwDftScfRuntimeConfiguration,
    ) -> None:
        """Create one net and advance it to its first external action."""
        self._runtime = LocalSnakesRun(
            build_dft_pw_scf_net(evaluation_id),
            maximum_firings=runtime.maximum_internal_firings,
        )
        self._runtime.drain_unique()

    def pending_actions(self) -> tuple[PwDftScfAction, ...]:
        """Return detached actions requested by the current marking."""
        return tuple(
            cast(PwDftScfAction, token)
            for place in _ACTION_PLACES
            for token in self._runtime.tokens(place)
        )

    def accept(self, event: PwDftScfEvent) -> tuple[str, ...]:
        """Add one typed event at its boundary place and drain internal work."""
        place = next(
            (
                candidate
                for event_type, candidate in _EVENT_PLACES.items()
                if isinstance(event, event_type)
            ),
            None,
        )
        if place is None:
            raise TypeError(f"unsupported SCF event: {type(event).__name__}")
        self._runtime.add_token(place, event)
        return self._runtime.drain_unique()

    def status(self) -> PwDftScfWorkflowStatus:
        """Project the private marking into an application-facing status."""
        if self._runtime.tokens("terminal_outcome"):
            return PwDftScfWorkflowStatus.terminated
        if self._runtime.tokens("analysis_action"):
            return PwDftScfWorkflowStatus.analyzing
        if self._runtime.tokens("task_waiting"):
            return PwDftScfWorkflowStatus.waiting_for_completion
        if self._runtime.tokens("submission_action"):
            return PwDftScfWorkflowStatus.awaiting_submission
        if self._runtime.tokens("registration_action"):
            return PwDftScfWorkflowStatus.awaiting_registration
        return PwDftScfWorkflowStatus.ready

    def outcome(self) -> PwDftScfWorkflowOutcome | None:
        """Return the unique terminal outcome without exposing mutable net state."""
        outcomes = self._runtime.tokens("terminal_outcome")
        if not outcomes:
            return None
        if len(outcomes) != 1:
            raise RuntimeError("SCF workflow must contain exactly one terminal outcome")
        return cast(PwDftScfWorkflowOutcome, outcomes[0])
