# projectkoios-applications

Workflow- and colored-Petri-net-enabled application composition for Project Koios.
The first capability is `projectkoios.applications.pw_dft_scf`, which composes
calculator-neutral simulation contracts into plane-wave DFT self-consistent-field
recipes, convergence policy, comparisons, workflow definitions, and engine-hiding
facades.

This repository does not own calculator integrations, neutral simulation records,
or generic workflow/CPN kernels. Those remain in `projectkoios-simulations` and
`projectkoios-workflow`. Provider-specific example declarations select those
public contracts without copying provider implementations.

## Safety boundary

No package API, test, replay, example, or ordinary command in this repository
authorizes an external calculator. Examples plan calculations, render static
inputs, or replay declared artifacts. Live calculator execution requires a
separate authority outside this repository.

## Extraction status

The accepted 105-path application overlay and 17 provider-routed candidates
come from Project Koios Frankenstein commit
`3eb562f2d6167ec20d6f2c892c517509a7abf283`. `TRANSFER.toml` records all 122
source identities and adaptations. Two transferred QE paths intentionally retain
known source limitations for the provenance-preserving transfer commit: replay
has an unresolved evidence import, and the relaxation command exposes inherited
`--execute` behavior. Neither path is validated or authorized for use until the
immediate corrective commit replaces it with first-class application contracts.

Full cross-provider example validation remains gated on one committed,
installable `projectkoios-simulations` revision containing both the VASP and
Quantum ESPRESSO integrations. Until then, no combined-provider compatibility is
claimed.

## Development

The maintained package uses Python 3.14 and a `src/python` layout. Verification
covers Ruff formatting and lint, strict Mypy, deterministic and adversarial
pytest cases, source-transfer policy, and reproducible wheel/sdist construction.
Calculator execution is excluded from verification.
