"""Immutable calculator-neutral SCF convergence values."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from projectkoios.simulations.dft.pw.scf.base import PwDftScfObject


class PwDftScfConvergenceAxis(StrEnum):
    """Identify one independently varied SCF convergence coordinate."""

    kpoint = "kpoint"
    wavefunction_cutoff = "wavefunction-cutoff"


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceCoordinate(PwDftScfObject):
    """Identify one cubic k-point density and cutoff energy in eV."""

    mesh_density: int
    wavefunction_cutoff_ev: float

    def __post_init__(self) -> None:
        if type(self.mesh_density) is not int or self.mesh_density <= 0:
            raise ValueError("mesh_density must be a positive integer")
        if (
            type(self.wavefunction_cutoff_ev) is not float
            or not math.isfinite(self.wavefunction_cutoff_ev)
            or self.wavefunction_cutoff_ev <= 0.0
        ):
            raise ValueError("wavefunction cutoff must be a positive finite float")


@dataclass(frozen=True, slots=True)
class PwDftScfEnergyObservation(PwDftScfObject):
    """Bind one convergence coordinate to total energy per atom."""

    coordinate: PwDftScfConvergenceCoordinate
    total_energy_ev_per_atom: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.total_energy_ev_per_atom):
            raise ValueError("energy per atom must be finite")


@dataclass(frozen=True, slots=True)
class PwDftScfConvergenceAssessment(PwDftScfObject):
    """Report acceptance, extension capability, and neighboring differences."""

    converged: bool
    can_extend: bool
    kpoint_tail_deltas_mev_per_atom: tuple[float, ...]
    cutoff_tail_deltas_mev_per_atom: tuple[float, ...]
    requested_points: tuple[PwDftScfConvergenceCoordinate, ...]
    reason: str
