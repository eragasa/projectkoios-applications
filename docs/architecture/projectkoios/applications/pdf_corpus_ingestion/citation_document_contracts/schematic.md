# Citation-document contracts schematic

```text
CitationDocumentReceipt : DataObjectModel
    exact CitationSourceDocumentDescriptor
             |
             v
CitationDocumentIngestionIntent : DataObjectModel
    exact References projection Result
    selected projection/identity items
    local authority assertion + admission decision
    extraction configuration + limits
             |
             v
References CitationSourceDocumentLinkResult
             |
             v
CitationDocumentIngestionRequest : DataObjectActionRequest
             |
             v
CitationDocumentIngestionResult : DataObjectActionResult
    full exact neutral link lineage
    SUCCEEDED | FAILED | INDETERMINATE
```

Every arrow is identity-bound and replay-validated. No value conveys rights,
human review, Search admission, manuscript use, or publication authority.
