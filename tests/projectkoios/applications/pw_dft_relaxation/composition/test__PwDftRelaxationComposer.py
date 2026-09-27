from __future__ import annotations

import unittest

import pytest

from projectkoios.applications.pw_dft_relaxation.composition import (
    PwDftRelaxationCampaign,
    PwDftRelaxationComposer,
    PwDftRelaxationExecutionHandoff,
)
from projectkoios.simulations.calculator import CalculatorIntegrationId
from projectkoios.simulations.dft.pw.relaxation.base import (
    PwDftRelaxationRequest,
    PwDftRelaxationScope,
)
from projectkoios.simulations.dft.pw.relaxation.capabilities import (
    PwDftRelaxationBackendDescription,
    PwDftRelaxationImplementationStatus,
    PwDftRelaxationInputModel,
)
from projectkoios.simulations.dft.pw.relaxation.integration import (
    PwDftRelaxationInputProjection,
    PwDftRelaxationIntegration,
    PwDftRelaxationIntegrationRegistry,
    PwDftRelaxationRenderedInput,
)
from tests.projectkoios.applications.support import silicon_relaxation_request


class _ProjectionOnlyIntegration(PwDftRelaxationIntegration):
    @property
    def description(self) -> PwDftRelaxationBackendDescription:
        return PwDftRelaxationBackendDescription(
            integration_id=CalculatorIntegrationId("projection-only"),
            display_name="Projection-only verification integration",
            input_model=PwDftRelaxationInputModel.QE_PW_NAMELISTS_AND_CARDS,
            status=PwDftRelaxationImplementationStatus.INPUT_PROJECTION_IMPLEMENTED,
            supported_scopes=(PwDftRelaxationScope.ATOMIC_POSITIONS,),
            authority_urls=("https://example.invalid/projection-only",),
            qualification="Synthetic software-verification integration only.",
        )

    def project(
        self,
        request: PwDftRelaxationRequest,
    ) -> PwDftRelaxationInputProjection:
        self.assert_request(request)
        return PwDftRelaxationInputProjection(
            integration_id=self.integration_id,
            rendered_inputs=(PwDftRelaxationRenderedInput("input.in", "input\n"),),
            required_external_inputs=("Si.UPF",),
            qualification="Projection only; calculator execution is not authorized.",
        )

    @staticmethod
    def assert_request(request: PwDftRelaxationRequest) -> None:
        if type(request) is not PwDftRelaxationRequest:
            raise TypeError("request must be a PwDftRelaxationRequest")


class PwDftRelaxationComposerTest(unittest.TestCase):
    def test_composes_projection_with_non_authorizing_external_handoff(self) -> None:
        integration = _ProjectionOnlyIntegration()
        campaign = PwDftRelaxationCampaign(
            campaign_id="silicon-relaxation",
            integration_id=integration.integration_id,
            request=silicon_relaxation_request(),
        )

        result = PwDftRelaxationComposer(
            PwDftRelaxationIntegrationRegistry((integration,))
        ).compose(campaign)

        self.assertEqual(result.projection.rendered_inputs[0].filename, "input.in")
        self.assertEqual(
            result.execution_handoff.authority_requirement,
            "separate-explicit-external-authority-required",
        )
        self.assertFalse(hasattr(result.execution_handoff, "execute"))
        self.assertFalse(hasattr(result.execution_handoff, "executable"))

    @pytest.mark.adversarial
    def test_rejects_any_application_attempt_to_change_authority_requirement(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "cannot grant execution authority",
        ):
            PwDftRelaxationExecutionHandoff(
                campaign_id="silicon-relaxation",
                integration_id=CalculatorIntegrationId("projection-only"),
                rendered_input_filenames=("input.in",),
                required_external_inputs=("Si.UPF",),
                authority_requirement="authorized",
            )


if __name__ == "__main__":
    unittest.main()
