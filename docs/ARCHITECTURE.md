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

### `export`
1. `export.read_timestamps` → `list[Clip]`.
2. `export.plan(video, clips, …)` resolves the authoring fps (NTSC-corrected),
   drop-frame mode and output path into an immutable `ExportPlan`.
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
- `test_timecode` — formatting, NTSC correction, timecode rollover
- `test_export` — `read_timestamps`, EDL header/events, contiguous records
- `test_config` — write/load roundtrip, no-clobber, missing file
- `test_selector` — fuzzy matching and the picker `_State` transitions
