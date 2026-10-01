# CitationDocumentRegistryProjection

Immutable `DataObjectModel` containing all bounded terminal results in canonical
request order and the derived successful document IDs. The registry contract ID
is closed and unversioned. `validate_identity()` reconstructs the projection and
rejects mutation, subtype substitution, duplicates, or inconsistent success
membership.
