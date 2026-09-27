# Silicon single-SCF examples

This hierarchy keeps calculator projections and comparison as three separate examples:

- [`vasp/`](vasp/README.md): deterministic VASP projection and retained-output replay;
- [`qe/`](qe/README.md): deterministic Quantum ESPRESSO projection and retained-output replay;
- [`comparator/`](comparator/README.md): qualified comparison of the two retained common results.

The shared example-only `workflow/dft_pw_scf/` directory owns the optional local SNAKES child-workflow implementation. `workflow/runner/` owns common projection, replay, planning, and comparison commands. Calculator directories contain declarations, not workflow nets or duplicated runners.

Convergence examples are separately organized under [`convergence/`](convergence/README.md).

`common/structures/` is the explicit temporary structure-repository boundary. It must be revisited when an owned durable structure database contract exists.

Render the shared primitive cell as standalone Plotly HTML:

```bash
PYTHONPATH=src/python:. .venv/bin/python \
  examples/projectkoios/applications/pw_dft_scf/runner/plot_structure.py \
  examples/projectkoios/applications/pw_dft_scf/providers/quantumespresso/Si/primitive/campaign.toml \
  --runner-config examples/projectkoios/applications/pw_dft_scf/runner/config/runner.toml \
  --output workspace/results/si-scf-example/si-primitive-cell.html
```
