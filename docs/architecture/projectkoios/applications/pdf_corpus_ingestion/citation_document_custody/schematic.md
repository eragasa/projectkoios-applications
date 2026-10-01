# Citation-document custody schematic

```text
bounded binary source + declared application/pdf
              |
       chunks <= configured bound
       SHA-256 + size + %PDF-
              |
       private temporary file (0600)
              |
       atomic content-addressed link
              v
AuthorizedRoot (local, non-symlink, 0700)
  `-- <source_document_id> (0600)
              |
              v
CitationDocumentReceipt (path-free)
```
