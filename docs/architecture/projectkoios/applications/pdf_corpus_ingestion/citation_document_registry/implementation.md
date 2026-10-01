# Citation-document registry implementation

The registry root must remain an exact local non-symlink mode-`0700`
`AuthorizedRoot`. Each mode-`0600` JSON file is named by the canonical request
ID and is published with create-exclusive semantics. Its closed outer envelope
uses `projectkoios.applications.citation-document-registry`; its nested terminal
Result independently uses the ingestion contract. Alternate caller-selected
contract IDs, unknown fields, oversized records, duplicates, and malformed
replay evidence are rejected.

On read, the complete neutral References link is reconstructed and replayed,
then the Applications Result identity is reconstructed. Projection sorts by
request ID, enforces a 10,000-record default bound, derives successful document
IDs, and validates its own deterministic identity. A fresh process can
therefore correlate each catalog entry without the original session request.
Registry write failure is raised: it is never converted into an unpersisted
terminal result.
