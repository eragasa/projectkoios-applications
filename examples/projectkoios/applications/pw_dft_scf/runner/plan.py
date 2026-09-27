"""Common convergence-plan runner for configured silicon campaigns."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from examples.projectkoios.applications.pw_dft_scf.runner.environment import (
    WorkflowRunnerEnvironment,
)
from projectkoios.applications.pw_dft_scf.recipe import (
    PwDftScfCutoffConvergenceRecipe,
    PwDftScfGridConvergenceRecipe,
    PwDftScfKpointConvergenceRecipe,
)

_CONVERGENCE_RECIPE_TYPES = (
    PwDftScfKpointConvergenceRecipe,
    PwDftScfCutoffConvergenceRecipe,
    PwDftScfGridConvergenceRecipe,
)


@dataclass(frozen=True, slots=True)
class ConvergencePlanRunner:
    """Render calculator-neutral child coordinates from shared configuration."""

    environment: WorkflowRunnerEnvironment

    def plan(self, campaign_path: Path) -> dict[str, object]:
        """Validate one campaign and return its detached coordinate plan."""
        loaded = self.environment.loader.load(campaign_path)
        recipe = loaded.campaign.recipe
        if not isinstance(recipe, _CONVERGENCE_RECIPE_TYPES):
            raise ValueError("campaign must declare a convergence recipe")
        return {
            "campaign_id": recipe.campaign_id,
            "integration_id": loaded.campaign.integration_id.value,
            "recipe_type": type(recipe).__name__,
            "structure_id": loaded.structure_id,
            "coordinates": [
                {
                    "mesh_density": coordinate.mesh_density,
                    "wavefunction_cutoff_ev": coordinate.wavefunction_cutoff_ev,
                }
                for coordinate in recipe.coordinates()
            ],
        }


@dataclass(frozen=True, slots=True)
class ConvergencePlanRunnerCommand:
    """Parse command paths and invoke `ConvergencePlanRunner`."""

    def run(self) -> int:
        """Print one validated calculator-neutral convergence plan."""
        parser = argparse.ArgumentParser(
            description="Print a configured silicon SCF convergence plan."
        )
        parser.add_argument("campaign", type=Path)
        parser.add_argument("--runner-config", required=True, type=Path)
        arguments = parser.parse_args()
        environment = WorkflowRunnerEnvironment.load(arguments.runner_config.resolve())
        payload = ConvergencePlanRunner(environment=environment).plan(
            campaign_path=arguments.campaign.resolve()
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(ConvergencePlanRunnerCommand().run())
