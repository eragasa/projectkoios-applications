"""Common declared-artifact replay runner for silicon single-SCF calculations."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from examples.projectkoios.applications.pw_dft_scf.runner.environment import (  # noqa: E501
    WorkflowRunnerEnvironment,
)
from examples.projectkoios.applications.pw_dft_scf.workflow.workflow import (  # noqa: E501
    LocalPwDftScfWorkflow,
)
from projectkoios.integrations.quantumespresso.pw.scf import (
    integration as qe_integration,
)
from projectkoios.integrations.quantumespresso.pw.scf import (
    projection as qe_projection,
)
from projectkoios.integrations.vasp.pw_dft_scf import (
    integration as vasp_integration,
)
from projectkoios.integrations.vasp.pw_dft_scf import (
    projection as vasp_projection,
)
from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfWorkflowOutcome,
)
from projectkoios.simulations.dft.pw.scf.handler import (
    ReplayPwDftScfActionHandler,
    ReplayPwDftScfTask,
)
from projectkoios.simulations.dft.pw.scf.integration import (
    PwDftScfIntegration,
)


@dataclass(frozen=True, slots=True)
class DeclaredScfReplayRunner:
    """Drive the shared child workflow using a configured output artifact."""

    environment: WorkflowRunnerEnvironment
    artifact_root: Path

    def replay(self, campaign_path: Path) -> PwDftScfWorkflowOutcome:
        """Replay one campaign without executing its external calculator."""
        loaded = self.environment.loader.load(campaign_path)
        replay = loaded.replay
        if replay is None:
            raise ValueError("calculation does not declare a replay artifact")
        integration = self._integration(
            integration_id=loaded.campaign.integration_id.value,
            projection_profile_id=loaded.projection_profile_id,
        )
        workflow = LocalPwDftScfWorkflow(
            evaluation_id=replay.evaluation_id,
            runtime=loaded.campaign.runtime,
        )
        handler = ReplayPwDftScfActionHandler(
            integration=integration,
            tasks=(
                ReplayPwDftScfTask(
                    evaluation_id=replay.evaluation_id,
                    task_id=replay.task_id,
                    output_artifact_id=replay.output_artifact_id,
                ),
            ),
        )
        while workflow.outcome() is None:
            actions = workflow.pending_actions()
            if len(actions) != 1:
                raise RuntimeError("replay requires exactly one pending SCF action")
            for event in handler.handle(actions[0]):
                workflow.accept(event)
        outcome = workflow.outcome()
        if outcome is None:
            raise RuntimeError("replayed workflow did not terminate")
        return outcome

    def _integration(
        self,
        *,
        integration_id: str,
        projection_profile_id: str,
    ) -> PwDftScfIntegration:
        """Construct one integration from the reviewed source-controlled set."""
        if integration_id == qe_projection.QE_SCF_INTEGRATION_ID.value:
            return qe_integration.QePwDftScfIntegration(
                artifact_root=self.artifact_root,
                projection_configuration=(
                    self.environment.loader.qe_projection_configuration(
                        projection_profile_id
                    )
                ),
            )
        if integration_id == vasp_projection.VASP_SCF_INTEGRATION_ID.value:
            return vasp_integration.VaspScfIntegration(
                artifact_root=self.artifact_root,
                projection_configuration=(
                    self.environment.loader.vasp_projection_configuration(
                        projection_profile_id
                    )
                ),
            )
        raise ValueError(f"unsupported integration: {integration_id}")


@dataclass(frozen=True, slots=True)
class DeclaredScfReplayRunnerCommand:
    """Parse command paths and invoke `DeclaredScfReplayRunner`."""

    def run(self) -> int:
        """Print one workflow outcome reconstructed from a declared artifact."""
        parser = argparse.ArgumentParser(
            description="Replay a configured silicon single-SCF output artifact."
        )
        parser.add_argument("campaign", type=Path)
        parser.add_argument("--runner-config", required=True, type=Path)
        parser.add_argument("--artifact-root", required=True, type=Path)
        arguments = parser.parse_args()
        environment = WorkflowRunnerEnvironment.load(arguments.runner_config.resolve())
        outcome = DeclaredScfReplayRunner(
            environment=environment,
            artifact_root=arguments.artifact_root.resolve(),
        ).replay(arguments.campaign.resolve())
        print(json.dumps(asdict(outcome), indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(DeclaredScfReplayRunnerCommand().run())
