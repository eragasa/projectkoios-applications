# Project Koios applications

This repository owns workflow- and CPN-enabled application composition under
`projectkoios.applications`. An application capability composes reusable domain
contracts, provider integrations, workflow/runtime contracts, and application
policy; it does not absorb those reusable components.

## Ownership

- Own application capability packages, scientific/application policy, recipes,
  workflow definitions and facades, application CPN composition, runners,
  replay, campaign declarations, and application-level evidence and outcomes.
- The first authorized extraction is
  `projectkoios.applications.pw_dft_scf` from the exact Project Koios
  Frankenstein incubation overlay.
- Preserve capability boundaries inside the shared application layer. A
  capability such as `pw_dft_scf` is not a separate application or repository.
- `projectkoios-simulations` owns calculator-neutral simulation contracts and
  calculator-provider integration implementations.
- `projectkoios-workflow` owns generic workflow execution, state, replay, and
  engine/CPN adapter contracts.
- `projectkoios-optimization` owns reusable optimization contracts and
  algorithms.
- Provider and reusable component repositories must not import this application
  layer. Application packages may depend on their public contracts.

## Extraction policy

- Frankenstein is an incubation source, not a subtree to copy indiscriminately.
- The overlay migration removes only the `frankensteins` namespace segment for
  accepted application behavior; preserve class names and dependency direction
  unless an explicit compatibility correction is documented.
- Record source repository, exact commit and tree, original path, selected and
  excluded file identities, namespace rewrite, license, notices, adaptations,
  and test/example mapping.
- Do not duplicate neutral simulation records, provider-native integrations, or
  generic workflow/CPN kernels here.
- Keep application examples bounded. Separate retained evidence, replay,
  numerical verification, scientific validation, and human acceptance.
- No test, example, replay, or ordinary command grants calculator execution
  authority. Live external execution requires explicit operator authorization.

## Development

- Mirror maintained package ownership under `docs/architecture` and tests.
- Use strict typing, deterministic fixtures, failure cases, reproducible builds,
  and isolated wheel checks.
- Keep one writer per worktree. Use exact-path staging, disable hooks/signing for
  controlled commits, and verify the staged tree before commit.
- This repository has no remote. Do not create one, fetch, push, publish, merge,
  or modify source/component repositories without explicit authorization.
