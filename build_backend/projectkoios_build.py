"""Setuptools backend wrapper with deterministic source archives."""

from __future__ import annotations

import copy
import gzip
import importlib
import os
import shutil
import tarfile
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast


class _SetuptoolsBackend(Protocol):
    def get_requires_for_build_sdist(
        self,
        config_settings: Mapping[str, Any] | None = None,
    ) -> list[str]: ...

    def get_requires_for_build_wheel(
        self,
        config_settings: Mapping[str, Any] | None = None,
    ) -> list[str]: ...

    def prepare_metadata_for_build_wheel(
        self,
        metadata_directory: str,
        config_settings: Mapping[str, Any] | None = None,
    ) -> str: ...

    def build_wheel(
        self,
        wheel_directory: str,
        config_settings: Mapping[str, Any] | None = None,
        metadata_directory: str | None = None,
    ) -> str: ...

    def build_sdist(
        self,
        sdist_directory: str,
        config_settings: Mapping[str, Any] | None = None,
    ) -> str: ...


_setuptools = cast(
    _SetuptoolsBackend,
    importlib.import_module("setuptools.build_meta"),
)


def get_requires_for_build_sdist(
    config_settings: Mapping[str, Any] | None = None,
) -> list[str]:
    return _setuptools.get_requires_for_build_sdist(config_settings)


def get_requires_for_build_wheel(
    config_settings: Mapping[str, Any] | None = None,
) -> list[str]:
    return _setuptools.get_requires_for_build_wheel(config_settings)


def prepare_metadata_for_build_wheel(
    metadata_directory: str,
    config_settings: Mapping[str, Any] | None = None,
) -> str:
    return _setuptools.prepare_metadata_for_build_wheel(
        metadata_directory,
        config_settings,
    )


def build_wheel(
    wheel_directory: str,
    config_settings: Mapping[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    return _setuptools.build_wheel(
        wheel_directory,
        config_settings,
        metadata_directory,
    )


def build_sdist(
    sdist_directory: str,
    config_settings: Mapping[str, Any] | None = None,
) -> str:
    filename = _setuptools.build_sdist(sdist_directory, config_settings)
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    _normalize_sdist(Path(sdist_directory) / filename, epoch=epoch)
    return filename


def _normalize_sdist(path: Path, *, epoch: int) -> None:
    if epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH must not be negative")
    with tempfile.TemporaryDirectory(dir=path.parent) as temporary_directory:
        temporary_root = Path(temporary_directory)
        tar_path = temporary_root / "normalized.tar"
        with (
            tarfile.open(path, mode="r:gz") as source,
            tarfile.open(
                tar_path,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as destination,
        ):
            for member in sorted(source.getmembers(), key=lambda item: item.name):
                normalized = _normalized_member(member, epoch=epoch)
                stream = source.extractfile(member) if member.isfile() else None
                destination.addfile(normalized, stream)
        replacement = temporary_root / path.name
        with (
            tar_path.open("rb") as source_tar,
            replacement.open("wb") as output,
            gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=output,
                mtime=epoch,
            ) as compressed,
        ):
            shutil.copyfileobj(source_tar, compressed)
        os.replace(replacement, path)


def _normalized_member(member: tarfile.TarInfo, *, epoch: int) -> tarfile.TarInfo:
    normalized = copy.copy(member)
    normalized.mtime = epoch
    normalized.uid = 0
    normalized.gid = 0
    normalized.uname = ""
    normalized.gname = ""
    normalized.pax_headers = {}
    return normalized
