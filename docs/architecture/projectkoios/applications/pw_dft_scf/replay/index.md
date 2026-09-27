# PW-DFT SCF convergence replay

`PwDftScfConvergenceReplayer` owns deterministic application-policy replay over
`PwDftScfConvergenceReplayEvidence`. The evidence contract carries normalized
energy observations, provider identity, source-evidence reference, and the
bounded application policy. Native parser behavior and raw artifacts remain in
the provider owner.

Replay must reproduce exactly one requested extension followed by policy
acceptance. It performs no discovery, parsing of calculator-native files, or
calculator execution. A successful replay is software evidence for the declared
finite-grid policy only; it is not numerical verification or scientific
validation.
