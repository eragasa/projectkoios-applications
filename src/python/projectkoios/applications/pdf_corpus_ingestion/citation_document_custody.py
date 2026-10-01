"""Bounded private custody for exact uploaded PDF bytes."""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, final

from projectkoios.references import AuthorizedRoot, RootStorageClass
from projectkoios.references.citation_document import (
    CITATION_DOCUMENT_MAX_PDF_BYTES,
    CitationSourceDocumentDescriptor,
)

from .citation_document_contracts import CitationDocumentReceipt

MAX_CITATION_DOCUMENT_PDF_BYTES = min(
    50_000_000,
    CITATION_DOCUMENT_MAX_PDF_BYTES,
)
_CUSTODY_CHUNK_BYTES = 1_048_576


class CitationDocumentCustodyError(ValueError):
    """Private custody input or retained evidence is unsafe."""


class CitationDocumentCustodyLimitError(CitationDocumentCustodyError):
    """A custody byte bound was exceeded."""


@final
@dataclass(frozen=True, slots=True)
class PrivatePdfCustody:
    """A private, local, immutable content-addressed PDF custody root."""

    root: AuthorizedRoot
    max_pdf_bytes: int = MAX_CITATION_DOCUMENT_PDF_BYTES

    def __post_init__(self) -> None:
        _require_private_root(self.root, field_name="custody root")
        if (
            type(self.max_pdf_bytes) is not int
            or not 0 < self.max_pdf_bytes <= MAX_CITATION_DOCUMENT_PDF_BYTES
        ):
            raise ValueError("max_pdf_bytes is outside the application bound")

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        root_alias: str = "citation-document-private-custody",
        max_pdf_bytes: int = MAX_CITATION_DOCUMENT_PDF_BYTES,
    ) -> PrivatePdfCustody:
        """Create a new mode-0700 custody root and bind it."""
        supplied = path.expanduser()
        if supplied.is_symlink():
            raise CitationDocumentCustodyError(
                "private PDF custody root must not be a symlink"
            )
        try:
            supplied.mkdir(parents=True, mode=0o700, exist_ok=False)
            os.chmod(supplied, 0o700, follow_symlinks=False)
        except FileExistsError:
            raise CitationDocumentCustodyError(
                "private PDF custody root already exists"
            ) from None
        root = AuthorizedRoot.existing(
            supplied,
            label="private citation-document custody",
            root_alias=root_alias,
            storage_class=RootStorageClass.LOCAL,
        )
        return cls(root=root, max_pdf_bytes=max_pdf_bytes)

    def receive(
        self,
        source: BinaryIO,
        *,
        media_type: str,
    ) -> CitationDocumentReceipt:
        """Validate declared MIME and atomically retain one exact PDF stream."""
        _require_private_root(self.root, field_name="custody root")
        if type(media_type) is not str or media_type != "application/pdf":
            raise CitationDocumentCustodyError(
                "declared media_type must be application/pdf"
            )
        if not callable(getattr(source, "read", None)):
            raise TypeError("source must be a readable binary stream")
        sha256, byte_size = _receive_into_root(
            self.root,
            source,
            max_bytes=self.max_pdf_bytes,
        )
        descriptor = CitationSourceDocumentDescriptor(
            source_document_id=f"private-pdf:sha256:{sha256}",
            sha256=sha256,
            byte_size=byte_size,
            media_type=media_type,
        )
        return CitationDocumentReceipt(source_document=descriptor)

    def read_for_ingestion(self, receipt: CitationDocumentReceipt) -> bytes:
        """Read retained bytes once through the bounded owner primitive."""
        _require_private_root(self.root, field_name="custody root")
        if type(receipt) is not CitationDocumentReceipt:
            raise TypeError("receipt must be a CitationDocumentReceipt")
        receipt.validate_identity()
        descriptor = receipt.source_document
        relative = _blob_name(descriptor.sha256)
        try:
            metadata = self.root.child_path(relative).lstat()
        except OSError as error:
            raise CitationDocumentCustodyError("retained PDF is unavailable") from error
        if (
            metadata.st_dev != self.root.device
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size != descriptor.byte_size
        ):
            raise CitationDocumentCustodyError(
                "retained PDF is not an exact mode-0600 regular file"
            )
        data = self.root.read_bytes(
            relative,
            max_bytes=self.max_pdf_bytes,
        )
        # The Ingestion call also validates these exact expectations.  This
        # check gives custody callers a precise failure before processing.
        if (
            len(data) != descriptor.byte_size
            or hashlib.sha256(data).hexdigest() != descriptor.sha256
            or not data.startswith(b"%PDF-")
        ):
            raise CitationDocumentCustodyError(
                "retained PDF no longer matches its custody receipt"
            )
        return data


def _blob_name(sha256: str) -> str:
    return f"citation-document-blob-{sha256}.pdf"


def _require_private_root(
    root: AuthorizedRoot,
    *,
    field_name: str,
) -> None:
    if type(root) is not AuthorizedRoot:
        raise TypeError(f"{field_name} must be an exact AuthorizedRoot")
    if root.preflight_evidence.storage_class is not RootStorageClass.LOCAL:
        raise CitationDocumentCustodyError(f"{field_name} must use local storage")
    try:
        metadata = root.path.stat(follow_symlinks=False)
    except OSError as error:
        raise CitationDocumentCustodyError(f"{field_name} is unavailable") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_dev != root.device
        or metadata.st_ino != root.inode
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise CitationDocumentCustodyError(
            f"{field_name} must retain exact mode 0700 and identity"
        )


def _require_mode_0600_files(
    root: AuthorizedRoot,
    *,
    field_name: str,
    max_files: int = 50_000,
) -> None:
    _require_private_root(root, field_name=field_name)
    try:
        paths = root.iter_files(
            suffix="",
            recursive=True,
            reject_directories=False,
            max_files=max_files,
            max_entries=max_files + 10_000,
            max_depth=8,
        )
        for relative in paths:
            metadata = root.child_path(relative).lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise CitationDocumentCustodyError(
                    f"{field_name} retained files must be regular mode-0600 files"
                )
    except CitationDocumentCustodyError:
        raise
    except (OSError, ValueError) as error:
        raise CitationDocumentCustodyError(
            f"{field_name} retained file inventory is unsafe"
        ) from error


def _open_root(root: AuthorizedRoot) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(root.path, flags)
    except OSError as error:
        raise CitationDocumentCustodyError(
            "private PDF custody root cannot be safely opened"
        ) from error
    metadata = os.fstat(descriptor)
    if (
        metadata.st_dev != root.device
        or metadata.st_ino != root.inode
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        os.close(descriptor)
        raise CitationDocumentCustodyError(
            "private PDF custody root identity or mode changed"
        )
    return descriptor


def _receive_into_root(
    root: AuthorizedRoot,
    source: BinaryIO,
    *,
    max_bytes: int,
) -> tuple[str, int]:
    directory = _open_root(root)
    temporary = f".koios-custody-{secrets.token_hex(16)}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory,
        )
        os.fchmod(descriptor, 0o600)
        digest = hashlib.sha256()
        prefix = bytearray()
        byte_size = 0
        with os.fdopen(descriptor, "wb", closefd=False) as destination:
            while True:
                block = source.read(_CUSTODY_CHUNK_BYTES)
                if not isinstance(block, bytes):
                    raise TypeError("PDF stream must yield bytes")
                if not block:
                    break
                if len(block) > _CUSTODY_CHUNK_BYTES:
                    raise CitationDocumentCustodyLimitError(
                        "PDF stream returned an oversized chunk"
                    )
                byte_size += len(block)
                if byte_size > max_bytes:
                    raise CitationDocumentCustodyLimitError(
                        "PDF exceeds the configured custody byte bound"
                    )
                digest.update(block)
                if len(prefix) < 5:
                    prefix.extend(block[: 5 - len(prefix)])
                destination.write(block)
            if byte_size == 0:
                raise CitationDocumentCustodyError("PDF stream is empty")
            if bytes(prefix) != b"%PDF-":
                raise CitationDocumentCustodyError(
                    "PDF stream does not begin with the required %PDF- header"
                )
            destination.flush()
            os.fsync(destination.fileno())
        temporary_metadata = os.fstat(descriptor)
        if (
            temporary_metadata.st_dev != root.device
            or not stat.S_ISREG(temporary_metadata.st_mode)
            or stat.S_IMODE(temporary_metadata.st_mode) != 0o600
            or temporary_metadata.st_size != byte_size
        ):
            raise CitationDocumentCustodyError(
                "private PDF temporary file is unsafe or changed"
            )
        sha256 = digest.hexdigest()
        leaf = _blob_name(sha256)
        try:
            os.link(
                temporary,
                leaf,
                src_dir_fd=directory,
                dst_dir_fd=directory,
                follow_symlinks=False,
            )
        except FileExistsError:
            _require_existing_match(
                root,
                directory,
                leaf,
                expected_sha256=sha256,
                expected_size=byte_size,
                max_bytes=max_bytes,
            )
        else:
            _require_link_identity(
                root,
                directory,
                leaf,
                temporary_metadata=temporary_metadata,
            )
        os.unlink(temporary, dir_fd=directory)
        os.fsync(directory)
        os.close(descriptor)
        descriptor = -1
        return sha256, byte_size
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory)
        raise
    finally:
        os.close(directory)


def _require_link_identity(
    root: AuthorizedRoot,
    directory: int,
    leaf: str,
    *,
    temporary_metadata: os.stat_result,
) -> None:
    try:
        metadata = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
    except OSError as error:
        raise CitationDocumentCustodyError(
            "private PDF publication is unavailable"
        ) from error
    if (
        metadata.st_dev != root.device
        or metadata.st_ino != temporary_metadata.st_ino
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size != temporary_metadata.st_size
    ):
        raise CitationDocumentCustodyError(
            "private PDF publication identity is unsafe or changed"
        )


def _require_existing_match(
    root: AuthorizedRoot,
    directory: int,
    leaf: str,
    *,
    expected_sha256: str,
    expected_size: int,
    max_bytes: int,
) -> None:
    try:
        metadata = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        raise CitationDocumentCustodyError(
            "private custody destination disappeared"
        ) from None
    if (
        metadata.st_dev != root.device
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size != expected_size
    ):
        raise CitationDocumentCustodyError(
            "private custody destination is unsafe or different"
        )
    observation = root.observe_file(
        leaf,
        max_bytes=max_bytes,
        prefix_bytes=5,
    )
    if (
        observation.sha256 != expected_sha256
        or observation.byte_size != expected_size
        or observation.prefix != b"%PDF-"
    ):
        raise CitationDocumentCustodyError("private custody destination is different")
