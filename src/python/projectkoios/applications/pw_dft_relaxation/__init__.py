"""Plane-wave DFT structural-relaxation application composition."""

from projectkoios.applications._optional_dependencies import (
    require_simulation_contract,
)

require_simulation_contract("projectkoios.simulations.dft.pw.relaxation.base")
