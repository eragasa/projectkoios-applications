from __future__ import annotations

import unittest

from projectkoios.applications.pw_dft_relaxation.workflow.definition import (
    pw_dft_relaxation_workflow_definition,
)


class PwDftRelaxationWorkflowDefinitionTest(unittest.TestCase):
    def test_stops_at_external_authority_handoff(self) -> None:
        definition = pw_dft_relaxation_workflow_definition()

        self.assertIn("external_authority_required", definition.places)
        self.assertIn("record_external_handoff", definition.transitions)
        self.assertNotIn("execute_calculator", definition.transitions)
        self.assertEqual(len(definition.places), len(set(definition.places)))
        self.assertEqual(len(definition.transitions), len(set(definition.transitions)))


if __name__ == "__main__":
    unittest.main()
