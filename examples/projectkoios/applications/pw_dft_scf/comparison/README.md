# Silicon single-SCF comparator

`comparison.toml` declares campaign identities and explicit energy treatment. Run the common comparator without rerunning either calculator:

```bash
PYTHONPATH=src/python:. .venv/bin/python \
  examples/projectkoios/applications/pw_dft_scf/runner/compare_single.py \
  examples/projectkoios/applications/pw_dft_scf/comparison/comparison.toml \
  --runner-config examples/projectkoios/applications/pw_dft_scf/runner/config/runner.toml \
  --artifact-root .
```

The result is qualified and descriptive; it does not assign calculator equivalence.
