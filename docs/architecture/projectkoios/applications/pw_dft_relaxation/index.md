# PW-DFT relaxation capability

`projectkoios.applications.pw_dft_relaxation` is a capability inside the shared
application layer. It composes calculator-neutral relaxation requests with an
installed public input-projection integration.

The composition result contains deterministic projected inputs and an
`PwDftRelaxationExecutionHandoff`. That handoff states that separate explicit
external authority is required. It contains no executable path, execution flag,
or method that starts a calculator.

The application workflow definition names projection and external-authority
handoff places and transitions without copying a generic workflow or CPN kernel.
