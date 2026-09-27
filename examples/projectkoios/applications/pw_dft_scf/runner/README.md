# PW-DFT SCF application runners

The runners share one `WorkflowRunnerEnvironment` and `WorkflowRunnerConfigurationLoader`:

- `render_inputs.py`: calculator projection;
- `replay.py`: declared-artifact replay through `dft_pw_scf`;
- `plan.py`: convergence coordinate planning;
- `compare_single.py`: qualified single-SCF comparison;
- `compare_convergence.py`: qualified convergence-test comparison;
- `plot_structure.py`: configured structure visualization.

Commands receive campaign, runner configuration, evidence, artifact-root, and output paths explicitly. Calculator selection is source controlled; no dynamic imports are accepted.

The single-SCF QE/VASP comparison declarations identify successful artifacts
under an operator-selected artifact root. Those artifacts are not retained in
the repository. Integration tests construct bounded parser fixtures at the
same declared artifact IDs, so clean verification does not depend on local
`workspace/` state. The separately retained VASP
`negative-lattice-orientation` failure is workflow evidence, but it is not a
successful observation suitable for energy comparison.
