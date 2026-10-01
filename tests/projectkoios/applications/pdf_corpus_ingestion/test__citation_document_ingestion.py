from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import cast

import pymupdf
import pytest

from projectkoios.applications.pdf_corpus_ingestion import (
    CitationDocumentCustodyError,
    CitationDocumentCustodyLimitError,
    CitationDocumentFailureCode,
    CitationDocumentIngestionIntent,
    CitationDocumentIngestionRequest,
    CitationDocumentIngestionService,
    CitationDocumentRegistry,
    CitationDocumentRegistryError,
    CitationDocumentTerminalStatus,
    PrivatePdfCustody,
)
from projectkoios.ingestion import (
    PdfExtractionArtifactLimits,
    PdfExtractionConfiguration,
    extract_pdf_bytes_artifacts,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass
from projectkoios.references.citation_document import (
    CitationBibliographyObservationBinding,
    CitationContentIdentity,
    CitationDocumentProjectionRequest,
    CitationDocumentProjector,
    CitationSourceLocator,
    CitationTargetBibliographyEntry,
    CitationTargetGroup,
    CitationTargetOccurrence,
    CitationTargetSnapshot,
)
from projectkoios.references.identity import (
    ProducerIdentity,
    ReferenceCandidate,
    SourceBibliographyObservation,
    replay_identity_decisions,
)


def _pdf(text: str) -> bytes:
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    page = document.new_page(width=300, height=300)
    page.insert_text((40, 100), text, fontsize=12)
    content = document.tobytes()  # type: ignore[no-untyped-call]
    document.close()  # type: ignore[no-untyped-call]
    return cast(bytes, content)


def _target_id(prefix: str, label: str) -> str:
    return f"{prefix}:{hashlib.sha256(label.encode()).hexdigest()}"


def _content_identity(content: bytes) -> CitationContentIdentity:
    return CitationContentIdentity(
        algorithm="sha256",
        digest=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
    )


def _projection(receipt: object) -> tuple[object, str, str]:
    assert hasattr(receipt, "observation")
    key = "paperKey"
    bibliography = b"@article{paperKey}\n"
    source = b"\\cite{paperKey}"
    observation = SourceBibliographyObservation.create(
        source_id="citation-document-test",
        asserted_source_revision="synthetic-revision",
        source_path="references.bib",
        bibliography_bytes=bibliography,
        entry_index=0,
        observed_citekey=key,
        verbatim_entry=bibliography.decode(),
        parser=ProducerIdentity("synthetic-parser", "1"),
    )
    candidate = ReferenceCandidate.create(
        proposed_citekey=key,
        entry_type="article",
        title="Synthetic article",
        authors=("A. Author",),
        year="2026",
        source_observation_ids=(observation.observation_id,),
        generator=ProducerIdentity("citation-document-test", "1"),
    )
    identity_projection = replay_identity_decisions((candidate,), ())
    entry = CitationTargetBibliographyEntry(
        entry_id=_target_id("citation-entry", "entry"),
        entry_index=0,
        key=key,
        entry_type="article",
        locator=CitationSourceLocator(
            source_path="references.bib",
            source_content_identity=_content_identity(bibliography),
            include_index=0,
            byte_start=0,
            byte_end=len(bibliography),
            line=1,
            column=1,
        ),
        entry_content_identity=_content_identity(bibliography),
    )
    occurrence = CitationTargetOccurrence(
        occurrence_id=_target_id("citation-occurrence", "occurrence"),
        occurrence_index=0,
        call_index=0,
        key_index=0,
        key=key,
        origin="direct",
        locator=CitationSourceLocator(
            source_path="manuscript/main.tex",
            source_content_identity=_content_identity(source),
            include_index=0,
            byte_start=0,
            byte_end=len(source),
            line=1,
            column=1,
        ),
        bibliography_entry_index=0,
        todo_marker_index=None,
    )
    group = CitationTargetGroup(
        group_id=_target_id("citation-group", "group"),
        group_index=0,
        key=key,
        occurrence_indexes=(0,),
        direct_occurrence_count=1,
        generated_occurrence_count=0,
        bibliography_entry_index=0,
    )
    snapshot = CitationTargetSnapshot(
        snapshot_id=_target_id("citation-snapshot", "snapshot"),
        bibliography_source_path="references.bib",
        bibliography_content_identity=_content_identity(bibliography),
        occurrences=(occurrence,),
        groups=(group,),
        bibliography_entries=(entry,),
        source_gaps=(),
        missing_keys=(),
        duplicate_keys=(),
        uncited_keys=(),
    )
    binding = CitationBibliographyObservationBinding(
        entry=entry,
        observation=observation,
    )
    document_observation = receipt.observation(
        target_snapshot_id=snapshot.snapshot_id,
        literal_citekey=key,
    )
    result = CitationDocumentProjector().project(
        request=CitationDocumentProjectionRequest(
            target_snapshot=snapshot,
            bibliography_bindings=(binding,),
            identity_projection=identity_projection,
            document_observations=(document_observation,),
        )
    )
    item = result.projection.items[0]
    return result, item.item_id, item.identity_items[0].item_id


def _root(path: Path, alias: str) -> AuthorizedRoot:
    return AuthorizedRoot.create(
        path,
        label=alias,
        root_alias=alias,
        storage_class=RootStorageClass.LOCAL,
    )


def _intent(receipt: object) -> CitationDocumentIngestionIntent:
    projection, item_id, identity_item_id = _projection(receipt)
    return CitationDocumentIngestionIntent(
        receipt=receipt,  # type: ignore[arg-type]
        projection_result=projection,  # type: ignore[arg-type]
        projection_item_id=item_id,
        identity_item_id=identity_item_id,
        local_processing_authority_assertion_id=(
            "local-operator-configuration:sha256:" + "a" * 64
        ),
        local_processing_admission_decision_id=(
            "private-processing-admission:sha256:" + "b" * 64
        ),
        extraction_configuration=PdfExtractionConfiguration(
            low_text_character_threshold=0,
            maximum_pages=10,
        ),
        artifact_limits=PdfExtractionArtifactLimits(),
    )


def _service(
    tmp_path: Path,
    *,
    max_pdf_bytes: int = 50_000_000,
    extractor: object = extract_pdf_bytes_artifacts,
) -> tuple[PrivatePdfCustody, CitationDocumentIngestionService]:
    custody = PrivatePdfCustody.create(
        tmp_path / "custody",
        max_pdf_bytes=max_pdf_bytes,
    )
    registry = CitationDocumentRegistry(_root(tmp_path / "registry", "registry"))
    service = CitationDocumentIngestionService(
        custody=custody,
        package_root=_root(tmp_path / "packages", "packages"),
        registry=registry,
        extractor=extractor,  # type: ignore[arg-type]
    )
    return custody, service


def test_private_custody_streams_with_exact_bounds_and_permissions(
    tmp_path: Path,
) -> None:
    class ShortReadStream(io.BytesIO):
        requested_sizes: list[int]

        def __init__(self, content: bytes) -> None:
            super().__init__(content)
            self.requested_sizes = []

        def read(self, size: int | None = -1) -> bytes:
            if size is None or size < 0:
                raise AssertionError("custody must not request an unbounded read")
            self.requested_sizes.append(size)
            return super().read(min(size, 7))

    custody = PrivatePdfCustody.create(
        tmp_path / "custody",
        max_pdf_bytes=20,
    )
    content = b"%PDF-1.7\nsynthetic"
    stream = ShortReadStream(content)
    receipt = custody.receive(stream)

    assert stream.requested_sizes
    assert max(stream.requested_sizes) <= 1_048_576
    assert receipt.source_document.sha256 == hashlib.sha256(content).hexdigest()
    assert custody.read_for_ingestion(receipt) == content
    assert (tmp_path / "custody").stat().st_mode & 0o777 == 0o700
    blob = next((tmp_path / "custody").iterdir())
    assert blob.stat().st_mode & 0o777 == 0o600

    assert custody.receive(io.BytesIO(content)) == receipt
    with pytest.raises(CitationDocumentCustodyError, match="%PDF-"):
        custody.receive(io.BytesIO(b"not-a-pdf"))
    with pytest.raises(CitationDocumentCustodyLimitError):
        custody.receive(io.BytesIO(b"%PDF-" + b"x" * 20))


def test_private_custody_rejects_a_symlinked_blob_destination(
    tmp_path: Path,
) -> None:
    custody = PrivatePdfCustody.create(tmp_path / "custody")
    content = b"%PDF-1.7\nsymlink"
    digest = hashlib.sha256(content).hexdigest()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(content)
    destination = custody.root.path / f"citation-document-blob-{digest}.pdf"
    destination.symlink_to(outside)

    with pytest.raises(CitationDocumentCustodyError, match="unsafe"):
        custody.receive(io.BytesIO(content))


def test_private_custody_rejects_public_or_symlinked_roots(tmp_path: Path) -> None:
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    os.chmod(public, 0o755)
    root = AuthorizedRoot.existing(
        public,
        label="public",
        root_alias="public",
        storage_class=RootStorageClass.LOCAL,
    )
    with pytest.raises(CitationDocumentCustodyError, match="0700"):
        PrivatePdfCustody(root)

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(CitationDocumentCustodyError, match="symlink"):
        PrivatePdfCustody.create(link)


def test_synchronous_success_exact_replay_and_multi_document_registry(
    tmp_path: Path,
) -> None:
    calls = 0

    def counted_extractor(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return extract_pdf_bytes_artifacts(*args, **kwargs)  # type: ignore[arg-type]

    custody, service = _service(tmp_path, extractor=counted_extractor)
    first_receipt = custody.receive(io.BytesIO(_pdf("First document")))
    first_request = service.request(_intent(first_receipt))
    first = service.ingest(first_request)

    assert first.status is CitationDocumentTerminalStatus.SUCCEEDED
    assert first.transcript_ready
    assert first.physical_page_count == 1
    assert calls == 1
    assert service.ingest(first_request) == first
    assert calls == 1

    second_receipt = custody.receive(io.BytesIO(_pdf("Second document")))
    second_request = service.request(_intent(second_receipt))
    second = service.ingest(second_request)
    projection = service.registry.project()

    assert second.status is CitationDocumentTerminalStatus.SUCCEEDED
    assert calls == 2
    assert projection.successful_document_ids == tuple(
        sorted((first.document_id, second.document_id))
    )
    assert service.registry.lookup_document(second.document_id) == second
    transcript = service.registry.transcript(
        document_id=first.document_id,
        package_root=service.package_root,
    )
    assert transcript.projection_id == first.transcript_projection_id


def test_unregistered_existing_package_is_indeterminate_without_reextracting(
    tmp_path: Path,
) -> None:
    custody, first_service = _service(tmp_path)
    receipt = custody.receive(io.BytesIO(_pdf("Reconciliation document")))
    request = first_service.request(_intent(receipt))
    original = first_service.ingest(request)
    assert original.status is CitationDocumentTerminalStatus.SUCCEEDED

    def forbidden_extractor(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("reconciliation must not rerun extraction")

    empty_registry = CitationDocumentRegistry(
        _root(tmp_path / "replacement-registry", "replacement-registry")
    )
    recovering = replace(
        first_service,
        registry=empty_registry,
        extractor=forbidden_extractor,  # type: ignore[arg-type]
    )
    reconciled = recovering.ingest(request)

    assert reconciled.status is CitationDocumentTerminalStatus.INDETERMINATE
    assert reconciled.failure_code is (
        CitationDocumentFailureCode.PUBLICATION_INDETERMINATE
    )
    assert not reconciled.transcript_ready
    assert empty_registry.lookup(request) == reconciled


def test_failed_extraction_is_terminal_and_is_not_retried(tmp_path: Path) -> None:
    calls = 0

    def broken_extractor(*args: object, **kwargs: object) -> object:
        del args, kwargs
        nonlocal calls
        calls += 1
        raise RuntimeError("synthetic extraction failure")

    custody, service = _service(tmp_path, extractor=broken_extractor)
    receipt = custody.receive(io.BytesIO(_pdf("Failure document")))
    request = service.request(_intent(receipt))

    result = service.ingest(request)
    assert result.status is CitationDocumentTerminalStatus.FAILED
    assert result.failure_code is CitationDocumentFailureCode.EXTRACTION_FAILED
    assert not result.transcript_ready
    assert service.ingest(request) == result
    assert calls == 1


def test_partial_publication_is_indeterminate_and_not_retried(
    tmp_path: Path,
) -> None:
    calls = 0

    def counted_extractor(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return extract_pdf_bytes_artifacts(*args, **kwargs)  # type: ignore[arg-type]

    custody, base = _service(tmp_path, extractor=counted_extractor)

    def partial_publisher(package: object, *, output_root: AuthorizedRoot) -> object:
        output_root.create_directory(package.document_key)  # type: ignore[attr-defined]
        raise RuntimeError("synthetic partial publication")

    service = replace(base, package_publisher=partial_publisher)  # type: ignore[arg-type]
    receipt = custody.receive(io.BytesIO(_pdf("Partial document")))
    request = service.request(_intent(receipt))
    result = service.ingest(request)

    assert result.status is CitationDocumentTerminalStatus.INDETERMINATE
    assert result.failure_code is (
        CitationDocumentFailureCode.PUBLICATION_INDETERMINATE
    )
    assert not result.transcript_ready
    assert service.ingest(request) == result
    assert calls == 1


def test_link_result_forgery_and_registry_extras_are_rejected(
    tmp_path: Path,
) -> None:
    custody, service = _service(tmp_path)
    receipt = custody.receive(io.BytesIO(_pdf("Forgery document")))
    intent = _intent(receipt)
    request = service.request(intent)
    forged = request.link_result
    object.__setattr__(forged.link, "pre_effect_intent_id", "forged-intent")

    with pytest.raises(ValueError):
        CitationDocumentIngestionRequest(intent=intent, link_result=forged)

    (service.registry.root.path / "../registry/unsupported.txt").write_text("x")
    with pytest.raises(CitationDocumentRegistryError, match="unsupported"):
        service.registry.project()


def test_registry_rejects_forged_result_identity(tmp_path: Path) -> None:
    custody, service = _service(tmp_path)

    def broken_extractor(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("synthetic extraction failure")

    service = replace(service, extractor=broken_extractor)  # type: ignore[arg-type]
    receipt = custody.receive(io.BytesIO(_pdf("Forged registry document")))
    request = service.request(_intent(receipt))
    service.ingest(request)
    record = next(service.registry.root.path.iterdir())
    value = json.loads(record.read_bytes())
    value["result_id"] = "citation-document-ingestion-result:sha256:" + "0" * 64
    record.write_text(json.dumps(value))

    with pytest.raises(CitationDocumentRegistryError, match="malformed"):
        service.registry.project()


def test_intent_binds_local_authority_without_claiming_user_authentication(
    tmp_path: Path,
) -> None:
    custody, _ = _service(tmp_path)
    receipt = custody.receive(io.BytesIO(_pdf("Authority document")))
    first = _intent(receipt)
    second = replace(
        first,
        local_processing_authority_assertion_id=(
            "local-operator-configuration:sha256:" + "c" * 64
        ),
    )

    assert first.intent_id != second.intent_id
    assert "user" not in first.identity_payload()
    assert "authentication" not in first.identity_payload()
