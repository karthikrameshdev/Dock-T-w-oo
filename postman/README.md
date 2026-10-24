# Local model verification

`contracts/ollama.openapi.json` is a minimal dependency contract for the two
[official Ollama API](https://docs.ollama.com/api/introduction) operations Brain
uses for discovery and conversation. The generated mock retains those response
shapes; unmodeled calls return 501. These files test client behavior, not the
quality or full compatibility of Ollama itself.

Run locally, each command in its own terminal (Postman CLI 1.70+):

```sh
postman simulation run postman/simulations/brain-local.sim.yaml --port 24920 --output ndjson > /tmp/brain-local-sim.ndjson
postman simulation run postman/simulations/brain-local-error.sim.yaml --port 24921 --output ndjson > /tmp/brain-local-error.ndjson
postman simulation run postman/simulations/brain-local-slow.sim.yaml --port 24922 --output ndjson > /tmp/brain-local-slow.ndjson
.venv/bin/python scripts/verify_local_language.py
```

Check the `request` events in the success log for GET `/api/tags` and POST
`/api/chat`. The other runs prove a JSON 503, a response exceeding the client's
200 ms test deadline, and an unreachable service become explicit unavailable
states. Stop each simulation with `pkill -INT -f 'simulation run postman/simulations/<file>'`.

Verify the real installed model separately, without recording Postman catalog
traffic, using the actual JSON contents as the body:

```sh
postman request POST http://127.0.0.1:11434/api/chat \
  --body "$(cat postman/requests/local-chat.json)" \
  -H Content-Type:application/json \
  --script-post-request @postman/checks/local-chat.js \
  --no-report-events --timeout 30000
```

The saved request contains only a generic rainbow question. Never place private
conversation history, credentials, or microphone recordings in these fixtures.
