# Development verification

Use Python 3.14 with the declared development dependencies and one committed,
installable `projectkoios-simulations` revision. Verification must not invoke a
calculator.

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check src/python tests
python -m mypy --strict src/python/projectkoios/applications tests
python -m build --sdist --wheel
```

Reproducibility checks build twice with the same `SOURCE_DATE_EPOCH` in separate
clean directories and compare wheel and sdist SHA-256 identities. The wheel is
then installed into an isolated environment without dependencies and imported
with separately installed declared dependencies.

Until one committed simulations revision supplies both VASP and QE, only the
calculator-neutral package, source-transfer integrity, static example safety,
and syntax boundaries can be checked. Do not label those checks as full provider
or application validation.
