"""Compose a relaxation campaign without granting calculator execution.

This source path is retained for transfer traceability. It is no longer a
command-line execution surface: callers provide public neutral contracts and an
installed projection integration, and receive a non-authorizing handoff.
"""

from __future__ import annotations

from projectkoios.applications.pw_dft_relaxation.composition import (
    PwDftRelaxationCampaign,
    PwDftRelaxationComposer,
    PwDftRelaxationCompositionResult,
)
from projectkoios.simulations.dft.pw.relaxation.integration import (
    PwDftRelaxationIntegrationRegistry,
)


def compose(
    campaign: PwDftRelaxationCampaign,
    registry: PwDftRelaxationIntegrationRegistry,
) -> PwDftRelaxationCompositionResult:
    """Project inputs and return an external-authority-required handoff."""
    return PwDftRelaxationComposer(registry).compose(campaign)
