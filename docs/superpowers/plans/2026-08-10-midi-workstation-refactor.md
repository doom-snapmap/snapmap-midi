# snapmap-midi workstation refactor implementation plan

**Goal:** Replace the tabbed control window with the approved one-screen MIDI
conversion workstation while keeping preview and map export on one sound
resolution path.

**Status:** Implemented. The current checkout is running for user acceptance.

**Source design:**
[`../specs/2026-08-10-midi-workstation-design.md`](../specs/2026-08-10-midi-workstation-design.md)

## 1. Preserve the conversion contract while exposing exact sounds

- [x] Extend channel settings with an optional exact `sound` choice while
  preserving existing `family` sidecars.
- [x] Validate exact choices against all names in the shipped speaker palette.
- [x] Make selection precedence explicit: mute, exact sound, selected pitched
  family, automatic percussion map, automatic General MIDI family.
- [x] Allow a selected pitched family on a percussion channel without requiring
  a separate drums mode.
- [x] Keep rawmap export byte-identical for documents that use no new setting.
- [x] Add settings, parsing, compilation, and compatibility tests.

## 2. Add the workstation data contract

- [x] Add original pitch to resolved note records without breaking existing
  positional construction.
- [x] Produce a piano-roll/preview manifest containing duration, channels,
  resolved notes, used sounds, hard-stop/release behavior, and conversion
  warnings.
- [x] Apply sustain caps, bass caps, polyphony thinning, and voice stealing to
  the preview manifest the same way export does.
- [x] Expand the catalog payload to all 24 categories and all 890 sound names,
  preserving pitched-family metadata and optional ear labels.
- [x] Add a bounded bridge call that returns cached WAV data only for sounds
  used by the current manifest.
- [x] Test stale/unknown requests, missing cache entries, and manifest/export
  agreement.

## 3. Replace the tabbed shell

- [x] Replace the button-heavy header and tab strip with conventional File,
  Playback, Options, and View menus and keyboard shortcuts.
- [x] Keep the Snapmap Plus token block, native frame, window controls, and
  theme behavior unchanged.
- [x] Build the one-screen workspace: transport, unified track column, piano
  roll, warning/status strip, and empty state.
- [x] Remove every per-channel and per-drum Play button.
- [x] Put Import, Export, audio setup, and conversion settings in traditional
  menus and a minimal transport toolbar.

## 4. Implement the piano roll and transport

- [x] Render the converted note manifest on a canvas with time on X, pitch on
  Y, channel colors, pitch labels, and adaptive grid lines.
- [x] Draw a single playhead across the complete canvas and update it with
  `requestAnimationFrame` while playing.
- [x] Seek from the transport range, click, or pointer drag on the note surface.
- [x] Decode only used WAV payloads into Web Audio buffers.
- [x] Schedule notes with a rolling look-ahead, pause/resume without losing
  position, stop old sources on seek, and resume from the dragged position.
- [x] Invalidate loaded audio when assignments or conversion settings change.

## 5. Build the conversion inspector

- [x] Add paired slider/number controls for maximum speakers, enabled maximum
  polyphony, and release.
- [x] Add hard-stop, sustain-limit, and bass-limit toggles with dependent fields.
- [x] Show MIDI note names beside the bass threshold.
- [x] Show decaying/category behavior as categorical rows rather than sliders.
- [x] Add Restore defaults and immediate validated application.
- [x] Open the inspector from warnings and the Options menu without navigating
  away from the workstation.

## 6. Integrate, document, and verify

- [x] Rewrite UI asset contract tests for the one-screen structure and global
  transport.
- [x] Update bridge/session tests for the catalog, exact sounds, and manifest.
- [x] Update README and every document that describes tabs, drum separation,
  per-row previews, tuning, or export.
- [x] Run formatting, lint, JavaScript parsing, focused tests, and the full suite.
- [x] Launch the repository's editable install, visually verify the current
  one-screen shell and theme, and prove real native menubar dragging against the
  live window. The application is left open for user-led acceptance with a
  personal MIDI file: menus, assignments, full-song playback, seeking,
  inspector controls, and export.
