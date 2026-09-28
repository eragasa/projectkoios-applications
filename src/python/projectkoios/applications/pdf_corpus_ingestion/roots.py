"""Explicit runtime root declarations for the PDF corpus application."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from projectkoios.references import (
    CloudPlaceholderProbe,
    MacOSFileProviderPlaceholderProbe,
    PdfCorpusRoot,
    RootStorageClass,
)


class PdfCorpusRootSpecificationError(ValueError):
    """Report ambiguous or unsupported root declarations."""


def parse_pdf_corpus_roots(
    specifications: Sequence[str],
    *,
    platform: str = sys.platform,
    probe_factory: Callable[[Path], CloudPlaceholderProbe] = (
        MacOSFileProviderPlaceholderProbe
    ),
) -> tuple[PdfCorpusRoot, ...]:
    """Parse ``local:alias=/path`` or ``cloud-backed:alias=/path`` roots."""
    if not specifications:
        raise PdfCorpusRootSpecificationError(
            "at least one explicitly classified root is required"
        )
    declarations: list[tuple[str, str, Path]] = []
    aliases: set[str] = set()
    for specification in specifications:
        classification, separator, binding = specification.partition(":")
        alias, equals, raw_path = binding.partition("=")
        if not separator or not equals or not alias or not raw_path:
            raise PdfCorpusRootSpecificationError(
                "root must use local:alias=/absolute/path or "
                "cloud-backed:alias=/absolute/path"
            )
        if classification not in {"local", "cloud-backed"}:
            raise PdfCorpusRootSpecificationError(
                "root classification must be local or cloud-backed"
            )
        path = Path(raw_path)
        if not path.is_absolute():
            raise PdfCorpusRootSpecificationError("root path must be absolute")
        if alias in aliases:
            raise PdfCorpusRootSpecificationError("root aliases must be unique")
        aliases.add(alias)
        declarations.append((classification, alias, path))

    normalized = tuple(
        (alias, Path(os.path.abspath(path))) for _, alias, path in declarations
    )
    for index, (left_alias, left_path) in enumerate(normalized):
        for right_alias, right_path in normalized[index + 1 :]:
            if (
                left_path == right_path
                or left_path.is_relative_to(right_path)
                or right_path.is_relative_to(left_path)
            ):
                raise PdfCorpusRootSpecificationError(
                    "PDF corpus roots must not overlap or nest: "
                    f"{left_alias!r}, {right_alias!r}"
                )

    roots: list[PdfCorpusRoot] = []
    for classification, alias, path in declarations:
        if classification == "local":
            roots.append(PdfCorpusRoot(alias, path, RootStorageClass.LOCAL))
            continue
        roots.append(
            PdfCorpusRoot(
                alias,
                path,
                RootStorageClass.CLOUD_BACKED,
                probe_factory(path) if platform == "darwin" else None,
            )
        )
    return tuple(roots)
