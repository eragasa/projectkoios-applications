# PDF corpus ingestion application

`projectkoios.applications.pdf_corpus_ingestion` composes references-owned,
bounded PDF discovery with ingestion-owned extraction and document processing.
It does not own filesystem discovery, PDF parsing, cloud placeholder probing,
reference canonicalization, or acceptance.

## Safety and plan boundary

The CLI accepts explicit roots classified as `local` or `cloud-backed`. It never
infers a cloud root and has no default home or filesystem root. Explicit roots
must not overlap or nest, so a broad local declaration cannot bypass cloud
placeholder preflight for a nested File Provider root. Discovery plans contain
aliases and relative paths, never absolute root paths. An application
plan embeds the canonical discovery plan, groups identical SHA-256 content while
retaining every observed location, and selects at most 256 unique contents from
an explicit cursor. The plan also binds an explicit PDF page ceiling compatible
with the owner extraction bound and the application's 10,000-file output
ceiling. Earlier and later contents remain recorded as deferred. Skipped
discovery observations make coverage incomplete and are never treated as
absence. On non-Darwin platforms, a declared `cloud-backed` root is passed to
the references contract without a production probe: references emits typed
`unsupported-platform` root/skip evidence before touching the path or bytes.

`plan` is non-mutating unless `--apply` exclusively creates its plan artifact.
`run` is non-mutating unless `--apply`. Before the first mutation it rebinds and
re-probes every selected source, checks exact size, SHA-256 and PDF header, and
inspects all staging and output targets. Cloud placeholders, symlinks,
non-regular files, drift, ambiguous outputs, and unsupported cloud platforms
fail closed. Runtime disjointness first uses lexical absolute normalization for
all declarations, then owner-binds local and supported cloud roots and compares
their concrete paths against staging, output, and one another. It never resolves
or stats an unsupported cloud root. Only hash-locked bytes copied with
the references safe-copy API to an explicit private local staging root reach
the ingestion-owned pure byte API. That API performs no writes; the application
publishes each immutable owner artifact payload through `AuthorizedRoot`.
Extracted semantics and unresolved-page selection are deterministic and use no
network, external process, OCR, or model. Owner raw evidence records runtime
timestamps, however, so fresh raw artifact bytes and manifest identities are
not claimed reproducible across separate runs.

Each unique content begins with an atomically exclusive final-directory create.
Artifacts are written there, and the canonical completion manifest is
atomically written last. A failure leaves a terminal partial final directory
that later preflight rejects; the application does not claim atomic directory
publication. Replay of one completed publication verifies the strict
application manifest, bounded canonical
page/status/path/identity summaries, and exact artifact path, size, and SHA-256
inventory; it never reruns Ollama. The content-addressed corpus runner still does
not semantically reconstruct renderer or Ollama JSON. Ingestion now exposes a
strict public parser for its PDF extraction artifact bundle; only the current
canonical document-package transcript projection below consumes that seam. Byte replay
detects stale or accidental drift, not an actor able to rewrite both artifacts
and manifest identity. Partial or different output fails closed. Pending, deferred, and failed page
resolution is immutable terminal-incomplete evidence for that plan/output; retry
requires a newly composed plan and fresh output root. It is never reported as
full processing completion.

## Synchronous citation-document ingestion

The citation-document slice composes one explicit uploaded PDF into the current
document package without Search, Workflow, a queue, a background task, or an
automatic retry. Its source-mirroring module documentation covers the
[contracts](citation_document_contracts/index.md),
[custody](citation_document_custody/index.md),
[registry](citation_document_registry/index.md), and
[service](citation_document_service/index.md). `PrivatePdfCustody.receive`
accepts a bounded binary stream with declared MIME exactly `application/pdf`,
checks that MIME, size, SHA-256, and the `%PDF-` header jointly and incrementally,
writes only bounded chunks to a private temporary file, and atomically publishes
an immutable mode-0600 blob under an exact local non-symlink mode-0700 root. The
path-free receipt contains only the
technical descriptor and deterministic receipt identity. It grants no rights,
use, admission, review, bibliographic, or publication authority. Retained bytes
are read from custody once for Ingestion's exact-bytes API.

The receipt can create a positive, explicitly incomplete
`CitationSourceDocumentObservation` for a target's exact literal key. A
`CitationDocumentIngestionIntent` then binds the receipt, an exact replay-valid
References projection Result and selected owner items, configured local-operator
authority assertion and private-processing admission decision identities, and
the complete extraction configuration and artifact limits. These are configured
local policy identities, not proof of an authenticated remote user. The
pre-effect intent exists before linkage. Target inventory types are consumed
from canonical `projectkoios.references.citations`, bibliography bindings from
`projectkoios.references.bibliography`, and document/projection/link contracts
from `projectkoios.references.citation_document`. References receives only its
opaque `pre_effect_intent_id`; its neutral link remains explicitly non-authorizing and
has no dependency on Applications. The downstream request is derived from that
intent plus the exact replay-valid References link Result, which keeps the
identity graph acyclic.

`CitationDocumentIngestionService` is a final `DataObjectActionizer`; its
keyword-only `action(*, request)` is the single synchronous behavior path and
`ingest(request)` delegates to it. It reads exact retained bytes, calls
`extract_pdf_bytes_artifacts`, builds and publishes the current deterministic
package, projects and verifies the exact transcript, and only then publishes an
immutable registry Result. Terminal status is exactly `SUCCEEDED`, `FAILED`, or
`INDETERMINATE`. Only `SUCCEEDED` carries package, extraction, and transcript
readiness evidence. An existing package without an exact retained terminal
Result, or transcript verification failure after publication, yields
`INDETERMINATE` without re-extraction, verification promotion, republication, or
mutation. Registry persistence failure propagates; an unpersisted terminal
Result is never fabricated. Resolving indeterminate state requires a separately
admitted reconciliation capability outside this slice.

`CitationDocumentRegistry` stores at most 10,000 immutable, 64-KB terminal
records under its own registry-contract envelope; the nested Result retains the
complete neutral References link lineage under the ingestion contract. Its
path-free `DataObjectModel` projection is ordered by exact request identity and
lists successful document identities separately. Transcript lookup accepts only a
registered successful document identity and re-verifies the current package and
projection. Failed and indeterminate results remain visible as terminal evidence
but are not documents. This registry is application-level evidence, not Search
admission, a bibliography, a rights ledger, or a human-review decision.
Contract IDs are canonical and unversioned; there is no `@version` suffix or
parallel compatibility shape.

The exact compatibility inputs for this slice are the ksdft citation-target
commit/tree `3ec21b4318020d700be671a8f220b2149b3d28c7` /
`9953c0e99a28443426b5093852292f7cfbada2cc`, References commit/tree
`f1ca7b4aee552af131ff7af7d1408d33dd338c93` /
`b37672e36af13014dc25170be725fbf3f909c2d7`, and Ingestion commit/tree
`be60640bec4fe15cc88b24161545eb1027ffbd2e` /
`d386a1744f79463fd7cd0b3087ee5fc361e0f7d5`. Literal target keys and source
paths remain owner values and are never normalized through filesystem naming
policy. These local Git identities, rather than the prototype `0.0.0` package
labels, define the verified handoff.

## Document-centric deterministic package

The bounded document-package candidate projects one exact source PDF, the
owner-built raw extraction bundle, and ingestion-owned deterministic equation
detection into a human-navigable document directory. It does not reinterpret
owner evidence or accept any proposal:

```text
<document-key>/
├── source/
│   ├── document.pdf
│   └── manifest.json
├── ingestion/
│   ├── extraction.json
│   ├── pages/
│   └── manifest.json
├── content/equations/
│   ├── deterministic/detection.json
│   ├── regions/<candidate-digest>/
│   │   ├── source/{image.png,manifest.json}
│   │   └── deterministic/manifest.json
│   ├── index.json
│   └── manifest.json
└── document-manifest.json
```

`build_deterministic_document_package` is pure and bounded. It requires source
bytes that exactly match an existing `PdfExtractionArtifactBundle`, invokes the
public deterministic equation detector, retains its complete canonical result,
and externalizes each exact rendered candidate image with source and processor
links. The one canonical current document completion contract and its
application ingestion manifest persist the complete canonical public
`PdfExtractionConfiguration` and `PdfExtractionArtifactLimits` values alongside
their configuration digest, bundle identity, source identity, and exact artifact
inventory. This makes owner replay self-contained without interpreting raw
extraction JSON. Alternate or version-tagged package shapes are malformed; they
are never migrated, upgraded, repaired, or accepted alongside the current
shape. The application index is navigational evidence; candidates remain `proposed` or
`ambiguous`. Assisted and human stages are explicitly `not-started` in the
initial deterministic publication. The transcript stage records package
processing state, not human review or acceptance.

`publish_deterministic_document_package` exclusively creates the final
`<document-key>` directory through `AuthorizedRoot`, writes the completion
manifest last, and verifies every deterministic path, size, and SHA-256. Exact
replay reports `unchanged`. After review append, replay still verifies the exact
deterministic inventory while admitting at most 39,998 additional files only in
listed-candidate `assisted/attempt-0001` and contiguous `human/revision-NNNN`
namespaces. A shared cycle-free validator requires canonical manifests, exact
artifact inventories and identities, matching evidence bindings, valid bounded
proposal text and method, contiguous human history, and every historical
assisted reference. Correctly named arbitrary bytes, or any other extra,
partial, or different output, fail closed and are not repaired.
The current corpus runner is not yet switched from its reviewed
content-addressed layout; wiring document keys, corpus completion, and the CLI
is a later application-composition slice.

## Exact document transcript projection

`project_document_transcript(*, document_root=...)` is the narrow read-only seam
for one explicitly supplied local `AuthorizedRoot`. It never searches a corpus
or accepts a document path or ID. It first verifies the exact current completion
identity and every bounded inventoried byte, then validates the application
owned ingestion manifest. It reconstructs the persisted public ingestion
configuration and artifact-limit value objects and calls
`read_pdf_extraction_transcript` with the verified expected bundle ID and source
SHA-256/byte size. Only that ingestion-owned parser interprets raw extraction
JSON. The operation performs no write, network, model, OCR, extraction, or
semantic cleanup.

The frozen path-free `DocumentTranscriptProjection` carries a stable content
identity, package/document/source identities, exact owner metadata, display name,
`AUTOMATED_UNREVIEWED` status, physical-page count, and a tuple of
`DocumentTranscriptPage`. Display name is the exact nonempty PDF `title`
metadata value when present and otherwise the document ID; it is never truncated
or inferred from a path. Every physical page is retained, including an exact
empty string. Pages are complete and ordered with contiguous zero-based
`page_index`, one-based `physical_page`, stable owner page identity, nullable
exact printed label, and exact native text-block content joined by the owner
with two LF characters. Page count is positive and equals tuple length.

Missing completion or owner artifacts raise
`DocumentTranscriptIncompleteError`; unreadable evidence raises
`DocumentTranscriptUnavailableError`; invalid package, binding, bounds, owner
evidence, or an extra version tag raises `DocumentTranscriptMalformedError`.
No exception returns an artifact path. Root selection, document lookup, API
routing/authentication, HTTP status mapping, list behavior, and presentation
remain consumer concerns.

## Append-only equation review

The narrow application-owned review seam keeps immutable assisted attempt schema
2 and writes new human revisions in schema 3. It can read and fully validate an
existing contiguous schema-2 human history before appending a later schema-3
revision; existing records are never rewritten:

```text
content/equations/regions/<candidate-digest>/
├── assisted/attempt-0001/
│   ├── proposal.txt
│   └── manifest.json
└── human/revision-0001/
    ├── decision.json
    ├── obsidian-markdown.md       # acceptance only
    ├── reviewer-latex.txt         # acceptance only
    └── manifest.json
```

`publish_assisted_equation_attempt` supports only immutable attempt 0001. The
proposal SHA-256 covers the exact UTF-8 bytes in `proposal.txt`; its status is
always `automated_unreviewed`. Exact replay is unchanged, while partial or
different existing output fails closed. The attempt directory is created
exclusively, proposal bytes are atomically written without replacement, and its
completion manifest is atomically written last.

`append_human_equation_revision` requires an optimistic
`expected_previous_revision`, scans a bounded contiguous revision inventory,
and exclusively creates only the next revision. Both the pre-create state race
and exclusive-create race are rescanned: an exact completed concurrent revision
is an unchanged replay, different completed evidence is a typed concurrency
failure, and partial or malformed output remains a publication failure. Every
distinct assisted digest referenced anywhere in existing contiguous human
history is revalidated before load or append, so a later unassisted revision
cannot hide missing or corrupt earlier acceptance evidence. A gap, stale
expected revision, or different idempotency replay is rejected. Each
human decision binds the document and candidate identities,
source PDF SHA-256, deterministic candidate-manifest SHA-256, region-image
SHA-256, and—when referenced—the exact attempt-0001 proposal SHA-256. Acceptance
requires that proposal binding and is represented only by the separate human
record; it never mutates or upgrades the assisted status. An accepted reviewer
transcription may be byte-identical to the proposal or a correction, but either
case preserves the proposal provenance.

The required interaction lifecycle is: show the immutable proposal source,
render it, allow editing of canonical reviewer LaTeX, explicitly render the
current representations, and only then perform a separate acceptance. Proposal
text remains immutable and read-only even when an upstream proposal includes
outer math delimiters. Schema-3 reviewer LaTeX is the math body only: creation
and replay reject rather than strip leading or trailing whitespace, CR/CRLF,
non-NFC Unicode, and outer `$...$` or `$$...$$` delimiters. Internal whitespace,
LF, and unambiguous internal or escaped dollar syntax remain exact. The
schema-3 acceptance persists exact bounded UTF-8 bytes and SHA-256 values for
both `reviewer-latex.txt` and canonically derived `obsidian-markdown.md`.
`INLINE` candidates derive `$<latex>$`; `DISPLAY` candidates derive
`$$\n<latex>\n$$`. The mode must match the deterministic candidate kind, and
callers cannot supply Markdown independently, so the representations cannot
silently diverge. Render confirmation identifies the renderer and version and
binds both current representation hashes. Editing either representation after
render makes acceptance fail. Renderer-produced MathML or HTML is only preview
evidence and is never substituted for either canonical source representation.
Rejection and other non-acceptance dispositions carry neither accepted source
artifact.

Disposition and note are preserved exactly. `recorded_at_utc` is a timezone-aware UTC receipt time
supplied only by the trusted API adapter; browsers and other untrusted request
callers cannot choose it. The application seam requires that trusted caller but
does not claim to authenticate it. Receipt time is stored in the immutable
record but excluded from stable decision/revision identity. A semantically
identical retry or collision with a later receipt time returns `unchanged` with
the originally stored time. Consumers order decisions solely by contiguous
revision number, never by receipt time.

Before mutation, both operations require the exact document-package contract
and schema, recompute its content-derived package identity, verify every bounded
completion-inventory file by size and SHA-256, and require the source PDF,
source manifest, equation index, candidate source manifest, deterministic
candidate manifest, and region image to be inventory members. The index must
name the exact candidate paths and hashes; independently supplied or unlisted
candidate files are rejected. Validation uses the provided local
`AuthorizedRoot`. The public dataclasses, publication/append
functions, and `load_latest_human_equation_revision` projection form the
API-consumable seam. The latest projection revalidates source evidence and all
assisted proposals referenced throughout human history before returning a human
record. Root
selection, API routing/authentication, and request-to-contract adaptation remain
outside it. This slice does not access a
corpus, run PDF extraction, invoke a model or network, or authorize training-data
publication.

## Deterministic equation review queue

`project_equation_review_queue` is the applications-owned read-only projection
for one explicitly supplied completed document-package `AuthorizedRoot`. It
never searches for document roots. It verifies the completion identity and every
inventoried artifact, requires exact equation-index membership, rejects duplicate
or mismatched candidate records, and validates every observed review extension
through the shared review-tree validator. Missing inventoried bytes raise a
typed incomplete error; malformed package, candidate, or review evidence raises
a typed malformed error instead of silently dropping an item.

The projection admits at most 256 indexed candidates and returns only candidates
whose deterministic state is `display` plus `proposed`. Items are ordered by
zero-based physical page, then top/left/bottom/right geometry, then candidate ID.
Each frozen path-free DTO carries document/candidate/page/box identity, `DISPLAY`
mode, native deterministic text and processor evidence, source/candidate/region
hashes, an optional complete immutable assisted attempt, and the latest validated
schema-2 or schema-3 human revision. Schema-2 acceptance therefore remains
visible without invented accepted text; schema-3 acceptance includes exact
reviewer LaTeX and derived Obsidian Markdown contents and hashes plus render
provenance. Rejection and revision-required states expose no accepted
representation.

The queue identity is SHA-256-derived from the completed package identity and
canonical projected content. It has no observation or runtime timestamp, so an
unchanged package and review tree replay byte-for-byte to the same ordering and
identity. The operation performs no write or model invocation and returns no
region-image bytes; it is the narrow API-consumable read seam, not an API route.

## Multimodal resolution stop boundary

Native extraction evidence deterministically selects only pages that meet the
recorded unresolved-page policy, such as image-only pages or pages below the
recorded native-text threshold. Exact full-page PNG regions are rendered by the
public ingestion renderer. Only those exact regions may be submitted, during an
explicitly applied run, to the ingestion-owned local Ollama multimodal adapter.
The plan and output evidence bind the selection policy, renderer configuration,
prompt version, expected model name and digest, and model options. Runtime also
requires an explicit local Ollama endpoint.

Unavailable or mismatched Ollama configuration leaves typed pending or failed
resolution evidence. There is no Tesseract, hosted API, alternate model, or
provider fallback. Model proposals retain the source and image hashes, exact
model identity, prompt/configuration, output, and their nondeterministic,
automated, unreviewed, non-source-fact status. PDF-rendered content is untrusted:
proposal text and warnings are inert evidence, never commands, paths, identities,
or policy. The application never enables tools or tool calls and never uses model
text for filesystem or control flow. Pages not selected by policy make no model
call. Tests use a bounded fake transport and never contact a daemon.

## Acceptance boundary

Discovery, extraction, and multimodal proposals are evidence, not accepted
references. This package does not import reference canonicalization or
acceptance APIs and does not mint citekeys. Human/reference acceptance remains a
separate references-owned workflow.

## Dependency status

The base applications wheel has no mandatory simulation or scientific
dependency. The `pdf-corpus` capability extra contains only the factual current
local candidates `projectkoios-references==0.0.0` and
`projectkoios-ingestion[pdf]==0.0.0`; it does not select
`projectkoios-simulations` or Physkit. Plane-wave DFT applications use the
separate `simulations` extra and fail explicitly only when those capabilities
are imported without it.
Legacy discovery/document-transcript development provenance remains pinned in
`plan.py` to references commit/tree
`b7581cb5f8a619883ecd73ed1d9354b85e5f57fd` /
`41c0165e2d4cb73ca41e2bb2acace1b77b7544d9` and ingestion commit/tree
`be60640bec4fe15cc88b24161545eb1027ffbd2e` /
`d386a1744f79463fd7cd0b3087ee5fc361e0f7d5`. These are local candidate
identities, not publication or version-compatibility promises.
