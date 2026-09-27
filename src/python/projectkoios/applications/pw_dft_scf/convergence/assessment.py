"""Pure calculator-neutral energy convergence assessment."""

from __future__ import annotations

import math
from dataclasses import dataclass

from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceAssessment,
    PwDftScfConvergenceAxis,
    PwDftScfConvergenceCoordinate,
    PwDftScfEnergyObservation,
)
from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)
from projectkoios.simulations.dft.pw.scf.base import PwDftScfObject


@dataclass(frozen=True, slots=True)
class EnergyAxisConvergenceAssessmentRequest(PwDftScfObject):
    """Provide one ordered-axis observation set and its bounded policy."""

    axis: PwDftScfConvergenceAxis
    observations: tuple[PwDftScfEnergyObservation, ...]
    policy: PwDftScfConvergencePolicy

    def __post_init__(self) -> None:
        _validate_observations(self.observations)


@dataclass(frozen=True, slots=True)
class EnergyAxisConvergenceAssessor(PwDftScfObject):
    """Assess neighboring energy changes along one convergence axis."""

    def assess(
        self,
        request: EnergyAxisConvergenceAssessmentRequest,
    ) -> PwDftScfConvergenceAssessment:
        """Return deterministic acceptance, extension, or exhaustion evidence."""
        policy = request.policy
        observations = request.observations
        coordinates = tuple(item.coordinate for item in observations)
        if request.axis is PwDftScfConvergenceAxis.kpoint:
            fixed_values = {item.wavefunction_cutoff_ev for item in coordinates}
            if len(fixed_values) != 1:
                raise ValueError("k-point assessment requires one fixed cutoff")
            ordered = tuple(
                sorted(
                    observations,
                    key=lambda item: item.coordinate.mesh_density,
                )
            )
            edge = tuple(
                (float(item.coordinate.mesh_density), item.total_energy_ev_per_atom)
                for item in ordered
            )
            deltas = _tail_deltas(
                edge,
                float(policy.mesh_increment),
                policy.required_consecutive_deltas,
            )
            passed = _meets_policy(deltas, policy)
            requested = () if passed else _next_kpoint_coordinates(ordered, policy)
            kpoint_deltas = deltas
            cutoff_deltas: tuple[float, ...] = ()
        else:
            fixed_values = {item.mesh_density for item in coordinates}
            if len(fixed_values) != 1:
                raise ValueError("cutoff assessment requires one fixed mesh density")
            ordered = tuple(
                sorted(
                    observations,
                    key=lambda item: item.coordinate.wavefunction_cutoff_ev,
                )
            )
            edge = tuple(
                (item.coordinate.wavefunction_cutoff_ev, item.total_energy_ev_per_atom)
                for item in ordered
            )
            deltas = _tail_deltas(
                edge,
                policy.cutoff_increment_ev,
                policy.required_consecutive_deltas,
            )
            passed = _meets_policy(deltas, policy)
            requested = () if passed else _next_cutoff_coordinates(ordered, policy)
            kpoint_deltas = ()
            cutoff_deltas = deltas

        within_budget = len(observations) + len(requested) <= policy.maximum_grid_points
        can_extend = bool(requested) and within_budget
        reason = (
            "axis satisfies the declared neighboring-point tolerance"
            if passed
            else "axis has not sustained the declared neighboring-point tolerance"
        )
        if not passed and not can_extend:
            reason += "; extension bound or job budget reached"
        return PwDftScfConvergenceAssessment(
            converged=passed,
            can_extend=False if passed else can_extend,
            kpoint_tail_deltas_mev_per_atom=kpoint_deltas,
            cutoff_tail_deltas_mev_per_atom=cutoff_deltas,
            requested_points=requested if can_extend else (),
            reason=reason,
        )


@dataclass(frozen=True, slots=True)
class EnergyGridConvergenceAssessmentRequest(PwDftScfObject):
    """Provide a two-dimensional observation grid and bounded policy."""

    observations: tuple[PwDftScfEnergyObservation, ...]
    policy: PwDftScfConvergencePolicy

    def __post_init__(self) -> None:
        _validate_observations(self.observations)


@dataclass(frozen=True, slots=True)
class EnergyGridConvergenceAssessor(PwDftScfObject):
    """Assess neighboring changes on both high-coordinate grid edges."""

    def assess(
        self,
        request: EnergyGridConvergenceAssessmentRequest,
    ) -> PwDftScfConvergenceAssessment:
        """Return deterministic acceptance, extension, or exhaustion evidence."""
        policy = request.policy
        energies = {
            item.coordinate: item.total_energy_ev_per_atom
            for item in request.observations
        }
        meshes = sorted({coordinate.mesh_density for coordinate in energies})
        cutoffs = sorted({coordinate.wavefunction_cutoff_ev for coordinate in energies})
        highest_mesh = meshes[-1]
        highest_cutoff = cutoffs[-1]
        k_edge = tuple(
            (float(mesh), energies[PwDftScfConvergenceCoordinate(mesh, highest_cutoff)])
            for mesh in meshes
            if PwDftScfConvergenceCoordinate(mesh, highest_cutoff) in energies
        )
        cutoff_edge = tuple(
            (cutoff, energies[PwDftScfConvergenceCoordinate(highest_mesh, cutoff)])
            for cutoff in cutoffs
            if PwDftScfConvergenceCoordinate(highest_mesh, cutoff) in energies
        )
        k_deltas = _tail_deltas(
            k_edge,
            float(policy.mesh_increment),
            policy.required_consecutive_deltas,
        )
        cutoff_deltas = _tail_deltas(
            cutoff_edge,
            policy.cutoff_increment_ev,
            policy.required_consecutive_deltas,
        )
        k_passed = _meets_policy(k_deltas, policy)
        cutoff_passed = _meets_policy(cutoff_deltas, policy)
        if k_passed and cutoff_passed:
            return PwDftScfConvergenceAssessment(
                converged=True,
                can_extend=False,
                kpoint_tail_deltas_mev_per_atom=k_deltas,
                cutoff_tail_deltas_mev_per_atom=cutoff_deltas,
                requested_points=(),
                reason="both grid edges satisfy the declared tolerance",
            )

        new_meshes = () if k_passed else _next_meshes(highest_mesh, policy)
        new_cutoffs = () if cutoff_passed else _next_cutoffs(highest_cutoff, policy)
        context_count = policy.required_consecutive_deltas + 1
        target_meshes = tuple(sorted({*meshes[-context_count:], *new_meshes}))
        target_cutoffs = tuple(sorted({*cutoffs[-context_count:], *new_cutoffs}))
        requested_points = tuple(
            PwDftScfConvergenceCoordinate(mesh, cutoff)
            for mesh in target_meshes
            for cutoff in target_cutoffs
            if PwDftScfConvergenceCoordinate(mesh, cutoff) not in energies
        )
        within_budget = len(energies) + len(requested_points) <= (
            policy.maximum_grid_points
        )
        can_extend = bool(requested_points) and within_budget
        failed_axes = ", ".join(
            axis
            for axis, passed in (
                ("k-point", k_passed),
                ("cutoff", cutoff_passed),
            )
            if not passed
        )
        reason = f"{failed_axes} edge has not sustained the declared tolerance"
        if not can_extend:
            reason += "; extension bound or job budget reached"
        return PwDftScfConvergenceAssessment(
            converged=False,
            can_extend=can_extend,
            kpoint_tail_deltas_mev_per_atom=k_deltas,
            cutoff_tail_deltas_mev_per_atom=cutoff_deltas,
            requested_points=requested_points if can_extend else (),
            reason=reason,
        )


def _validate_observations(
    observations: tuple[PwDftScfEnergyObservation, ...],
) -> None:
    if not observations:
        raise ValueError("assessment requires at least one observation")
    coordinates = tuple(item.coordinate for item in observations)
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("assessment coordinates must be unique")


def _tail_deltas(
    edge: tuple[tuple[float, float], ...],
    expected_increment: float,
    required: int,
) -> tuple[float, ...]:
    deltas: list[float] = []
    for (previous_axis, previous_energy), (current_axis, current_energy) in reversed(
        tuple(zip(edge, edge[1:], strict=False))
    ):
        if not math.isclose(
            current_axis - previous_axis,
            expected_increment,
            rel_tol=0.0,
            abs_tol=1.0e-10,
        ):
            break
        deltas.append(1000.0 * abs(current_energy - previous_energy))
        if len(deltas) == required:
            break
    return tuple(reversed(deltas))


def _meets_policy(
    deltas: tuple[float, ...],
    policy: PwDftScfConvergencePolicy,
) -> bool:
    return len(deltas) == policy.required_consecutive_deltas and all(
        delta <= policy.tolerance_mev_per_atom for delta in deltas
    )


def _next_kpoint_coordinates(
    observations: tuple[PwDftScfEnergyObservation, ...],
    policy: PwDftScfConvergencePolicy,
) -> tuple[PwDftScfConvergenceCoordinate, ...]:
    highest = observations[-1].coordinate
    return tuple(
        PwDftScfConvergenceCoordinate(mesh, highest.wavefunction_cutoff_ev)
        for mesh in _next_meshes(highest.mesh_density, policy)
    )


def _next_cutoff_coordinates(
    observations: tuple[PwDftScfEnergyObservation, ...],
    policy: PwDftScfConvergencePolicy,
) -> tuple[PwDftScfConvergenceCoordinate, ...]:
    highest = observations[-1].coordinate
    return tuple(
        PwDftScfConvergenceCoordinate(highest.mesh_density, cutoff)
        for cutoff in _next_cutoffs(highest.wavefunction_cutoff_ev, policy)
    )


def _next_meshes(
    highest_mesh: int,
    policy: PwDftScfConvergencePolicy,
) -> tuple[int, ...]:
    values = tuple(
        highest_mesh + policy.mesh_increment * index
        for index in range(1, policy.extension_steps + 1)
    )
    return tuple(value for value in values if value <= policy.maximum_mesh_density)


def _next_cutoffs(
    highest_cutoff: float,
    policy: PwDftScfConvergencePolicy,
) -> tuple[float, ...]:
    values = tuple(
        highest_cutoff + policy.cutoff_increment_ev * index
        for index in range(1, policy.extension_steps + 1)
    )
    return tuple(value for value in values if value <= policy.maximum_cutoff_ev)
