"""Configured standalone visualization runner for the shared silicon structure."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import plotly.graph_objects as go  # type: ignore[import-untyped]
from physkit.units import MODEL_SYSTEM_UNIT_CONVERTER, PhysicalUnit

from examples.projectkoios.applications.pw_dft_scf.runner.environment import (
    WorkflowRunnerEnvironment,
)


@dataclass(frozen=True, slots=True)
class StructurePlotRunner:
    """Render the configured calculator-neutral unit cell as Plotly HTML."""

    environment: WorkflowRunnerEnvironment

    def render(self, campaign_path: Path, output: Path) -> Path:
        """Resolve one campaign structure and write a standalone HTML plot."""
        loaded = self.environment.loader.load(campaign_path)
        unit_cell = loaded.campaign.recipe.base_request.simulation.unit_cell
        lattice_matrix = unit_cell.A.magnitude
        angstrom_factor = MODEL_SYSTEM_UNIT_CONVERTER.conversion_factor(
            unit_cell.H.unit,
            PhysicalUnit("angstrom"),
        )
        cell_matrix = unit_cell.H.magnitude * angstrom_factor
        fractional_positions = np.array(
            tuple(
                atom.position_fractional.magnitude
                for atom in unit_cell.atomic_basis.atoms
            )
        )
        labels = tuple(
            f"{atom.symbol}{index}"
            for index, atom in enumerate(unit_cell.atomic_basis.atoms, start=1)
        )
        cartesian_positions = (cell_matrix @ fractional_positions.T).T
        figure = go.Figure()
        figure.add_trace(self._cell_edges(cell_matrix))
        self._add_lattice_vectors(figure, lattice_matrix, cell_matrix)
        figure.add_trace(
            go.Scatter3d(
                x=cartesian_positions[:, 0],
                y=cartesian_positions[:, 1],
                z=cartesian_positions[:, 2],
                mode="markers+text",
                marker={
                    "color": "#ffbf00",
                    "line": {"color": "black", "width": 2},
                    "size": 10,
                },
                name="Atomic basis",
                text=labels,
                textposition="top center",
                customdata=fractional_positions,
                hovertemplate=(
                    "%{text}<br>Cartesian: (%{x:.4f}, %{y:.4f}, %{z:.4f}) Å"
                    "<br>Fractional: (%{customdata[0]:.2f}, "
                    "%{customdata[1]:.2f}, %{customdata[2]:.2f})<extra></extra>"
                ),
            )
        )
        figure.update_layout(
            title=f"Configured structure: {loaded.structure_id}",
            scene={
                "aspectmode": "data",
                "xaxis_title": "x (Å)",
                "yaxis_title": "y (Å)",
                "zaxis_title": "z (Å)",
                "camera": {"eye": {"x": 1.45, "y": 1.45, "z": 1.1}},
            },
            legend={"x": 0.01, "y": 0.99},
            margin={"b": 10, "l": 10, "r": 10, "t": 55},
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.write_html(
            output,
            include_plotlyjs=True,
            full_html=True,
            config={
                "displaylogo": False,
                "responsive": True,
                "scrollZoom": True,
            },
        )
        return output

    @staticmethod
    def _cell_edges(lattice_vectors: np.ndarray) -> go.Scatter3d:
        """Return one trace containing all primitive-cell edges."""
        corners = {
            coefficients: lattice_vectors @ np.asarray(coefficients)
            for coefficients in product((0, 1), repeat=3)
        }
        x_coordinates: list[float | None] = []
        y_coordinates: list[float | None] = []
        z_coordinates: list[float | None] = []
        for coefficients, start in corners.items():
            for dimension in range(3):
                if coefficients[dimension] == 1:
                    continue
                neighbor = list(coefficients)
                neighbor[dimension] = 1
                end = corners[tuple(neighbor)]
                x_coordinates.extend((float(start[0]), float(end[0]), None))
                y_coordinates.extend((float(start[1]), float(end[1]), None))
                z_coordinates.extend((float(start[2]), float(end[2]), None))
        return go.Scatter3d(
            x=x_coordinates,
            y=y_coordinates,
            z=z_coordinates,
            mode="lines",
            line={"color": "#777777", "width": 3},
            hoverinfo="skip",
            name="Primitive-cell edges",
        )

    @staticmethod
    def _add_lattice_vectors(
        figure: go.Figure,
        lattice_matrix: np.ndarray,
        cell_matrix: np.ndarray,
    ) -> None:
        """Add direct-lattice vectors and arrowheads to a figure."""
        colors = ("#d62728", "#2ca02c", "#1f77b4")
        for index, (vector_a, vector_h, color) in enumerate(
            zip(lattice_matrix.T, cell_matrix.T, colors, strict=True),
            start=1,
        ):
            name = f"h{index}"
            figure.add_trace(
                go.Scatter3d(
                    x=(0.0, vector_h[0]),
                    y=(0.0, vector_h[1]),
                    z=(0.0, vector_h[2]),
                    mode="lines+text",
                    line={"color": color, "width": 8},
                    text=("", name),
                    textposition="top center",
                    hovertemplate=(
                        f"{name}: ({vector_h[0]:.3f}, {vector_h[1]:.3f}, "
                        f"{vector_h[2]:.3f}) Å"
                        f"<br>a{index}: ({vector_a[0]:.1f}, {vector_a[1]:.1f}, "
                        f"{vector_a[2]:.1f})<extra></extra>"
                    ),
                    name=name,
                )
            )
            cone_origin = vector_h * 0.82
            cone_vector = vector_h * 0.18
            figure.add_trace(
                go.Cone(
                    x=(cone_origin[0],),
                    y=(cone_origin[1],),
                    z=(cone_origin[2],),
                    u=(cone_vector[0],),
                    v=(cone_vector[1],),
                    w=(cone_vector[2],),
                    anchor="tail",
                    colorscale=((0.0, color), (1.0, color)),
                    hoverinfo="skip",
                    name=f"{name} arrowhead",
                    showscale=False,
                    showlegend=False,
                    sizemode="absolute",
                    sizeref=0.5,
                )
            )


@dataclass(frozen=True, slots=True)
class StructurePlotRunnerCommand:
    """Parse command paths and invoke `StructurePlotRunner`."""

    def run(self) -> int:
        """Write one configured structure visualization."""
        parser = argparse.ArgumentParser(
            description="Write an interactive configured unit-cell HTML plot."
        )
        parser.add_argument("campaign", type=Path)
        parser.add_argument("--runner-config", required=True, type=Path)
        parser.add_argument("--output", required=True, type=Path)
        arguments = parser.parse_args()
        output = arguments.output.resolve()
        if output.suffix.casefold() != ".html":
            parser.error("--output must have an .html suffix")
        environment = WorkflowRunnerEnvironment.load(arguments.runner_config.resolve())
        rendered = StructurePlotRunner(environment=environment).render(
            campaign_path=arguments.campaign.resolve(),
            output=output,
        )
        print(rendered)
        return 0


if __name__ == "__main__":
    raise SystemExit(StructurePlotRunnerCommand().run())
