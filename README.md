<p align="center">
  <img src="assets/icons/logo.svg" width="96" height="96" alt="Dock T(w)oo Logo" />
</p>

<h1 align="center">Dock T(w)oo</h1>

<p align="center">
  <b>Modern Secondary Resident Dock Panel for macOS, Windows, and Ubuntu</b><br>
  <i>(Pronounced "Dock 2")</i>
</p>

<p align="center">
  <a href="https://github.com/karthikrameshdev/Dock-T-w-oo/actions/workflows/ci.yml"><img src="https://github.com/karthikrameshdev/Dock-T-w-oo/actions/workflows/ci.yml/badge.svg" alt="CI Status" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue?logo=python" alt="Python Versions" /></a>
  <a href="CODE_OF_CONDUCT.md"><img src="https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg" alt="Contributor Covenant" /></a>
</p>

<p align="center">
  🌐 <b>Live Project Showcase & Overview:</b> <a href="https://karthikramesh.dev/projects/dock-twoo/"><b>karthikramesh.dev/projects/dock-twoo/</b></a>
</p>

<p align="center">
  <a href="https://karthikramesh.dev/projects/dock-twoo/"><b>Website</b></a> •
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#built-in-apps">Built-in Apps</a> •
  <a href="#web-configuration-console">Web Console</a> •
  <a href="#quickstart">Quickstart</a> •
  <a href="#testing">Testing</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## 🌟 Overview

**Dock T(w)oo** is an open-source, resident secondary desktop dock panel built entirely in **Python** using **PySide6**. Designed for daily workflow productivity across macOS, Windows, and Ubuntu, Dock T(w)oo provides an always-accessible, edge-pinned capsule dock with attached companion drawers that expand right next to the dock.

Visit the [**Dock T(w)oo Project Showcase**](https://karthikramesh.dev/projects/dock-twoo/) to explore the visual design, interactive features, and live demonstrations.

From quick encrypted credential lookups in **Vault**, fast scratchpad notes in **Notes**, to resident AI voice interaction in **Brain**, Dock T(w)oo brings essential desktop workflows into a unified, distraction-free companion panel.

---

## ✨ Features

- 📍 **Always-Pinned Edge Docking**:
  - Automatically pins to the **Right Edge** (default) or **Left Edge** of your desktop display.
  - Smart multi-monitor clamping that respects macOS menu bars, Windows taskbars, and Linux panels (`availableGeometry`).
  - Seamless acrylic backdrop styling with rounded pill corners (`border-radius: 28px`) and native overlay window levels (`NSMainMenuWindowLevel + 1`).

- 🪟 **Attached Companion Windows (Full Height Matching)**:
  - Clicking any dock icon opens its dedicated application drawer **attached directly next to the dock**.
  - **Height matches the icon menu dock exactly**: spans the same vertical height and aligns to the top of the dock seamlessly.
  - Smooth toggle and instant switching between apps without window clutter.

- 📐 **3-Icon Focused Architecture**:
  - **Notes**: First icon on top for instant note-taking and markdown editing.
  - **3-Dots Divider**: Clean non-interactive separator dots.
  - **Settings**: Direct one-click launcher for the Web Console in your browser.
  - **3-Dots Divider**: Clean non-interactive separator dots.
  - **Brain**: Robot assistant mascot SVG sticking to the bottom, following the system/theme color dynamically.

- 🌐 **Interactive Web Configuration Console**:
  - Clicking the **Settings / Sliders** icon launches a local HTTP Web Console (`http://127.0.0.1:28842`) in your default browser.
  - Real-time sliders for **dock width**, **standard icon size**, **dock opacity**, **icon opacity**, **attached window dimensions**, and **gap spacing**.
  - Interactive live desktop mockup that updates immediately as you adjust sliders and color pickers.
  - Config changes are automatically persisted to `~/.dock_twoo/config.json` and applied to the running desktop dock via IPC.

- 📐 **Strict Standardized Icon Sizing**:
  - All icons follow an identical, uniform bounding box standard (default `20px`, adjustable from `16px` to `48px`).
  - Zero mismatched sizes or irregular paddings across any icon.

- 🎯 **Pointed Callout Tooltips**:
  - Every icon tooltip follows a distinct callout design with a corner pointer triangle directed straight at the hovered icon.
  - When the dock is on the right, the pointer extends toward the right; when on the left, it extends toward the left.

- 🎨 **SVG Vector Icons & Dynamic Theming**:
  - Every icon is vector SVG format for crisp rendering on high-DPI Retina and 4K displays.
  - **Brain icon is a clean vector robot mascot SVG** that dynamically tints with the theme color (light/dark/custom).
  - Dynamic color tinting based on system theme (macOS Dark/Light mode detection, Windows Personalize registry, GNOME color-scheme).
  - Full customization of dock background color, border, opacity, and icon tints.

- 🔤 **Unified Typography**:
  - Consistent modern font system (`-apple-system`, `SF Pro Display`, `Segoe UI`) shared across root app, tooltips, and console.

---

## 📱 Dock Layout

| Item | Type | Description |
|---|---|---|
| **Traffic Dots** | Header | Window control dots (Red hides/closes, Green/Yellow dock controls). |
| **Notes** | App (Top) | First icon on top — quick scratchpad with markdown editing and auto-save. |
| **•••** | Divider | Subtle 3-dots separator above Settings. |
| **Settings** | Launcher | Sliders icon — clicking opens the Web Console in your default browser. |
| **•••** | Divider | Subtle 3-dots separator above Brain. |
| **Brain** | App (Bottom) | Robot mascot SVG following theme color — resident AI voice companion with visualizer orb. |

---

## 🌐 Web Configuration Console

Dock T(w)oo runs an embedded lightweight HTTP server in Python. Click the **Sliders** icon on the dock or run `dock-twoo --console` to open the configuration interface:

- **Dock Edge**: Switch between Left Edge and Right Edge.
- **Icon Size Slider**: Scale all icons from `16px` to `44px`.
- **Dock Dimensions**: Width (`48px` - `96px`), height mode (`fill`, `auto`, `fixed`), corner radius.
- **Color Customizer**: Pick dock background, icon tint, and acrylic opacity levels.
- **Attached Window**: Adjust drawer width (`280px` - `640px`) and height (`360px` - `840px`).
- **App Toggles**: Enable or disable any app from the dock.

---

## 🚀 Quickstart

### Prerequisites

- Python 3.10+
- macOS, Windows, or Linux (Ubuntu)

### Installation

```bash
# Clone the repository
git clone https://github.com/karthikrameshdev/Dock-T-w-oo.git
cd "Dock-T-w-oo"

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

### Running Dock T(w)oo

```bash
# Launch the dock
./run.sh

# Or launch directly with python
python -m dock_twoo.main

# Open directly into the Web Console
./run.sh --console

# Force dock to left edge
./run.sh --edge left
```

---

## 🧪 Testing

Run the test suite with `pytest`:

```bash
pytest -v
```

The test suite covers:
- Configuration serialization, defaults, and live update observers.
- SVG icon loading, dynamic tinting, and standardized dimensions.
- Screen geometry clamping for left/right edge docking.
- Pointed callout tooltip positioning.
- Attached companion window stacking and switching.
- Web Console REST API endpoints (`GET /api/config`, `POST /api/config`, `GET /api/status`).

For long-running character/input checks, see the [resident rendering verification](docs/agent-ecosystem.md#resident-rendering-and-input-priority).

---

## Local Brain voice

Enable **Follow Cursor** in Brain settings → Motions or the Brain menu. Brain walks
toward the latest pointer position at a calm pace and redirects immediately when
you move it. Following pauses during voice interaction and explicit animations.
Brain lets clicks pass through while following; use settings or the menu to stop.
The head turns with the body while retaining the same live eyes and mouth.

The base installation includes the local voice runtime. A small streaming
Zipformer model listens for “Brain”, “Hey Brain”, “Hello Brain”, and “Hey Buddy”
without waiting for dictation, silence detection, or a macOS Speech permission
prompt. Whisper small.en INT8 transcribes commands locally on CPU. The wake assets
are about 6 MB; command recognition adds about 380 MB. First launch downloads these
in background workers and Brain settings reports when each stage is ready.

Brain uses **one cloud profile per request** for reasoning and iterative tool calls.
Save any number of named profiles under **Brain → Cloud Profiles**, each with its own provider,
HTTPS base URL, exact model ID and API key. OpenAI-compatible APIs (including
Gemini and OpenRouter) and Anthropic Messages are supported. Choose a model that
supports tool calling. Until configured, Brain says **“Model is not configured.”**
There is no local reasoning model, local LLM service, or hidden provider fallback.
Keys are encrypted in a separate local file and never returned by the console.

Speech stays local: Whisper small.en INT8 for transcription, Silero for speech
boundaries, GTCRN ONNX for buffered noise enhancement, and Kokoro 82M INT8 ONNX
for speech. Six American/British male and female voices and speed controls are
available. Speech is synthesized in phrases, with the next phrase prepared while
the current one plays. Models download in background loaders; the audio callback
never downloads weights. Platform speech is available while the local voice loads.
Optional WavLM speaker enrollment uses `pip install -e '.[voice]'` and stores only
a derived voice vector. These models do not reason about user requests.

A bare “Brain” starts a conversation. “Brain, open Cursor and type hello world”
is captured as one complete request. Silero VAD allows natural pauses before
ending a turn. The configured cloud model chooses local tools, sees their actual
results and iterates until it can answer. The console shows progress and provides
**Stop request**. Local tools cover files, PDF/DOCX text, Notes, Tasks, apps,
accessibility controls, typing, scrolling and character actions. No generated
shell or Python code is executed. Image explanation uses local ONNX captioning
and Apple Vision OCR; only resulting text reaches the cloud model. Audio, image
bytes and video are never sent to the provider. Requested document contents are
sent as text to the configured provider for summarization.

**Tasks** is a persistent work log grouped by date. The drawer opens on today, with title/detail search, status filters, yesterday, the last seven days, month selection, a specific day, custom ranges and all dates. Click any entry to view or edit its full details. Summary shows all matching work (up to 1,000 entries, with an explicit limit notice); a voice task summary opens the same filtered drawer and displays Brain’s answer. Say “Today I worked on the
release notes” or “What did I work on January fifth?” The cloud agent records and
retrieves dated entries, then summarizes them through local speech. Identical
entries on the same day are deduplicated. Notes use the existing Notes drawer.
“Open settings” or “open control” opens Dock settings; “open Mac settings” opens
System Settings. Windows Settings requires Windows; the desktop CUA and full
window reader currently support macOS Accessibility apps.

**Scheduler** has its own dock drawer. Add, search, pause, resume or delete
one-time, daily, weekday, weekly and monthly reminders. Say “Rio, remind me
tomorrow at 11 am about the meeting” or “Brain, every day at 10 am remind me to
review my tasks.” The agent saves the reminder locally with its character and
time zone. Notifications appear five minutes before, one minute before and at
the scheduled time. Spoken reminders use local TTS and wait for the shared audio
lane. Keep Dock running and the computer awake for timely alerts; after sleep or
restart, it delivers one catch-up alert instead of replaying stale warnings.

Right-click the Voice Assistant icon and choose **Choose assistant** to switch
between the 30 characters. Only one character window exists across all displays.
Every agent can delegate to available peers; background workers have no character
renderer, microphone or audio output. Brief top-of-screen toasts report assignment
and completion. Completed work and live progress remain in the console task trail.

Dock samples its own process tree every two seconds and cooperatively targets
20% CPU, where 100% means one CPU core. Under load it reduces frame/readback rates
and lets the idle assistant rest in its current rendered pose when necessary. Clicking or addressing a character resumes it. Hidden
character pages are discarded after 45 seconds and reload when shown. This is
not a hard OS quota: startup, local speech inference, active interactions and
external model CLIs can exceed the target. Housekeeping removes completed worker
projects, retired view state and expired activity traces; it does not kill other
applications, clear user documents or repeatedly unload active speech models.

The **Keep Awake** coffee icon above Settings toggles idle system/display sleep
prevention (`caffeinate -d -i` on macOS). It releases its own assertion when disabled
or when Dock exits. It does not disable manual locks or managed security policies.
It is also available in the console and as a cloud-agent tool.

The **Dashboard** icon between Keep Awake and Settings opens an attached cloud
usage drawer. The console has the same dashboard plus **Activity Tracker**.
Choose this month (default), seven days, or From/To dates. Charts show cloud input,
output, daily consumption, models and API outcomes. Counts come from provider
usage for the full sent payload and generated output; local speech/vision has no
token metrics. Missing usage and currency costs remain explicitly unavailable.

Activity Tracker records accepted voice transcripts and typed requests, every
cloud payload/response, local tool results, recovery calls and stop reasons.
Credentials are redacted and fixed system instructions are represented by size
and fingerprint. Detailed traces expire after seven days; compact daily totals
remain. Tracking starts with this update; older usage cannot be reconstructed.

Three stalled cloud turns stop the request without another paid call. Defaults
also cap a request at eight cloud calls, a 24,000-token budget guard and 1,024 output
tokens per call. Activity Tracker exposes these limits. Preflight token estimates
protect the budget, while displayed totals use provider-reported counts only.

The **Ask Brain** field uses the same agent as speech. Connection failures,
unsupported app controls and missing OS permissions return explicit errors.
Local reactions follow the model's emotion/gesture choice and use the artist's
saved rig, with speech/reading priority and reduced-motion support.

Brain's antenna shows green when online, red when offline or in error, yellow
while listening, and purple while processing/thinking. Listening emits expanding
rings; thinking uses rotating rings; online/offline use glow/pulse effects.
Reduced motion keeps a steady color without moving rings. The status material is
isolated from the artist's shared chest/scanner materials.

The app allows only one resident instance per account to avoid competing
microphone captures. The dock releases its cursor override outside its own area,
so console buttons, selectors, toggles and sliders retain their hand pointer.

On macOS, verify the cached models with generated speech, reduced volume, continuous
noise, inline commands, and negative phrases without opening a microphone stream:

```bash
.venv/bin/python scripts/verify_brain_voice.py
```

The check uses installed Samantha and Daniel voices and writes a JSON report to
`/tmp/dock-twoo-voice-check.json`. It requires the checkpoints to be cached and does
not download or retain microphone recordings.

Check the legacy artwork fallback animation sequence without opening a microphone or
moving application windows:

```bash
.venv/bin/python scripts/verify_brain_animation.py
```

This renders turns, walking in both directions, inspection, climbing, and the
return to idle. It writes a contact sheet and transition report under `/tmp`,
plus an MP4 preview when `ffmpeg` is installed.

## Blender character and document reading

The editable rig lives in [`characters/default/default.blend`](characters/default/default.blend).
Brain uses its exported GLB through a transparent local Qt/WebGL renderer. The same
opaque meshes, white eyes, pupils, smile, gloves and boots appear at every angle.
See [`characters/default/README.md`](characters/default/README.md) for rebuilding and animation validation.

The [companion library](characters/README.md) contains 30 separate Blender projects,
each with 136 animation clips and its own antenna. Browse the running app at
`http://127.0.0.1:28842/brain3d/library.html` or open `characters/index.html` for the
local catalog and source links. The original Brain remains the default.
The interactive preview is at `/brain3d/index.html` on the local console server.

Say **“Brain, go to top left”** in one statement. Capture waits for 1.5 seconds of
trailing silence and keeps recording if speech resumes while transcription runs.
Long statements are transcribed in overlapping windows. Captures over two minutes
are rejected after speech stops rather than executing an incomplete command.
Unrecognized speech receives a repeat/rephrase request.

**Read Desktop** and **Read Active Window** both read the remembered frontmost
external app from its first line. On macOS, Brain uses Accessibility text with a
window-only OCR fallback, reads continuous phrases in document order, and pulls upward while scrolling
to the next page. The underline follows speech playback. Switching to another app,
window or document stops reading. The window is never moved or resized. Use
**Stop Reading** to cancel. **Read Selected Text** reads an existing selection without changing it or using the clipboard. It checks the original document window, including browser text-marker selections when the keyboard focus remains on a button or input field. Accessibility and Screen Recording permissions may be
needed depending on the target app; errors explain what is unavailable. Apps that
do not expose text or scrollable content cannot be guaranteed to read completely.

The local reader controls send `POST /api/brain/action` with an action of
`read_desktop`, `read_window`, `read_selected`, or `stop_reading` and `X-Brain-Reader: local`.
The endpoint rejects foreign browser origins and reports when the desktop manager
is unavailable.

```bash
# Requires the local console server; microphone stays closed.
.venv/bin/python scripts/verify_brain_3d.py
```

See [the agent design](docs/brain-agent-design.md) and [provider simulations](postman/README.md) for architecture, limits and repeatable verification.

## 🤝 Contributing

Contributions are welcome! Dock T(w)oo operates under a strictly protected open-source model:
- Direct pushes and unreviewed merges to `main` are blocked.
- Primary code owner: **@karthikrameshdev**. Secondary code owner and backup reviewer: **@jobphone24**. One approval from either listed code owner is required.
- All contributions must be submitted via a **Fork & Pull Request**.
- For detailed instructions on running tests and coding guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).
- Please adhere to our [Code of Conduct](CODE_OF_CONDUCT.md) and report any security concerns privately via [SECURITY.md](SECURITY.md).

## 📄 License

Apache 2.0 License. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for details.

Brain audio follows the **system default microphone and speaker** through Qt
Multimedia on Windows, macOS and Linux. Device changes reopen only the affected
route; microphone capture retains the statement and speech resumes from the last
played frame. Bluetooth/native sample rates are converted to 16 kHz for local
recognition and to the output device's supported format for speech.

Click Brain once to listen, then again to finish and process the recorded statement.
During speech, thinking and reading, the local keyword model listens for **Stop**
or **Brain Stop**. These controls cancel the agent and speech without a cloud
request. A playback-reference echo suppressor reduces self-triggering; difficult
room acoustics and overlapping voices still require real-device validation.

On Ubuntu/Debian, Qt audio also needs the native PulseAudio client library (this
is used with PulseAudio or PipeWire's PulseAudio compatibility service):

```bash
sudo apt-get install libpulse0 libasound2-dev
```

Windows and macOS use Qt's native audio backend from the installed PySide6 wheels.

### Displays and named voice agents

Use **Placement & Sizing → Show Dock on** to select one display, all displays, or
specific screens such as 1 and 4. Disconnected selections are remembered. The dock
falls back to the primary screen until a selected screen returns.

Right-click **Voice Assistant → Choose assistant** to select Brain, Orbit, Rio,
Luma, Fable or another supplied Blender character. A named wake such as “Hey Rio,
open my notes” changes the same renderer to Rio and routes the complete statement
to that identity. The selected character is remembered. **Move assistant to
screen** and **Roam across all screens** control the one assistant independently
of the dock's multi-display placement. Old saved crowds migrate to one window;
model bindings, memory, task history and documents remain intact.

The selected character uses its own rig and animation library. Local ONNX semantic
ranking varies idle actions. There is no listening body aura; the head light shows
state. The live body silhouette controls clicks, leaving transparent margins,
effects and props click-through. **Hide assistant** and **Show assistant** control
that single window. The parachute action includes descent, landing and retraction.

### Peer agent ecosystem

All 30 agents have equal delegation capabilities. Orbit can assign Brain and Owl
independent work, collect their artifacts and prepare a final document; Brain can
do the same. Each logical identity owns at most one live job. Completed agents can
be reused in a later batch, and workers can delegate further. Busy, self and ancestor
assignments are rejected promptly, so a dependency cycle cannot deadlock the pool.
Up to 29 background workers can process concurrently, with one shared desktop-input
lease for CUA operations. They never create hidden windows or audio services.

Only the selected agent listens or speaks. Selecting another character ends the
old audio session without cancelling background jobs. Inactive agents' finished
jobs produce a brief toast, retain their results and can be queried later; they do
not interrupt the selected agent. Ask “Orbit, what is the status?” to hear its live
worker reports over authenticated gRPC without another model call. The console
provides the durable task trail and downloadable outputs. **Stop** cancels running
and queued work, including descendants.

In **AI Voice Assistant → Agent Models**, configure API, explicit network/Ollama,
or installed headless Gemini, Codex, Claude Code, Kilo and custom CLI profiles.
Assign a profile per character; an unassigned character uses the active default.
Accepted tasks retain their captured profile and credentials. Each CLI task gets
an isolated temporary working directory and process, with cancellation propagated
to its process tree. Generated outputs are copied to local document storage before
the temporary project is removed. CLI native permissions still apply; temporary
working directories do not provide an OS sandbox.

Speech recognition, Kokoro speech synthesis, speaker tuning, species sound cues,
semantic ranking, extractive memory compaction and failure review run locally.
The configured API/CLI/network model performs reasoning. No local generative LLM
server is installed. A shared quantized MiniLM transformer ranks evidence/actions;
scoped memory learns workflows only from explicit, attributable feedback. Current
instructions override preferences; repeated topic interest does not create one.

Stable prompt templates are cached locally for every transport. Native provider
prefix adapters support OpenAI and Claude; Gemini and other compatible providers
use their supported implicit caching. Provider-side cache availability, minimums
and hits remain provider-controlled. Local template reuse never claims a billed
cache hit. No generated answer or desktop action is replayed from cache.

Detailed activity expires after seven days; daily usage totals remain. Dashboards
filter by date, profile and character, with overall totals. Only provider-reported
input/output tokens are counted; unavailable CLI usage remains unknown. Native CLI
usage and events reflect what that CLI exposes, rather than invented internal API
calls. Progressive work has no default three-call stop. Repeated failures trigger
local review and targeted Brain recovery, then a clear error if recovery fails.
Optional call, token and time limits remain available in local agent settings.

Head lights: **green** online/idle, **yellow** listening, **purple** processing,
**cyan** responding, **orange** queued, **red** offline. Head effects respect reduced
motion. Desktop reading/automation availability depends on the platform adapter.
See [the implementation and verification notes](docs/agent-ecosystem.md).
