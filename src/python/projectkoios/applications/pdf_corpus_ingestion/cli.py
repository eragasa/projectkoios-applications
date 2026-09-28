"""Plan-first CLI for bounded PDF-corpus ingestion."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from projectkoios.references import (
    AuthorizedRoot,
    RootStorageClass,
    discover_pdf_corpus,
)

from .composition import compose_pdf_corpus_ingestion_plan
from .multimodal import PdfCorpusMultimodalPolicy
from .plan import (
    MAX_APPLICATION_PDF_BYTES,
    MAX_APPLICATION_PDF_PAGES,
    MAX_APPLICATION_PLAN_BYTES,
    MAX_TRANCHE_ITEMS,
    PdfCorpusIngestionPlan,
)
from .roots import parse_pdf_corpus_roots
from .runner import PdfCorpusRunError, run_pdf_corpus_ingestion

_PLANNED_EXIT = 2
_INCOMPLETE_EXIT = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="koios-pdf-corpus-ingestion")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    _root_arguments(plan)
    plan.add_argument("--cursor", type=int, default=0)
    plan.add_argument("--tranche-size", type=int, default=MAX_TRANCHE_ITEMS)
    plan.add_argument(
        "--maximum-file-bytes",
        type=int,
        default=MAX_APPLICATION_PDF_BYTES,
    )
    plan.add_argument(
        "--maximum-pdf-pages",
        type=int,
        default=MAX_APPLICATION_PDF_PAGES,
    )
    plan.add_argument("--low-text-threshold", type=int, default=40)
    plan.add_argument("--maximum-pages-per-document", type=int, default=16)
    plan.add_argument("--maximum-pages-per-tranche", type=int, default=128)
    plan.add_argument("--request-max-selections", type=int, default=8)
    plan.add_argument("--renderer-resolution-dpi", type=int, default=144)
    plan.add_argument("--ollama-version", required=True)
    plan.add_argument("--model", required=True)
    plan.add_argument("--model-digest", required=True)
    plan.add_argument("--plan-output", type=Path)
    plan.add_argument("--apply", action="store_true")

    run = subparsers.add_parser("run")
    run.add_argument("plan", type=Path)
    _root_arguments(run)
    run.add_argument("--staging-root", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--ollama-endpoint")
    run.add_argument("--ollama-version")
    run.add_argument("--model")
    run.add_argument("--model-digest")
    run.add_argument("--apply", action="store_true")
    return parser


def _root_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        action="append",
        required=True,
        metavar="STORAGE:ALIAS=ABSOLUTE_PATH",
        help="repeat explicit local: or cloud-backed: roots",
    )


def main(arguments: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        if args.command == "plan":
            return _plan(args, parser)
        return _run(args, parser)
    except (OSError, TypeError, ValueError, PdfCorpusRunError) as error:
        parser.error(str(error))
    return 2  # pragma: no cover - argparse.error exits


def _plan(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    roots = parse_pdf_corpus_roots(args.root)
    discovery = discover_pdf_corpus(roots)
    policy = PdfCorpusMultimodalPolicy.create(
        native_text_character_threshold=args.low_text_threshold,
        maximum_pages_per_document=args.maximum_pages_per_document,
        maximum_pages_per_tranche=args.maximum_pages_per_tranche,
        request_max_selections=args.request_max_selections,
        expected_ollama_version=args.ollama_version,
        model_name=args.model,
        expected_model_digest=args.model_digest,
        renderer_resolution_dpi=args.renderer_resolution_dpi,
    )
    plan = compose_pdf_corpus_ingestion_plan(
        discovery,
        cursor=args.cursor,
        tranche_size=args.tranche_size,
        maximum_file_bytes=args.maximum_file_bytes,
        maximum_pdf_pages=args.maximum_pdf_pages,
        low_text_threshold=args.low_text_threshold,
        multimodal_policy=policy,
    )
    if not args.apply:
        sys.stdout.write(plan.to_json())
        return _PLANNED_EXIT
    if args.plan_output is None:
        parser.error("--plan-output is required with --apply")
    _write_plan_exclusively(args.plan_output, plan.to_json())
    print(args.plan_output)
    return 0


def _run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    plan = _read_plan(args.plan)
    supplied_model_values = (
        args.ollama_version,
        args.model,
        args.model_digest,
    )
    if args.ollama_endpoint is None:
        if any(value is not None for value in supplied_model_values):
            parser.error(
                "--ollama-version, --model and --model-digest require --ollama-endpoint"
            )
    elif any(value is None for value in supplied_model_values):
        parser.error(
            "--ollama-endpoint requires --ollama-version, --model and --model-digest"
        )
    else:
        _require_runtime_model(plan, args)
    roots = parse_pdf_corpus_roots(args.root)
    report = run_pdf_corpus_ingestion(
        plan,
        roots=roots,
        staging_root_path=args.staging_root,
        output_root_path=args.output_root,
        apply=args.apply,
        ollama_endpoint=args.ollama_endpoint,
    )
    sys.stdout.write(report.to_json())
    if not args.apply:
        return _PLANNED_EXIT
    if (
        not report.raw_complete
        or not report.multimodal_complete
        or report.corpus_coverage_status != "complete"
        or report.deferred_content_count
    ):
        return _INCOMPLETE_EXIT
    return 0


def _require_runtime_model(
    plan: PdfCorpusIngestionPlan,
    args: argparse.Namespace,
) -> None:
    expected_digest = str(args.model_digest).removeprefix("sha256:")
    policy = plan.multimodal_policy
    if (
        args.ollama_version != policy.expected_ollama_version
        or args.model != policy.model_name
        or expected_digest != policy.expected_model_digest
    ):
        raise ValueError("runtime Ollama identity conflicts with the plan")


def _read_plan(path: Path) -> PdfCorpusIngestionPlan:
    if not path.is_absolute():
        raise ValueError("plan path must be absolute")
    root = AuthorizedRoot.existing(
        path.parent,
        label="PDF corpus plan parent",
        root_alias="pdf-corpus-plan-parent",
        storage_class=RootStorageClass.LOCAL,
    )
    return PdfCorpusIngestionPlan.from_json(
        root.read_text(path.name, max_bytes=MAX_APPLICATION_PLAN_BYTES)
    )


def _write_plan_exclusively(path: Path, content: str) -> None:
    if not path.is_absolute():
        raise ValueError("plan output path must be absolute")
    root = AuthorizedRoot.existing(
        path.parent,
        label="PDF corpus plan output parent",
        root_alias="pdf-corpus-plan-output-parent",
        storage_class=RootStorageClass.LOCAL,
    )
    root.write_bytes(path.name, content.encode("utf-8"), replace=False)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
