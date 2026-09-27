"""Common runner for retained silicon convergence-test comparisons."""

from __future__ import annotations

import argparse
import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from examples.projectkoios.applications.pw_dft_scf.runner.configuration import (
    resolve_projectkoios_example_reference,
)
from examples.projectkoios.applications.pw_dft_scf.runner.environment import (
    WorkflowRunnerEnvironment,
)
from projectkoios.applications.pw_dft_scf.convergence.base import (
    PwDftScfConvergenceCoordinate,
    PwDftScfEnergyObservation,
)
from projectkoios.applications.pw_dft_scf.convergence.comparison import (
    PwDftScfConvergenceComparator,
    PwDftScfConvergenceComparisonAnalysis,
    PwDftScfConvergenceComparisonRequest,
    PwDftScfConvergenceTest,
    PwDftScfConvergenceTestKind,
)
from projectkoios.applications.pw_dft_scf.recipe import (
    PwDftScfCutoffConvergenceRecipe,
    PwDftScfGridConvergenceRecipe,
    PwDftScfKpointConvergenceRecipe,
)

_RECIPE_KIND = {
    PwDftScfKpointConvergenceRecipe: PwDftScfConvergenceTestKind.K_POINTS,
    PwDftScfCutoffConvergenceRecipe: (PwDftScfConvergenceTestKind.WAVEFUNCTION_CUTOFF),
    PwDftScfGridConvergenceRecipe: PwDftScfConvergenceTestKind.CROSS,
}


@dataclass(frozen=True, slots=True)
class ConvergenceComparisonRunner:
    """Load two evidence sets and invoke the maintained common comparator."""

    environment: WorkflowRunnerEnvironment

    def compare(
        self,
        *,
        comparison_path: Path,
        left_evidence_path: Path,
        right_evidence_path: Path,
    ) -> PwDftScfConvergenceComparisonAnalysis:
        """Return one qualified comparison selected by reviewed declarations."""
        declaration = self._toml(comparison_path)
        left = self._load_test(
            campaign_path=self._declared_path(
                declaration,
                "left_campaign",
                comparison_path.parent,
            ),
            evidence_path=left_evidence_path,
        )
        right = self._load_test(
            campaign_path=self._declared_path(
                declaration,
                "right_campaign",
                comparison_path.parent,
            ),
            evidence_path=right_evidence_path,
        )
        declared_kind = PwDftScfConvergenceTestKind(self._string(declaration, "kind"))
        if left.kind is not declared_kind or right.kind is not declared_kind:
            raise ValueError("comparison kind does not match both campaign recipes")
        request = PwDftScfConvergenceComparisonRequest(
            comparison_id=self._string(declaration, "comparison_id"),
            input_alignment_id=self._string(
                declaration,
                "input_alignment_id",
            ),
            left=left,
            right=right,
        )
        return PwDftScfConvergenceComparator().compare(request)

    def _load_test(
        self,
        *,
        campaign_path: Path,
        evidence_path: Path,
    ) -> PwDftScfConvergenceTest:
        """Bind one evidence projection to its configured campaign and policy."""
        loaded = self.environment.loader.load(campaign_path)
        recipe = loaded.campaign.recipe
        kind = _RECIPE_KIND.get(type(recipe))
        if kind is None or not isinstance(
            recipe,
            PwDftScfKpointConvergenceRecipe
            | PwDftScfCutoffConvergenceRecipe
            | PwDftScfGridConvergenceRecipe,
        ):
            raise ValueError("campaign must declare a convergence recipe")
        evidence = self._json(evidence_path)
        raw_observations = evidence.get("observations")
        if not isinstance(raw_observations, list):
            raise ValueError("evidence observations must be an array")
        observations = tuple(self._observation(value) for value in raw_observations)
        return PwDftScfConvergenceTest(
            test_id=recipe.campaign_id,
            integration_id=loaded.campaign.integration_id,
            kind=kind,
            observations=observations,
            policy=recipe.policy,
            evidence_id=self._string(evidence, "evidence_id"),
        )

    @classmethod
    def _observation(cls, value: object) -> PwDftScfEnergyObservation:
        """Decode one normalized energy observation from retained JSON."""
        if not isinstance(value, dict):
            raise ValueError("each observation must be an object")
        mesh_density = value.get("mesh_density")
        if type(mesh_density) is not int:
            raise ValueError("mesh_density must be an integer")
        return PwDftScfEnergyObservation(
            coordinate=PwDftScfConvergenceCoordinate(
                mesh_density=mesh_density,
                wavefunction_cutoff_ev=cls._number(
                    value,
                    "wavefunction_cutoff_ev",
                ),
            ),
            total_energy_ev_per_atom=cls._number(
                value,
                "total_energy_ev_per_atom",
            ),
        )

    @staticmethod
    def _toml(path: Path) -> dict[str, object]:
        """Read one bounded comparison declaration."""
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 100_000:
            raise ValueError("comparison declaration must be a bounded regular file")
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported comparison schema")
        return payload

    @staticmethod
    def _json(path: Path) -> dict[str, object]:
        """Read one bounded convergence evidence projection."""
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 10_000_000:
            raise ValueError("evidence path must be a bounded regular file")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported convergence evidence schema")
        return payload

    @classmethod
    def _declared_path(
        cls,
        declaration: dict[str, object],
        key: str,
        root: Path,
    ) -> Path:
        """Resolve one integration declaration inside the examples boundary."""
        return resolve_projectkoios_example_reference(
            root,
            cls._string(declaration, key),
        )

    @staticmethod
    def _string(mapping: dict[str, object], key: str) -> str:
        """Require one nonempty stripped string."""
        value = mapping.get(key)
        if type(value) is not str or not value or value != value.strip():
            raise ValueError(f"{key} must be a nonempty stripped string")
        return value

    @staticmethod
    def _number(mapping: dict[str, object], key: str) -> float:
        """Convert one built-in numeric value to float."""
        value = mapping.get(key)
        if type(value) not in {int, float}:
            raise ValueError(f"{key} must be a number")
        assert isinstance(value, (int, float))
        return float(value)


@dataclass(frozen=True, slots=True)
class ConvergenceComparisonRunnerCommand:
    """Parse command paths and invoke `ConvergenceComparisonRunner`."""

    def run(self) -> int:
        """Print one configured convergence-test comparison."""
        parser = argparse.ArgumentParser(
            description="Compare retained silicon SCF convergence evidence."
        )
        parser.add_argument("comparison", type=Path)
        parser.add_argument("--runner-config", required=True, type=Path)
        parser.add_argument("--left-evidence", required=True, type=Path)
        parser.add_argument("--right-evidence", required=True, type=Path)
        arguments = parser.parse_args()
        environment = WorkflowRunnerEnvironment.load(arguments.runner_config.resolve())
        analysis = ConvergenceComparisonRunner(environment=environment).compare(
            comparison_path=arguments.comparison.resolve(),
            left_evidence_path=arguments.left_evidence.resolve(),
            right_evidence_path=arguments.right_evidence.resolve(),
        )
        print(json.dumps(asdict(analysis), indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(ConvergenceComparisonRunnerCommand().run())
