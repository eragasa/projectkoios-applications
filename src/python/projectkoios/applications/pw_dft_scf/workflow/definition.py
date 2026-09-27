"""Fixed engine-neutral definition of the single-SCF lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

from projectkoios.simulations.dft.pw.scf.base import PwDftScfObject


@dataclass(frozen=True, slots=True)
class PwDftScfWorkflowDefinition(PwDftScfObject):
    """Name the fixed places and transitions required from an engine binding."""

    name: str
    places: tuple[str, ...]
    transitions: tuple[str, ...]


def pw_dft_scf_workflow_definition() -> PwDftScfWorkflowDefinition:
    """Return the fixed single-calculation lifecycle with explicit boundaries."""
    return PwDftScfWorkflowDefinition(
        name="dft_pw_scf",
        places=(
            "workflow_start",
            "request",
            "registration_action",
            "task_registered",
            "submission_action",
            "task_submitted",
            "task_waiting",
            "task_completed",
            "task_failed",
            "analysis_action",
            "output_analyzed",
            "terminal_outcome",
        ),
        transitions=(
            "start_workflow",
            "accept_registration",
            "accept_submission",
            "accept_completion",
            "accept_analysis",
            "reject_analysis",
            "accept_analysis_failure",
            "accept_failure",
        ),
    )
