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
- [x] Validate curated exact choices directly and other exact choices as bounded DOOM Play event identifiers.
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
- [x] Add a bounded bridge call that returns WAV data only for sounds used by
  the current manifest.
- [x] Test stale/unknown requests, unavailable audio sources, and manifest/export
  agreement.

## 3. Replace the tabbed shell

- [x] Replace the button-heavy header and tab strip with conventional File,
  Playback, Options, and View menus and keyboard shortcuts.
- [x] Keep the Snapmap Plus token block, native frame, window controls, and
  theme behavior unchanged.
- [x] Build the one-screen workspace: transport, unified track column, piano
  roll, bottom control plane, status bar, and empty state.
- [x] Remove every per-channel and per-drum Play button.
- [x] Put Import, Export, audio-source refresh, and conversion settings in
  traditional menus and a minimal transport toolbar.

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
- [x] Replace text glyphs and bespoke control drawings with a purpose-trimmed
  Lucide SVG subset and ship its license without a runtime or network fetch.
- [x] Extend asset coverage and re-run focused and complete validation.

## 14. Keep note emphasis available for inspection

- [x] Brighten only the note under the pointer with a restrained channel-colored
  glow, independently of the blue playhead.
- [x] Keep hover inspection active during playback, pause, and seek drags.
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

## 16. Virtualize dense piano-roll rendering

- [x] Normalize the preview once into pitch buckets with start-time ordering and
  prefix end-time indexes, then query only visible pitch/time overlaps.
- [x] Split the static roll and rulers from pointer-transparent playhead and hover
  overlays so ordinary playback does not repaint notes, labels, or grid lines.
- [x] Rasterize the full 100% overview within a fixed pixel budget and blit the
  visible vertical slice during wheel scrolling.
- [x] Batch tiny overview notes while preserving rounded blocks and labels at
  inspection sizes.
- [x] Cache theme, tempo, timing-line, ruler, and transport work; cap backing
  canvas density at 2x and bound timing-line sampling by viewport pixels.
- [x] Advance playback following in sections so the static roll changes only
  when the visible time passage changes.
- [x] Keep note glow pointer-only during playback as well as pause.
- [x] Add regression coverage and update user, capability, architecture, design,
  and implementation-plan documentation.
- [x] Bump the package version to 0.3.3 and run complete validation.
- [x] Run focused and complete validation.

Release target: `v0.3.3`, created only after the pushed `main` commit passes CI.

## 17. Read preview audio directly from installed banks

- [x] Reuse one indexed retail-bank source per process and decode only the unique
  sounds selected by the current conversion.
- [x] Prepare missing song samples in one background lane and retain overlapping
  browser buffers when assignments or conversion settings change.
- [x] Remove the UI extraction/setup workflow and replace it with audio-source
  refresh; retain the explicit CLI cache as an offline fallback.
- [x] Keep bank discovery rooted at the retail sound directory so DoomForge banks
  under `mods` cannot override stock palette events or media by hash collision.
- [x] Add provider, fallback, reuse, mod-isolation, bridge, and asset regression
  coverage; update the repository documentation for the new source model.
- [x] Bump the package version to 0.3.4 and run complete validation.

Release target: `v0.3.4`, created only after the pushed `main` commit passes CI.

## 18. Expose the installed full-game sound catalog

- [x] Reverse and parse the generated soundbanksinfo.events catalog for event names,
  Wwise paths, buses, environments, numeric IDs, durations, and loop flags.
- [x] Stream soundbanksinfo.xml as a duration-type overlay so Mixed events are stopped
  like Infinite events instead of leaking an emitter.
- [x] Index language-neutral banks plus one installed localization and resolve the first
  available media source for each event.
- [x] Offer every named Play event while excluding Stop/control records. Mark direct-media
  events as locally previewable and retain engine-only music/state/legacy/DLC events for
  export. The reference retail install has 7,589 choices and 7,353 local previews.
- [x] Keep automatic MIDI and pitched-family mapping on the curated 890-name palette.
  Treat the full catalog as an exact manual channel override. The later
  [pitch/dynamics architecture](2026-08-11-pitch-dynamics-note-inspector-architecture.md)
  may apply root-relative pitch to that one selected event; it does not widen automatic mapping.
- [x] Replace the channel select with a lazy searchable file-explorer modal, organized by
  Wwise folders and paginated to bound live DOM rows.
- [x] Show readable names, exact event strings, paths, buses, loop behavior, durations,
  numeric IDs, preview availability, and per-event audition controls where available.
- [x] Match the SnapMap Plus modal overlay, token, radius, border, and shadow contract;
  extend only the purpose-trimmed local Lucide subset.
- [x] Fall back to the 890-name palette when installed metadata is unavailable and keep
  the optional extract command limited to that offline palette.
- [x] Add synthetic parser, localization, source-fallback, settings, scheduling, bridge,
  asset-contract, and real-install catalog coverage.
- [x] Update README, user, capability, game-data, architecture, contributor, design, and
  implementation-plan documentation.
- [x] Run complete automated validation.
- [x] Receive user acceptance before assigning a release target.

## 19. Add pitch, dynamics, and note expression

- [x] Preserve stable source-note identity and MIDI velocity through parsing.
- [x] Resolve pitched families and arbitrary exact events from a trusted root or explicit
  relative natural-playback reference.
- [x] Use one integer pitch/dB expression model for preview and Timeline export.
- [x] Add sparse per-note pitch/volume overrides and the Note expression inspector.
- [x] Isolate decaying notes that need pitch or gain while retaining the neutral shared path.
- [x] Complete the separate
  [pitch/dynamics architecture plan](2026-08-11-pitch-dynamics-note-inspector-architecture.md).
- [x] Commit and push the implementation after the complete CI matrix passes.

## 20. Add a global volume control

- [x] Place a persisted -60 through +20 dB Volume slider beside Notifications in the bottom
  control plane, with neutral 0 dB as the default.
- [x] Resolve `velocity dB + global dB + note trim dB` once in Python and send the same clamped
  value to browser preview and rawmap export.
- [x] Advance the sidecar to settings version 3 and migrate version 1 and 2 files losslessly.
- [x] Add expression, settings, compile, preview-manifest, and UI asset-contract coverage.
- [x] Bump the package version to 0.3.5 and update repository-wide documentation.
- [x] Run complete lint, JavaScript, test, package-build, and diff validation.

Release target: `v0.3.5`, created only after the pushed `main` commit passes CI.
