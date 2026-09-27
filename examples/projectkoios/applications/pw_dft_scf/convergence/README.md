# Calculator-neutral PW-DFT convergence behavior

This application boundary demonstrates coordinate planning, independent
evidence assessment, and cross-integration comparison. Application-owned
provider campaign declarations live under `../providers/`; calculator-native
evidence remains in the provider owner.

Plan one Quantum ESPRESSO k-point example:

```bash
PYTHONPATH=src/python:. .venv/bin/python \
  examples/projectkoios/applications/pw_dft_scf/runner/plan.py \
  examples/projectkoios/applications/pw_dft_scf/providers/quantumespresso/Si/primitive/convergence/kpoint/campaign.toml \
  --runner-config examples/projectkoios/applications/pw_dft_scf/runner/config/runner.toml
```

Compare independently supplied convergence evidence:

```bash
PYTHONPATH=src/python:. .venv/bin/python \
  examples/projectkoios/applications/pw_dft_scf/runner/compare_convergence.py \
  examples/projectkoios/applications/pw_dft_scf/convergence/kpoint/comparison.toml \
  --runner-config examples/projectkoios/applications/pw_dft_scf/runner/config/runner.toml \
  --left-evidence /path/to/qe-evidence.json \
  --right-evidence /path/to/vasp-evidence.json
```
