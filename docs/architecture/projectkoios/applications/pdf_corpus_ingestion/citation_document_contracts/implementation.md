# Citation-document contracts implementation

Receipt and intent are immutable `DataObjectModel` values. The effect request is
a `DataObjectActionRequest`; the terminal result is a
`DataObjectActionResult`. Every derived identity is canonical SHA-256 over an
unversioned contract payload. `validate_identity()` reconstructs the exact
runtime class and compares the complete value, so mutation through
`object.__setattr__`, subclass substitution, or stale nested owner evidence is
rejected.

The intent consumes an exact replay-valid References projection Result and uses
the References link request constructor as the semantic validator for selected
target item, identity item, and uploaded descriptor. References citation-target
inventory values come from canonical `projectkoios.references.citations`, and
bibliography bindings come from canonical
`projectkoios.references.bibliography`; document, projection, and link contracts
remain in `projectkoios.references.citation_document`. The downstream request
consumes the exact References link Result. The terminal Result retains the full
replay-valid neutral link, including target snapshot/item, literal key,
identity lineage, descriptor, basis, observations, and limitations. Registry
reload therefore needs no browser/session state.

The result identity belongs to
`projectkoios.applications.citation-document-ingestion`. Registry ownership is a
separate envelope contract. Only `SUCCEEDED` permits transcript readiness
fields; both other statuses require one bounded failure code and carry no
readiness claim.
