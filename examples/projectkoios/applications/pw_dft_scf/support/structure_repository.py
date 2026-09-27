"""Minimal bounded JSON structure repository for the silicon examples."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from physkit.periodic.unit_cell import (
    UnitCell,
    UnitCellJsonCodec,
)

_STRUCTURE_ID = re.compile(r"[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+")
_MAXIMUM_STRUCTURE_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class MinimalStructureRepository:
    """Resolve bounded JSON records until an owned structure database exists.

    This example repository owns only filesystem lookup and bounds. The maintained
    unit-cell deserializer owns scientific schema validation and subtype selection.
    """

    root: Path

    def __post_init__(self) -> None:
        if not self.root.is_dir() or self.root.is_symlink():
            raise ValueError("structure repository root must be a nonsymlink directory")

    def resolve(self, structure_id: str) -> UnitCell:
        """Deserialize one record selected by a stable qualified identifier."""
        if type(structure_id) is not str or not _STRUCTURE_ID.fullmatch(structure_id):
            raise ValueError("structure_id must be a qualified stable identifier")
        root = self.root.resolve()
        path = (root / f"{structure_id}.json").resolve()
        if not path.is_relative_to(root):
            raise ValueError("structure record must remain inside repository root")
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(path)
        if path.stat().st_size > _MAXIMUM_STRUCTURE_BYTES:
            raise ValueError("structure record exceeds the byte limit")
        return UnitCellJsonCodec().loads(
            path.read_text(encoding="utf-8"),
            expected_structure_id=structure_id,
        )
