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
python -m killcutter diagnose            # check the HUD constants against a clip
python -m killcutter traits              # list traits / check one against footage
python -m killcutter doctor              # check this machine has the dependencies
```

(`pip install -e .` also installs a `killcutter` console script — same commands.)

## Package layout

Everything lives under `killcutter/`. Core logic is presentation-free; all terminal
output goes through `reporting.py` / `ui/`. See `docs/ARCHITECTURE.md` for the full map.

| Module | Responsibility |
|---|---|
| `cli.py` | Argument parsing, config wiring, command dispatch (`detect`/`export`/`calibrate`/`diagnose`) |
| `detection.py` | Kill-detection algorithm; returns `Clip`s, reports progress via a reporter |
| `diagnose.py` | Checks the HUD constants against footage; reports which stage broke |
| `hud.py` | Resolution-independent banner geometry (anchored top-right, scaled) |
| `environment.py` | Tesseract discovery + readiness checks behind `doctor` |
| `export.py` | Pure EDL planning + rendering (`read_timestamps`, `plan`, `build_edl`, `write_edl`) |
| `reporting.py` | All terminal presentation (banner, panels, progress reporter, result/export views) |
| `video.py` | Clip discovery, metadata probing, the interactive picker (`pick`) |
| `calibration.py` | OpenCV region / trigger-pixel calibration helpers |
| `config.py` | Layered TOML config (`--config`, `--write-config`) |
| `traits.py` | Tri-state per-kill facts (`real-player`), their probes, and the clip filters |
| `traitcheck.py` | Samples footage to verify a trait's accuracy before you trust it |
| `timecode.py` | Pure time/timecode/frame-rate math (well unit-tested) |
| `models.py` | `Clip` dataclass shared across the pipeline |
| `constants.py` | Tunables: region, trigger pixels, thresholds, header matching, clips dir |
| `errors.py` | `KillcutterError` hierarchy the CLI catches and prints tidily |
| `ui/` | Zero-dependency ANSI toolkit: `ansi`, `layout`, `progress`, `selector`, `keys` |

Tests are in `tests/` (pytest); `timecode`, `export`, `config`, the selector
state-machine and the detection gates are covered without needing a video file.

## Detection approach

CoD shows an **"ENEMY DOWNED"** banner top-right on a kill. OCR on every frame is too
slow, so each sampled frame is gated by two cheap pixel checks, and only frames that
pass get OCR'd. **The OCR'd header must then read "ENEMY DOWNED"** — that check is not
optional: `TEAMMATE DOWN` uses the same slot, the same icon and the same accent colour,
so the pixel gate cannot reject it.

- Constants live in `killcutter/constants.py`: `DEFAULT_REGION = (1598, 186, 189, 45)`,
  trigger pixels white `(1581, 195)` (banner icon) / accent `(1506, 208)` (left bar).
- **The accent bar's hue is deliberately not checked.** It was red until the Sept 2026
  HUD restyle and is yellow now; other notifications use red and orange in the same
  slot. Hue says nothing about what kind of banner it is — only the header does.
- The white pixel does most of the filtering: it is bright only for a kill banner, and
  dark or tinted for pickups, contracts and killstreak notifications.
- Banners stack downward in 95px slots, newest on top. Every kill hits slot 1 first, so
  scanning slot 1 alone catches them all.
- A banner lingers ~4s, which **outlives the 3s cooldown**, so the same one can be read
  twice. A re-read is only counted as a new kill if the banner dropped in between or a
  different player is on it (`_same_player`, which folds OCR-confusable characters —
  OCR rarely spells a name the same way twice: "Antho" / "Amtho").
- Detection time is corrected back to the kill itself (`_notice_lag`): the banner
  sweeps in before it reaches the trigger pixel (~0.3s) and we only sample every
  `1/rate` seconds (~0.25s at the default rate), so raw detection runs ~0.55s late.
  Uncorrected, `--offset 5` produced only ~4.45s of lead-in. Measured against
  banner onset at 60fps: mean error went +0.56s → +0.01s.
- Kills within `--merge-gap` seconds merge into one clip.
- Timing uses container timestamps (`CAP_PROP_POS_MSEC`), not frame÷fps, so VFR OBS captures don't drift.
- Sampling walks the file sequentially with `grab()`/`retrieve()` rather than seeking per
  sample — seeking forces a keyframe re-decode each time and measured ~3x slower.
- **The scan is decode-bound and already near the floor.** Measured: pure `grab()` over a
  240s span takes 13.35s; the full pipeline at `--rate 2` takes 15.05s — 12% above the
  floor. Raising `--rate` is therefore nearly free (rate 4 costs +8%) while halving the
  sampling jitter, which is why the default is 4. **Do not add multiprocessing**: OpenCV
  already saturates the cores decoding, and chunking across processes measured *slower*
  (1 worker 46.9s vs 10 workers 57.1s on 20 cores).
- Banner geometry comes from `hud.for_size(width, height)`, anchored to the top-right and
  scaled by height, so non-1080p footage works. At 1920x1080 it resolves to exactly the
  constants. An explicit `--region` is taken literally and never rescaled.
- `detect()` returns `(clips, completed)`. Ctrl-C sets `completed=False` and keeps the
  clips found so far; `timestamps.txt` is written atomically via a temp file + rename.

## Key flags (`detect`)

| Flag | Default | Effect |
|---|---|---|
| `--offset` / `--end-offset` | `5` / `5` | Seconds before / after the kill for the clip window |
| `--merge-gap` | `10` | Kills within this gap merge into one clip |
| `--cooldown` | `3` | Min seconds between detections |
| `--rate` | `4` | Frame samples per second |
| `--region X Y W H` | — | Override the scan region |
| `--preview` | off | Show the scan region + OCR live (tune a new clip first) |
| `--dry-run` | off | Print detected clips without writing `timestamps.txt` |
| `--no-export` | off | Stop after `timestamps.txt`; don't auto-run the exporter |
| `--require TRAIT` / `--exclude TRAIT` | — | Keep / drop clips by trait, e.g. `--exclude bot` (repeatable; also on `export`) |
| `--drop-unknown` | off | Also drop clips whose trait could not be determined |
| `--no-traits` | off | Skip trait probing entirely |

Global flags (any command): `--config PATH`, `--write-config [PATH]`, `--no-color`, `--version`.

## Traits (sorting kills)

A **trait** is one tri-state fact about a kill — `True`, `False`, or `None` for
"the evidence wasn't on screen". Detection records every registered trait on every
clip, writes them into `timestamps.txt` as a `[real-player=yes]` suffix, and
`--require` / `--exclude` filter on them. Because the traits are stored,
`export --exclude bot` re-filters an existing `timestamps.txt` without rescanning.

**Unknown is never treated as false.** By default a clip whose trait could not be
determined is kept, so a filter can't silently cost you a highlight; `--drop-unknown`
opts into the strict reading. Adding a trait means registering one `Trait` in
`traits.py`; nothing else in the pipeline needs to know it exists.

### `real-player` (negate with `bot`)

CoD suffixes a real account's name with `#<Activision id>`; bots have a bare name.

- **That suffix is not on the ENEMY DOWNED banner** — only on the bottom-centre
  **ELIMINATED:** line, which is a separate region (`ELIMINATED_REGION`, resolved
  per-resolution by `hud.for_size`). It scales from the left, not the right edge,
  because it sits near screen centre rather than against an edge.
- **OCR cannot read the `#`.** Tesseract returns it as `s` on real footage
  (`Twitch ZenXe#1028757` → `Twitch ZenxXes 1028757`) on every PSM tried, which is
  exactly the error that would make the feature useless. The glyph is found
  geometrically instead.
- What makes that reliable is the colour: the victim's name is saturated red while
  `ELIMINATED:` beside it is white, so `name_mask` isolates precisely the name and
  its suffix and rejects the whole game world behind it — measured on real frames
  with zero background bleed.
- On that clean binary the `#` must be confirmed **twice**: a template match
  locates it, and `looks_like_hash` confirms the topology — two near-full-width
  crossbars crossing two full-height stems, with ink overhanging both. `E` and `8`
  have three bars, `H` has one, `=` has no stems. **Both checks are load-bearing.**
  A merged digit pair in real footage passes `looks_like_hash` (only the template
  rejects it); an OpenCV vector `#` passes the template poorly (only at a threshold
  so low the false positives explode). Neither alone works — measured, structural-only
  gave 84% false positives, template-only gave 34% recall off-font.
- **The template scale is measured from the text, not the frame.** `hud.scale`
  is only a guess — the game has its own HUD-size slider — and
  `_candidate_scales` reads the font size off the mask's text band, then searches a
  few steps either side. This is the single biggest reliability win here: with one
  template sized from the frame alone, a 1.2× error in that guess dropped per-frame
  recall from 78% to **9%**. With the search, per-kill accuracy is unchanged across
  a 0.8×–1.45× error.
- **`BAR_FILL` is relative to the glyph's own fullest row, not absolute.** Video
  compression thickens these strokes until the stems alone fill 80% of the glyph
  width, so a fixed 0.8 cutoff merges the crossbar gaps and the whole glyph reads
  as one solid band. Verified: an absolute cutoff passed the PNG and failed the
  same frame re-encoded.
- The ELIMINATED line only appears for the **finishing** blow, so a knock a
  teammate confirms yields a kill banner with no line at all → `None`. Evidence is
  therefore gathered over a `WINDOW_SECONDS` (3s) window after the kill, on every
  sampled frame rather than only triggered ones.
- **`min_votes=2`: one positive frame does not decide a kill.** Because a single
  `True` decides the whole clip, per-frame false positives *compound* over the ~12
  frame window while per-frame misses wash out. Measured: a 2% per-frame false
  positive rate became **17% per kill** under a one-vote rule. Two agreeing frames
  costs no measurable recall. Windows that only yielded one or two decidable frames
  fall back to a single vote so thin evidence is not punished.
- **Do not tune `HASH_MATCH_MIN` on composed strips alone.** They paste clean
  bitmaps and score higher than genuine H.264 footage; doing exactly that once
  pushed the cutoff to 0.65, which the corpus called free and which silently broke
  every real re-encoded frame (they peak near 0.60). Always check a real clip, and
  watch the headroom readout described below.
- The two errors are **not symmetric**: a missed `#` marks a real player as a bot
  and `--exclude bot` throws the highlight away, while a false `#` merely keeps a
  bot clip. Prefer headroom over the last point of false-positive rate.

Measured on strips composed from glyphs cut out of the real screenshots, scored
per kill over a 12-frame window: **96.8% recall, 0% false positives**, invariant
across a 0.8×–1.45× scale error. Probe cost is 0.07ms on an empty strip and 2.7ms
worst case, ~32ms per kill — negligible against a decode-bound scan.

### Verifying a trait

`python -m killcutter traits --video clip.mp4 --dump DIR` samples footage, prints
yes / no / not-on-screen counts, and writes every crop it judged to `DIR` named by
its verdict. A threshold tuned on a couple of screenshots is a guess — check it
against real footage before trusting it.

It also prints the **headroom**: how far the weakest confirmed frame cleared
`HASH_MATCH_MIN`. Under +0.05 it warns, because that is the state in which
slightly worse footage starts reading real players as bots. Compare it against
the *best rejected* score too — a large gap between them (0.59 vs 0.00 on the
test clip) means the discrimination is healthy and only the cutoff placement is
delicate.

`diagnose` also covers this region now: the PIPELINE panel reports how many frames
showed the name line and how many carried a `#`, and flags it when the strip never
appears at all — so a HUD move that breaks bot sorting is caught by the same tool
as a HUD move that breaks detection.

## When detection breaks after a game update

`python -m killcutter diagnose [--start S] [--span S]` samples footage and prints how many
frames passed each stage (white pixel → accent pixel → both → header confirmed), the accent
colour it saw, and every banner header OCR read. It names the likely broken assumption and
exits non-zero. Use it before reaching for `calibrate`.

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
- Trigger pixels / region assume 1920×1080 and the current HUD — run `diagnose`, then
  `calibrate`, if it changes.
- Two kills on the *same* player with no banner gap between them count once (the clip still
  covers both; only the extra name is lost).
- The exporter authors timecode at the media's **real** rate (`timecode.resolve_fps`)
  and never converts between the integer and NTSC families. Rewriting a true 60.000
  as 59.94 — which it used to do unconditionally — makes every timecode 0.1% short:
  cuts land 3.6s early at 1h, 5.4s at 1h30, 7.2s at 2h, so a 10s highlight can end
  before its own kill. `export.plan` cross-checks the authored rate against
  `frames / duration` and warns. The Premiere sequence fps **must** match what it prints.
- Timecodes are authored **non-drop**, so the EDL declares `FCM: NON-DROP FRAME`.
  Drop-frame only relabels frames; claiming it while emitting non-drop labels makes
  Premiere read every cut at the wrong frame.
- Future: auto-export individual clips, and dump detected frames to disk for offline review.
