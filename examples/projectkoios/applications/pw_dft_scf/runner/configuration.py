"""Typed loading for shared silicon workflow-runner configuration."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from examples.projectkoios.applications.pw_dft_scf.support.structure_repository import (
    MinimalStructureRepository,
)
from projectkoios.applications.pw_dft_scf.configuration import (
    PwDftScfCampaignConfiguration,
    PwDftScfRuntimeConfiguration,
)
from projectkoios.applications.pw_dft_scf.convergence.policy import (
    PwDftScfConvergencePolicy,
)
from projectkoios.applications.pw_dft_scf.recipe import (
    PwDftScfCutoffConvergenceRecipe,
    PwDftScfGridConvergenceRecipe,
    PwDftScfKpointConvergenceRecipe,
    PwDftScfRecipe,
    PwDftScfSingleCalculationRecipe,
)
from projectkoios.integrations.quantumespresso.pw.scf import (
    configuration as qe_configuration,
)
from projectkoios.integrations.vasp.pw_dft_scf.configuration import (
    VaspScfProjectionConfiguration,
)
from projectkoios.simulations.calculator import CalculatorIntegrationId
from projectkoios.simulations.dft.pw.scf.base import (
    PwDftScfRequest,
    PwDftScfSampling,
)
from projectkoios.simulations.dft.pw.settings import (
    CalculationType,
    PwDftSettings,
)
from projectkoios.simulations.dft.pw.simulation import PwDftSimulation


def resolve_projectkoios_example_reference(
    base_directory: Path,
    reference: str,
) -> Path:
    """Resolve a declaration path within the Project Koios example boundary."""
    resolved_base = base_directory.resolve()
    example_root = next(
        (
            candidate
            for candidate in (resolved_base, *resolved_base.parents)
            if candidate.name == "projectkoios" and candidate.parent.name == "examples"
        ),
        None,
    )
    if example_root is None:
        raise ValueError("base directory is outside examples/projectkoios")
    resolved = (resolved_base / reference).resolve()
    if not resolved.is_relative_to(example_root):
        raise ValueError("example reference escapes examples/projectkoios")
    return resolved


@dataclass(frozen=True, slots=True)
class ReplayDeclaration:
    """Bind a workflow identity to one declared output artifact."""

    evaluation_id: str
    task_id: str
    output_artifact_id: str


@dataclass(frozen=True, slots=True)
class LoadedWorkflowRunnerConfiguration:
    """Preserve resolved common configuration and runner-only declarations."""

    campaign: PwDftScfCampaignConfiguration
    structure_id: str
    projection_profile_id: str
    replay: ReplayDeclaration | None


@dataclass(frozen=True, slots=True)
class WorkflowRunnerConfigurationLoader:
    """Resolve campaign profile IDs through reviewed local repositories."""

    catalog_path: Path
    structure_repository: MinimalStructureRepository

    def __post_init__(self) -> None:
        if not self.catalog_path.is_file() or self.catalog_path.is_symlink():
            raise ValueError("catalog_path must be a regular nonsymlink file")
        if type(self.structure_repository) is not MinimalStructureRepository:
            raise TypeError("structure_repository must be a MinimalStructureRepository")

    def load(self, campaign_path: Path) -> LoadedWorkflowRunnerConfiguration:
        """Resolve one compact campaign into typed scientific configuration."""
        campaign_payload = self._toml(campaign_path, expected_schema=2)
        catalog = self._toml(self.catalog_path, expected_schema=1)
        campaign_id = self._string(campaign_payload, "campaign_id")
        structure_id = self._string(campaign_payload, "structure_id")
        sampling_profile_id = self._string(
            campaign_payload,
            "sampling_profile",
        )
        projection_profile_id = self._string(
            campaign_payload,
            "projection_profile",
        )
        sampling_profile = self._profile(
            catalog,
            "sampling",
            sampling_profile_id,
        )
        simulation = PwDftSimulation(
            unit_cell=self.structure_repository.resolve(structure_id),
            settings=PwDftSettings(calculation_type=CalculationType.scf),
        )
        base_request = PwDftScfRequest(
            evaluation_id=f"{campaign_id}-base",
            simulation=simulation,
            sampling=PwDftScfSampling(
                kpoint_mesh=self._integer_triplet(
                    sampling_profile,
                    "kpoint_mesh",
                ),
                kpoint_shift=self._integer_triplet(
                    sampling_profile,
                    "kpoint_shift",
                ),
                wavefunction_cutoff_ev=self._float(
                    sampling_profile,
                    "wavefunction_cutoff_ev",
                ),
            ),
        )
        mode = self._string(campaign_payload, "mode")
        recipe = self._recipe(
            mode=mode,
            campaign_id=campaign_id,
            base_request=base_request,
            campaign_payload=campaign_payload,
            catalog=catalog,
        )
        runtime = self._mapping(campaign_payload, "runtime")
        configuration = PwDftScfCampaignConfiguration(
            integration_id=CalculatorIntegrationId(
                value=self._string(campaign_payload, "integration")
            ),
            recipe=recipe,
            runtime=PwDftScfRuntimeConfiguration(
                maximum_internal_firings=self._integer(
                    runtime,
                    "maximum_internal_firings",
                )
            ),
        )
        replay_payload = campaign_payload.get("replay")
        replay = (
            None
            if replay_payload is None
            else self._replay(self._require_mapping(replay_payload, "replay"))
        )
        return LoadedWorkflowRunnerConfiguration(
            campaign=configuration,
            structure_id=structure_id,
            projection_profile_id=projection_profile_id,
            replay=replay,
        )

    def qe_projection_configuration(
        self,
        profile_id: str,
    ) -> qe_configuration.QeScfProjectionConfiguration:
        """Resolve one reviewed QE projection profile from the shared catalog."""
        catalog = self._toml(self.catalog_path, expected_schema=1)
        profile = self._profile(catalog, "projection", profile_id)
        raw_species = profile.get("species")
        if not isinstance(raw_species, list) or not raw_species:
            raise ValueError("QE projection species must be a nonempty array")
        species = tuple(
            self._qe_species(self._require_mapping(value, "species"))
            for value in raw_species
        )
        return qe_configuration.QeScfProjectionConfiguration(
            species=species,
            charge_density_cutoff_ratio=self._float(
                profile,
                "charge_density_cutoff_ratio",
            ),
            electronic_tolerance_ry=self._float(
                profile,
                "electronic_tolerance_ry",
            ),
            prefix=self._string(profile, "prefix"),
            pseudo_dir=self._string(profile, "pseudo_dir"),
            outdir=self._string(profile, "outdir"),
            input_filename=self._string(profile, "input_filename"),
            coordinate_precision=self._integer(profile, "coordinate_precision"),
        )

    def vasp_projection_configuration(
        self,
        profile_id: str,
    ) -> VaspScfProjectionConfiguration:
        """Resolve one reviewed VASP projection profile from the shared catalog."""
        catalog = self._toml(self.catalog_path, expected_schema=1)
        profile = self._profile(catalog, "projection", profile_id)
        if self._string(profile, "profile_kind") != "vasp-static-scf":
            raise ValueError("unsupported VASP projection profile")
        return VaspScfProjectionConfiguration(
            system_label=self._string(profile, "system_label"),
            poscar_comment=self._string(profile, "poscar_comment"),
            algorithm=self._string(profile, "algorithm"),
            maximum_electronic_steps=self._integer(
                profile,
                "maximum_electronic_steps",
            ),
            electronic_tolerance_ev=self._float(
                profile,
                "electronic_tolerance_ev",
            ),
            smearing_method=self._integer(profile, "smearing_method"),
            smearing_width_ev=self._float(profile, "smearing_width_ev"),
            spin_polarization=self._integer(profile, "spin_polarization"),
            real_space_projection=self._boolean(
                profile,
                "real_space_projection",
            ),
        )

    def _recipe(
        self,
        *,
        mode: str,
        campaign_id: str,
        base_request: PwDftScfRequest,
        campaign_payload: dict[str, object],
        catalog: dict[str, object],
    ) -> PwDftScfRecipe:
        """Construct one scientific recipe from stable profile identifiers."""
        if mode == "single":
            return PwDftScfSingleCalculationRecipe(
                campaign_id=campaign_id,
                base_request=base_request,
            )
        coordinate_profile = self._profile(
            catalog,
            "coordinates",
            self._string(campaign_payload, "coordinate_profile"),
        )
        policy_profile = self._profile(
            catalog,
            "policy",
            self._string(campaign_payload, "policy_profile"),
        )
        policy = self._policy(policy_profile)
        meshes = self._integer_tuple(coordinate_profile, "mesh_densities")
        cutoffs = self._float_tuple(
            coordinate_profile,
            "wavefunction_cutoffs_ev",
        )
        if mode == "kpoint":
            return PwDftScfKpointConvergenceRecipe(
                campaign_id=campaign_id,
                base_request=base_request,
                mesh_densities=meshes,
                policy=policy,
            )
        if mode == "cutoff":
            return PwDftScfCutoffConvergenceRecipe(
                campaign_id=campaign_id,
                base_request=base_request,
                wavefunction_cutoffs_ev=cutoffs,
                policy=policy,
            )
        if mode == "kpoint-cutoff":
            return PwDftScfGridConvergenceRecipe(
                campaign_id=campaign_id,
                base_request=base_request,
                mesh_densities=meshes,
                wavefunction_cutoffs_ev=cutoffs,
                policy=policy,
            )
        raise ValueError(f"unsupported convergence mode: {mode}")

    def _policy(
        self,
        profile: dict[str, object],
    ) -> PwDftScfConvergencePolicy:
        """Construct one bounded convergence policy profile."""
        return PwDftScfConvergencePolicy(
            tolerance_mev_per_atom=self._float(
                profile,
                "tolerance_mev_per_atom",
            ),
            required_consecutive_deltas=self._integer(
                profile,
                "required_consecutive_deltas",
            ),
            mesh_increment=self._integer(profile, "mesh_increment"),
            cutoff_increment_ev=self._float(profile, "cutoff_increment_ev"),
            extension_steps=self._integer(profile, "extension_steps"),
            maximum_mesh_density=self._integer(
                profile,
                "maximum_mesh_density",
            ),
            maximum_cutoff_ev=self._float(profile, "maximum_cutoff_ev"),
            maximum_grid_points=self._integer(profile, "maximum_grid_points"),
        )

    def _qe_species(
        self,
        payload: dict[str, object],
    ) -> qe_configuration.QeScfSpeciesConfiguration:
        """Construct one QE species declaration from catalog data."""
        return qe_configuration.QeScfSpeciesConfiguration(
            symbol=self._string(payload, "symbol"),
            mass_amu=self._float(payload, "mass_amu"),
            pseudopotential_filename=self._string(
                payload,
                "pseudopotential_filename",
            ),
        )

    def _replay(self, payload: dict[str, object]) -> ReplayDeclaration:
        """Construct one retained-artifact replay declaration."""
        return ReplayDeclaration(
            evaluation_id=self._string(payload, "evaluation_id"),
            task_id=self._string(payload, "task_id"),
            output_artifact_id=self._string(payload, "output_artifact_id"),
        )

    @staticmethod
    def _toml(path: Path, *, expected_schema: int) -> dict[str, object]:
        """Read one bounded local TOML mapping with an exact schema version."""
        if not path.is_file() or path.is_symlink():
            raise ValueError("configuration path must be a regular nonsymlink file")
        if path.stat().st_size > 1_000_000:
            raise ValueError("configuration file exceeds the byte limit")
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != expected_schema:
            raise ValueError("unsupported configuration schema")
        return payload

    @classmethod
    def _profile(
        cls,
        catalog: dict[str, object],
        section: str,
        profile_id: str,
    ) -> dict[str, object]:
        """Resolve one named profile from a catalog section."""
        profiles = cls._mapping(catalog, section)
        return cls._require_mapping(profiles.get(profile_id), profile_id)

    @staticmethod
    def _mapping(mapping: Mapping[str, object], key: str) -> dict[str, object]:
        """Require one nested mapping selected by key."""
        return WorkflowRunnerConfigurationLoader._require_mapping(
            mapping.get(key),
            key,
        )

    @staticmethod
    def _require_mapping(value: object, label: str) -> dict[str, object]:
        """Require one built-in string-keyed dictionary."""
        if not isinstance(value, dict) or any(type(key) is not str for key in value):
            raise ValueError(f"{label} must be a string-keyed table")
        return value

    @staticmethod
    def _string(mapping: Mapping[str, object], key: str) -> str:
        """Require one nonempty stripped string."""
        value = mapping.get(key)
        if type(value) is not str or not value or value != value.strip():
            raise ValueError(f"{key} must be a nonempty stripped string")
        return value

    @staticmethod
    def _integer(mapping: Mapping[str, object], key: str) -> int:
        """Require one built-in integer."""
        value = mapping.get(key)
        if type(value) is not int:
            raise ValueError(f"{key} must be an integer")
        return value

    @staticmethod
    def _boolean(mapping: Mapping[str, object], key: str) -> bool:
        """Require one built-in boolean."""
        value = mapping.get(key)
        if type(value) is not bool:
            raise ValueError(f"{key} must be a boolean")
        return value

    @staticmethod
    def _float(mapping: Mapping[str, object], key: str) -> float:
        """Convert one built-in finite TOML number to float."""
        value = mapping.get(key)
        if type(value) not in {int, float}:
            raise ValueError(f"{key} must be a number")
        return float(value)

    @classmethod
    def _integer_tuple(
        cls,
        mapping: Mapping[str, object],
        key: str,
    ) -> tuple[int, ...]:
        """Require one integer array."""
        value = mapping.get(key)
        if not isinstance(value, list) or any(type(item) is not int for item in value):
            raise ValueError(f"{key} must be an integer array")
        return tuple(value)

    @staticmethod
    def _float_tuple(
        mapping: Mapping[str, object],
        key: str,
    ) -> tuple[float, ...]:
        """Convert one numeric array to built-in floats."""
        value = mapping.get(key)
        if not isinstance(value, list) or any(
            type(item) not in {int, float} for item in value
        ):
            raise ValueError(f"{key} must be a number array")
        return tuple(float(item) for item in value)

    @classmethod
    def _integer_triplet(
        cls,
        mapping: Mapping[str, object],
        key: str,
    ) -> tuple[int, int, int]:
        """Require exactly three integer values."""
        value = cls._integer_tuple(mapping, key)
        if len(value) != 3:
            raise ValueError(f"{key} must contain three integers")
        return value[0], value[1], value[2]
