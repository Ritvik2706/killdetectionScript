# Killcutter Studio desktop foundation

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
with your package manager. On WSL the GUI requires WSLg or another display
server. A native Windows build does not use WSL.

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
   Scrub the slider to inspect frames; preview decoding runs off the UI thread.
   The current foundation is a frame viewer, not a real-time video/audio player.
2. Enter IN/OUT times or set them from the current frame. OUT includes that
   frame's nominal duration. Input accepts seconds, MM:SS, or HH:MM:SS.
3. **Analyze** runs the existing ENEMY DOWNED detector in a worker. **Stop**
   cooperatively stops at a sample boundary and keeps partial results in memory.
   The window stays open so you can review and export them.
4. **Highlights** lists actual scan results. All are initially selected. Use
   Ctrl/Shift to change the selection, double-click to seek to a clip, or export
   selected rows as timestamps, a Premiere EDL, or H.264/AAC MP4 clips.
   Nothing is exported automatically. Exporting only some rows does not mark
   the other rows as saved. Closing or replacing unexported results prompts.
5. **Settings** saves independent input, timestamp, EDL and MP4 directories,
   detection parameters and sequence name. Changes apply on Save. Config search
   order is shared with the CLI; without a file the default user config path is
   used. The desktop's default output folders are under `~/Videos/Killcutter`;
   choose other locations with the folder pickers. The working directory of a
   packaged executable is not used as the default export destination.
6. **Frame inspector** maps a click through the letterboxed preview into the
   original frame's X/Y coordinates and RGB value. Save this as versioned JSON.
   Samples are inspection data; they do not yet modify detection rules.

Analysis, frame decoding, environment checks, and export happen in workers.
Only the Tk thread owns widgets and image handles. EDL/timestamps are atomic,
and MP4 output is replaced only after a successful render. Closing is deferred
while an export finishes; MP4 rendering does not yet have a cancel control.

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
| `gui/theme.py` | Palette, typography and widget styles |
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
exercises import/seeking/settings/inspection, and saves window screenshots in a
temporary directory. No game recording or OCR service is required for this test.
