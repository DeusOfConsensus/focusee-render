# focusee-render

A CLI tool that renders [FocuSee](https://focusee.app) screen recording
projects into polished MP4 videos — replicating every visual effect FocuSee locks
behind its premium paywall.

**What it produces:**

| Effect | Details |
|---|---|
| Background | Your chosen FocuSee background image, full canvas |
| Rounded corners | Matches your project's `round` setting |
| Drop shadow | Soft Gaussian shadow behind the recording |
| Cursor overlay | Real arrow / hand / ibeam PNGs at correct size & hotspot |
| Click ripples | Expanding gold rings on every mouse click |
| Auto-zoom | Smooth ease-in/out zoom events, centered on the cursor |
| Audio | System audio merged into the final MP4 via ffmpeg |

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [One-Time Setup](#one-time-setup)
   - [Clone the repo](#step-1--clone-the-repo)
   - [Install Python dependencies](#step-2--install-python-dependencies)
   - [Install the CLI globally](#step-3--install-the-cli-globally)
   - [Install ffmpeg](#step-4--install-ffmpeg)
3. [Using It (Every Time You Record)](#using-it-every-time-you-record)
4. [Command Reference](#command-reference)
5. [VS Code Integration](#vs-code-integration-optional-but-recommended)
6. [File Structure Expected](#file-structure-expected)
7. [How It Works Internally](#how-it-works-internally)
8. [Updating the Tool](#updating-the-tool)
9. [Troubleshooting](#troubleshooting)
10. [New PC Setup](#new-pc-setup)

---

## Prerequisites

Before you start, make sure these are installed on your PC:

| Tool | Version | Check command | Download |
|---|---|---|---|
| Python | 3.11+ | `python --version` | https://python.org/downloads |
| Git | Any | `git --version` | https://git-scm.com |
| ffmpeg | Any | `ffmpeg -version` | https://www.gyan.dev/ffmpeg/builds |

### Installing ffmpeg (Windows)

1. Download the **release essentials** build from:
    https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip

2. Extract the zip. Inside you'll find a folder like `ffmpeg-8.x-essentials_build`.

3. Open it → open `bin` → copy `ffmpeg.exe`.

4. Paste `ffmpeg.exe` into `C:\Windows\System32\` — this makes it available
   system-wide in any terminal.

5. Verify: open a new terminal and run `ffmpeg -version`. You should see version info.

> **Alternative:** You can also place `ffmpeg.exe` directly inside each FocuSee
> project folder. The renderer will find it there automatically if it's not on
> your system PATH.

---

## One-Time Setup

You only do this **once**. After this, every future FocuSee project renders
with a single command.

### Step 1 — Clone the repo

Open a terminal and run:

```bash
git clone https://github.com/DeusOfConsensus/focusee-render.git C:\Tools\focusee-render
```

> You can clone to any folder you like — `C:\Tools\focusee-render` is just a suggestion.

### Step 2 — Install Python dependencies

```bash
pip install opencv-python Pillow numpy
```

These three libraries are all the renderer needs beyond the standard library.

### Step 3 — Install the CLI globally

```bash
pip install -e C:\Tools\focusee-render
```

The `-e` flag means **editable install**. This means:
- The `focusee-render` command is now available in every terminal on your PC.
- If you ever edit the source code in `C:\Tools\focusee-render`, the changes
  apply instantly — no reinstall needed.

Verify it worked:

```bash
focusee-render --help
```

You should see the help text printed. That's it — setup is complete.

### Step 4 — Install ffmpeg

Follow the ffmpeg instructions in [Prerequisites](#prerequisites) above.

---

## Using It (Every Time You Record)

After you finish a recording in FocuSee and it asks you to upgrade to export:

1. **Open the project folder** in File Explorer or VS Code.
   The folder has a `.focusee` extension and lives wherever FocuSee stores projects
   (usually `C:\FocuSee\FocuSee Projects\`).

2. **Open a terminal inside that folder.**
   In VS Code: press `` Ctrl+` `` to open the integrated terminal.
   In File Explorer: right-click inside the folder → "Open in Terminal".

3. **Run:**

```bash
focusee-render
```

4. Watch the progress bar. When it finishes you'll see (for example):

```
  ✅  Done!  →  C:\...\rendered_output.mp4  (45.2 MB)
```

5. Open `rendered_output.mp4` in any video player. Done.

---

## Command Reference

```
focusee-render [OPTIONS]

Options:
  -p, --project PATH   Path to the .focusee project folder.
                       Default: current working directory.

  -o, --output PATH    Where to save the final MP4.
                       Default: rendered_output.mp4 inside the project folder.

  -h, --help           Show this help message and exit.
```

### Examples

```bash
# Standard usage — run from inside the project folder
cd "C:\FocuSee\FocuSee Projects\FocuSee Project 2026-05-04 10-06-55.focusee"
focusee-render

# Pass the path explicitly from anywhere
focusee-render --project "C:\FocuSee\FocuSee Projects\FocuSee Project 2026-05-04 10-06-55.focusee"

# Save to a custom output location
focusee-render --output "C:\Users\Asmodeus\Videos\tutorial_part1.mp4"

# Both options together
focusee-render -p "C:\Projects\recording.focusee" -o "C:\Videos\output.mp4"
```

---

## VS Code Integration (Optional but Recommended)

You can add a keyboard shortcut so that inside any FocuSee project opened in
VS Code, you press `Ctrl+Shift+B` and the render starts automatically — no
terminal typing needed.

Create a file called `.vscode/tasks.json` inside the project folder with this content:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Render FocuSee Video",
      "type": "shell",
      "command": "focusee-render",
      "group": {
        "kind": "build",
        "isDefault": true
      },
      "presentation": {
        "reveal": "always",
        "panel": "new"
      },
      "problemMatcher": []
    }
  ]
}
```

After saving, press `Ctrl+Shift+B` in VS Code to start rendering. The output
panel will show the progress bar in real time.

---

## File Structure Expected

The renderer expects this layout inside the `.focusee` project folder.
FocuSee creates all of these automatically when you record:

```
YourProject.focusee/
│
├── configure.focuseeproj          ← Project settings (zoom, padding, cursor size…)
│
├── recording/
│   ├── display-0.mp4              ← Raw screen capture video
│   ├── systemaudio-0.m4a          ← System audio recording
│   ├── metadata.json              ← Session timing and bounds info
│   ├── mousemoves-0.json          ← Cursor position at every frame
│   ├── mouseclicks-0.json         ← Click events with timestamps
│   ├── keystrokes-0.json          ← Keyboard events (not used in render)
│   ├── cursor.json                ← Cursor image definitions and hotspots
│   └── cursors/
│       ├── arrow.png              ← Arrow cursor image
│       ├── hand.png               ← Hand/pointer cursor image
│       └── ibeam.png              ← Text cursor image
│
└── resource/
    ├── background.png             ← Full background image
    └── background_C.png           ← Cropped background (preferred if present)
```

**Output** (created by the renderer):

```
YourProject.focusee/
└── rendered_output.mp4            ← Your final polished video
```

---

## How It Works Internally

Understanding this helps you modify the renderer if you want to tweak the output.

### 1. Data loading
All JSON files are loaded at startup. FocuSee uses a slightly invalid JSON
format (trailing commas) — the loader strips these automatically before parsing.

### 2. Layout geometry
The recording is placed inside a padded canvas matching your `background.png`.
The padding, corner radius, and shadow settings all come from `configure.focuseeproj`.

### 3. Frame loop
For each output frame (30 fps):
- Read the corresponding source frame from `display-0.mp4`
- Look up cursor position by interpolating between the two nearest entries
  in `mousemoves-0.json` using the `processTimeMs` timestamp
- Calculate the zoom factor for this moment (from `zoomTracks` in the config)
- If zoomed: crop the source frame around the cursor, then upscale
- Composite: background → shadow → recording (with rounded corners) → ripples → cursor
- Write the composited frame to a temporary output file

### 4. Zoom timing
Zoom events are stored as `begin` and `end` values between 0.0 and 1.0,
representing fractions of the total recording duration. The renderer converts
these to absolute milliseconds and applies a smooth cubic ease-in/out curve
at the start and end of each zoom event (400ms by default).

### 5. Audio merge
After all frames are written, ffmpeg merges `systemaudio-0.m4a` into the
video and produces the final `rendered_output.mp4`. The temporary raw video
file is deleted after a successful merge.

---

## Updating the Tool

When you want to improve the renderer or fix something:

### Edit locally

1. Open `C:\Tools\focusee-render\focusee_render\render.py` in VS Code.
2. Make your changes and save.
3. Because you installed with `-e` (editable), changes apply **immediately**.
   No reinstall needed.

### Sync to GitHub

```bash
cd C:\Tools\focusee-render
git add .
git commit -m "Describe what you changed"
git push
```

### Pull updates on another machine

```bash
cd C:\Tools\focusee-render
git pull
```

That's it — since the install is editable, the pulled changes are live instantly.

---

## Troubleshooting

### `focusee-render: command not found`

The editable install did not add the script to your PATH. Try:

```bash
pip install -e C:\Tools\focusee-render --force-reinstall
```

If it still doesn't work, close and reopen your terminal (PowerShell sometimes
needs a restart to pick up new PATH entries).

### `This does not look like a FocuSee project folder`

You're running `focusee-render` from the wrong directory. Make sure you're
**inside** the `.focusee` folder (the one that contains `configure.focuseeproj`),
not outside it.

```bash
# Wrong:
cd "C:\FocuSee\FocuSee Projects"
focusee-render

# Correct:
cd "C:\FocuSee\FocuSee Projects\FocuSee Project 2026-05-04 10-06-55.focusee"
focusee-render
```

### `ffmpeg not found`

Either ffmpeg is not installed, or it's not on your system PATH. Fix options:

**Option A** — Add ffmpeg to system PATH:
Copy `ffmpeg.exe` to `C:\Windows\System32\`

**Option B** — Place `ffmpeg.exe` directly in the project folder:
The renderer checks for `ffmpeg.exe` in the project folder before checking PATH.

### `JSONDecodeError`

This usually means a JSON file is corrupted or truncated. The renderer handles
FocuSee's trailing-comma quirk automatically, but if the file is genuinely
broken, try re-recording or let me know the error details.

### `Cannot open video: recording/display-0.mp4`

The mp4 file is missing or corrupted. Open File Explorer inside the project
folder and check that `recording/display-0.mp4` exists and is not 0 bytes.

### Zoom events not appearing / wrong timing

Check that `configure.focuseeproj` exists in the project root and contains
a `zoomTracks` array. If you added zoom manually in FocuSee after recording,
save the project in FocuSee first so the config updates.

### Video renders but looks stretched

Your recording was done at a non-standard resolution. The renderer reads the
resolution from `metadata.json` automatically, so this should not happen. If it
does, open `metadata.json` and check the `bounds.width` and `bounds.height`
values in the `legacyDisplay` recorder entry.

---

## New PC Setup

If you get a new PC or reinstall Windows, here's everything you need to do —
start to finish:

```bash
# 1. Install Python 3.11+ from https://python.org

# 2. Install Git from https://git-scm.com

# 3. Install ffmpeg — copy ffmpeg.exe to C:\Windows\System32\

# 4. Clone this repo
git clone https://github.com/DeusOfConsensus/focusee-render.git C:\Tools\focusee-render

# 5. Install dependencies
pip install opencv-python Pillow numpy

# 6. Install the CLI
pip install -e C:\Tools\focusee-render

# 7. Verify
focusee-render --help
```

Total time: about 5 minutes. Then `focusee-render` works from any project folder.
