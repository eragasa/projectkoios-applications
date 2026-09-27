# PW-DFT SCF application examples

This directory mirrors the calculator-neutral `applications/pw_dft_scf`
boundary. Application-owned provider campaign declarations are grouped under
`providers/`; native calculator input, output, and retained evidence remain in
`projectkoios-simulations`.

- `comparison/` demonstrates qualified single-SCF comparison;
- `convergence/` demonstrates convergence planning and assessment;
- `providers/` declares application selection of external integrations;
- `runner/` binds declarations to maintained application behavior;
- `support/` owns the shared example structure repository;
- `workflow/` demonstrates the single-SCF CPN workflow state machine.
