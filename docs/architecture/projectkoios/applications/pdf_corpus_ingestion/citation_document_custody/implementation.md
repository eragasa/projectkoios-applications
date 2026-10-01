# Citation-document custody implementation

A custody root must be an exact References `AuthorizedRoot`, local, non-symlink,
and mode `0700`; its identity and filesystem state are revalidated for each
operation. Intake requires the declared MIME type to be exactly
`application/pdf`, reads bounded chunks into a mode-`0600` temporary file,
incrementally checks size and SHA-256, and requires `%PDF-` at byte zero.

After validation, the temporary file is fsynced and atomically linked to the
content-addressed descriptor ID. Exact existing content is idempotent; malformed
or conflicting state fails closed. No caller path or filename enters any model.
`read()` validates the exact receipt and retained mode/size/hash/header before
returning the bytes once to the synchronous service.
