from __future__ import annotations

import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SIMULATIONS = "projectkoios-simulations>=0.1.0.dev0,<0.2"


def test_capability_extras_keep_pdf_corpus_free_of_scientific_dependencies() -> None:
    configuration = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    project = configuration["project"]
    extras = project["optional-dependencies"]

    assert project["dependencies"] == []
    assert set(extras["pdf-corpus"]) == {
        "projectkoios-ingestion[pdf]==0.0.0",
        "projectkoios-references==0.0.0",
    }
    assert extras["simulations"] == [_SIMULATIONS]
    assert _SIMULATIONS in extras["examples"]
    assert _SIMULATIONS in extras["development"]
    assert not any(
        "simulations" in requirement.lower() or "physkit" in requirement.lower()
        for requirement in extras["pdf-corpus"]
    )
