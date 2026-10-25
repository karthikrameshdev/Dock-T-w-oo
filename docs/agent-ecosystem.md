# Character agent ecosystem implementation

The 30 catalog identities are equal logical agents. There is exactly one
presentation window in the application, even when docks appear on multiple
screens. Choosing or waking an identity replaces the model in that same view.
Delegation allocates a task lease, model context and temporary workspace only.
Background agents have no renderer, microphone, animation policy or audio output.

Every identity can delegate and aggregate results. An authenticated gRPC Assign
must start the caller's own root task or reference its own running parent task.
Self/ancestor delegation is rejected; busy peers return immediately rather than
occupying waiting pool threads. Leases are reserved before entering the bounded
29-worker pool. Completed peers can be reused, and cancellation propagates to
all descendants while keeping their leases until termination is acknowledged.
Report/Publish and Cancel require task ownership; Brain has no special credential.

The foreground agent owns the shared audio lane. Character switching preserves
background work and captures identity/profile in accepted turns. Inactive root
results remain in history and the job ledger and show a completion toast instead
of speaking through the wrong character. Live status bypasses model calls. A
nonactivating top toast coalesces at most three recent events and disappears three
seconds after the latest event; it never allocates a character view or queues an
unbounded backlog. The gRPC trail retains detailed events for seven days.

Model bindings support HTTPS APIs, explicit network/Ollama endpoints and installed
CLI transports. A missing character binding uses the active default profile.
Each accepted request retains its model/credential snapshot. CLI work runs in an
isolated temporary project, with outputs preserved before cleanup. CPU-heavy
speech, vision and semantic inference are local; core reasoning uses the selected
agent model. One shared semantic policy chooses only the foreground animation.

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
The character library verifier samples all catalog assets;
the Three.js runtime sampled all 4,080 clips (24,480 poses). Real hardware on
Windows/Linux still needs device-level testing in addition to the CI OS matrix.

The gRPC/HTTP research verifier uses Orbit as the root, Brain and Fox as peers,
Owl nested under Fox, and Brain reused for a later task. It verifies 18 model
attempts, 4,880 synthetic tokens, four documents and cleanup of five task projects
while exactly one Orbit character remains visible. These fixture documents prove execution and attribution,
not factual research quality. Native CLI authentication/provider quality is separate
from the disposable Python CLI process tests. A CLI's internal API calls/caches
are visible only to the extent exposed in that CLI's structured output.

Status requests use the live gRPC registry and each worker's latest owned progress
report. They bypass work leases and paid model calls. Independent root tasks and
delegated peers run in parallel; only one task owns a character. Replies
for the selected identity wait for the shared speech lane; microphone capture delays speech. Per-character
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
view. Rendering/readback frequency follows the measured resource budget. A stalled/crashed renderer clears its hit area and
gets a bounded restart, without restarting the application. Lost mouse capture is
cleared, and Cocoa click-through flags are periodically verified. Native tracking
areas are installed once per view, including repeatedly opened drawers.

Run `node scripts/verify_animation_lifecycle.mjs` for the real Three.js retention
regression. With the normal application stopped, run
`python scripts/verify_resident_stability.py --seconds 600 --interval 10` for the
native single-view stress check. It uses isolated data, switches through 30 models
in one production renderer, and uses real OS
mouse events on macOS (Qt events elsewhere), repeated dock/listening toggles,
deliberate overlap behind the close button, hide/resume and renderer termination
(termination is exercised on POSIX hosts).
It opens no microphone and makes no provider calls; it does not establish speech
recognition quality. Results use `dock-resident-stability.json` in the OS temporary
directory; use `--output` to select another path.

## Resource budget and worker presentation

The supported Qt binding is PySide6 6.11.2–6.11.x. Linux/Python 3.11 exposed a
native reference-count regression in 6.12.0: every `Signal.emit` dropped one
reference to Python's `True` singleton, causing an eventual process abort.
A standalone 10,000-emission subprocess regression checks both reference counts
and clean process exit. Keep `pyproject.toml` and `requirements.txt` aligned when
updating Qt, and run that regression on Python 3.11 as well as newer Python.

`ResourceKeeper` samples the Python process and all descendants using process CPU
time deltas on macOS, Windows and Linux. The target is 20% of one core, matching
Activity Monitor's process units, not 20% divided by the machine's core count.
The two-second GUI timer only applies bounded decisions; process sampling,
completed-project cleanup and hourly trace pruning run in one background worker.
No unbounded cleanup jobs accumulate when that worker is busy. Completed projects
temporarily locked by a CLI or scanner retry after 30 seconds without holding the
agent's work lease or deleting an active project's contents.

Five quality levels reduce rendering/readback frequency. An idle assistant may
freeze behind a snapshot of its own current 3D render; interacting resumes the
same rig. Listening, speaking, dragging, cursor following and short explicitly
requested animations take priority. Long-hidden pages are discarded after 45
seconds. Speech, vision and semantic ONNX sessions use one intra-op inference
thread. Streaming keyword detection runs on every microphone frame. Full Whisper
fallback checks once per ambient utterance, including short utterances, rather
than repeatedly transcribing overlapping background speech. When the keyword
model is unavailable, rolling ASR fallback remains enabled. Capture has a hard
two-minute duration limit and reports timeout instead of executing a partial command.
Startup and active work can exceed the cooperative CPU target. No cross-platform
hard quota is claimed; RSS includes shared renderer pages.

Saved `brain_instances` are cleared during display configuration. Character choice
and its home display are saved separately. Background task lifetime has no effect
on renderer lifetime. Edge/navigation recovery remains bounded and uses silhouette
checks; there are no crowd collisions or multi-character controls in the product.

## Persistent local reminders

`create_reminder`, `list_reminders`, `delete_reminder` and `set_reminder_enabled`
are strict agent tools, also exposed through the native Scheduler drawer. Natural
language/date interpretation uses the configured model; dispatch and all scheduled
alerts run locally without a model call. The tool uses the addressed character's
identity, and `system_status` supplies local time and IANA time zone for relative
dates. Ambiguous times should be clarified before creating a reminder.

The SQLite store persists civil date/time, IANA zone, recurrence and next due time.
It supports once/daily/weekdays/weekly/monthly; month-end days clamp to the end of
short months. DST gaps move to the next valid minute, and repeated times use their
first occurrence. A durable outbox deduplicates five-minute, one-minute and due
alerts, including restart recovery. Sleep or a clock jump produces the latest
applicable alert, not an entire backlog. Notifications use a nonactivating local
card; audio waits for the shared microphone/speaker lane and retains only the
latest unsaid alert per reminder, bounded to 100. Pausing/deleting suppresses queued
speech. Completed one-time reminders retain their final alert. There is no separate
OS scheduling service: exact delivery requires Dock running and the machine awake.

Run the native resource test with the normal app stopped:
`python scripts/verify_resident_stability.py --seconds 180 --interval 15 --resource-budget --characters 30`.
It alternates Tasks/Scheduler clicks, listening toggles, hidden page discard/reload
and isolated renderer crash recovery. Test code uses disposable data and no real mic
or cloud credits. `tests/test_scheduler.py` advances a deterministic clock through
all three alert stages, recurrence, DST, restart and pause/delete cases.

## Single-view verification (2026-10-25, macOS)

The final native run switched all 30 identities through one renderer, then ran
140 seconds of Tasks/Scheduler open-close and click-to-listen/finish interactions.
All five OS-click cycles, 45-second hidden-page discard/reload and isolated renderer
crash recovery passed; maximum measured event-loop delay was 94.6 ms. Automated
fixtures open no microphone or real cloud account.

With the updated production app and microphone wake listener running, a warm
30.6-second process-tree sample averaged 18.22% CPU and ended at 1.20 GiB summed
RSS. The first post-launch sample averaged 23.07%, peaking at 1.58 GiB RSS. The
previous crowded baseline was 282.4% CPU and 2.32 GiB RSS. These are observed local
samples, not a cross-device guarantee or hard ceiling; speech/CLI work can exceed
the target. Shared-memory pages may be counted in more than one process's RSS.
