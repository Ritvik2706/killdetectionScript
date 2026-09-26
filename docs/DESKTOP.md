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
   **Play / Pause / Stop**, the seek slider and volume control provide embedded
   video/audio playback through libmpv. Space toggles playback in Recording.
   Playback stops before analysis/export and when leaving Recording. On Linux,
   install `libmpv` (Arch: `mpv`; Debian/Ubuntu: `libmpv-dev`). On Windows, set
   `KILLCUTTER_MPV` to the full path of `mpv-2.dll`. Frame inspection remains
   available without libmpv. Settings → Check environment reports its availability.
2. Enter IN/OUT times or set them from the current frame. OUT includes that
   frame's nominal duration. Input accepts seconds, MM:SS, or HH:MM:SS.
3. Choose a **Detection preset** in Recording. **Analyze** runs its detector in a worker.
   The built-in Warzone preset reads ENEMY DOWNED banners; custom text and colour
   presets work with other games and general videos. See [Presets](PRESETS.md). **Stop**
   cooperatively stops at a sample boundary and keeps partial results in memory.
   The window stays open so you can review and export them. The live analysis
   panel shows detected labels immediately (player names for Warzone), updates merged highlights in place,
   and reports progress, elapsed time, scan position, and estimated time remaining.
   **Follow scan frames** updates the preview once per second; turn it off to
   reduce extra decoding work. The preview is sampled, not real-time playback.
   Detected highlights also remain available if a scan encounters an error.
4. **Highlights** lists actual scan results. All are initially selected. Use
   Ctrl/Shift to change the selection, double-click to seek to a clip, or export
   selected rows as timestamps, a Premiere EDL, or H.264/AAC MP4 clips.
   Search event labels with Ctrl+F, click column headings to sort, and use
   **Copy** for clipboard timestamps. Warzone results can filter by **All kills**, **Real players**,
   **Bots**, or **Undetermined**; the sortable **Kill type** column shows each
   verdict. Real-player and bot filters include undetermined kills by default;
   uncheck **Include undetermined kills** for confirmed matches only. A merged
   clip counts as real player if any kill is confirmed. Filters combine with
   player search without rescanning or deleting clips. **Reset filters** shows
   everything again. Hidden rows are deselected and cannot be exported.
   Selection stays tied to the same clips
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
6. **New preset…** starts by choosing a sample video. Scrub the timeline, step
   through frames, or enter a timestamp. Then choose the detection type and draw
   an area or pick a pixel colour directly on the picture. Name it and click
   **Save & use preset**. Detailed thresholds are under **Advanced settings**.
   The active analysis preset is visible above every page.

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
while work finishes. **Stop** or Escape cancels MP4 encoding, terminates the
encoder, removes its partial temporary file, and keeps completed exports. Only
completed clips are marked exported; existing files survive an interrupted replacement.

## Preset library

**Presets** (Ctrl+3) creates, edits, imports, and exports saved JSON recipes.
The built-in Warzone preset is ready to use and protected from editing or deletion.
Custom recipes support text, colour, motion, scene changes, and audio levels.
Use **New preset…** or **Edit preset…** for guided setup from a sample
video. Picking a colour preserves the selected region. **Save & use preset**
saves and selects it for analysis. Precise pixel controls and optional thresholds
live inside this guided editor. The tab shows a short summary instead of a second
editable form. **More** contains Rename, Duplicate, Export preset file, and Delete
for saved custom presets.

Selecting a saved preset or saving your edits changes the next scan. Existing results retain a
snapshot of their original recipe, name, and capabilities; player/bot filters
only appear for Warzone results. Colour analysis works without Tesseract.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+O | Open a recording |
| Ctrl+Enter | Analyze the selected range |
| Escape | Stop analysis or MP4 encoding and keep completed work |
| Space in Recording | Play/pause audio and video |
| Ctrl+1 / 2 / 3 / 4 | Recording / Highlights / Presets / Settings |
| Ctrl+F | Search highlights by label |
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
python tools/build_desktop.py --installer
```

The portable app folder is `dist/KillcutterStudio`. On Windows, open
`KillcutterStudio.exe`; on Linux, open `KillcutterStudio`. Keep the executable
and `_internal` folder together. Python, Tk, and Python dependencies are bundled.
To include native dependencies, build with
`python tools/build_desktop.py --installer --runtime-dir /path/to/runtime`.
That directory can contain FFmpeg, Tesseract, libmpv, supporting DLLs/shared
libraries, `tessdata/`, and third-party notices. PyInstaller collects binary
dependencies; the app discovers the included tools at startup. Explicit user
environment overrides are preserved. Without a runtime directory, the app uses
installed system tools. Prepare runtimes on the target OS; the local development
Linux bundle is not a substitute for a Windows runtime package.

`.github/workflows/desktop.yml` runs the core tests, GUI integration tests, and
native packaging on Windows and Ubuntu. It uploads separate portable folders;
it does not publish a release. Linux binaries inherit the build machine's libc
requirements: prefer the Ubuntu CI build for distribution rather than an Arch
build. CI is configured but must run on GitHub to establish Windows results.

`--installer` also produces a Linux archive with a per-user `install.sh`, or a
Windows installer when Inno Setup 6 is installed. Windows installation creates
Start-menu shortcuts and an uninstaller without requiring administrator rights.
The Linux script installs the app and a desktop launcher under the user data
folder. Native installer artifacts are built in CI; Windows execution still
requires verification on Windows. Signing is not configured.

Settings → **Check for updates** checks this repository's latest public GitHub
release on request. It opens the releases page with consent; it never downloads
or executes an update automatically. Before a release exists it reports that
clearly. Offline/network errors leave the installed application untouched.

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
| `presets.py` | Validated, versioned recipe model and atomic JSON persistence |
| `generic_detection.py` | General text/colour matching and event scanning |
| `gui/preset_views.py` | Preset selection, editing, import and export |
| `gui/playback.py` / `gui/playback_views.py` | Embedded libmpv transport with native audio/video synchronization |
| `audio_detection.py` | Cancellable, bounded-memory FFmpeg audio level sampling |
| `gui/updates.py` | Explicit read-only check of official releases |
| `gui/services.py` | Job lifecycle, frame loading and detection reporter adapter |
| `detection.py` | Existing engine, now with an optional cooperative cancellation callback |

New detector implementations should consume a validated preset and return clips
through the existing reporter contract. Keep Warzone-specific HUD geometry and
trait probes out of general detectors. See [Preset architecture](PRESETS.md).

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

Playback integration follows the [libmpv client API](https://github.com/mpv-player/mpv/blob/master/include/mpv/client.h).
Release checks use [GitHub's latest release endpoint](https://docs.github.com/en/rest/releases/releases#get-the-latest-release).

### Video library

Click **Open recording** (or press **Ctrl+O**) to choose a video from the
recording picker modal, with export status and metadata visible before opening it.
It starts in the saved Recordings folder; choose another folder with **Browse…**.
**Cancel**, **Escape**, or closing the dialog leaves your current page and recording
intact. Select a row and click **Open recording**, or double-click it to open. This lists videos directly inside that folder (not
subfolders). Search by filename, filter by export status, click column headings
to sort, and double-click a recording to load it for preview and analysis.

The list shows duration, size, and time since the file was last modified. Select
a recording to see the exact save time and matching export paths. **Done** means
`<recording>_highlights.edl` or `<recording>.edl` exists in the configured EDL
folder. **Timestamps** means `<recording>_timestamps.txt` exists in the configured
Timestamps folder without a matching EDL; otherwise the status is **Pending**.
Matching uses the recording filename without its extension, so recordings with
the same stem share a match. Custom export names are not automatically matched.
Done indicates file presence, not validation or a guarantee that every highlight
was exported.

Metadata loads in the background and is cached until the video changes. The
visible library refreshes every 30 seconds; **Refresh** checks immediately.
Exports and saved folder settings also trigger a refresh. Unreadable videos
remain listed with an unavailable duration.

### Reopen saved highlights

Opening a recording automatically loads the newest matching EDL from the saved
EDL directory into **Highlights**. Matching uses the EDL's `FROM CLIP NAME`
comments, so custom and versioned filenames work. Files without source comments
are discovered only under the recording's standard EDL names. Newest means the
most recently modified file for this recording, not an EDL for another video.

Use the EDL selector to switch versions, **Browse…** for another file, **Latest**
to discover newly generated files, or **Reload** after editing an EDL externally.
Player labels come from `COMMENT` lines; missing labels use numbered highlight
names. The table uses source in/out timecodes. Existing preview, rename, trim,
remove, and export actions work on imported highlights. Export EDL suggests the
loaded filename, allowing you to update it or save another version. Switching
files or reloading asks before replacing unsaved highlights.

A complete EDL export becomes the selected EDL. Exporting only some highlights
keeps the remaining unsaved results in view; the saved file is available in the
selector. New analyses also stay in view until saved or replaced explicitly.

Import supports non-drop-frame CMX video/audio-video cuts, including EDLs already
produced by Killcutter. Transitions, separate audio events, and drop-frame EDLs
show an error without replacing current results. Older EDLs use the recording's
frame rate; new exports include a frame-rate comment for accurate reimport.
Player/bot classifications are restored from metadata comments in new exports;
legacy EDLs do not contain these classifications.

### Create a preset from a video

**New preset…** opens the video picker with an explanation of the setup steps.
Choose a sample video, or **Use current recording**, then click **Choose frame**.
In the wizard, scrub or enter a time to find a clear example. Continue to select
the detection area, or choose colour detection and click **Pick a pixel colour**.
Name the preset and select **Save & use preset**. You can go back to choose
another frame before saving. Choosing a sample video leaves your current
recording and highlights intact; cancelling does not create a preset.

**Import preset file…** is for an existing preset JSON file, rather than a video.

### Precise preset selection and OCR

Choose **Text recognition (OCR)** to detect a phrase inside a selected area.
Draw the area or enter **X, Y, Width, Height** in source pixels and click
**Apply area**. Coordinates begin at zero at the video's top-left corner.
The cropped preview shows the exact region used by detection.

**Read selected area (OCR)** runs recognition on that frame in the background
and displays the recognized text. **Use read text as phrase** fills the phrase
field, which you can edit before saving. Matching ignores case and repeated
spaces. Changing frames, detection modes, or regions clears the old readout.
OCR requires local Tesseract; missing dependencies or timeouts are reported
inside the editor without losing your draft.

Colour detection reports the sampled pixel's coordinates, RGB values, and hex
colour. Motion, scene-change, and audio-level detectors remain available with
mode-specific controls. Use the frame buttons for individual-frame adjustments,
**Use whole frame** to reset the area, and **Advanced settings** for thresholds
and coverage.

### Analyze several videos

In **Open recording**, use Ctrl/Shift to select videos and choose **Add to analysis
queue**. Review the list, then **Start queue**. The queue analyzes full recordings
one at a time with the preset and saved settings captured when you start. Each
result gets uniquely named EDL and timestamp files in the configured folders.
Existing exports and the current recording workspace are preserved.

The **Queue** button reopens the list. **Stop queue** stops the current analysis,
saves returned partial highlights, and leaves pending videos for a later start.
A failed video is listed with its error while subsequent videos continue. Use
**Review results** on a finished row; results retained after a save failure can
also be reviewed and exported manually. The queue is kept for this app session.

### Application identity

The shared icon in `killcutter/gui/assets` appears in the sidebar and Tk window
icons. Desktop builds embed the Windows ICO and macOS ICNS; the Linux installer
installs the PNG into the user's icon theme. Rebuild desktop distributions to
include changed assets. The generation prompt and asset provenance are recorded
in `killcutter/gui/assets/BRAND.md`.
