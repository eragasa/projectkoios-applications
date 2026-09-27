"""Invoke the maintained runner for one declared QE relaxation calculation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from projectkoios.integrations.quantumespresso.pw.relaxation.execution import (  # noqa: E501
    QeRelaxationCalculationRunner,
    QeRelaxationCalculationRunRequest,
    QeRelaxationStructureOverride,
)


def run(arguments: Sequence[str] | None = None) -> int:
    """Parse explicit paths and delegate rendering or execution."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--structure", type=Path)
    parser.add_argument("--structure-id")
    parser.add_argument("--structure-sha256")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--pseudopotential", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parsed = parser.parse_args(arguments)

    if parsed.structure is None:
        if parsed.structure_id is not None or parsed.structure_sha256 is not None:
            parser.error("structure identity overrides require --structure")
        structure_override = None
    else:
        if parsed.structure_id is None or parsed.structure_sha256 is None:
            parser.error(
                "an external structure requires --structure-id and --structure-sha256"
            )
        structure_override = QeRelaxationStructureOverride(
            path=parsed.structure,
            structure_id=parsed.structure_id,
            sha256=parsed.structure_sha256,
        )

    QeRelaxationCalculationRunner().run(
        QeRelaxationCalculationRunRequest(
            configuration_path=parsed.configuration,
            output_directory=parsed.output,
            execute=parsed.execute,
            structure_override=structure_override,
            executable=parsed.executable,
            pseudopotential=parsed.pseudopotential,
            timeout_seconds=parsed.timeout_seconds,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
