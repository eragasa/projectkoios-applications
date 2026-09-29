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
inventory; it never reruns Ollama. It does not claim to
semantically reconstruct ingestion-owned raw, renderer, or Ollama JSON because
those owners do not yet expose read validators. This detects stale or accidental
byte drift, not an actor able to rewrite both artifacts and manifest identity.
An ingestion-owned semantic replay parser is a follow-up, not application code.
Partial or different output fails closed. Pending, deferred, and failed page
resolution is immutable terminal-incomplete evidence for that plan/output; retry
requires a newly composed plan and fresh output root. It is never reported as
full processing completion.

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
links. The application index is navigational evidence; candidates remain
`proposed` or `ambiguous`. Assisted, human, and transcript stages are explicitly
`not-started` in the initial deterministic publication.

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
Development provenance is pinned to references commit/tree
`b7581cb5f8a619883ecd73ed1d9354b85e5f57fd` /
`41c0165e2d4cb73ca41e2bb2acace1b77b7544d9` and ingestion commit/tree
`024162ca65f4552c274b29e30462888d4379f2fc` /
`f093adbc318302fe02854708339df18fd1dcb263`. These are local candidate
identities, not publication or version-compatibility promises.
