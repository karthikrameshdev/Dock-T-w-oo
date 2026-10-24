# Brain cloud agent and local media architecture

One configured cloud model receives user text, the system instructions and text
results from local tools. There is no local conversation/reasoning model, daemon,
provider fallback or per-modality routing. Existing local-model profiles migrate
to an unconfigured cloud setup. Missing credentials say **Model is not configured**.

Flow: microphone → Zipformer wake → Silero boundaries → Whisper small.en ONNX →
cloud tool loop → validated local tools → tool results → cloud final answer →
Kokoro ONNX speech. The configured model is reused on every iteration. Audio,
pixels and video never enter the provider payload. Local image captions/OCR may
be returned as text. File contents go to the selected provider when a user asks
the agent to read or summarize them.

The agent exposes structured filesystem, document, browser/URL, desktop
accessibility, keyboard, pointer, scrolling, reading and character actions.
Desktop mutations use a fresh observation id and target process; focus changes,
stale controls and missing OS permissions produce tool errors. Tool errors return
to the model so it can recover. Stop invalidates the request and prevents later
actions/replies. Iterations are bounded by a configurable step budget, with
visible progress, and never silently claim a partial task finished. No arbitrary
model-generated Python or shell program is executed.

A response includes an optional emotion/gesture. The local director selects from
the saved artist animation library, prioritizes speech/reading and movement, and
blends gestures with cooldowns and reduced-motion support. Whistling has actual
local audio; handshake uses a local skeletal track alongside the 47 authored
clips. The shared animation binding prevents it from interfering with waving. The Blender character and
its materials are preserved.

Reading bypasses cloud reasoning for immediate explicit reading commands. It
reads existing selected text without changing selection, or reads the frontmost
app from the first page. Speech is grouped into phrases and prefetched while the
previous phrase plays. Reading starts without waiting for mascot travel. Smooth
pull/scroll effects run between pages; target/document changes stop reading.

Verification separates unit checks, the real agent against local Postman provider
simulations, real local model synthesis/transcription, native UI actions, and live
cloud calls. Provider-contract checks use local Postman fixtures so verification
does not spend credits on the configured cloud account.

Tasks persist in SQLite under the configured storage root, shared by the native
Tasks drawer, web console and agent. ISO dates/ranges and pagination allow exact
historical queries. Same-day identical entries are deduplicated. Notes retain the
existing JSON format. Settings/control resolves to Dock settings; platform names
resolve to the matching OS settings and report a mismatch otherwise.

Keep Awake owns only its own caffeinate process (or Windows execution-state
thread). Disable/exit releases it. It never changes security policies or manual
locking. Local control endpoints reject foreign origins and require explicit
application headers for mutations. Provider credentials use an encrypted file
with an owner-only key; ordinary settings cannot replace the model configuration.

Local media models are pinned: Whisper small.en INT8, Zipformer keyword spotting,
Silero VAD, GTCRN enhancement (verified SHA-256), Kokoro 82M INT8, and optional
ViT-GPT2 INT8 image captions. OCR is Apple Vision on macOS. Captioning can miss or
misdescribe objects; neither captions nor accessibility guarantee access to every
app. Native CUA and page reading currently require macOS. Windows supports Keep
Awake and opening its Settings, but its full accessibility driver is not implemented.


Credit protection stops after three cloud turns without measurable progress,
including repeated errors or unchanged observations with new IDs. The default
request budget is eight cloud calls, 24,000 tokens with a conservative preflight
estimate, and 1,024 output tokens per call. Controls permit 2–3 stalled turns,
1–12 total calls, 2,000–64,000 budget tokens and 128–2,048 output tokens. Provider
errors have no automatic HTTP retry. A local stop explanation never adds a model
call. Whole requests also have a 120-second scheduling budget; in-flight requests
are bounded by a 25-second transport timeout. Already-submitted calls may still
be billed after cancellation; their returned usage is recorded when available.

The Activity Tracker stores actual transcribed requests, outgoing conversation
and tool payloads, returned responses, tool outcomes, retries and stop reasons.
The fixed system instruction text is represented by length and SHA-256, and
provider keys/auth fields are redacted. Full input token accounting still uses
the provider's count of the real request, including instructions, history and
tool schemas. Token values are never inferred from visible text for the ledger.
Unknown usage is explicit. When a provider total exceeds its input/output
breakdown, the difference is shown as unclassified rather than guessed. Cached and reasoning details are already part of
input/output totals, so are not added twice. Anthropic input sums uncached,
cache creation and cache read usage. Only explicit USD costs or OpenRouter's
reported USD costs are displayed; the app does not invent pricing or balances.

Compressed detailed traces expire after seven days, with a 128 MiB payload quota
that can prune the oldest completed traces sooner. Durable daily aggregates keep
monthly/custom date charts available without retaining old conversation text.
The native Dashboard drawer and console share local accessible SVG charts. There
is no remote chart service and no local speech/vision token accounting. Historical
usage before tracing was introduced cannot be reconstructed.

A newer request cancels queued work from the previous one. The agent serializes
cloud calls so repeated requests cannot stack overlapping paid calls while an
earlier network request is still finishing. Local reading also cancels prior
agent work. Cancellation cannot undo a request already submitted to a provider.

The status API snapshots Qt widget/browser state on the GUI thread. Cyclic
QObject collection is scheduled there too. Desktop observation resolves the
foreground process through the GUI dispatcher, excludes Brain's own embedded
browser before any accessibility query, and applies a per-application messaging
timeout. This keeps console polling and worker-driven desktop observation from
entering WebEngine on an unrelated thread.


The Tasks drawer places controls and results inside the base content container,
so the former empty expanding panel above the list is gone. Today is the default;
search and status filtering combine with yesterday, seven days, month, exact date,
custom ranges and all dates. The store supplies whole-result counts independently
of the 100-row page size. Clicking an item opens its full editable record. Local
summaries read all matching pages up to 1,000 entries and disclose truncation.
A successful agent list_tasks query accompanies its final reply; delivery opens
Tasks with that query and the cloud answer. This happens only after the agent
finishes, so the drawer cannot steal focus during desktop automation.

ConsoleControls owns every single-select control, including asynchronously
inserted animation options and the shared Dashboard. Searchable option lists are
portaled outside cards to avoid clipping, support keyboard selection/Escape,
and mirror the underlying select's value, labels and disabled state. Form fields
and dropdown triggers use the same 42-pixel height; the top settings search is
46 pixels tall. The native web Dashboard loads this same component and styles.
