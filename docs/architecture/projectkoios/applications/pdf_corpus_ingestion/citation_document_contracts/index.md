# Citation-document contracts

`citation_document_contracts.py` owns the path-free application values that bind
private custody, configured local processing authority, neutral References
linkage, synchronous execution, and terminal replay. It does not own target
citation semantics, bibliographic identity, source-document linkage rules, PDF
extraction, filesystem custody, or registry persistence.

Public values:

- [`CitationDocumentTerminalStatus`](CitationDocumentTerminalStatus/index.md)
- [`CitationDocumentFailureCode`](CitationDocumentFailureCode/index.md)
- [`CitationDocumentReceipt`](CitationDocumentReceipt/index.md)
- [`CitationDocumentIngestionIntent`](CitationDocumentIngestionIntent/index.md)
- [`CitationDocumentIngestionRequest`](CitationDocumentIngestionRequest/index.md)
- [`CitationDocumentIngestionResult`](CitationDocumentIngestionResult/index.md)

See [implementation](implementation.md) and [schematic](schematic.md).
