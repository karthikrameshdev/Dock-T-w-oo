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
prompt. Whisper tiny.en INT8 transcribes commands locally on CPU. The wake assets
are about 6 MB; command recognition adds about 105 MB. First launch downloads these
in background workers and Brain settings reports when each stage is ready.

On Apple Silicon, optional models add MossFormer2-SE noise enhancement, Qwen3-TTS
0.6B CustomVoice (Ryan), and WavLM speaker verification:

```bash
python -m pip install -e '.[voice]'
```

These models use more disk space and download after the command model. While Qwen
is unavailable, a greeting uses platform speech immediately. Model downloads never
run inside the microphone or speech playback path. Audio is processed locally;
voice enrollment stores only a WavLM speaker vector. Set your first name in Brain
settings and select **Enroll my voice** to personalize your greeting. Unenrolled
or uncertain speakers receive “Hey Buddy”.

On macOS, verify the cached models with generated speech, reduced volume, continuous
noise, inline commands, and negative phrases without opening a microphone stream:

```bash
.venv/bin/python scripts/verify_brain_voice.py
```

The check uses installed Samantha and Daniel voices and writes a JSON report to
`/tmp/dock-twoo-voice-check.json`. It requires the checkpoints to be cached and does
not download or retain microphone recordings.

Check the complete Mini Agent animation sequence without opening a microphone or
moving application windows:

```bash
.venv/bin/python scripts/verify_brain_animation.py
```

This renders turns, walking in both directions, inspection, climbing, and the
return to idle. It writes a contact sheet and transition report under `/tmp`,
plus an MP4 preview when `ffmpeg` is installed.

## 📄 License

Apache 2.0 License. See [LICENSE](LICENSE) for details.
