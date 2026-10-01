# Citation-document registry schematic

```text
registry AuthorizedRoot (local, non-symlink, 0700)
  `-- <request_id>.json (0600, <= 64 KiB)
        registry contract envelope
          `-- ingestion Result
                `-- full neutral References link lineage

sorted immutable records (<= 10,000)
              |
              v
CitationDocumentRegistryProjection : DataObjectModel
  results + successful_document_ids + projection_id
```
