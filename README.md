# projectkoios-applications

Workflow- and colored-Petri-net-enabled application composition for Project Koios.
The first capability is `projectkoios.applications.pw_dft_scf`, which composes
calculator-neutral simulation contracts into plane-wave DFT self-consistent-field
recipes, convergence policy, comparisons, workflow definitions, and engine-hiding
facades. The `projectkoios.applications.pdf_corpus_ingestion` capability composes
bounded references-owned PDF discovery with ingestion-owned extraction and
local-only multimodal resolution while keeping reference acceptance separate.

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

## Capability dependencies

The base wheel has no mandatory scientific or simulation dependency. Install
`projectkoios-applications[pdf-corpus]` for the PDF-corpus and equation-review
seam; that extra contains only references, ingestion, and ingestion's PDF
support. Install `projectkoios-applications[simulations]` before importing the
plane-wave DFT application capabilities. Simulation imports fail with an
explicit extra-install message when those optional contracts are unavailable.
The `examples` and `development` extras retain the simulation dependency needed
by their existing scientific tests and examples.

## PDF corpus ingestion

Install the capability dependencies with `projectkoios-applications[pdf-corpus]`.
`koios-pdf-corpus-ingestion plan` scans only repeated explicit
`local:ALIAS=/absolute/path` or `cloud-backed:ALIAS=/absolute/path` roots and
prints its canonical plan unless `--apply --plan-output ...` is given. The plan
records `--maximum-pdf-pages` and bounded multimodal page policy. The separate
`run` command rebinds the same roots plus explicit private staging and local
output roots; it likewise performs only preflight unless `--apply` is given.
Hash-locked staged bytes use ingestion's non-writing byte API, and returned
artifacts are written only through the authorized output root. Local Ollama
identity and endpoint arguments never imply a hosted or fallback provider.

The package also exposes a synchronous citation-document seam for an explicitly
uploaded PDF. It streams the upload into mode-0600 private custody under a
mode-0700 root, binds configured local authority and admission identities in a
deterministic pre-link intent, consumes an exact neutral References link Result,
publishes the deterministic package, verifies its exact transcript, and only
then adds an immutable bounded registry entry. Results are terminal
`SUCCEEDED`, `FAILED`, or `INDETERMINATE`; only success is transcript-ready, and
exact replay never reruns extraction. This seam does not invoke Search,
Workflow, a queue, a background task, or an automatic retry, and it grants no
rights, review, manuscript-use, or publication authority.

## Development

The maintained package uses Python 3.14 and a `src/python` layout. Verification
covers Ruff formatting and lint, strict Mypy, deterministic and adversarial
pytest cases, source-transfer policy, and reproducible wheel/sdist construction.
Calculator execution is excluded from verification. PDF-corpus tests use only
explicit temporary roots and fake Ollama transport; they never scan a user
filesystem or contact a model daemon.
