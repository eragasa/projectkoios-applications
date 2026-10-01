from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import subprocess
import sys
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
    CitationDocumentReceipt,
    CitationDocumentRegistry,
    CitationDocumentRegistryError,
    CitationDocumentRegistryLimitError,
    CitationDocumentRegistryProjection,
    CitationDocumentTerminalStatus,
    PrivatePdfCustody,
)
from projectkoios.base import (
    DataObjectActionizer,
    DataObjectActionRequest,
    DataObjectActionResult,
    DataObjectModel,
)
from projectkoios.ingestion import (
    PdfExtractionArtifactLimits,
    PdfExtractionConfiguration,
    extract_pdf_bytes_artifacts,
)
from projectkoios.references import AuthorizedRoot, RootStorageClass
from projectkoios.references.bibliography import (
    CitationBibliographyObservationBinding,
)
from projectkoios.references.citation_document import (
    CitationDocumentProjectionRequest,
    CitationDocumentProjectionResult,
    CitationDocumentProjector,
    CitationSourceDocumentDescriptor,
)
from projectkoios.references.citations import (
    CitationContentIdentity,
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


def _projection(
    receipt: CitationDocumentReceipt,
) -> tuple[CitationDocumentProjectionResult, str, str]:
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
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return AuthorizedRoot.existing(
        path,
        label=alias,
        root_alias=alias,
        storage_class=RootStorageClass.LOCAL,
    )


def _intent(receipt: CitationDocumentReceipt) -> CitationDocumentIngestionIntent:
    projection, item_id, identity_item_id = _projection(receipt)
    return CitationDocumentIngestionIntent(
        receipt=receipt,
        projection_result=projection,
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
    receipt = custody.receive(stream, media_type="application/pdf")

    assert stream.requested_sizes
    assert max(stream.requested_sizes) <= 1_048_576
    assert receipt.source_document.sha256 == hashlib.sha256(content).hexdigest()
    assert custody.read_for_ingestion(receipt) == content
    assert (tmp_path / "custody").stat().st_mode & 0o777 == 0o700
    blob = next((tmp_path / "custody").iterdir())
    assert blob.stat().st_mode & 0o777 == 0o600

    assert custody.receive(io.BytesIO(content), media_type="application/pdf") == receipt

    class MustNotRead(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            del size
            raise AssertionError("wrong declared MIME must fail before reading")

    with pytest.raises(CitationDocumentCustodyError, match="media_type"):
        custody.receive(MustNotRead(content), media_type="application/octet-stream")
    with pytest.raises(CitationDocumentCustodyError, match="%PDF-"):
        custody.receive(io.BytesIO(b"not-a-pdf"), media_type="application/pdf")
    with pytest.raises(CitationDocumentCustodyLimitError):
        custody.receive(
            io.BytesIO(b"%PDF-" + b"x" * 20),
            media_type="application/pdf",
        )


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
        custody.receive(io.BytesIO(content), media_type="application/pdf")


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
    first_receipt = custody.receive(
        io.BytesIO(_pdf("First document")), media_type="application/pdf"
    )
    first_request = service.request(_intent(first_receipt))
    first = service.ingest(first_request)

    assert first.status is CitationDocumentTerminalStatus.SUCCEEDED
    assert first.transcript_ready
    assert first.physical_page_count == 1
    assert calls == 1
    assert service.ingest(first_request) == first
    assert calls == 1

    second_receipt = custody.receive(
        io.BytesIO(_pdf("Second document")), media_type="application/pdf"
    )
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
    receipt = custody.receive(
        io.BytesIO(_pdf("Reconciliation document")),
        media_type="application/pdf",
    )
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
    receipt = custody.receive(
        io.BytesIO(_pdf("Failure document")), media_type="application/pdf"
    )
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
    receipt = custody.receive(
        io.BytesIO(_pdf("Partial document")), media_type="application/pdf"
    )
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
    receipt = custody.receive(
        io.BytesIO(_pdf("Forgery document")), media_type="application/pdf"
    )
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
    receipt = custody.receive(
        io.BytesIO(_pdf("Forged registry document")),
        media_type="application/pdf",
    )
    request = service.request(_intent(receipt))
    service.ingest(request)
    record = next(service.registry.root.path.iterdir())
    value = json.loads(record.read_bytes())
    value["result"]["result_id"] = (
        "citation-document-ingestion-result:sha256:" + "0" * 64
    )
    record.write_text(json.dumps(value))

    with pytest.raises(CitationDocumentRegistryError, match="malformed"):
        service.registry.project()


def test_intent_binds_local_authority_without_claiming_user_authentication(
    tmp_path: Path,
) -> None:
    custody, _ = _service(tmp_path)
    receipt = custody.receive(
        io.BytesIO(_pdf("Authority document")), media_type="application/pdf"
    )
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


def test_data_object_taxonomy_and_semantic_replay_reject_mutable_forgery(
    tmp_path: Path,
) -> None:
    custody, service = _service(tmp_path)
    receipt = custody.receive(
        io.BytesIO(_pdf("Taxonomy document")), media_type="application/pdf"
    )
    intent = _intent(receipt)
    request = service.request(intent)
    with pytest.raises(TypeError):
        service.action(request)  # type: ignore[call-arg]
    result = service.action(request=request)
    projection = service.registry.project()

    assert isinstance(receipt, DataObjectModel)
    assert isinstance(intent, DataObjectModel)
    assert isinstance(request, DataObjectActionRequest)
    assert isinstance(result, DataObjectActionResult)
    assert isinstance(projection, DataObjectModel)
    assert isinstance(service, DataObjectActionizer)
    receipt.validate_identity()
    intent.validate_identity()
    request.validate_identity()
    result.validate_identity()
    projection.validate_identity()

    forged_receipt = CitationDocumentReceipt(source_document=receipt.source_document)
    object.__setattr__(forged_receipt, "receipt_id", "forged-receipt")
    with pytest.raises(ValueError, match="receipt does not match replay"):
        forged_receipt.validate_identity()

    forged_intent = _intent(receipt)
    object.__setattr__(forged_intent, "intent_id", "forged-intent")
    with pytest.raises(ValueError, match="intent does not match replay"):
        service.request(forged_intent)

    forged_request = service.request(_intent(receipt))
    object.__setattr__(forged_request, "request_id", "forged-request")
    with pytest.raises(ValueError, match="request does not match replay"):
        service.action(request=forged_request)

    object.__setattr__(result, "result_id", "forged-result")
    with pytest.raises(ValueError, match="result does not match replay"):
        service.registry.record(request, result)


def test_exact_runtime_types_reject_subclass_and_overridden_validator(
    tmp_path: Path,
) -> None:
    custody, service = _service(tmp_path)
    receipt = custody.receive(
        io.BytesIO(_pdf("Subtype document")), media_type="application/pdf"
    )

    receipt_subclass = type(
        "ReceiptSubclass",
        (CitationDocumentReceipt,),
        {"validate_identity": lambda self: None},
    )
    overridden_receipt = receipt_subclass(source_document=receipt.source_document)
    assert overridden_receipt.validate_identity() is None
    projection, item_id, identity_item_id = _projection(receipt)
    with pytest.raises(TypeError, match="receipt"):
        CitationDocumentIngestionIntent(
            receipt=overridden_receipt,
            projection_result=projection,
            projection_item_id=item_id,
            identity_item_id=identity_item_id,
            local_processing_authority_assertion_id="authority:one",
            local_processing_admission_decision_id="admission:one",
            extraction_configuration=PdfExtractionConfiguration(),
            artifact_limits=PdfExtractionArtifactLimits(),
        )

    descriptor_subclass = type(
        "DescriptorSubclass",
        (CitationSourceDocumentDescriptor,),
        {},
    )
    descriptor = descriptor_subclass(
        source_document_id=receipt.source_document.source_document_id,
        sha256=receipt.source_document.sha256,
        byte_size=receipt.source_document.byte_size,
    )
    with pytest.raises(TypeError, match="source_document"):
        CitationDocumentReceipt(source_document=descriptor)

    exact_request = service.request(_intent(receipt))
    link_result_subclass = type(
        "LinkResultSubclass",
        (type(exact_request.link_result),),
        {"validate_identity": lambda self: None},
    )
    overridden_link_result = link_result_subclass(
        request=exact_request.link_result.request,
        link=exact_request.link_result.link,
    )
    assert overridden_link_result.validate_identity() is None
    with pytest.raises(TypeError, match="link_result"):
        CitationDocumentIngestionRequest(
            intent=exact_request.intent,
            link_result=overridden_link_result,
        )

    root = service.package_root
    root_subclass = type("AuthorizedRootSubclass", (AuthorizedRoot,), {})
    overridden_root = root_subclass(
        path=root.path,
        label=root.label,
        device=root.device,
        inode=root.inode,
        preflight_evidence=root.preflight_evidence,
        placeholder_probe=root.placeholder_probe,
    )
    with pytest.raises(TypeError, match="exact AuthorizedRoot"):
        CitationDocumentRegistry(overridden_root)

    service_subclass = type(
        "ServiceSubclass",
        (CitationDocumentIngestionService,),
        {},
    )
    overridden_service = service_subclass(
        custody=service.custody,
        package_root=service.package_root,
        registry=service.registry,
    )
    with pytest.raises(TypeError, match="exact CitationDocumentIngestionService"):
        overridden_service.request(_intent(receipt))


def test_transcript_failure_after_publication_is_indeterminate(
    tmp_path: Path,
) -> None:
    calls = 0

    def counted_extractor(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return extract_pdf_bytes_artifacts(*args, **kwargs)  # type: ignore[arg-type]

    def broken_projector(**kwargs: object) -> object:
        del kwargs
        raise RuntimeError("synthetic transcript failure")

    custody, base = _service(tmp_path, extractor=counted_extractor)
    service = replace(
        base,
        transcript_projector=broken_projector,  # type: ignore[arg-type]
    )
    receipt = custody.receive(
        io.BytesIO(_pdf("Transcript failure")), media_type="application/pdf"
    )
    request = service.request(_intent(receipt))
    result = service.action(request=request)

    assert service.package_root.state(request.document_id) == "directory"
    assert result.status is CitationDocumentTerminalStatus.INDETERMINATE
    assert result.failure_code is (
        CitationDocumentFailureCode.TRANSCRIPT_VERIFICATION_FAILED
    )
    assert not result.transcript_ready
    assert service.action(request=request) == result
    assert calls == 1


def test_registry_persistence_failure_raises_without_fabricated_result(
    tmp_path: Path,
) -> None:
    custody = PrivatePdfCustody.create(tmp_path / "custody")
    registry = CitationDocumentRegistry(
        _root(tmp_path / "registry", "registry"),
        max_entries=1,
    )
    service = CitationDocumentIngestionService(
        custody=custody,
        package_root=_root(tmp_path / "packages", "packages"),
        registry=registry,
    )
    first_receipt = custody.receive(
        io.BytesIO(_pdf("Registry first")), media_type="application/pdf"
    )
    assert service.action(
        request=service.request(_intent(first_receipt))
    ).transcript_ready

    calls = 0

    def counted_extractor(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return extract_pdf_bytes_artifacts(*args, **kwargs)  # type: ignore[arg-type]

    service = replace(
        service,
        extractor=counted_extractor,  # type: ignore[arg-type]
    )
    second_receipt = custody.receive(
        io.BytesIO(_pdf("Registry second")), media_type="application/pdf"
    )
    second_request = service.request(_intent(second_receipt))
    with pytest.raises(CitationDocumentRegistryLimitError, match="full"):
        service.action(request=second_request)
    assert service.package_root.state(second_request.document_id) == "directory"
    assert calls == 1

    with pytest.raises(CitationDocumentRegistryLimitError, match="full"):
        service.action(request=second_request)
    assert calls == 1


def test_registry_reload_retains_complete_neutral_link_lineage(
    tmp_path: Path,
) -> None:
    custody, service = _service(tmp_path)
    receipt = custody.receive(
        io.BytesIO(_pdf("Restart catalog")), media_type="application/pdf"
    )
    request = service.request(_intent(receipt))
    result = service.action(request=request)

    root = service.registry.root
    reopened_root = AuthorizedRoot.existing(
        root.path,
        label="reopened registry",
        root_alias=root.preflight_evidence.root_alias,
        storage_class=RootStorageClass.LOCAL,
    )
    reopened = CitationDocumentRegistry(reopened_root)
    catalog = reopened.project()
    reloaded = catalog.results[0]
    link = reloaded.source_document_link

    assert reloaded == result
    assert link.target_snapshot_id == request.link_result.link.target_snapshot_id
    assert link.prior_item_id == request.link_result.link.prior_item_id
    assert link.literal_citekey == "paperKey"
    assert link.identity_item_id == request.link_result.link.identity_item_id
    assert link.requested_identity_id == request.link_result.link.requested_identity_id
    assert link.source_document == receipt.source_document
    assert link.linkage_basis == "explicit-upload-for-requested-citation"
    assert link.limitations == request.link_result.link.limitations

    fresh_process = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json
import sys
from pathlib import Path
from projectkoios.applications.pdf_corpus_ingestion import CitationDocumentRegistry
from projectkoios.references import AuthorizedRoot, RootStorageClass

root = AuthorizedRoot.existing(
    Path(sys.argv[1]),
    label="fresh-process registry",
    root_alias="registry",
    storage_class=RootStorageClass.LOCAL,
)
result = CitationDocumentRegistry(root).project().results[0]
link = result.source_document_link
print(json.dumps({
    "result_id": result.result_id,
    "target_snapshot_id": link.target_snapshot_id,
    "prior_item_id": link.prior_item_id,
    "identity_item_id": link.identity_item_id,
    "source_document_id": link.source_document.source_document_id,
    "link_id": link.link_id,
}, sort_keys=True))
""",
            str(root.path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    correlation = json.loads(fresh_process.stdout)
    assert correlation == {
        "identity_item_id": link.identity_item_id,
        "link_id": link.link_id,
        "prior_item_id": link.prior_item_id,
        "result_id": result.result_id,
        "source_document_id": link.source_document.source_document_id,
        "target_snapshot_id": link.target_snapshot_id,
    }


def test_effect_roots_are_private_disjoint_and_exact(tmp_path: Path) -> None:
    custody = PrivatePdfCustody.create(tmp_path / "custody")
    registry = CitationDocumentRegistry(_root(tmp_path / "registry", "registry"))

    public_path = tmp_path / "public-package"
    public_path.mkdir(mode=0o755)
    os.chmod(public_path, 0o755)
    public_root = AuthorizedRoot.existing(
        public_path,
        label="public package",
        root_alias="public-package",
        storage_class=RootStorageClass.LOCAL,
    )
    with pytest.raises(CitationDocumentCustodyError, match="0700"):
        CitationDocumentIngestionService(
            custody=custody,
            package_root=public_root,
            registry=registry,
        )

    with pytest.raises(ValueError, match="disjoint"):
        CitationDocumentIngestionService(
            custody=custody,
            package_root=custody.root,
            registry=registry,
        )

    nested_path = custody.root.path / "nested-package"
    nested_path.mkdir(mode=0o700)
    os.chmod(nested_path, 0o700)
    nested = AuthorizedRoot.existing(
        nested_path,
        label="nested package",
        root_alias="nested-package",
        storage_class=RootStorageClass.LOCAL,
    )
    with pytest.raises(ValueError, match="non-nested"):
        CitationDocumentIngestionService(
            custody=custody,
            package_root=nested,
            registry=registry,
        )

    public_registry_path = tmp_path / "public-registry"
    public_registry_path.mkdir(mode=0o755)
    os.chmod(public_registry_path, 0o755)
    public_registry = AuthorizedRoot.existing(
        public_registry_path,
        label="public registry",
        root_alias="public-registry",
        storage_class=RootStorageClass.LOCAL,
    )
    with pytest.raises(CitationDocumentCustodyError, match="0700"):
        CitationDocumentRegistry(public_registry)


def test_effect_roots_are_revalidated_after_construction(tmp_path: Path) -> None:
    custody, service = _service(tmp_path)
    receipt = custody.receive(
        io.BytesIO(_pdf("Mutable root state")), media_type="application/pdf"
    )
    request = service.request(_intent(receipt))

    os.chmod(service.registry.root.path, 0o755)
    with pytest.raises(CitationDocumentCustodyError, match="0700"):
        service.action(request=request)
    os.chmod(service.registry.root.path, 0o700)

    os.chmod(custody.root.path, 0o755)
    with pytest.raises(CitationDocumentCustodyError, match="0700"):
        custody.receive(
            io.BytesIO(_pdf("Rejected mutable root")),
            media_type="application/pdf",
        )
    os.chmod(custody.root.path, 0o700)
    custody_blob = next(custody.root.path.iterdir())
    os.chmod(custody_blob, 0o644)
    with pytest.raises(CitationDocumentCustodyError, match="0600"):
        custody.read_for_ingestion(receipt)
    os.chmod(custody_blob, 0o600)

    os.chmod(service.package_root.path, 0o755)
    with pytest.raises(CitationDocumentCustodyError, match="0700"):
        service.action(request=request)


def test_successful_effect_retains_mode_0600_files(tmp_path: Path) -> None:
    custody, service = _service(tmp_path)
    receipt = custody.receive(
        io.BytesIO(_pdf("Private files")), media_type="application/pdf"
    )
    request = service.request(_intent(receipt))
    result = service.action(request=request)
    assert result.transcript_ready

    for root in (
        custody.root.path,
        service.package_root.path,
        service.registry.root.path,
    ):
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        for path in root.rglob("*"):
            mode = stat.S_IMODE(path.stat().st_mode)
            assert mode == (0o700 if path.is_dir() else 0o600)

    registry_file = next(service.registry.root.path.iterdir())
    os.chmod(registry_file, 0o644)
    with pytest.raises(CitationDocumentRegistryError, match="0600"):
        service.action(request=request)
    os.chmod(registry_file, 0o600)

    package_file = next(
        path for path in service.package_root.path.rglob("*") if path.is_file()
    )
    os.chmod(package_file, 0o644)
    with pytest.raises(CitationDocumentRegistryError, match="transcript"):
        service.action(request=request)


def test_registry_contract_envelope_and_projection_contract_are_closed(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="contract"):
        CitationDocumentRegistryProjection(
            results=(),
            successful_document_ids=(),
            contract_id="caller-selected-registry-contract",
        )

    custody, service = _service(tmp_path)
    receipt = custody.receive(
        io.BytesIO(_pdf("Registry envelope")), media_type="application/pdf"
    )
    result = service.action(request=service.request(_intent(receipt)))
    record = next(service.registry.root.path.iterdir())
    envelope = json.loads(record.read_bytes())

    assert envelope["contract_id"] == (
        "projectkoios.applications.citation-document-registry"
    )
    assert envelope["result"]["contract_id"] == (
        "projectkoios.applications.citation-document-ingestion"
    )
    assert result.record_payload()["contract_id"] == (
        "projectkoios.applications.citation-document-ingestion"
    )

    envelope["contract_id"] = "caller-selected-registry-contract"
    record.write_text(json.dumps(envelope))
    with pytest.raises(CitationDocumentRegistryError, match="malformed"):
        service.registry.project()
