# CitationDocumentReceipt

Immutable `DataObjectModel` for the technical custody outcome. It binds one
exact References `CitationSourceDocumentDescriptor` and derives `receipt_id`
from the unversioned receipt contract. `validate_identity()` reconstructs the
value and rejects mutation or subtype substitution. `observation()` emits
positive, incomplete References availability evidence; it grants no authority.
