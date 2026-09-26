# Detection presets

Killcutter treats a game or visual task as a saved recipe, rather than assuming
that every video is a Call of Duty recording.

| Detector | What it finds | Dependencies |
|---|---|---|
| Warzone (built-in) | ENEMY DOWNED banners, player names, and player/bot evidence | Tesseract |
| Text | A literal phrase in a selected region, ignoring case and whitespace | Tesseract |
| Colour | Enough pixels close to a target RGB colour in a selected region | OpenCV only |
| Motion | A changed fraction of a region between samples | OpenCV only |
| Scene change | Large changes between samples, with a separate event for each cut | OpenCV only |
| Audio level | RMS volume above a dBFS threshold in the first audio stream | FFmpeg |

Semantic object recognition and action understanding are not implemented.
Motion measures pixel changes; audio level measures loudness, not sound identity. New games do not automatically inherit Warzone's HUD rules.

## Create a recipe

1. Open **Presets** and click **New preset…**. Choose a sample video.
2. Find a clear example using the timeline, frame-step buttons, or a timestamp
   (seconds, `MM:SS`, or `HH:MM:SS`). Click **Next: set up detection**.
3. Choose what to look for: text, a colour, movement, scene changes, or loud sounds.
4. Draw a detection area directly on the picture, or use the whole frame.
   For colour detection, click **Pick a pixel colour** and click the target colour.
   Audio detection does not need a picture selection.
5. Give the preset a name. For text detection, enter the words to find.
   **Advanced settings** contains optional thresholds and the clip label.
6. Click **Save & use preset**. The active preset name appears above every page
   and in the Recording selector. This is what the next analysis will use.

**Edit preset…** uses the same video-first flow for custom presets.
The sample video opens independently of the recording being analyzed. Going back
lets you choose another frame without losing your selections. Closing setup
without saving leaves the active preset unchanged. The built-in Warzone detector
is ready to use; create a custom preset for your own visual or audio signal.
The tab shows the selected preset and a short summary. Numeric area controls and
optional thresholds belong to the guided editor. **More** contains Rename,
Duplicate, Export preset file, and Delete; **Import** loads a saved preset JSON.

A continuous match produces one event (scene changes are evaluated separately at each sample). It must disappear before another event
can be detected. Cooldown prevents rapid repetitions; merge gap combines nearby
events. Sampling and before/after clip timing use the saved Detection defaults
in Settings. General detectors timestamp the sampled match directly; Warzone's
banner animation compensation only applies to Warzone.

## Persistence and portability

User recipes live in a `presets/` directory beside the active TOML configuration.
They are written atomically as version 1 JSON files. Built-in Warzone cannot be
overwritten. **More → Duplicate** creates a separate copy of a custom preset. **Import** validates a
recipe and assigns a new ID so existing recipes are preserved. **Export** writes
the selected saved recipe (not unsaved editor changes).

Malformed recipes are reported in the library without preventing the app from
starting. Unsupported detector names and schema versions are rejected. Presets
contain data only, never code to execute. The selected recipe ID is remembered
in `[gui] detection_preset`.

Normalized geometry scales with video dimensions. It does not compensate for
letterboxing inside the source, different camera framing, or HUD layout changes.
Warzone retains its specialized right-anchored, resolution-aware geometry.

## Architecture

`presets.Preset` is an immutable recipe. `detection.DetectionSettings.preset`
selects it at the shared detection entry point. `None` preserves the existing
Warzone behavior for terminal callers. `generic_detection` handles text/colour
rules; Warzone continues to use its tuned engine and trait observation windows.

Both engines emit progress, new clips, and merged-clip updates through the same
reporter, so live analysis, cancellation, review, editing and export are shared.
The historical reporter method `kill()` remains a compatibility callback for a
new event. General events carry no player/bot traits. GUI results retain their
recipe snapshot, so switching recipes never reinterprets existing detections.

To add a detector, extend preset validation and dependency/capability declarations,
implement its matching/scan behavior, add the appropriate editor fields, and test
it with representative footage. No changes to the export pipeline are required.
The terminal defaults to Warzone for compatibility. Load any exported recipe with:

```sh
killcutter detect --video recording.mp4 --preset my-preset.json --no-export
```

Warzone trait filters are rejected for general presets rather than silently
misclassifying events. Desktop and terminal use the same detector implementations.
