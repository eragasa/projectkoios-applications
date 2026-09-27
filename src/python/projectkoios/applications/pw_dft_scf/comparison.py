"""Qualified terminal comparison of calculator-neutral SCF results."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfObject,
    PwDftScfResult,
)


class PwDftScfEnergyAlignmentKind(StrEnum):
    """Identify how one calculator-native total-energy zero is treated."""

    NATIVE = "native"
    EXPLICIT_REFERENCE = "explicit-reference"


class PwDftScfComparisonInterpretation(StrEnum):
    """Bound the scientific interpretation allowed for a comparison."""

    NATIVE_DESCRIPTIVE = "native-descriptive"
    EXPLICIT_REFERENCE_ALIGNED = "explicit-reference-aligned"


@dataclass(frozen=True, slots=True)
class PwDftScfEnergyAlignment(PwDftScfObject):
    """Bind one successful result to an explicit energy-zero treatment."""

    result: PwDftScfResult
    kind: PwDftScfEnergyAlignmentKind = PwDftScfEnergyAlignmentKind.NATIVE
    reference_energy_ev_per_atom: float = 0.0
    reference_id: str | None = None
    qualification: str | None = None

    def __post_init__(self) -> None:
        if type(self.result) is not PwDftScfResult:
            raise TypeError("result must be a PwDftScfResult")
        if type(self.kind) is not PwDftScfEnergyAlignmentKind:
            raise TypeError("kind must be a PwDftScfEnergyAlignmentKind")
        if not math.isfinite(self.reference_energy_ev_per_atom):
            raise ValueError("reference energy must be finite")
        if (
            not self.result.observation.completed
            or not self.result.observation.converged
        ):
            raise ValueError("comparison requires a completed, converged SCF result")
        if self.kind is PwDftScfEnergyAlignmentKind.NATIVE:
            if self.reference_energy_ev_per_atom != 0.0:
                raise ValueError("native alignment cannot subtract a reference energy")
            if self.reference_id is not None or self.qualification is not None:
                raise ValueError("native alignment cannot declare reference metadata")
            return
        for label, value in (
            ("reference_id", self.reference_id),
            ("qualification", self.qualification),
        ):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError(f"{label} must be nonempty and stripped")

    @property
    def native_energy_ev_per_atom(self) -> float:
        """Return the calculator-native total energy per atom."""
        return self.result.observation.total_energy_ev_per_atom

    @property
    def aligned_energy_ev_per_atom(self) -> float:
        """Subtract the declared per-atom reference from the native energy."""
        return self.native_energy_ev_per_atom - self.reference_energy_ev_per_atom


@dataclass(frozen=True, slots=True)
class PwDftScfEnergyAlignmentDeclaration(PwDftScfObject):
    """Declare energy-zero treatment before a successful result exists."""

    kind: PwDftScfEnergyAlignmentKind = PwDftScfEnergyAlignmentKind.NATIVE
    reference_energy_ev_per_atom: float = 0.0
    reference_id: str | None = None
    qualification: str | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not PwDftScfEnergyAlignmentKind:
            raise TypeError("kind must be a PwDftScfEnergyAlignmentKind")
        if not math.isfinite(self.reference_energy_ev_per_atom):
            raise ValueError("reference energy must be finite")
        if self.kind is PwDftScfEnergyAlignmentKind.NATIVE:
            if self.reference_energy_ev_per_atom != 0.0:
                raise ValueError("native alignment cannot subtract a reference energy")
            if self.reference_id is not None or self.qualification is not None:
                raise ValueError("native alignment cannot declare reference metadata")
            return
        for label, value in (
            ("reference_id", self.reference_id),
            ("qualification", self.qualification),
        ):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError(f"{label} must be nonempty and stripped")

    def bind(self, result: PwDftScfResult) -> PwDftScfEnergyAlignment:
        """Bind the declaration to one completed, converged result."""
        return PwDftScfEnergyAlignment(
            result=result,
            kind=self.kind,
            reference_energy_ev_per_atom=self.reference_energy_ev_per_atom,
            reference_id=self.reference_id,
            qualification=self.qualification,
        )


@dataclass(frozen=True, slots=True)
class PwDftScfComparisonRequest(PwDftScfObject):
    """Request an ordered terminal comparison backed by input-alignment evidence."""

    comparison_id: str
    input_alignment_id: str
    left: PwDftScfEnergyAlignment
    right: PwDftScfEnergyAlignment

    def __post_init__(self) -> None:
        for label, value in (
            ("comparison_id", self.comparison_id),
            ("input_alignment_id", self.input_alignment_id),
        ):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError(f"{label} must be nonempty and stripped")
        if type(self.left) is not PwDftScfEnergyAlignment:
            raise TypeError("left must be a PwDftScfEnergyAlignment")
        if type(self.right) is not PwDftScfEnergyAlignment:
            raise TypeError("right must be a PwDftScfEnergyAlignment")
        left_observation = self.left.result.observation
        right_observation = self.right.result.observation
        if left_observation.atom_count != right_observation.atom_count:
            raise ValueError("comparison requires equal atom counts")
        left_artifact = left_observation.native_artifact
        right_artifact = right_observation.native_artifact
        if left_artifact == right_artifact or (
            left_artifact.integration_id == right_artifact.integration_id
            and left_artifact.sha256 == right_artifact.sha256
        ):
            raise ValueError("comparison requires two distinct native artifacts")


@dataclass(frozen=True, slots=True)
class PwDftScfComparisonAnalysis(PwDftScfObject):
    """Preserve native and aligned differences with an explicit claim boundary."""

    request: PwDftScfComparisonRequest
    interpretation: PwDftScfComparisonInterpretation
    native_left_minus_right_mev_per_atom: float
    aligned_left_minus_right_mev_per_atom: float
    irreducible_kpoint_counts_match: bool | None
    wavefunction_cutoff_left_minus_right_ev: float | None
    qualifications: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.request) is not PwDftScfComparisonRequest:
            raise TypeError("request must be a PwDftScfComparisonRequest")
        if type(self.interpretation) is not PwDftScfComparisonInterpretation:
            raise TypeError("interpretation must be a PwDftScfComparisonInterpretation")
        for value in (
            self.native_left_minus_right_mev_per_atom,
            self.aligned_left_minus_right_mev_per_atom,
        ):
            if not math.isfinite(value):
                raise ValueError("energy differences must be finite")
        if (
            self.irreducible_kpoint_counts_match is not None
            and type(self.irreducible_kpoint_counts_match) is not bool
        ):
            raise TypeError("irreducible k-point comparison must be a boolean or None")
        if (
            self.wavefunction_cutoff_left_minus_right_ev is not None
            and not math.isfinite(self.wavefunction_cutoff_left_minus_right_ev)
        ):
            raise ValueError("wavefunction cutoff difference must be finite")
        if type(self.qualifications) is not tuple or not self.qualifications:
            raise ValueError("qualifications must be a nonempty tuple")
        if any(
            type(value) is not str or not value or value != value.strip()
            for value in self.qualifications
        ):
            raise ValueError("qualifications must contain nonempty stripped strings")


@dataclass(frozen=True, slots=True)
class PwDftScfComparator(PwDftScfObject):
    """Compute a pure terminal analysis without claiming code equivalence."""

    def compare(
        self,
        request: PwDftScfComparisonRequest,
    ) -> PwDftScfComparisonAnalysis:
        """Compare the ordered left and right energies and sampling observations."""
        if type(request) is not PwDftScfComparisonRequest:
            raise TypeError("request must be a PwDftScfComparisonRequest")
        left = request.left
        right = request.right
        left_observation = left.result.observation
        right_observation = right.result.observation
        native_difference = (
            left.native_energy_ev_per_atom - right.native_energy_ev_per_atom
        ) * 1000.0
        aligned_difference = (
            left.aligned_energy_ev_per_atom - right.aligned_energy_ev_per_atom
        ) * 1000.0
        if (
            left.kind is PwDftScfEnergyAlignmentKind.NATIVE
            and right.kind is PwDftScfEnergyAlignmentKind.NATIVE
        ):
            interpretation = PwDftScfComparisonInterpretation.NATIVE_DESCRIPTIVE
        else:
            interpretation = PwDftScfComparisonInterpretation.EXPLICIT_REFERENCE_ALIGNED
        kpoint_match = _optional_match(
            left_observation.irreducible_kpoint_count,
            right_observation.irreducible_kpoint_count,
        )
        cutoff_difference = _optional_difference(
            left_observation.wavefunction_cutoff_ev,
            right_observation.wavefunction_cutoff_ev,
        )
        qualifications = [
            (
                "Native total energies retain calculator- and "
                "pseudopotential-dependent reference zeros."
            ),
            (
                "Input alignment is asserted by an external evidence identifier and is "
                "not reconstructed by this comparator."
            ),
        ]
        if (
            interpretation
            is PwDftScfComparisonInterpretation.EXPLICIT_REFERENCE_ALIGNED
        ):
            qualifications.append(
                "Explicit reference-zero alignment is not a substitute for matched "
                "relative-energy calculations."
            )
        qualifications.extend(
            qualification
            for qualification in (left.qualification, right.qualification)
            if qualification is not None
        )
        return PwDftScfComparisonAnalysis(
            request=request,
            interpretation=interpretation,
            native_left_minus_right_mev_per_atom=native_difference,
            aligned_left_minus_right_mev_per_atom=aligned_difference,
            irreducible_kpoint_counts_match=kpoint_match,
            wavefunction_cutoff_left_minus_right_ev=cutoff_difference,
            qualifications=tuple(qualifications),
        )


def _optional_match(left: int | None, right: int | None) -> bool | None:
    if left is None or right is None:
        return None
    return left == right


def _optional_difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right
