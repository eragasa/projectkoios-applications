"""Application-owned composition for plane-wave DFT relaxation input planning."""

from __future__ import annotations

import re
from dataclasses import dataclass

from projectkoios.simulations.calculator import CalculatorIntegrationId
from projectkoios.simulations.dft.pw.relaxation.base import PwDftRelaxationRequest
from projectkoios.simulations.dft.pw.relaxation.integration import (
    PwDftRelaxationInputProjection,
    PwDftRelaxationInputWrapper,
    PwDftRelaxationIntegrationRegistry,
)

_IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True, slots=True)
class PwDftRelaxationCampaign:
    """Bind application identity and provider selection to neutral intent."""

    campaign_id: str
    integration_id: CalculatorIntegrationId
    request: PwDftRelaxationRequest

    def __post_init__(self) -> None:
        if type(self.campaign_id) is not str or not _IDENTIFIER.fullmatch(
            self.campaign_id
        ):
            raise ValueError("campaign_id must be a lowercase slug")
        if type(self.integration_id) is not CalculatorIntegrationId:
            raise TypeError("integration_id must be a CalculatorIntegrationId")
        if type(self.request) is not PwDftRelaxationRequest:
            raise TypeError("request must be a PwDftRelaxationRequest")


@dataclass(frozen=True, slots=True)
class PwDftRelaxationExecutionHandoff:
    """Describe prepared inputs while leaving execution authority external."""

    campaign_id: str
    integration_id: CalculatorIntegrationId
    rendered_input_filenames: tuple[str, ...]
    required_external_inputs: tuple[str, ...]
    authority_requirement: str = "separate-explicit-external-authority-required"

    def __post_init__(self) -> None:
        if type(self.campaign_id) is not str or not _IDENTIFIER.fullmatch(
            self.campaign_id
        ):
            raise ValueError("campaign_id must be a lowercase slug")
        if type(self.integration_id) is not CalculatorIntegrationId:
            raise TypeError("integration_id must be a CalculatorIntegrationId")
        if not self.rendered_input_filenames:
            raise ValueError("rendered_input_filenames must not be empty")
        for label, values in (
            ("rendered_input_filenames", self.rendered_input_filenames),
            ("required_external_inputs", self.required_external_inputs),
        ):
            if type(values) is not tuple or len(values) != len(set(values)):
                raise ValueError(f"{label} must be a unique tuple")
            if any(type(value) is not str or not value for value in values):
                raise ValueError(f"{label} must contain nonempty strings")
        if self.authority_requirement != (
            "separate-explicit-external-authority-required"
        ):
            raise ValueError("application composition cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class PwDftRelaxationCompositionResult:
    """Return projected inputs and a non-authorizing external handoff."""

    campaign: PwDftRelaxationCampaign
    projection: PwDftRelaxationInputProjection
    execution_handoff: PwDftRelaxationExecutionHandoff


@dataclass(frozen=True, slots=True)
class PwDftRelaxationComposer:
    """Compose neutral intent with one installed provider projection."""

    registry: PwDftRelaxationIntegrationRegistry

    def __post_init__(self) -> None:
        if type(self.registry) is not PwDftRelaxationIntegrationRegistry:
            raise TypeError("registry must be a PwDftRelaxationIntegrationRegistry")

    def compose(
        self,
        campaign: PwDftRelaxationCampaign,
    ) -> PwDftRelaxationCompositionResult:
        """Project input only; never invoke or authorize a calculator."""
        if type(campaign) is not PwDftRelaxationCampaign:
            raise TypeError("campaign must be a PwDftRelaxationCampaign")
        projection = PwDftRelaxationInputWrapper(self.registry).project(
            integration_id=campaign.integration_id,
            request=campaign.request,
        )
        return PwDftRelaxationCompositionResult(
            campaign=campaign,
            projection=projection,
            execution_handoff=PwDftRelaxationExecutionHandoff(
                campaign_id=campaign.campaign_id,
                integration_id=campaign.integration_id,
                rendered_input_filenames=tuple(
                    item.filename for item in projection.rendered_inputs
                ),
                required_external_inputs=projection.required_external_inputs,
            ),
        )
