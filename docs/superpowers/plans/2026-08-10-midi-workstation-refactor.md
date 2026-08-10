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
  roll, bottom control plane, status bar, and empty state.
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
- [x] Open the inspector from the Conversion toolbar control and Options menu
  without navigating away from the workstation.

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

## 7. Add the notifications control plane

- [x] Remove the collapsed warning sentence above the status bar.
- [x] Reserve that row as a persistent toolbar for workstation-level controls.
- [x] Add the warning-shaped Notifications button using the Play/Pause control
  geometry and a compact warning-count badge.
- [x] Add a mutually exclusive right-side Notifications inspector.
- [x] Render every warning in full, separated by the channel list's faint row
  borders, with close, toggle, and `Escape` behavior.

## 8. Build the navigable musical note surface

- [x] Replace song-derived pitch cropping with a fixed 0-127 MIDI surface and
  label every piano-key row.
- [x] Add synchronized fixed pitch and measure rulers around native horizontal
  and vertical scrollbars.
- [x] Carry the MIDI tempo and time-signature map into the preview manifest.
- [x] Add visual whole through thirty-second-note Grid choices and common meter
  overrides with stronger numbered measure lines.
- [x] Add an exponential 100-6400% time Zoom control with capped 3x pitch
  scaling that preserves viewport context.
- [x] Keep the sweeping playhead proportional at every zoom and advance the
  horizontal viewport automatically during playback.
- [x] Update asset/session tests and all user, contributor, architecture, and
  design documentation, then run the complete validation suite.

## 9. Correct deep zoom and playback following

- [x] Replace the shallow 4x linear limit with a 64x exponential horizontal
  range while keeping piano-key height usable.
- [x] Route notes, seeking, and the playhead through one absolute-time screen
  transform.
- [x] Replace edge-triggered page jumps with continuous left-third playback
  following so the sounding passage remains under the sweeper.
- [x] Re-run focused and complete validation.

## 10. Finish the piano and scrollbar rulers

- [x] Render black keys across the complete 72px pitch ruler without exposing
  an unintended panel-colored strip.
- [x] Extend the time-ruler divider across the vertical scrollbar gutter while
  keeping the scrollbar itself inside the note-surface row.
- [x] Re-run focused and complete validation.

## 11. Complete playhead drag and playback scrollbar states

- [x] Paint the time-ruler boundary exactly once across the canvas and scrollbar
  gutter so its thickness cannot change at the corner.
- [x] Auto-pan horizontally while a captured playhead drag remains inside either
  edge zone.
- [x] Cover the native horizontal scrollbar with a noninteractive disabled track
  during playback without blocking the vertical pitch scrollbar.
- [x] Re-run focused and complete validation.

## 12. Anchor zoom and retire deprecated dialogs

- [x] Preserve the blue playhead's on-screen position while horizontal zoom
  expands or contracts the piano roll.
- [x] Center the playhead before zooming when its song position is outside the
  visible passage.
- [x] Replace pywebview's deprecated open-file and folder-dialog constants with
  the current `FileDialog` enum.
- [x] Re-run focused and complete validation.

## 13. Refine the workstation surface and pane layout

- [x] Match Snapmap Plus's 8 px primary-panel radius on the complete shared
  Channels and piano-roll workspace.
- [x] Render note blocks with 4 px rounded corners and sharper, full-contrast,
  high-DPI Segoe UI labels.
- [x] Add a persistent pointer- and keyboard-adjustable divider with dynamic
  minimum widths for the channel list and piano roll.
- [x] Replace text glyphs and bespoke control drawings with a bundled eight-icon
  Lucide SVG subset and ship its license without a runtime or network fetch.
- [x] Extend asset coverage and re-run focused and complete validation.

## 14. Synchronize note emphasis with playback and inspection

- [x] Derive every active-note state from the same output-timestamp position
  used to draw the blue playhead.
- [x] Brighten all simultaneous and overlapping events under the playhead with
  a restrained channel-colored glow.
- [x] Reuse visible note geometry for paused pointer hover while suppressing
  hover during playback and seek drags.
- [x] Add source-contract coverage and update user, capability, architecture,
  design, and implementation-plan documentation.
- [x] Re-run focused and complete validation.

## 15. Keep pitch scrolling responsive during playback

- [x] Make the playback animation the sole canvas-paint owner while audio is
  running so auto-follow scroll events cannot enqueue a duplicate frame.
- [x] Cancel a pending idle draw when a direct playback or resize draw already
  provides the current viewport.
- [x] Forward vertical wheel deltas through the disabled horizontal-scrollbar
  cover without restoring horizontal click or drag behavior.
- [x] Add regression coverage and update user, capability, architecture,
  design, and implementation-plan documentation.
- [x] Bump the package version to 0.3.2 and run complete validation.

Release target: `v0.3.2`, created only after the pushed `main` commit passes CI.
