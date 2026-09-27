# Development verification

Use Python 3.14 with the declared development dependencies and one committed,
installable `projectkoios-simulations` revision. Verification must not invoke a
calculator.

```bash
PROJECTKOIOS_FRANKENSTEIN_REPOSITORY=/path/to/projectkoios-frankenstein \
PROJECTKOIOS_SIMULATIONS_REPOSITORY=/path/to/projectkoios-simulations \
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
validation; do not substitute an uncommitted worktree. Provider validation loads and checks exact rendered identities for all eight
VASP/QE SCF campaigns, composes QE relaxation through the non-authorizing
handoff, and replays a provenance-bound 30-initial-plus-6-adaptive normalized QE
evidence fixture. It never executes a calculator.

The donor environment variable enables per-file source Git-object verification;
the simulations variable rederives normalized replay evidence from the exact
provider manifest Git object.
When `.git` or the explicitly supplied donor checkout is absent (as in an
sdist), only those Git-object checks are skipped; fixed inventory digests and all
artifact-independent transfer checks still run. The ordinary suite includes a
bounded build regression that constructs two wheels and sdists, compares bytes,
checks archive policy and licenses, rebuilds the same wheel from the sdist, and
imports replay and relaxation from the extracted wheel.
