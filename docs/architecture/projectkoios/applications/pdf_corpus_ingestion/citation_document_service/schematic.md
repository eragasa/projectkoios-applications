# Citation-document service schematic

```text
intent --request()--> neutral References link --> action request
                                                   |
                                      exact terminal replay?
                                       yes /        \ no
                                          /          \
                                  return Result   read custody once
                                                    |
                                               Ingestion extract
                                                    |
                                      deterministic package publish
                                                    |
                                         exact transcript verify
                                                    |
                                      registry record (must succeed)
                                                    |
                                              terminal Result
```

Publication without provable transcript readiness is `INDETERMINATE`; no
automatic repair is attempted.
