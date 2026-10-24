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
inference requires a user-configured URL, model and key in Brain → Cloud Model.
No key is included in fixtures or logs. The application never uses a simulation
endpoint: the loopback exception exists only in explicit test clients.

Local speech/vision verification: `.venv/bin/python scripts/verify_local_media.py`.
This uses cached models and generated speech/images; it records no microphone.
