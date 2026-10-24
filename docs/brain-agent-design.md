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
cloud calls. No cloud key is currently configured, so live provider inference is
reported as unverified until a user configures it in the console.

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
