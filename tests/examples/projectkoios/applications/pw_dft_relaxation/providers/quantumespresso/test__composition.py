from __future__ import annotations

import unittest

from projectkoios.applications.pw_dft_relaxation.composition import (
    PwDftRelaxationCampaign,
    PwDftRelaxationComposer,
)
from projectkoios.integrations.quantumespresso.pw.inputfile.base import (
    QeAtomicSpecies,
)
from projectkoios.integrations.quantumespresso.pw.inputfile.ions import QeIonDynamics
from projectkoios.integrations.quantumespresso.pw.relax.configuration import (
    QeRelaxProjectionConfiguration,
)
from projectkoios.integrations.quantumespresso.pw.relax.integration import (
    QePwRelaxIntegration,
)
from projectkoios.simulations.dft.pw.relaxation.integration import (
    PwDftRelaxationIntegrationRegistry,
)
from tests.projectkoios.applications.support import silicon_relaxation_request


class QuantumEspressoRelaxationCompositionTest(unittest.TestCase):
    def test_composes_real_projection_but_exposes_no_execution_authority(self) -> None:
        integration = QePwRelaxIntegration(
            QeRelaxProjectionConfiguration(
                species=(QeAtomicSpecies("Si", 28.086, "Si.test.UPF"),),
                ion_dynamics=QeIonDynamics.BFGS,
                charge_density_cutoff_ratio=8.0,
                electronic_tolerance_ry=1.0e-8,
                prefix="system",
                pseudo_dir="./",
                outdir="./tmp/",
                input_filename="pw.in",
                coordinate_precision=8,
            )
        )
        campaign = PwDftRelaxationCampaign(
            campaign_id="silicon-relaxation",
            integration_id=integration.integration_id,
            request=silicon_relaxation_request(),
        )

        result = PwDftRelaxationComposer(
            PwDftRelaxationIntegrationRegistry((integration,))
        ).compose(campaign)

        self.assertEqual(result.projection.rendered_inputs[0].filename, "pw.in")
        self.assertIn("calculation = 'relax'", result.projection.rendered_inputs[0].text)
        self.assertEqual(
            result.execution_handoff.authority_requirement,
            "separate-explicit-external-authority-required",
        )
        self.assertFalse(hasattr(result.execution_handoff, "execute"))


if __name__ == "__main__":
    unittest.main()
