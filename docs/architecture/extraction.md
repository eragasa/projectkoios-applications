# Frankenstein application extraction

`TRANSFER.toml` is the exact machine-readable transfer inventory. Its source is
Project Koios Frankenstein commit
`3eb562f2d6167ec20d6f2c892c517509a7abf283`, root tree
`e5daec9f5a16e03f998afb9158a101246acd40d1`.

The authorized set has 122 solely authored Project Koios files: the exact
105-file application overlay plus 17 paths routed out of provider extractions.
The rightsholder explicitly authorized Apache-2.0 distribution in this owner.
That authorization does not affect third-party dependencies, calculator
artifacts, or external executables.

The first transfer preserves two known source limitations so provenance and the
subsequent redesign remain auditable:

1. the QE SCF convergence replay has a relative import of provider-retained
   evidence code and corpus that are not present here; and
2. the QE relaxation command exposes an inherited `--execute` flag.

Neither path is accepted behavior at the transfer checkpoint. The immediate
corrective milestone replaces them with first-class application-owned
composition/workflow/CPN contracts. SCF replay now consumes provider-normalized
application evidence rather than copying raw corpora. Relaxation now composes
neutral requests with provider input projection and emits only a non-authorizing
handoff: external execution authority remains explicit, separate, and absent
from this repository.

The neutral simulation API originates at commit `51427a0`. VASP and QE handoffs
are recorded at `a736800` and `48d3c43`. Combined-provider behavior is verified
against immutable simulations commit `24dffe10c29e60afcd5fe07aaacb84921a41a43d`,
tree `b7897a05de39072126e6162ce6e8b8fb25be5f31`, whose parents are the exact
reviewed VASP and QE heads. Validation covers provider imports, all eight SCF
campaign projections, QE relaxation composition, and replay composition without
calculator execution.
