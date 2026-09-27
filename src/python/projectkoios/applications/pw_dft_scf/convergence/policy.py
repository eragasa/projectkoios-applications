"""Bounded calculator-neutral SCF convergence policy."""

from __future__ import annotations

import math
from dataclasses import dataclass

from projectkoios.simulations.dft.pw.scf.base import PwDftScfObject


@dataclass(frozen=True, slots=True)
class PwDftScfConvergencePolicy(PwDftScfObject):
    """Bound acceptance, adaptive increments, axis limits, and total work."""

    tolerance_mev_per_atom: float = 1.0
    required_consecutive_deltas: int = 2
    mesh_increment: int = 2
    cutoff_increment_ev: float = 50.0
    extension_steps: int = 2
    maximum_mesh_density: int = 20
    maximum_cutoff_ev: float = 1200.0
    maximum_grid_points: int = 80

    def __post_init__(self) -> None:
        values = (
            self.tolerance_mev_per_atom,
            self.required_consecutive_deltas,
            self.mesh_increment,
            self.cutoff_increment_ev,
            self.extension_steps,
            self.maximum_mesh_density,
            self.maximum_cutoff_ev,
            self.maximum_grid_points,
        )
        if any(value <= 0 for value in values) or not all(
            math.isfinite(float(value)) for value in values
        ):
            raise ValueError("convergence policy values must be positive and finite")
