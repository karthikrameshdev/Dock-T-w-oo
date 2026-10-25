# Character agent ecosystem implementation

The 30 catalog identities are the complete logical agent roster. Brain (`default`)
is the sole orchestrator. A rendered instance on another display is a view of the
same agent, not another worker. One character owns one job at a time. Human voice
capture and speech output remain single-owner; background research may run in
parallel and desktop input is serialized.

## Delivery plan

1. Complete named activation, own-rig animation, collision yielding and per-screen
   uniqueness; retain all source Blender projects and packaged exports.
2. Add authenticated loopback gRPC task leases, lifecycle/events, cancellation and
   durable task lineage. Only Brain can delegate; workers report results and errors.
3. Add per-character agent-model bindings: HTTPS APIs, explicit network/Ollama
   endpoints and cancellable headless CLI transports in isolated work directories.
4. Add a shared small ONNX semantic transformer for extractive compaction,
   similarity review and stochastic animation selection. Keep reasoning in the
   selected external model/CLI. Add scoped adaptive memory and auditable feedback.
5. Add stable staged prompt templates and provider cache adapters; separate local
   template hits from provider-reported cached input tokens. Never cache side effects.
6. Attribute every model call to character, profile, task and parent task. Add
   console configuration, live task trail, character dashboard and voice controls.
7. Test transport contracts through local provider simulations, real loopback gRPC,
   real disposable CLI fixtures, cached ONNX inference, native rendering and the
   OS test matrix. No paid provider calls during automated verification.

## Research decisions

The [adaptive memory paper](https://karthikramesh.dev/research/adaptive-personalized-llm-agents-memory-contextual-bandits)
separates working memory, a scoped semantic preference ledger, salient episodes,
and procedural workflows. Its discounted LinUCB updates require attributed user
feedback; silence and repeated topic interest are not rewards or preferences.
Current instructions override learned policies. The implementation enforces those boundaries
rather than treating embedding retrieval as reinforcement learning. This adaptation
is an engineering implementation, not a reproduction of the paper's benchmark.

[Hermes](https://github.com/nousresearch/hermes-agent) was inspected at commit
`3440aa5212284308e9ef7ee56c501c967ad5f706` in a temporary checkout. Relevant patterns
are isolated child context/ownership, per-child routes, task result aggregation,
cancellation propagation, bounded live registries, protected compression boundaries,
and stable cache lineage. The implementation uses these concepts in this application's
Qt/ONNX architecture, not executing or vendoring the reference agent.

[OpenAI caching](https://developers.openai.com/api/docs/guides/prompt-caching),
[Claude caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching),
and [Gemini caching](https://ai.google.dev/gemini-api/docs/caching/) differ. The local
cache works for every transport. Native prefix caching is capability-dependent;
provider cache hits are reported only when confirmed in usage. Dynamic date,
retrieval, job and memory context belong after the stable prompt prefix. Compaction
must not rewrite the stable system/tool prefix. Cache keys are scoped by profile,
model, character, prompt version and credential identity, without storing secrets.

CLI work is launched with argv and stdin, never generated shell command text. No
permission-bypass flags are added. Temporary projects are working directories, not
a promise of OS confinement; native CLI permission/sandbox policy still applies.


## Verification and runtime boundaries

The named audio verifier passed all 30 names through generated local speech,
production keyword spotting plus Whisper ONNX, full-statement endpointing and
named signals. This is synthetic audio, not a physical microphone/noisy-room test.
The native crowd verifier loaded all 30 production renderers and body masks;
the Three.js runtime sampled all 4,080 clips (24,480 poses). Real hardware on
Windows/Linux still needs device-level testing in addition to the CI OS matrix.

The gRPC/HTTP research verifier used Brain and three concurrent workers, verified
15 model attempts with 3,880 synthetic reported tokens, and saved three section
files plus one final report. These fixture documents prove execution and attribution,
not factual research quality. Native CLI authentication/provider quality is separate
from the disposable Python CLI process tests. A CLI's internal API calls/caches
are visible only to the extent exposed in that CLI's structured output.

Status requests use the live gRPC registry and each worker's latest owned progress
report. They bypass work leases and paid model calls. Independent root tasks and
Brain's delegated workers run in parallel; only one task owns a character. Replies
wait for the shared speech lane; microphone capture delays speech. Per-character
histories are bounded to the latest twelve entries, with scoped local checkpoints.
Large completed tool payloads are compacted without breaking tool-call/result ids.

An unassigned character inherits the active default profile at acceptance. CLI
workspaces/processes are distinct per task; generated outputs are copied to durable
storage before cleanup. Stop propagates cancellation to child work and process
cleanup. Prompt reuse caches immutable templates only, across API/network/CLI
transports; provider-reported native cache usage remains separate.

## Resident rendering and input priority

Character collision regions retain the full rendered silhouette. Their native hit
regions exclude visible Dock2 controls and drawers on every platform. This matters
because a character's invisible input window can be reordered above a drawer while
its separate visual window remains behind it. Control show/hide/move/resize events
refresh these masks; closing a panel restores the character's exposed hit area.

Animation actions are created lazily and retired after the short transition. A
mixer retains at most the current and outgoing actions, rather than every clip
played during a long roaming session. Hidden character pages freeze, their update
timers stop, and only one native-to-renderer state update may be outstanding per
view. Crowds use a lower rendering/readback budget; nearby or active characters
retain the interactive budget. A stalled/crashed renderer clears its hit area and
gets a bounded restart, without restarting the application. Lost mouse capture is
cleared, and Cocoa click-through flags are periodically verified. Native tracking
areas are installed once per view, including repeatedly opened drawers.

Run `node scripts/verify_animation_lifecycle.mjs` for the real Three.js retention
regression. With the normal application stopped, run
`python scripts/verify_resident_stability.py --seconds 600 --interval 10` for the
native crowd stress check. It uses isolated data, 30 production renderers, real OS
mouse events on macOS (Qt events elsewhere), repeated dock/listening toggles,
deliberate overlap behind the close button, hide/resume and renderer termination
(termination is exercised on POSIX hosts).
It opens no microphone and makes no provider calls; it does not establish speech
recognition quality. Results use `dock-resident-stability.json` in the OS temporary
directory; use `--output` to select another path.
