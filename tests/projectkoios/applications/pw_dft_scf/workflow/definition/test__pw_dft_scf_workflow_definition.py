from __future__ import annotations

import unittest

from projectkoios.applications.pw_dft_scf.workflow.definition import (
    pw_dft_scf_workflow_definition,
)


class PwDftScfWorkflowDefinitionTest(unittest.TestCase):
    def test_has_explicit_start_and_terminal_places(self) -> None:
        definition = pw_dft_scf_workflow_definition()

        self.assertEqual(definition.name, "dft_pw_scf")
        self.assertIn("workflow_start", definition.places)
        self.assertIn("terminal_outcome", definition.places)
        self.assertIn("start_workflow", definition.transitions)
        self.assertIn("accept_analysis_failure", definition.transitions)


if __name__ == "__main__":
    unittest.main()
