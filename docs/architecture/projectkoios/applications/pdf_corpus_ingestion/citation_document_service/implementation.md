# Citation-document service implementation

The final service is a
`DataObjectActionizer[CitationDocumentIngestionRequest,
CitationDocumentIngestionResult]`. Its keyword-only `action(*, request)` is the
single execution path; `ingest()` is only a compatibility alias that delegates
to it. `request()` performs the neutral References linkage before effect
execution.

Before every action, the service requires exact runtime types and replay-valid
identities, revalidates custody/package/registry roots, and proves the three
canonical paths are pairwise disjoint and non-nested. It first returns an exact
terminal replay if registered. Otherwise it reads retained bytes once, invokes
the public Ingestion extractor, builds and atomically publishes the deterministic
package, projects the transcript, and requires exact request/document/manifest/
extraction identity equality before recording success.

Extraction failure and pre-publication package failure are terminal `FAILED`.
An existing package without an exact registry result, or transcript verification
failure after publication, is terminal `INDETERMINATE`. Registry persistence
failure propagates as an exception because no durable replay result exists. The
service performs no repair, promotion, Search, Workflow, retry, queue, or
background work.
