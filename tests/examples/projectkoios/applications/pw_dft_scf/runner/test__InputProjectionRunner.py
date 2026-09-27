from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from examples.projectkoios.applications.pw_dft_scf.runner.environment import (
    WorkflowRunnerEnvironment,
)
from examples.projectkoios.applications.pw_dft_scf.runner.render_inputs import (
    InputProjectionRunner,
)


class InputProjectionRunnerTest(unittest.TestCase):
    def test_projects_every_reviewed_vasp_and_qe_campaign_without_execution(
        self,
    ) -> None:
        repository = Path(__file__).resolve().parents[6]
        example = repository / "examples/projectkoios/applications/pw_dft_scf"
        environment = WorkflowRunnerEnvironment.load(
            example / "runner/config/runner.toml"
        )
        campaigns = sorted(
            (example / "providers").glob("*/Si/primitive/**/campaign.toml")
        )
        self.assertEqual(len(campaigns), 8)

        integrations: set[str] = set()
        with tempfile.TemporaryDirectory() as temporary_directory:
            for index, campaign in enumerate(campaigns):
                output = Path(temporary_directory) / str(index)
                rendered = InputProjectionRunner(environment).render(campaign, output)
                self.assertGreaterEqual(len(rendered), 2)
                metadata = json.loads(
                    (output / "input-projection.json").read_text(encoding="ascii")
                )
                integrations.add(str(metadata["integration_id"]))
        self.assertEqual(
            integrations,
            {"quantum-espresso", "vasp"},
        )


if __name__ == "__main__":
    unittest.main()
