# brain-cloud simulation

Local fixture derived from the repository's cloud tool-call contracts. Updated
2026-10-25; no live provider or real key is used.

## Purpose

Exercise production CloudClient, BrainAgent, profile selection and the SQLite
usage ledger over real HTTP. The single `cloud` member serves both chat and
Anthropic protocols from `postman/mocks/cloud/default.js`.

## Execution

Start with `postman simulation run postman/simulations/brain-cloud.sim.yaml
--port 24930 --no-history --output ndjson` and wait for its listening event.
Run `python scripts/verify_cloud_profiles.py`; stop the owned simulation afterward.
The same server is used by the existing cloud-agent verification script.

## Assumptions

- 2026-10-25: the synthetic member accepts only `fixture-key`; profile isolation
  with different saved keys is tested in `tests/test_cloud_profiles.py`.
- 2026-10-25: test clients explicitly permit the loopback URL; application
  configuration still requires an external HTTPS provider. This fixture verifies
  routing and accounting, rather than live inference quality or billed usage.

## Observations

<!-- begin:observations -->
2026-10-25: the only member, `cloud`, served four requests: two chat completions
and two Anthropic messages. The first request retained its original profile after
an active-profile switch. Synthetic totals were 480 and 620 tokens (1,100 overall);
deleting a configuration retained its usage history. No member was silent.
<!-- end:observations -->

- 2026-10-25: Shared multi-screen queue verification uses the production local
  HTTP endpoint and Qt dispatch against the same Postman fixture. Screens 1 and 4
  share one agent; both accepted requests preserve their original profiles after
  switching. Four provider calls report 1,100 synthetic tokens (480 + 620).
  No live-provider requests were made.

- 2026-10-26: `verify_privacy_transport.py` sends chat and Anthropic requests
  through real quantized ONNX NER redaction. The receiving fixture rejects any of
  five synthetic secrets/PII values. Both requests passed and opaque values were
  restored locally. No production data or provider requests were used.
- 2026-10-26: Parallel gRPC research passed with the optional resource cap enabled:
  5 tasks, peak 3 workers, 18 HTTP calls, 4,880 fixture tokens, 4 retained documents,
  and all temporary projects released. The native responsiveness check passed
  for generated Brain and Rio wake+command audio, Notes dispatch, Kokoro PCM,
  facial motion and working/completion toasts. Hardware audio was not opened.
