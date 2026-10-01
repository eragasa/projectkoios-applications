# PrivatePdfCustody

Private local content-addressed custody. `create()` creates a mode-`0700` root;
`receive()` jointly validates declared PDF MIME, `%PDF-`, bounded size, and
incremental hash before atomic retention; `read()` revalidates an exact receipt
and returns retained bytes for one synchronous extraction attempt.
