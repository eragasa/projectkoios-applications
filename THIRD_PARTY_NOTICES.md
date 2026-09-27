# Third-party notices

The packaged `projectkoios.applications` modules contain no vendored third-party
source.

Runtime contracts are provided by `projectkoios-simulations` under its own
Apache-2.0 license and notices. Optional examples use PhysKit, NumPy, Plotly, and
SNAKES as separate dependencies under their respective licenses. In particular,
SNAKES 0.9.33 is licensed under LGPL-3.0; it is imported by an example-local CPN
composition and is not copied into this distribution.

Provider integrations are supplied by `projectkoios-simulations`; no VASP,
Quantum ESPRESSO, pseudopotential, executable, or raw calculator corpus is
included in this package.
