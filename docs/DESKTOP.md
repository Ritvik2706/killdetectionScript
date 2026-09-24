# Killcutter Studio desktop

A native Python/Tk desktop interface for Linux and Windows. It uses Road Trip's
visual vocabulary (dark layered surfaces, a sidebar, restrained blue accents)
without depending on the Road Trip repository. The TUI and existing CLI remain
available.

## Run from source

Python 3.11+ with Tk is required. Use Python 3.12 for the CI/build baseline.

Linux / Arch:

```bash
sudo pacman -S tk tesseract tesseract-data-eng ffmpeg
python -m venv .venv
.venv/bin/python -m pip install -e '.[gui]'
.venv/bin/python -m killcutter.gui
```

On Debian/Ubuntu, install `python3-tk`, `tesseract-ocr`, and optional `ffmpeg`
with your package manager. A native Windows build does not use WSL.

### On WSL: automatic handoff to Windows Python

Launched inside WSL, `killcutter-desktop` / `python -m killcutter.gui` runs the
window with **Windows** Python instead of WSLg. WSLg mirrors Linux windows to
Windows over RDP, and when a Windows window manager resizes that mirror (any
tiling WM, e.g. GlazeWM) the new size never reaches X — the window stays blank.
The app cannot see that resize, so it avoids WSLg altogether.

On each launch it:

1. Finds a real Windows Python 3.11+ with Tk (`py.exe`, `python.exe`, the usual
   install folders; the Microsoft Store placeholder is ignored). If there is
   none it offers `winget install Python.Python.3.12` — only in a terminal, and
   only after you answer yes.
2. Keeps a private venv in `%LOCALAPPDATA%\killcutter\wsl-desktop\venv` and
   installs the runtime + `gui` dependencies into it, again whenever they change.
3. Offers to install Tesseract with winget if Windows has none (asked once;
   the desktop still opens without it).
4. Runs this checkout's code live over `\\wsl.localhost`, so edits in WSL take
   effect on the next launch with no reinstall.

The Windows window uses Windows' own config location
(`%USERPROFILE%\.config\killcutter\config.toml`) unless you pass `--config`,
which is translated to a Windows path. Paths saved there are Windows paths.

`--wslg` or `KILLCUTTER_WSLG=1` keeps the window inside WSLg. If the handoff
fails, the reason is printed and it falls back to WSLg.

Windows PowerShell (install Python with Tcl/Tk support):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[gui]"
.\.venv\Scripts\pythonw.exe -m killcutter.gui
```

Installing the project also adds `killcutter-desktop` (`killcutter-desktop.exe`
on Windows). The Windows GUI entry point runs without a console window.
Tesseract must be installed on Windows for analysis; the existing discovery
logic searches PATH and common installation locations. FFmpeg on PATH is needed
only for MP4 rendering. Settings → Check environment reports dependencies.

## Working workflow

1. **Recording** opens a native file picker, loads metadata and displays a frame.
   **Recent ▾** in the header reopens one of the last eight recordings; entries
   whose file has moved are shown as missing rather than silently failing.
   Scrub the slider to inspect frames; preview decoding runs off the UI thread.
   The current foundation is a frame viewer, not a real-time video/audio player.
2. Enter IN/OUT times or set them from the current frame. OUT includes that
   frame's nominal duration. Input accepts seconds, MM:SS, or HH:MM:SS.
3. **Analyze** runs the existing ENEMY DOWNED detector in a worker. **Stop**
   cooperatively stops at a sample boundary and keeps partial results in memory.
   The window stays open so you can review and export them. The live analysis
   panel shows player names immediately, updates merged highlights in place,
   and reports progress, elapsed time, scan position, and estimated time remaining.
   **Follow scan frames** updates the preview once per second; turn it off to
   reduce extra decoding work. The preview is sampled, not real-time playback.
   Detected highlights also remain available if a scan encounters an error.
4. **Highlights** lists actual scan results. All are initially selected. Use
   Ctrl/Shift to change the selection, double-click to seek to a clip, or export
   selected rows as timestamps, a Premiere EDL, or H.264/AAC MP4 clips.
   Search player names with Ctrl+F, click column headings to sort, and use
   **Copy** for clipboard timestamps. Selection stays tied to the same clips
   when sorting. Select all applies to the visible search results; exports remain
   in chronological order. The selection summary shows count and total duration.
   **Rename…** (F2) relabels a detection whose OCR name came out wrong, **Remove**
   (Delete) drops false positives, and **Ctrl+Z** restores the last removal.
   **Nudge selected** shifts the in or out point of every selected highlight by a
   second, clamped inside the recording and never past the other end. Edits
   re-index the list, so an export mark follows its clip and an edited clip is
   marked unexported again.
   Nothing is exported automatically. Exporting only some rows does not mark
   the other rows as saved. Closing or replacing unexported results prompts.
5. **Settings** saves independent input, timestamp, EDL and MP4 directories,
   detection parameters and sequence name. Changes apply on Save. Config search
   order is shared with the CLI; without a file the default user config path is
   used. The desktop's default output folders are under `~/Videos/Killcutter`;
   choose other locations with the folder pickers. The working directory of a
   packaged executable is not used as the default export destination.
6. **Frame inspector** maps a click through the letterboxed preview into the
   original frame's X/Y coordinates, RGB value and hex, with a colour swatch and
   **Copy colour**. Save this as versioned JSON. Samples are inspection data;
   they do not yet modify detection rules.

## Appearance and session state

Settings → Appearance holds the desktop-only preferences: a **theme**
(Midnight, Graphite, Daylight), an **accent** from six presets or any custom
colour, an **interface scale** from 80% to 160%, and a **chime** when an
analysis finishes. Changes apply to the live window — the ttk styles are
rebuilt, plain Tk widgets are remapped from the old palette to the new, and
every label rebuilds at its own scaled size, so the type hierarchy is kept.
Only colours that came from the previous palette are replaced, so a deliberate
one-off colour survives. Restyling happens when a slider is released, not on
every drag step.

These live in the same config file as the CLI settings, under `[gui]`, together
with the window geometry, the last page, and the recent recordings list. Every
value is validated when read: an out-of-range scale is clamped and anything
unusable falls back to the default, so a hand-edited or stale file can't stop
the app from starting. They are written as soon as they change, and the window
geometry and page are written on close.

Analysis, frame decoding, environment checks, and export happen in workers.
Only the Tk thread owns widgets and image handles. EDL/timestamps are atomic,
and MP4 output is replaced only after a successful render. Closing is deferred
while an export finishes; MP4 rendering does not yet have a cancel control.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+O | Open a recording |
| Ctrl+Enter | Analyze the selected range |
| Escape | Stop analysis and keep partial results |
| Ctrl+1 / 2 / 3 / 4 | Recording / Highlights / Inspector / Settings |
| Ctrl+F | Search highlights by player |
| Ctrl+A in the highlights table | Select all visible highlights |
| Enter in the highlights table | Preview the selected highlight |
| F2 in the highlights table | Rename the selected highlight |
| Delete in the highlights table | Remove the selected highlights |
| Ctrl+Z | Undo the last removal |
| Ctrl+C in the highlights table | Copy selected timestamps |
| F1 | Show this list in the app |

The recording controls also step one frame or five seconds in either direction.
Cards, buttons, and input fields use antialiased rounded surfaces. Buttons and
fields retain native Tk keyboard focus and interaction behavior.

## Native builds

Build on each target OS; a Linux/WSL build cannot produce a Windows executable.

```bash
python -m pip install -e ".[gui,build]"
python tools/build_desktop.py
```

The portable app folder is `dist/KillcutterStudio`. On Windows, open
`KillcutterStudio.exe`; on Linux, open `KillcutterStudio`. Keep the executable
and `_internal` folder together. Python, Tk, and Python dependencies are bundled.
Tesseract and FFmpeg are external dependencies in this foundation.

`.github/workflows/desktop.yml` runs the core tests, GUI integration tests, and
native packaging on Windows and Ubuntu. It uploads separate portable folders;
it does not publish a release. Linux binaries inherit the build machine's libc
requirements: prefer the Ubuntu CI build for distribution rather than an Arch
build. CI is configured but must run on GitHub to establish Windows results.

This is a working development foundation, not a signed commercial installer.
Installer integration, bundled external tools, application updates, and video
playback can be added without replacing the detection engine.

## Extension points

| Module | Responsibility |
|---|---|
| `gui/app.py` | Navigation, workflow state, queue polling, native dialogs |
| `gui/views.py` | Page layouts and bindings to application actions |
| `gui/theme.py` | Palettes, accent/scale wiring, typography and widget styles |
| `gui/preferences.py` | Validated `[gui]` preferences: theme, accent, scale, chime, session |
| `gui/surfaces.py` | Bounded corner cache and antialiased surface rendering |
| `gui/widgets.py` | Reusable cards, preview canvas and scrollable forms |
| `gui/state.py` | Media/workspace models and pure image-coordinate mapping |
| `gui/services.py` | Job lifecycle, frame loading and detection reporter adapter |
| `detection.py` | Existing engine, now with an optional cooperative cancellation callback |

For custom detectors, introduce a versioned detection-profile model containing
source dimensions, regions, sample points, color tolerances and matching rules.
The inspector already produces source coordinates, so the profile UI does not
need to understand screen scaling. Keep profile evaluation in the core and pass
results through the same reporter; do not put pixel tests in widget callbacks.

## Verification

```bash
python -m pytest -q
# Linux desktop, or prepend xvfb-run -a on a headless machine:
KILLCUTTER_GUI_TESTS=1 python -m pytest tests/test_gui.py -q
# Windows PowerShell:
$env:KILLCUTTER_GUI_TESTS = "1"
python -m pytest tests/test_gui.py -q
```

`python tools/gui_smoke.py` opens a real window, creates synthetic footage,
exercises import/seeking/live updates/compact layout/settings/inspection,
removal and undo, and each theme at a scaled size, and saves window screenshots
in a temporary directory. No game recording or OCR service is required for this test.
