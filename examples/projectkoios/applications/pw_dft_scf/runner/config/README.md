# Runner configuration

`runner.toml` identifies the reviewed profile catalog and temporary structure repository by bounded relative paths. `catalog.toml` owns shared sampling, convergence-coordinate, policy, QE projection, and VASP projection profiles.

Campaign files contain stable IDs rather than copied numerical tables. Operator-local executable, pseudopotential, workspace, and timeout paths remain outside these source-controlled files.

The file-backed structure repository is temporary incubation infrastructure. Revisit it when an owned Project Koios structure-database contract is available.
