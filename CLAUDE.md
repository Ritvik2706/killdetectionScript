# Killfeed Auto-Cutter — CLAUDE.md

## What this project does

A Python package that detects kills from a CoD gameplay recording and assembles the
highlight clips into a Premiere Pro–ready EDL. Detection runs straight into export, so
one command takes you from raw footage to an importable highlight reel.

```
gameplay video → detect → timestamps.txt → export → <video>_highlights.edl → Premiere import
```

Run everything through one CLI:

```bash
python -m killcutter detect              # pick a clip, scan, auto-export
python -m killcutter export              # build an EDL from an existing timestamps.txt
python -m killcutter calibrate           # re-find the region / trigger pixel
```

(`pip install -e .` also installs a `killcutter` console script — same commands.)

## Package layout

Everything lives under `killcutter/`. Core logic is presentation-free; all terminal
output goes through `reporting.py` / `ui/`. See `docs/ARCHITECTURE.md` for the full map.

| Module | Responsibility |
|---|---|
| `cli.py` | Argument parsing, config wiring, command dispatch (`detect`/`export`/`calibrate`) |
| `detection.py` | Kill-detection algorithm; returns `Clip`s, reports progress via a reporter |
| `export.py` | Pure EDL planning + rendering (`read_timestamps`, `plan`, `build_edl`, `write_edl`) |
| `reporting.py` | All terminal presentation (banner, panels, progress reporter, result/export views) |
| `video.py` | Clip discovery, metadata probing, the interactive picker (`pick`) |
| `calibration.py` | OpenCV region / trigger-pixel calibration helpers |
| `config.py` | Layered TOML config (`--config`, `--write-config`) |
| `timecode.py` | Pure time/timecode/NTSC math (well unit-tested) |
| `models.py` | `Clip` dataclass shared across the pipeline |
| `constants.py` | Tunables: region, trigger pixels, thresholds, clips dir |
| `errors.py` | `KillcutterError` hierarchy the CLI catches and prints tidily |
| `ui/` | Zero-dependency ANSI toolkit: `ansi`, `layout`, `progress`, `selector`, `keys` |

Tests are in `tests/` (pytest); `timecode`, `export`, `config`, and the selector
state-machine are covered without needing a video file.

## Detection approach

CoD shows an **"ENEMY DOWNED"** banner top-right on a kill. OCR on every frame is too
slow, so each sampled frame is gated by two cheap pixel checks — a known-white pixel on
the banner text and a known-red pixel on its accent. Only when both pass do we OCR the
banner ROI for the player name.

- Constants live in `killcutter/constants.py`: `DEFAULT_REGION = (1598, 186, 189, 45)`,
  trigger pixels white `(1581, 195)` / red `(1607, 195)`.
- A cooldown prevents double-counting; kills within `--merge-gap` seconds merge into one clip.
- Timing uses container timestamps (`CAP_PROP_POS_MSEC`), not frame÷fps, so VFR OBS captures don't drift.

## Key flags (`detect`)

| Flag | Default | Effect |
|---|---|---|
| `--offset` / `--end-offset` | `5` / `5` | Seconds before / after the kill for the clip window |
| `--merge-gap` | `10` | Kills within this gap merge into one clip |
| `--cooldown` | `3` | Min seconds between detections |
| `--rate` | `2` | Frame samples per second |
| `--region X Y W H` | — | Override the scan region |
| `--preview` | off | Show the scan region + OCR live (tune a new clip first) |
| `--dry-run` | off | Print detected clips without writing `timestamps.txt` |
| `--no-export` | off | Stop after `timestamps.txt`; don't auto-run the exporter |

Global flags (any command): `--config PATH`, `--write-config [PATH]`, `--no-color`, `--version`.

## Interactive clip picker (vim keys)

When `--video` is omitted, commands open a full-screen fuzzy picker (`ui.select`,
alternate-screen, raw input). It falls back to a numbered prompt when stdout isn't a TTY.

| Key | Action |
|---|---|
| `j`/`k`, `↓`/`↑` | move cursor |
| `gg` / `G` | top / bottom |
| `Ctrl-d`/`Ctrl-u`, `Ctrl-f`/`Ctrl-b`, `PgDn`/`PgUp` | half / full page |
| `/` | incremental fuzzy search (subsequence); `Esc` clears, `⏎` accepts |
| digits then `⏎` | jump to a row by number |
| `⏎` select · `q` / `Esc` / `Ctrl-c` cancel | |

## Configuration

TOML, first match wins: `--config PATH` → `./.killcutter.toml` → `~/.config/killcutter/config.toml`.
`python -m killcutter --write-config` drops a commented starter. Sections: `[detect]`
(clips_dir, offset, end_offset, merge_gap, cooldown, rate, region, export), `[export]`
(fps, name), `[ui]` (color). Explicit CLI flags always win.

## Dependencies

```bash
sudo apt install tesseract-ocr
pip install -e .          # or: pip install opencv-python numpy pytesseract
```

The `ui` package is pure standard library.

## Known limitations / future work

- Only detects kills that surface the **"ENEMY DOWNED"** banner; banner-less kills won't trigger.
- Trigger pixels / region assume 1920×1080 and the current HUD — re-run `calibrate` if it changes.
- The exporter authors NTSC-correct timecode (60 → 59.94) so cuts don't drift; the Premiere sequence fps **must** match what it prints.
- Future: auto-export individual clips, and dump detected frames to disk for offline review.
