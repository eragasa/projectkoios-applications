"""Common configured environment for silicon workflow example runners."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from examples.projectkoios.applications.pw_dft_scf.runner.configuration import (
    WorkflowRunnerConfigurationLoader,
)
from examples.projectkoios.applications.pw_dft_scf.support.structure_repository import (
    MinimalStructureRepository,
)


@dataclass(frozen=True, slots=True)
class WorkflowRunnerEnvironment:
    """Resolve runner-owned repositories from one reviewed configuration file."""

    configuration_path: Path
    loader: WorkflowRunnerConfigurationLoader

    @classmethod
    def load(cls, configuration_path: Path) -> WorkflowRunnerEnvironment:
        """Construct the common environment from bounded relative paths."""
        if not configuration_path.is_file() or configuration_path.is_symlink():
            raise ValueError("runner configuration must be a regular file")
        if configuration_path.stat().st_size > 100_000:
            raise ValueError("runner configuration exceeds the byte limit")
        payload = tomllib.loads(configuration_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported runner configuration schema")
        root = configuration_path.parent.resolve()
        catalog_path = cls._resolve_file(
            root,
            cls._string(payload, "catalog"),
        )
        structure_root = cls._resolve_directory(
            root,
            cls._string(payload, "structure_repository"),
        )
        return cls(
            configuration_path=configuration_path.resolve(),
            loader=WorkflowRunnerConfigurationLoader(
                catalog_path=catalog_path,
                structure_repository=MinimalStructureRepository(
                    root=structure_root,
                ),
            ),
        )

    @staticmethod
    def _resolve_file(root: Path, value: str) -> Path:
        """Resolve one regular file beneath the example hierarchy."""
        path = (root / value).resolve()
        if not path.is_relative_to(root.parent.parent.parent):
            raise ValueError("runner file path escapes the example hierarchy")
        if not path.is_file() or path.is_symlink():
            raise ValueError("runner file path must identify a regular file")
        return path

    @staticmethod
    def _resolve_directory(root: Path, value: str) -> Path:
        """Resolve one nonsymlink directory beneath the example hierarchy."""
        path = (root / value).resolve()
        if not path.is_relative_to(root.parent.parent.parent):
            raise ValueError("runner directory path escapes the example hierarchy")
        if not path.is_dir() or path.is_symlink():
            raise ValueError("runner directory path must identify a directory")
        return path

    @staticmethod
    def _string(payload: dict[str, object], key: str) -> str:
        """Require one nonempty relative-path string."""
        value = payload.get(key)
        if type(value) is not str or not value or value != value.strip():
            raise ValueError(f"{key} must be a nonempty stripped string")
        if Path(value).is_absolute():
            raise ValueError(f"{key} must be relative")
        return value
