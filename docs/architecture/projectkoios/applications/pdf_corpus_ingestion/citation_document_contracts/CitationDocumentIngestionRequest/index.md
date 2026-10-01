# CitationDocumentIngestionRequest

Immutable `DataObjectActionRequest` for one synchronous effect. It requires an
exact replay-valid intent and exact replay-valid neutral References link Result.
Construction and `validate_identity()` prove that the link request, intent,
descriptor, and pre-effect identity are identical. `document_id` is derived from
the request identity and is never caller-selected.
