# Silicon SCF input alignment

| Input | Quantum ESPRESSO | VASP | Alignment |
|---|---:|---:|---|
| Exchange-correlation | PBE | PBE | Same |
| Lattice representation | `A = [a1; a2; a3]` through `CELL_PARAMETERS (angstrom)` | `H = 5.43 Å × A`; POSCAR scale `1.0` | Same physical cell |
| Conventional lattice parameter | `5.43 Å` | `5.43 Å` | Same physical length |
| `a1` / `h1` | `a1 = (2.715, 2.715, 0.000) Å` | `h1 = (2.715, 2.715, 0.000) Å` | Same physical vector |
| `a2` / `h2` | `a2 = (2.715, 0.000, 2.715) Å` | `h2 = (2.715, 0.000, 2.715) Å` | Same physical vector |
| `a3` / `h3` | `a3 = (0.000, 2.715, 2.715) Å` | `h3 = (0.000, 2.715, 2.715) Å` | Same physical vector |
| `AtomicBasis` Si1 fractional position | `(0.00, 0.00, 0.00)` | `(0.00, 0.00, 0.00)` | Same |
| `AtomicBasis` Si2 fractional position | `(0.25, 0.25, 0.25)` | `(0.25, 0.25, 0.25)` | Same |
| Si1 Cartesian position from `H` | `(0.0000, 0.0000, 0.0000) Å` | `(0.0000, 0.0000, 0.0000) Å` | Same physical position |
| Si2 Cartesian position from `H` | `(1.3575, 1.3575, 1.3575) Å` | `(1.3575, 1.3575, 1.3575) Å` | Same physical position |
| K-point mesh | Gamma-centered `8×8×8` | Gamma-centered `8×8×8` | Same |
| Wavefunction cutoff | `30 Ry = 408.17 eV` | `400 eV = 29.40 Ry` | Approximately same |
| SCF tolerance | `1e-6 Ry` | `1e-6 eV` | Same numeric threshold, different energy units |
| Occupations | Fixed | Gaussian | Different |
| Smearing width | None | `0.05 eV` | Different |
| Spin | Non-spin-polarized | Non-spin-polarized | Same |
| Ionic motion | None | None | Same |
| Energy output unit | Ry | eV | Unit conversion required |
