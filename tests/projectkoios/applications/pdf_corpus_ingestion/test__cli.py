from __future__ import annotations

from pathlib import Path
from typing import cast

import pymupdf
import pytest

from projectkoios.applications.pdf_corpus_ingestion.cli import main
from projectkoios.applications.pdf_corpus_ingestion.plan import (
    PdfCorpusIngestionPlan,
)


def _pdf() -> bytes:
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    document.new_page(width=72, height=72)
    content = document.tobytes()  # type: ignore[no-untyped-call]
    document.close()  # type: ignore[no-untyped-call]
    return cast(bytes, content)


def _plan_arguments(source: Path, destination: Path) -> list[str]:
    return [
        "plan",
        "--root",
        f"local:papers={source}",
        "--ollama-version",
        "0.12.3",
        "--model",
        "fixture-vision:1",
        "--model-digest",
        "a" * 64,
        "--plan-output",
        str(destination),
    ]


def test_plan_dry_run_prints_only_and_apply_writes_exclusively(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.pdf").write_bytes(_pdf())
    destination = tmp_path / "plan.json"
    arguments = _plan_arguments(source, destination)

    assert main(arguments) == 2
    printed = capsys.readouterr().out
    assert not destination.exists()
    assert PdfCorpusIngestionPlan.from_json(printed).selected_items

    assert main([*arguments, "--apply"]) == 0
    capsys.readouterr()
    assert PdfCorpusIngestionPlan.from_json(destination.read_text())
    with pytest.raises(SystemExit) as error:
        main([*arguments, "--apply"])
    assert error.value.code == 2


def test_run_dry_rebinds_without_writes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.pdf").write_bytes(_pdf())
    destination = tmp_path / "plan.json"
    assert main([*_plan_arguments(source, destination), "--apply"]) == 0
    capsys.readouterr()
    staging = tmp_path / "staging"
    output = tmp_path / "output"
    staging.mkdir(mode=0o700)
    output.mkdir(mode=0o700)

    code = main(
        [
            "run",
            str(destination),
            "--root",
            f"local:papers={source}",
            "--staging-root",
            str(staging),
            "--output-root",
            str(output),
        ]
    )
    report = capsys.readouterr().out

    assert code == 2
    assert '"applied": false' in report
    assert tuple(staging.iterdir()) == ()
    assert tuple(output.iterdir()) == ()


def test_cli_has_no_implicit_root_and_rejects_model_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as missing:
        main(
            [
                "plan",
                "--ollama-version",
                "0.12.3",
                "--model",
                "fixture-vision:1",
                "--model-digest",
                "a" * 64,
            ]
        )
    assert missing.value.code == 2
    capsys.readouterr()

    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "plan.json"
    assert main([*_plan_arguments(source, destination), "--apply"]) == 0
    capsys.readouterr()
    staging = tmp_path / "staging"
    output = tmp_path / "output"
    staging.mkdir(mode=0o700)
    output.mkdir(mode=0o700)

    with pytest.raises(SystemExit) as drift:
        main(
            [
                "run",
                str(destination),
                "--root",
                f"local:papers={source}",
                "--staging-root",
                str(staging),
                "--output-root",
                str(output),
                "--ollama-endpoint",
                "http://127.0.0.1:11434",
                "--ollama-version",
                "0.12.3",
                "--model",
                "other-model:1",
                "--model-digest",
                "a" * 64,
            ]
        )
    assert drift.value.code == 2
