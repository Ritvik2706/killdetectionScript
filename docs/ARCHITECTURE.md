# Architecture

A small, layered package. The guiding rule: **core logic never prints**, and
**presentation never decodes video**. That separation keeps each piece readable
and lets the pure logic be unit-tested without a clip or a terminal.

## Layers

```
            ┌──────────────────────────────────────────────┐
   CLI      │ cli.py    arg parsing · config wiring · flow  │
            └───────────────┬───────────────┬──────────────┘
                            │               │
        ┌───────────────────┴───┐   ┌───────┴───────────────────┐
 Core   │ detection.py          │   │ export.py                 │
 logic  │  scan → list[Clip]    │   │  timestamps → ExportPlan  │
        │  (reports via hooks)  │   │  → EDL string             │
        └───────┬───────────────┘   └───────────┬───────────────┘
                │                                │
        ┌───────┴────────────┐          ┌────────┴───────────┐
 I/O    │ video.py           │          │ calibration.py     │
        │  probe · discover  │          │  region / pixel    │
        │  · pick (uses ui)  │          │  (OpenCV windows)  │
        └────────────────────┘          └────────────────────┘
                            ┌──────────────────────────────┐
 Health                     │ diagnose.py    environment.py│
                            │  footage →      deps →       │
                            │  Diagnosis      doctor report│
                            └──────────────────────────────┘

 Portability    hud.py — banner geometry for any resolution, anchored top-right

 Presentation   reporting.py  ──uses──▶  ui/  (ansi · layout · progress · selector · keys)
 Shared         models.Clip · timecode · constants · errors · config
```

## Data flow

### `detect`
1. `cli.cmd_detect` resolves the video (`video.pick` if not given) and builds a
   `DetectionSettings`.
2. `detection.detect(video, settings, reporter)` walks the file and returns
   `list[Clip]`. It calls the reporter's hooks (`begin`, `frame`, `progress`,
   `kill`, `extended`) for everything that appears on screen — it never prints.
3. `cli` renders results (`reporting.detection_results`), writes `timestamps.txt`,
   and — unless `--no-export` / `[detect] export=false` — calls `_do_export`
   **in process** (no subprocess).

### `diagnose`
1. `cli.cmd_diagnose` resolves the video and calls `diagnose.diagnose(...)`.
2. It samples a window with detection's own `_samples`, `_pixel_is_*` and
   `_is_kill_header`, so it measures the real pipeline rather than a copy of it,
   and tallies how many frames survive each stage.
3. `Diagnosis.problems` turns those tallies into an ordered list of likely
   causes; `reporting.diagnosis` draws them. A non-empty list exits non-zero.

### `doctor`
`environment.check()` probes Python, OpenCV, NumPy, pytesseract, the Tesseract
binary, the config and the clips folder, returning `Check` records that
`reporting.doctor` renders. Non-required failures (a missing clips folder) are
reported without blocking, since `--video` bypasses the picker entirely.

### `export`
1. `export.read_timestamps` → `list[Clip]`.
2. `export.plan(video, clips, …)` resolves the authoring fps (snapped to the
   media's real rate, never converted between 60 and 59.94), cross-checks it
   against `frames / duration`, and settles the output path into an immutable
   `ExportPlan`.
3. `export.build_edl(plan)` renders the EDL string; `write_edl` saves it.
4. `reporting.export_plan` / `export_saved` draw the panels.

## Why a `reporter`?

The detection loop has tightly-timed terminal output (a `\r`-redrawn progress
bar interleaved with kill lines). Rather than bake that into the algorithm, the
loop emits semantic events and `reporting.ConsoleReporter` decides how to draw
them. Swapping in a silent or JSON reporter would need no change to detection.

## The `ui` package

Zero third-party dependencies, split by concern:

| Module | Contents |
|---|---|
| `ansi` | colour-capability detection, palette, `paint`, `badge`, `set_color` |
| `layout` | `term_*`, `rule`, `banner`, `panel`, `kv`, `hint`, `rel_time` |
| `progress` | `gradient_bar`, `spinner_frame` |
| `keys` | raw-mode single-keypress reader (termios / msvcrt), normalised key names |
| `selector` | `select()` — the vim-navigable fuzzy picker and its `_State` machine |

`set_color` mutates a single module-global flag that every styling function
reads at call time, so `--no-color` / `[ui] color=false` switch styling off
everywhere at once.

## Testing

`tests/` covers the pure layers without a video file:
- `test_timecode` — formatting, frame-rate resolution, drift over hours
- `test_hud` — 1080p is byte-identical to the constants; scaling and ultrawide
- `test_validation` — impossible settings fail before the scan, not during
- `test_environment` — Tesseract discovery and what counts as blocking
- `test_reporting` — the progress line always fits the terminal
- `test_export` — `read_timestamps`, EDL header/events, contiguous records
- `test_config` — write/load roundtrip, no-clobber, missing file
- `test_selector` — fuzzy matching and the picker `_State` transitions

## Interactive workspace and destinations

`ui/workspace.py` provides the home screen, settings draft editor, and guided
scan setup using the existing picker. It builds ordinary CLI argument namespaces
and dispatches the same command handlers as scripted usage. No additional UI
framework is required. `ranges.py` parses human-readable times and validates
source-time ranges shared by setup and detection; highlight boundaries are
clamped to that range.

`config.save_updates()` updates known scalar settings atomically while retaining
unrelated configuration. `outputs.py` resolves destination filenames, rejects
input/output collisions, writes text atomically, and optionally renders MP4 clips
through FFmpeg. FFmpeg is required only when rendering is requested. CLI flags
continue to override saved settings. Detection remains independent of UI and
rendering concerns.


## Desktop GUI

The optional `killcutter.gui` package owns the native desktop interface. Core
modules never import Tk. Worker threads publish data to a queue; the main thread
polls it and updates widgets. `detection.detect(cancelled=callable)` provides
cooperative cancellation without coupling the detector to a UI toolkit. See
[DESKTOP.md](DESKTOP.md) for the module map, packaging and calibration roadmap.
