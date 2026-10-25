# Cloud agent verification

`contracts/brain-cloud.openapi.json` describes the OpenAI-compatible chat and
Anthropic Messages tool-call shapes used by Brain. The cloud mock contains only
synthetic documents and tasks. It tests transport and agent behavior, not actual
cloud reasoning quality or compatibility with every provider/model.

Run each simulation in its own terminal (Postman CLI 1.70+):

```sh
postman simulation run postman/simulations/brain-cloud.sim.yaml --port 24930 --output ndjson > /tmp/brain-cloud-sim.ndjson
postman simulation run postman/simulations/brain-cloud-error.sim.yaml --port 24931 --output ndjson > /tmp/brain-cloud-error.ndjson
postman simulation run postman/simulations/brain-cloud-slow.sim.yaml --port 24932 --output ndjson > /tmp/brain-cloud-slow.ndjson
.venv/bin/python scripts/verify_cloud_agent.py
```

The script runs the production CloudClient, BrainAgent, filesystem tools and
SQLite Tasks store against real HTTP simulations. It checks multi-step folder
summaries in both protocols, invalid-tool recovery, dated work recording/recall,
HTTP 401 and 503, a response exceeding the test deadline and an unreachable service.
Check request events for `/cloud/chat/completions` and `/cloud/messages`. Stop
each owned simulation with Ctrl-C after verification.

`tests/test_web_server.py` exercises the actual local control endpoints with
isolated storage: date filters, task updates/deduplication, configuration/key
redaction, missing-model feedback, and foreign-origin rejection. Real provider
inference requires a user-configured URL, model and key in AI Voice Assistant → Agent Models.
No key is included in fixtures or logs. The application never uses a simulation
endpoint: the loopback exception exists only in explicit test clients.

Local speech/vision verification: `.venv/bin/python scripts/verify_local_media.py`.
This uses cached models and generated speech/images; it records no microphone.


## Credit protection and tracing

The fixture also exercises endless invalid actions and unchanged observations.
Each triggers two local recovery reviews before a bounded error after nine failed model turns; there is no extra final-response call. A changing file-read sequence demonstrates the separate total-call limit.
The combined open/type scenario verifies that the real local-tool dispatch sends
both arguments to one editor integration; the OS integration is isolated in that
fixture. Successful responses carry synthetic provider usage in both protocols;
the production ledger counts full input/output totals, including cached input,
and preserves monthly aggregates after seven-day trace expiry.

`brain-activity.openapi.json` specifies the local trace and usage endpoints.
All require the local request header; foreign origins are rejected. No live
configured-provider credits are used by these tests.


The Tasks query contract is `contracts/brain-tasks.openapi.json`: inclusive date
ranges, literal title/detail search, status, pagination and whole-result counts.
`tests/test_tasks_window.py` covers native today/history/search, editing, local
summary pagination and final voice-summary display. `tests/test_web_server.py`
exercises these combined filters through the real local HTTP server. Provider
simulation verification also checks that task queries survive to the final reply.
`python scripts/verify_tasks_window.py` renders disposable preview data without
opening a microphone or submitting a cloud request; the dashboard verifier checks
shared dropdown coverage and all four filter control heights.

Agent model profile management is specified in `contracts/brain-profiles.openapi.json`.
Use `scripts/verify_cloud_profiles.py` against the existing cloud simulation to
verify switching during an iterative request and per-profile token accounting.
Profiles never share saved credentials, even when their provider and model match.
Historical totals without a profile identity stay under Earlier activity; deleting
a profile preserves its daily usage. Both dashboard surfaces use the same profile
filter and overall aggregate endpoint.

Display selection and the shared execution queue are specified in
`contracts/brain-displays.openapi.json`. `tests/test_multi_brain.py` exercises a
four-display inventory, screens 1 and 4, hot-plug fallback/reconnection, one
renderer across all docks, character switching, profile snapshots, Stop and the
shared microphone. Real local HTTP tests reject invalid/unselected screen ids
and foreign origins. No live cloud calls are used for these checks.

Named ecosystem controls are specified in `contracts/agent-ecosystem.openapi.json`.
`verify_agent_ecosystem.py` runs Orbit with Brain/Fox peers, Owl nested under Fox, and Brain reused later over
real local gRPC and Postman HTTP, producing four generated documents with durable
per-character/profile accounting. `verify_named_agent.py` tests named routing via
the actual local HTTP endpoint. `test_parallel_agent_io.py` runs real CLI processes
in separate temporary projects and verifies live status, default-profile fallback,
workspace cleanup, 29 simultaneous background peers and selected-agent speech while internal work continues in parallel.
The simulation uses synthetic sources; it does not establish live research quality.

With the primary simulation on port 24930, run
`QT_QPA_PLATFORM=offscreen python scripts/verify_reminder_agent.py` for the full
named request → model tool call → durable reminder → onscreen notification →
shared speech-queue path. The clock is advanced locally and speech is intercepted;
no microphone or live provider is used. Reminder schemas live in `agent_tools.py`
because these are agent tools, not new public REST endpoints. The ecosystem verifier
also asserts that only one character view exists and all task projects are released
after nested and reused workers complete. Manual Scheduler add/search/pause/delete and durable
alert timing are covered by the native Qt/SQLite tests.
