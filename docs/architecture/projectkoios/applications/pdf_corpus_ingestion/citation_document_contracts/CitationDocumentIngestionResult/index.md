# CitationDocumentIngestionResult

Immutable terminal `DataObjectActionResult` for one exact request. It retains
the complete neutral References source-document link, terminal status, bounded
failure detail, and success-only package/transcript identities. Its identity
uses the ingestion contract. `from_record_payload()` accepts only the exact
closed persisted shape and replays all owner/application identities.
