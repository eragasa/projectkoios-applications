# CitationDocumentCustodyLimitError

Specialized custody exception raised when the streaming upload or retained read
would exceed its configured byte bound. It is raised before unbounded content
is accepted into memory or published to custody.
