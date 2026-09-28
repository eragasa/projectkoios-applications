# Architecture

`projectkoios.applications` composes reusable simulation, provider, and workflow
contracts into application capabilities. The initial `pw_dft_scf` capability
owns scientific recipes and policy, comparison semantics, campaign configuration,
workflow definition and facade, application CPN composition, bounded runners,
and replay behavior.

It does not own calculator-neutral records, provider integrations, generic
workflow runtime, or a generic CPN kernel. Dependencies point from applications
to those owners; reusable owners must not import this package.

See the [extraction record](extraction.md), the mirrored
[`pw_dft_scf` reference](projectkoios/applications/pw_dft_scf/index.md), and the
[`pdf_corpus_ingestion` composition boundary](projectkoios/applications/pdf_corpus_ingestion/index.md).
