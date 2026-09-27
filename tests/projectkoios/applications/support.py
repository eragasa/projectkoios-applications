"""Application-test construction through public simulation and PhysKit contracts."""

from __future__ import annotations

import numpy as np
from physkit.periodic import DirectLattice3D
from physkit.periodic.unit_cell import Atom, AtomicBasis, UnitCell
from physkit.units import PhysicalUnit, ScalarQuantity, Unitless, VectorQuantity

from projectkoios.simulations.dft.pw.relaxation.base import (
    PwDftRelaxationConvergencePolicy,
    PwDftRelaxationRequest,
    PwDftRelaxationSampling,
    PwDftRelaxationScope,
)
from projectkoios.simulations.dft.pw.scf.base import PwDftScfRequest, PwDftScfSampling
from projectkoios.simulations.dft.pw.settings import CalculationType, PwDftSettings
from projectkoios.simulations.dft.pw.simulation import PwDftSimulation


def silicon_scf_request() -> PwDftScfRequest:
    """Return one deterministic calculator-neutral silicon request fixture."""
    return PwDftScfRequest(
        evaluation_id="silicon-scf",
        simulation=PwDftSimulation(
            unit_cell=_silicon_unit_cell(),
            settings=PwDftSettings(calculation_type=CalculationType.scf),
        ),
        sampling=PwDftScfSampling(
            kpoint_mesh=(8, 8, 8),
            kpoint_shift=(0, 0, 0),
            wavefunction_cutoff_ev=400.0,
        ),
    )


def silicon_relaxation_request() -> PwDftRelaxationRequest:
    """Return one deterministic fixed-cell relaxation request fixture."""
    return PwDftRelaxationRequest(
        evaluation_id="silicon-relaxation",
        simulation=PwDftSimulation(
            unit_cell=_silicon_unit_cell(),
            settings=PwDftSettings(calculation_type=CalculationType.relax),
        ),
        scope=PwDftRelaxationScope.ATOMIC_POSITIONS,
        sampling=PwDftRelaxationSampling(
            kpoint_mesh=(8, 8, 8),
            kpoint_shift=(0, 0, 0),
            wavefunction_cutoff_ev=400.0,
        ),
        convergence=PwDftRelaxationConvergencePolicy(
            maximum_ionic_steps=60,
            total_energy_tolerance_ev=1.0e-5,
            force_tolerance_ev_per_angstrom=1.0e-3,
            target_pressure_kbar=None,
            pressure_tolerance_kbar=None,
        ),
    )


def _silicon_unit_cell() -> UnitCell:
    return UnitCell(
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
    )


def _silicon_atom(position: tuple[float, float, float]) -> Atom:
    return Atom(
        symbol="Si",
        position_fractional=VectorQuantity(np.array(position), Unitless()),
    )
