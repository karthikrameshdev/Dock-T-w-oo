<p align="center">
  <img src="assets/icons/logo.svg" width="96" height="96" alt="Dock T(w)oo Logo" />
</p>

<h1 align="center">Dock T(w)oo</h1>

<p align="center">
  <b>Modern Secondary Resident Dock Panel for macOS, Windows, and Ubuntu</b><br>
  <i>(Pronounced "Dock 2")</i>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#built-in-apps">Built-in Apps</a> •
  <a href="#web-configuration-console">Web Console</a> •
  <a href="#quickstart">Quickstart</a> •
  <a href="#testing">Testing</a>
</p>

---

## 🌟 Overview

**Dock T(w)oo** is an open-source, resident secondary desktop dock panel built entirely in **Python** using **PySide6**. Designed for daily workflow productivity across macOS, Windows, and Ubuntu, Dock T(w)oo provides an always-accessible, edge-pinned capsule dock with attached companion drawers that expand right next to the dock.

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

Brain uses **one external cloud model** for reasoning and iterative tool calls.
Open **Brain → Cloud Model** in the local settings console and enter the provider,
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

The editable rig lives in [`character/MiniAssistant.blend`](character/MiniAssistant.blend).
Brain uses its exported GLB through a transparent local Qt/WebGL renderer. The same
opaque meshes, white eyes, pupils, smile, gloves and boots appear at every angle.
See [`character/README.md`](character/README.md) for rebuilding and animation validation.
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
**Stop Reading** to cancel. **Read Selected Text** reads an existing selection without changing it. Accessibility and Screen Recording permissions may be
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

## 📄 License

Apache 2.0 License. See [LICENSE](LICENSE) for details.
