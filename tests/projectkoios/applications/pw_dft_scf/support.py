"""Application-test construction through public simulation and PhysKit contracts."""

from __future__ import annotations

import numpy as np
from physkit.periodic import DirectLattice3D
from physkit.periodic.unit_cell import Atom, AtomicBasis, UnitCell
from physkit.units import PhysicalUnit, ScalarQuantity, Unitless, VectorQuantity

from projectkoios.simulations.dft.pw.scf.base import PwDftScfRequest, PwDftScfSampling
from projectkoios.simulations.dft.pw.settings import CalculationType, PwDftSettings
from projectkoios.simulations.dft.pw.simulation import PwDftSimulation


def silicon_scf_request() -> PwDftScfRequest:
    """Return one deterministic calculator-neutral silicon request fixture."""
    return PwDftScfRequest(
        evaluation_id="silicon-scf",
        simulation=PwDftSimulation(
            unit_cell=UnitCell(
                direct_lattice=DirectLattice3D(
                    a1=np.array([0.5, 0.5, 0.0]),
                    a2=np.array([0.5, 0.0, 0.5]),
                    a3=np.array([0.0, 0.5, 0.5]),
                ),
                lattice_parameter=ScalarQuantity(5.43, PhysicalUnit("angstrom")),
                atomic_basis=AtomicBasis(
                    atoms=(
                        _silicon_atom((0.0, 0.0, 0.0)),
                        _silicon_atom((0.25, 0.25, 0.25)),
                    )
                ),
            ),
            settings=PwDftSettings(calculation_type=CalculationType.scf),
        ),
        sampling=PwDftScfSampling(
            kpoint_mesh=(8, 8, 8),
            kpoint_shift=(0, 0, 0),
            wavefunction_cutoff_ev=400.0,
        ),
    )


def _silicon_atom(position: tuple[float, float, float]) -> Atom:
    return Atom(
        symbol="Si",
        position_fractional=VectorQuantity(np.array(position), Unitless()),
    )
