# Development verification

Use Python 3.14 with the declared development dependencies and one committed,
installable `projectkoios-simulations` revision. Verification must not invoke a
calculator.

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check src/python tests
python -m mypy --strict build_backend src/python/projectkoios/applications tests
python -m build --sdist --wheel
```

Reproducibility checks build twice with the same `SOURCE_DATE_EPOCH` in separate
clean directories and compare wheel and sdist SHA-256 identities. Under the
extraction task's no-install rule, the wheel is then extracted into an isolated
temporary import root and imported with the separately provided committed
dependency source.

The cross-provider baseline is simulations commit
`24dffe10c29e60afcd5fe07aaacb84921a41a43d`, tree
`b7897a05de39072126e6162ce6e8b8fb25be5f31`. Archive that exact Git object for
validation; do not substitute an uncommitted worktree. Provider validation loads
and projects all eight VASP/QE SCF campaigns, composes QE relaxation through the
non-authorizing handoff, and replays normalized evidence. It never executes a
calculator.
