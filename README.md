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
source identities and adaptations. The provenance-preserving transfer commit
retains two known QE source limitations: an unresolved replay evidence import
and inherited direct `--execute` behavior. The immediate corrective commit then
replaces them with first-class application replay and relaxation-composition
contracts. The application layer exposes no calculator execution authority.

Cross-provider example validation uses the immutable combined
`projectkoios-simulations` commit
`24dffe10c29e60afcd5fe07aaacb84921a41a43d` (tree
`b7897a05de39072126e6162ce6e8b8fb25be5f31`). Both VASP and Quantum ESPRESSO
campaign projections are checked byte-for-byte, QE relaxation composition is
exercised through its non-authorizing handoff, and the retained 30+6 QE dataset
is replayed from provider-normalized, provenance-bound evidence without
calculator execution.

## Development

The maintained package uses Python 3.14 and a `src/python` layout. Verification
covers Ruff formatting and lint, strict Mypy, deterministic and adversarial
pytest cases, source-transfer policy, and reproducible wheel/sdist construction.
Calculator execution is excluded from verification.
