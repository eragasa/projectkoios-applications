"""Run the SCF campaign provider graph from one explicit simulations archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


def main() -> int:
    """Render all pinned campaigns and emit their exact provider-module graph."""
    if any(
        name == "projectkoios" or name.startswith("projectkoios.")
        for name in sys.modules
    ):
        raise RuntimeError("projectkoios modules were preloaded")
    arguments = _arguments()
    repository = arguments.repository.resolve()
    provider_root = arguments.provider_root.resolve()
    sys.path[:0] = [
        str(provider_root),
        str(repository / "src/python"),
        str(repository),
    ]

    from examples.projectkoios.applications.pw_dft_scf.runner.environment import (
        WorkflowRunnerEnvironment,
    )
    from examples.projectkoios.applications.pw_dft_scf.runner.render_inputs import (
        InputProjectionRunner,
    )

    fixture = _mapping(
        json.loads(
            (
                repository / "tests/fixtures/pw_dft_scf/campaign-projections.json"
            ).read_text(encoding="utf-8")
        )
    )
    expected = {
        _string(item, "module"): _string(item, "path").removeprefix("src/python/")
        for item in _mappings(fixture, "provider_modules")
    }
    example = repository / "examples/projectkoios/applications/pw_dft_scf"
    environment = WorkflowRunnerEnvironment.load(example / "runner/config/runner.toml")
    with tempfile.TemporaryDirectory() as directory:
        for index, campaign in enumerate(_mappings(fixture, "campaigns")):
            InputProjectionRunner(environment).render(
                example / _string(campaign, "path"),
                Path(directory) / str(index),
            )

    prefixes = (
        "projectkoios.integrations.quantumespresso",
        "projectkoios.integrations.vasp",
    )
    loaded: dict[str, dict[str, str]] = {}
    for name, module in sys.modules.items():
        module_file = getattr(module, "__file__", None)
        if not name.startswith(prefixes) or not isinstance(module_file, str):
            continue
        path = Path(module_file).resolve()
        expected_path = (provider_root / expected[name]).resolve()
        if path != expected_path or not path.is_relative_to(provider_root):
            raise RuntimeError(f"provider module escaped archive root: {name}")
        loaded[name] = {
            "path": path.relative_to(provider_root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    if set(loaded) != set(expected):
        raise RuntimeError("loaded provider module set does not match expectation")
    print(json.dumps(loaded, sort_keys=True))
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-root", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    return parser.parse_args()


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise TypeError("fixture value must be a string-keyed mapping")
    return value


def _mappings(mapping: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = mapping.get(key)
    if not isinstance(value, list):
        raise TypeError(f"{key} must be an array")
    return [_mapping(item) for item in value]


def _string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
