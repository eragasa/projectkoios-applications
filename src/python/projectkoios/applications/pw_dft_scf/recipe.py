"""Scientific recipes for single and converged plane-wave DFT SCF studies."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace

from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceCoordinate,
)
from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)
from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfObject,
    PwDftScfRequest,
    PwDftScfSampling,
)

_IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True, slots=True)
class PwDftScfRecipe(PwDftScfObject):
    """Base scientific recipe rooted in one calculator-neutral SCF request."""

    campaign_id: str
    base_request: PwDftScfRequest

    def __post_init__(self) -> None:
        if type(self.campaign_id) is not str or not _IDENTIFIER.fullmatch(
            self.campaign_id
        ):
            raise ValueError("campaign_id must be a lowercase slug")
        if type(self.base_request) is not PwDftScfRequest:
            raise TypeError("base_request must be a PwDftScfRequest")

    def request_for(
        self,
        coordinate: PwDftScfConvergenceCoordinate,
        *,
        scope: str,
    ) -> PwDftScfRequest:
        """Project one coordinate into a uniquely identified immutable request."""
        mesh = coordinate.mesh_density
        cutoff = coordinate.wavefunction_cutoff_ev
        cutoff_label = f"{cutoff:g}".replace(".", "p")
        return replace(
            self.base_request,
            evaluation_id=(
                f"{self.campaign_id}-{scope}-k{mesh}-e{cutoff_label}".lower()
            ),
            sampling=PwDftScfSampling(
                kpoint_mesh=(mesh, mesh, mesh),
                kpoint_shift=self.base_request.sampling.kpoint_shift,
                wavefunction_cutoff_ev=cutoff,
            ),
        )


@dataclass(frozen=True, slots=True)
class PwDftScfSingleCalculationRecipe(PwDftScfRecipe):
    """Declare one SCF calculation without parameter convergence."""


@dataclass(frozen=True, slots=True)
class PwDftScfKpointConvergenceRecipe(PwDftScfRecipe):
    """Vary cubic k-point density while holding cutoff energy fixed."""

    mesh_densities: tuple[int, ...]
    policy: PwDftScfConvergencePolicy

    def __post_init__(self) -> None:
        PwDftScfRecipe.__post_init__(self)
        _validate_axis(self.mesh_densities, "mesh_densities")
        if any(type(value) is not int for value in self.mesh_densities):
            raise TypeError("mesh_densities must contain integers")
        if type(self.policy) is not PwDftScfConvergencePolicy:
            raise TypeError("policy must be a PwDftScfConvergencePolicy")

    def coordinates(self) -> tuple[PwDftScfConvergenceCoordinate, ...]:
        """Return ordered initial k-point convergence coordinates."""
        cutoff = self.base_request.sampling.wavefunction_cutoff_ev
        return tuple(
            PwDftScfConvergenceCoordinate(mesh, cutoff) for mesh in self.mesh_densities
        )


@dataclass(frozen=True, slots=True)
class PwDftScfCutoffConvergenceRecipe(PwDftScfRecipe):
    """Vary cutoff energy while holding a cubic k-point mesh fixed."""

    wavefunction_cutoffs_ev: tuple[float, ...]
    policy: PwDftScfConvergencePolicy

    def __post_init__(self) -> None:
        PwDftScfRecipe.__post_init__(self)
        _validate_axis(self.wavefunction_cutoffs_ev, "wavefunction_cutoffs_ev")
        if any(type(value) is not float for value in self.wavefunction_cutoffs_ev):
            raise TypeError("wavefunction_cutoffs_ev must contain floats")
        if type(self.policy) is not PwDftScfConvergencePolicy:
            raise TypeError("policy must be a PwDftScfConvergencePolicy")
        _cubic_mesh_density(self.base_request.sampling.kpoint_mesh)

    def coordinates(self) -> tuple[PwDftScfConvergenceCoordinate, ...]:
        """Return ordered initial cutoff convergence coordinates."""
        mesh = _cubic_mesh_density(self.base_request.sampling.kpoint_mesh)
        return tuple(
            PwDftScfConvergenceCoordinate(mesh, cutoff)
            for cutoff in self.wavefunction_cutoffs_ev
        )


@dataclass(frozen=True, slots=True)
class PwDftScfGridConvergenceRecipe(PwDftScfRecipe):
    """Vary cubic k-point density and cutoff energy over a finite grid."""

    mesh_densities: tuple[int, ...]
    wavefunction_cutoffs_ev: tuple[float, ...]
    policy: PwDftScfConvergencePolicy

    def __post_init__(self) -> None:
        PwDftScfRecipe.__post_init__(self)
        _validate_axis(self.mesh_densities, "mesh_densities")
        if any(type(value) is not int for value in self.mesh_densities):
            raise TypeError("mesh_densities must contain integers")
        _validate_axis(self.wavefunction_cutoffs_ev, "wavefunction_cutoffs_ev")
        if any(type(value) is not float for value in self.wavefunction_cutoffs_ev):
            raise TypeError("wavefunction_cutoffs_ev must contain floats")
        if type(self.policy) is not PwDftScfConvergencePolicy:
            raise TypeError("policy must be a PwDftScfConvergencePolicy")

    def coordinates(self) -> tuple[PwDftScfConvergenceCoordinate, ...]:
        """Return the ordered Cartesian product of both initial axes."""
        return tuple(
            PwDftScfConvergenceCoordinate(mesh, cutoff)
            for mesh in self.mesh_densities
            for cutoff in self.wavefunction_cutoffs_ev
        )


def _cubic_mesh_density(mesh: tuple[int, int, int]) -> int:
    if len(set(mesh)) != 1:
        raise ValueError("cutoff convergence requires a cubic k-point mesh")
    return mesh[0]


def _validate_axis(values: tuple[int | float, ...], label: str) -> None:
    if not values or tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} must be nonempty, unique, and increasing")
    if any(float(value) <= 0.0 or not math.isfinite(float(value)) for value in values):
        raise ValueError(f"{label} must contain positive finite values")
