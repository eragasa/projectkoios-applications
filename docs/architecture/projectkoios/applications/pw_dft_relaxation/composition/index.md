# Relaxation composition

- `PwDftRelaxationCampaign` binds application identity, integration identity,
  and a neutral `PwDftRelaxationRequest`.
- `PwDftRelaxationComposer` selects a registered public projection integration.
- `PwDftRelaxationCompositionResult` returns projected native input text and a
  non-authorizing external handoff.
- `PwDftRelaxationExecutionHandoff` cannot represent execution approval.

Provider integrations remain in `projectkoios-simulations`; this component does
not wrap a provider-native runner or expose direct execution.
