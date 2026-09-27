"""Engine-neutral CPN topology for relaxation application composition."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PwDftRelaxationWorkflowDefinition:
    """Name application places and transitions without implementing a kernel."""

    name: str
    places: tuple[str, ...]
    transitions: tuple[str, ...]


def pw_dft_relaxation_workflow_definition() -> PwDftRelaxationWorkflowDefinition:
    """Return the fixed projection and external-authority handoff lifecycle."""
    return PwDftRelaxationWorkflowDefinition(
        name="pw_dft_relaxation",
        places=(
            "campaign",
            "projection_action",
            "input_projected",
            "external_authority_required",
            "terminal_outcome",
        ),
        transitions=(
            "start_projection",
            "accept_projection",
            "reject_projection",
            "record_external_handoff",
        ),
    )
