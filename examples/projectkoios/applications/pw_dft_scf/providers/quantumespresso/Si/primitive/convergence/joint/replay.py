"""Replay retained QE evidence through maintained convergence behavior."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from physkit.periodic.unit_cell import (
    UnitCell,
    UnitCellJsonCodec,
)
from physkit.units import MODEL_SYSTEM_UNIT_CONVERTER, PhysicalUnit, ScalarQuantity

from projectkoios.applications.pw_dft_scf.convergence.assessment import (
    EnergyGridConvergenceAssessmentRequest,
    EnergyGridConvergenceAssessor,
)
from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceAssessment,
    PwDftScfConvergenceCoordinate,
    PwDftScfEnergyObservation,
)
from projectkoios.applications.pw_dft_scf.convergence.controller import (
    ExtendPwDftScfConvergence,
    PwDftScfConvergenceAccepted,
    PwDftScfConvergenceController,
)
from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)
from projectkoios.integrations.quantumespresso.outputs.pw_stderr import (
    QePwStderrFile,
    QePwStderrFileParser,
)
from projectkoios.integrations.quantumespresso.outputs.pw_stdout import (
    QePwStdoutFile,
    QePwStdoutFileParser,
)
from projectkoios.integrations.quantumespresso.pw.inputfile.model import (
    PwInput,
    PwInputGroup,
    PwInputParser,
)
from projectkoios.integrations.quantumespresso.pw.scf import (
    data_extraction as qe_data_extraction,
)

from .evidence import (
    RetainedArtifactRole,
    RetainedConvergenceObservation,
    RetainedObservationStage,
    RetainedQeScfConvergenceEvidence,
    RetainedQeScfEvidenceError,
    RetainedQeScfEvidenceLoader,
)

_FLAG_CODE = {
    "IEEE_INVALID_FLAG": "ieee-invalid-flag",
    "IEEE_DIVIDE_BY_ZERO": "ieee-divide-by-zero",
    "IEEE_OVERFLOW_FLAG": "ieee-overflow-flag",
    "IEEE_UNDERFLOW_FLAG": "ieee-underflow-flag",
}


@dataclass(frozen=True, slots=True)
class RetainedQeScfConvergenceReplayResult:
    """Record both the initial extension and final accepted policy outcomes."""

    evidence_id: str
    observation_count: int
    warning_count: int
    initial_assessment: PwDftScfConvergenceAssessment
    initial_extension: ExtendPwDftScfConvergence
    final_assessment: PwDftScfConvergenceAssessment
    terminal_outcome: PwDftScfConvergenceAccepted
    highest_mesh_density: int
    highest_wavefunction_cutoff_ry: float


@dataclass(frozen=True, slots=True)
class RetainedQeScfConvergenceReplayer:
    """Verify native declarations, then invoke maintained assessment and control."""

    repository_root: Path

    def replay(self, manifest_path: Path) -> RetainedQeScfConvergenceReplayResult:
        """Replay retained bytes without invoking Quantum ESPRESSO."""
        evidence = RetainedQeScfEvidenceLoader(self.repository_root).load(manifest_path)
        evidence_root = manifest_path.resolve().parent
        structure = self._load_structure(evidence)
        extractor = qe_data_extraction.QeScfDataExtractor(
            artifact_root=evidence_root
        )
        replayed = tuple(
            self._replay_observation(evidence, structure, extractor, item)
            for item in evidence.observations
        )
        policy = self._policy(evidence)
        assessor = EnergyGridConvergenceAssessor()
        controller = PwDftScfConvergenceController()
        initial_observations = tuple(
            replayed[index]
            for index, declaration in enumerate(evidence.observations)
            if declaration.stage is RetainedObservationStage.INITIAL_GRID
        )
        adaptive_declarations = tuple(
            item
            for item in evidence.observations
            if item.stage is RetainedObservationStage.ADAPTIVE_EXTENSION
        )
        initial_assessment = assessor.assess(
            EnergyGridConvergenceAssessmentRequest(
                observations=initial_observations,
                policy=policy,
            )
        )
        initial_decision = controller.decide(initial_assessment)
        if type(initial_decision) is not ExtendPwDftScfConvergence:
            raise RetainedQeScfEvidenceError(
                "initial evidence does not reproduce the declared grid extension"
            )
        requested = set(initial_decision.coordinates)
        retained_extension = {self._coordinate(item) for item in adaptive_declarations}
        if requested != retained_extension:
            raise RetainedQeScfEvidenceError(
                "retained adaptive coordinates do not match controller request"
            )
        final_assessment = assessor.assess(
            EnergyGridConvergenceAssessmentRequest(
                observations=replayed,
                policy=policy,
            )
        )
        terminal_outcome = controller.decide(final_assessment)
        if type(terminal_outcome) is not PwDftScfConvergenceAccepted:
            raise RetainedQeScfEvidenceError(
                "complete retained evidence does not reproduce policy acceptance"
            )
        return RetainedQeScfConvergenceReplayResult(
            evidence_id=evidence.evidence_id,
            observation_count=len(evidence.observations),
            warning_count=sum(len(item.diagnostics) for item in evidence.observations),
            initial_assessment=initial_assessment,
            initial_extension=initial_decision,
            final_assessment=final_assessment,
            terminal_outcome=terminal_outcome,
            highest_mesh_density=max(
                item.coordinate.mesh_density for item in evidence.observations
            ),
            highest_wavefunction_cutoff_ry=max(
                item.coordinate.wavefunction_cutoff_ry for item in evidence.observations
            ),
        )

    def _replay_observation(
        self,
        evidence: RetainedQeScfConvergenceEvidence,
        structure: UnitCell,
        extractor: qe_data_extraction.QeScfDataExtractor,
        declaration: RetainedConvergenceObservation,
    ) -> PwDftScfEnergyObservation:
        input_identity = declaration.artifact(RetainedArtifactRole.PW_INPUT)
        output_identity = declaration.artifact(RetainedArtifactRole.PW_STDOUT)
        stderr_identity = declaration.artifact(RetainedArtifactRole.PW_STDERR)
        evidence_root = extractor.artifact_root
        parsed_input = PwInputParser().parse(
            (evidence_root / input_identity.artifact_id).read_text()
        )
        self._verify_input(evidence, structure, declaration, parsed_input)
        output_payload = (evidence_root / output_identity.artifact_id).read_bytes()
        parsed_output = QePwStdoutFileParser().parse(
            output_payload,
            output_file=QePwStdoutFile(relative_path=output_identity.artifact_id),
        )
        stderr_payload = (evidence_root / stderr_identity.artifact_id).read_bytes()
        parsed_stderr = QePwStderrFileParser().parse(
            stderr_payload,
            output_file=QePwStderrFile(relative_path=stderr_identity.artifact_id),
        )
        expected = declaration.native_observation
        observed_native = (
            parsed_output.program_version,
            parsed_output.job_completed,
            parsed_output.scf_converged,
            parsed_output.total_energy_ry,
            parsed_output.atom_count,
            parsed_output.k_point_count,
            parsed_output.scf_iteration_count,
        )
        declared_native = (
            expected.program_version,
            expected.job_completed,
            expected.scf_converged,
            expected.total_energy_ry,
            expected.atom_count,
            expected.irreducible_kpoint_count,
            expected.scf_iteration_count,
        )
        if observed_native != declared_native:
            raise RetainedQeScfEvidenceError(
                f"native observation mismatch: {declaration.run_id}"
            )
        declared_diagnostics = tuple(
            (item.native_flag, item.code) for item in declaration.diagnostics
        )
        parsed_diagnostics = tuple(
            (flag, _FLAG_CODE[flag]) for flag in parsed_stderr.ieee_flags
        )
        if parsed_diagnostics != declared_diagnostics:
            raise RetainedQeScfEvidenceError(
                f"diagnostic mismatch: {declaration.run_id}"
            )
        normalized = extractor.extract(output_identity.artifact_id)
        normalized_codes = tuple(item.code for item in normalized.diagnostics)
        if normalized_codes != tuple(item.code for item in declaration.diagnostics):
            raise RetainedQeScfEvidenceError(
                f"normalized diagnostic mismatch: {declaration.run_id}"
            )
        if (
            not normalized.completed
            or not normalized.converged
            or normalized.atom_count != expected.atom_count
            or normalized.program_version != expected.program_version
        ):
            raise RetainedQeScfEvidenceError(
                f"normalized observation mismatch: {declaration.run_id}"
            )
        return PwDftScfEnergyObservation(
            coordinate=self._coordinate(declaration),
            total_energy_ev_per_atom=(
                normalized.total_energy_ev / normalized.atom_count
            ),
        )

    def _verify_input(
        self,
        evidence: RetainedQeScfConvergenceEvidence,
        structure: UnitCell,
        declaration: RetainedConvergenceObservation,
        parsed_input: PwInput,
    ) -> None:
        control = self._group(parsed_input, "&CONTROL")
        system = self._group(parsed_input, "&SYSTEM")
        species = self._group(parsed_input, "ATOMIC_SPECIES")
        cell = self._group(parsed_input, "CELL_PARAMETERS")
        positions = self._group(parsed_input, "ATOMIC_POSITIONS")
        kpoints = self._group(parsed_input, "K_POINTS")
        if self._assignment(control, "calculation").strip("'\"") != "scf":
            raise RetainedQeScfEvidenceError("retained input is not an SCF calculation")
        if self._integer_assignment(system, "ibrav") != 0:
            raise RetainedQeScfEvidenceError("retained input does not use ibrav=0")
        if self._integer_assignment(system, "nat") != evidence.structure.atom_count:
            raise RetainedQeScfEvidenceError("retained input atom count mismatch")
        if not math.isclose(
            self._float_assignment(system, "ecutwfc"),
            declaration.coordinate.wavefunction_cutoff_ry,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise RetainedQeScfEvidenceError("retained input ecutwfc mismatch")
        if not math.isclose(
            self._float_assignment(system, "ecutrho"),
            declaration.coordinate.charge_density_cutoff_ry,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise RetainedQeScfEvidenceError("retained input ecutrho mismatch")
        if kpoints.tag.casefold() != "k_points automatic" or len(kpoints.lines) != 1:
            raise RetainedQeScfEvidenceError("retained input K_POINTS is unsupported")
        kpoint_values = tuple(int(value) for value in kpoints.lines[0].split())
        expected_kpoints = (
            declaration.coordinate.mesh_density,
            declaration.coordinate.mesh_density,
            declaration.coordinate.mesh_density,
            0,
            0,
            0,
        )
        if kpoint_values != expected_kpoints:
            raise RetainedQeScfEvidenceError("retained input k-point mesh mismatch")
        declared_pseudopotentials = {
            item.species: item.artifact_name for item in evidence.pseudopotentials
        }
        observed_pseudopotentials = {
            values[0]: values[2]
            for line in species.lines
            if len(values := line.split()) == 3
        }
        if observed_pseudopotentials != declared_pseudopotentials:
            raise RetainedQeScfEvidenceError("retained input pseudopotential mismatch")
        self._verify_structure(structure, cell, positions)

    @staticmethod
    def _verify_structure(
        structure: UnitCell,
        cell: PwInputGroup,
        positions: PwInputGroup,
    ) -> None:
        if cell.tag.casefold() != "cell_parameters (angstrom)":
            raise RetainedQeScfEvidenceError(
                "retained input CELL_PARAMETERS unit mismatch"
            )
        observed_vectors = np.array(
            [[float(value) for value in line.split()] for line in cell.lines]
        )
        expected_vectors = np.array(
            [
                structure.h1.magnitude,
                structure.h2.magnitude,
                structure.h3.magnitude,
            ]
        )
        if observed_vectors.shape != (3, 3) or not np.allclose(
            observed_vectors, expected_vectors, rtol=0.0, atol=1.0e-10
        ):
            raise RetainedQeScfEvidenceError("retained input cell mismatch")
        if positions.tag.casefold() != "atomic_positions (crystal)":
            raise RetainedQeScfEvidenceError(
                "retained input ATOMIC_POSITIONS basis mismatch"
            )
        observed_atoms = tuple(
            (values[0], tuple(float(item) for item in values[1:]))
            for line in positions.lines
            if len(values := line.split()) == 4
        )
        expected_atoms = tuple(
            (
                atom.symbol,
                tuple(float(item) for item in atom.position_fractional.magnitude),
            )
            for atom in structure.atomic_basis.atoms
        )
        if observed_atoms != expected_atoms:
            raise RetainedQeScfEvidenceError("retained input atomic basis mismatch")

    def _load_structure(self, evidence: RetainedQeScfConvergenceEvidence) -> UnitCell:
        path = self.repository_root / evidence.structure.repository_path
        return UnitCellJsonCodec().loads(
            path.read_text(),
            expected_structure_id=evidence.structure.structure_id,
        )

    def _policy(
        self, evidence: RetainedQeScfConvergenceEvidence
    ) -> PwDftScfConvergencePolicy:
        declaration = evidence.policy
        return PwDftScfConvergencePolicy(
            tolerance_mev_per_atom=declaration.tolerance_mev_per_atom,
            required_consecutive_deltas=declaration.required_consecutive_deltas,
            mesh_increment=declaration.mesh_increment,
            cutoff_increment_ev=self._ry_to_ev(declaration.cutoff_increment_ry),
            extension_steps=declaration.extension_steps,
            maximum_mesh_density=declaration.maximum_mesh_density,
            maximum_cutoff_ev=self._ry_to_ev(declaration.maximum_cutoff_ry),
            maximum_grid_points=declaration.maximum_grid_points,
        )

    def _coordinate(
        self, declaration: RetainedConvergenceObservation
    ) -> PwDftScfConvergenceCoordinate:
        return PwDftScfConvergenceCoordinate(
            mesh_density=declaration.coordinate.mesh_density,
            wavefunction_cutoff_ev=self._ry_to_ev(
                declaration.coordinate.wavefunction_cutoff_ry
            ),
        )

    @staticmethod
    def _group(parsed_input: PwInput, tag_prefix: str) -> PwInputGroup:
        matches = tuple(
            group
            for group in parsed_input.groups
            if group.tag.casefold().startswith(tag_prefix.casefold())
        )
        if len(matches) != 1:
            raise RetainedQeScfEvidenceError(
                f"retained input must declare one {tag_prefix} group"
            )
        return matches[0]

    @classmethod
    def _assignment(cls, group: PwInputGroup, name: str) -> str:
        matches = tuple(
            line.split("=", maxsplit=1)[1].strip().rstrip(",")
            for line in group.lines
            if line.split("=", maxsplit=1)[0].strip().casefold() == name.casefold()
        )
        if len(matches) != 1:
            raise RetainedQeScfEvidenceError(
                f"retained input must declare one {name} assignment"
            )
        return matches[0]

    @classmethod
    def _integer_assignment(cls, group: PwInputGroup, name: str) -> int:
        return int(cls._assignment(group, name))

    @classmethod
    def _float_assignment(cls, group: PwInputGroup, name: str) -> float:
        return float(cls._assignment(group, name).replace("d", "e").replace("D", "E"))

    @staticmethod
    def _ry_to_ev(value: float) -> float:
        return MODEL_SYSTEM_UNIT_CONVERTER.convert_scalar(
            ScalarQuantity(magnitude=value, unit=PhysicalUnit("Ry")),
            PhysicalUnit("eV"),
        ).magnitude


def main() -> None:
    """Print one deterministic replay report without calculator execution."""
    repository_root = Path(__file__).resolve().parents[10]
    manifest_path = Path(__file__).parent / "evidence/manifest.json"
    result = RetainedQeScfConvergenceReplayer(repository_root).replay(manifest_path)
    print(
        json.dumps(
            {
                "evidence_id": result.evidence_id,
                "observation_count": result.observation_count,
                "warning_count": result.warning_count,
                "initial_outcome": type(result.initial_extension).__name__,
                "initial_requested_coordinates": [
                    {
                        "mesh_density": item.mesh_density,
                        "wavefunction_cutoff_ev": item.wavefunction_cutoff_ev,
                    }
                    for item in result.initial_extension.coordinates
                ],
                "terminal_outcome": type(result.terminal_outcome).__name__,
                "highest_mesh_density": result.highest_mesh_density,
                "highest_wavefunction_cutoff_ry": result.highest_wavefunction_cutoff_ry,
                "kpoint_tail_deltas_mev_per_atom": list(
                    result.final_assessment.kpoint_tail_deltas_mev_per_atom
                ),
                "cutoff_tail_deltas_mev_per_atom": list(
                    result.final_assessment.cutoff_tail_deltas_mev_per_atom
                ),
                "qualification": (
                    "Finite-grid total-energy convergence under the declared "
                    "policy only."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
