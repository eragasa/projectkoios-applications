"""Configuration boundaries for calculator-neutral SCF campaigns."""

from __future__ import annotations

from dataclasses import dataclass

from projectkoios.applications.pw_dft_scf.recipe import PwDftScfRecipe
from projectkoios.simulations.calculator import CalculatorIntegrationId
from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfObject,
)


@dataclass(frozen=True, slots=True)
class PwDftScfRuntimeConfiguration(PwDftScfObject):
    """Bound engine-local progress independently of calculator execution policy."""

    maximum_internal_firings: int = 1000

    def __post_init__(self) -> None:
        if (
            type(self.maximum_internal_firings) is not int
            or self.maximum_internal_firings <= 0
        ):
            raise ValueError("maximum_internal_firings must be a positive integer")


@dataclass(frozen=True, slots=True)
class PwDftScfCampaignConfiguration(PwDftScfObject):
    """Select a registered backend for one scientific recipe and runtime bound."""

    integration_id: CalculatorIntegrationId
    recipe: PwDftScfRecipe
    runtime: PwDftScfRuntimeConfiguration

    def __post_init__(self) -> None:
        if type(self.integration_id) is not CalculatorIntegrationId:
            raise TypeError("integration_id must be a CalculatorIntegrationId")
        if not isinstance(self.recipe, PwDftScfRecipe):
            raise TypeError("recipe must inherit from PwDftScfRecipe")
        if type(self.runtime) is not PwDftScfRuntimeConfiguration:
            raise TypeError("runtime must be a PwDftScfRuntimeConfiguration")
