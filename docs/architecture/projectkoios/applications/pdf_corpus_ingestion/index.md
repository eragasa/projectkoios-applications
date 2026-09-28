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
an explicit cursor. Earlier and later contents remain recorded as deferred.
Skipped discovery observations make coverage incomplete and are never treated as
absence. On non-Darwin platforms, a declared `cloud-backed` root is passed to
the references contract without a production probe: references emits typed
`unsupported-platform` root/skip evidence before touching the path or bytes.

`plan` is non-mutating unless `--apply` exclusively creates its plan artifact.
`run` is non-mutating unless `--apply`. Before the first mutation it rebinds and
re-probes every selected source, checks exact size, SHA-256 and PDF header, and
inspects all staging and output targets. Cloud placeholders, symlinks,
non-regular files, drift, ambiguous outputs, and unsupported cloud platforms
fail closed. Only hash-locked bytes copied with the references safe-copy API to
an explicit private local staging root reach ingestion. Raw extraction is
deterministic and uses no network, external process, OCR, or model.

Each unique content has one atomically published output directory and canonical
manifest. Replay verifies the strict application manifest, bounded canonical
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

The capability extra uses the factual current local candidate versions
`projectkoios-references==0.0.0` and `projectkoios-ingestion[pdf]==0.0.0`.
Development provenance is pinned to references commit/tree
`cb5a1fbcaf6bd898aaff7c7505b496b75d8123d6` /
`5cca1e7d072a35ea496686855e1badf1e5474103` and ingestion commit/tree
`3a697104de112eed62a9ee28c2f94d91d347c9eb` /
`61f160d466ac02aa8f6f6f663bb948da0ae5d7ce`. These are local candidate
identities, not publication or version-compatibility promises.
