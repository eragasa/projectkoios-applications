"""Abstract engine-hiding façade for one calculator-neutral SCF workflow."""

from __future__ import annotations

from abc import ABC, abstractmethod

from projectkoios.applications.pw_dft_scf.workflow.base import (
    PwDftScfWorkflowStatus,
)
from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfAction,
    PwDftScfEvent,
    PwDftScfWorkflowOutcome,
)


class PwDftScfWorkflowFacade(ABC):
    """Hide a replaceable workflow engine behind calculator-neutral operations."""

    __slots__ = ()

    @abstractmethod
    def pending_actions(self) -> tuple[PwDftScfAction, ...]:
        """Return detached external actions represented by the marking."""
        raise NotImplementedError

    @abstractmethod
    def accept(self, event: PwDftScfEvent) -> tuple[str, ...]:
        """Accept one correlated event and return fired transition names."""
        raise NotImplementedError

    @abstractmethod
    def status(self) -> PwDftScfWorkflowStatus:
        """Return application-facing progress without exposing engine state."""
        raise NotImplementedError

    @abstractmethod
    def outcome(self) -> PwDftScfWorkflowOutcome | None:
        """Return the unique terminal outcome when represented."""
        raise NotImplementedError
