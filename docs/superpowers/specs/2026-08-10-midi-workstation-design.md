# snapmap-midi workstation redesign

Status: implemented 2026-08-10; pitch, dynamics, and channel-mix corrections implemented 2026-08-11.

The expression amendment is specified in
[`../plans/2026-08-11-pitch-dynamics-note-inspector-architecture.md`](../plans/2026-08-11-pitch-dynamics-note-inspector-architecture.md)
and supersedes this document's original fixed-pitch exact-event and no-per-note-control rules.
The current behavior is defined by
[Pitch Model and Channel Mix Correction](../plans/2026-08-11-pitch-model-and-channel-mix-correction.md).
It supersedes the amendment's target-note movement and rootless auto-follow rules.


## Product statement

snapmap-midi is a compact MIDI-to-SnapMap workstation. It is not a tabbed
settings form and it is not a MIDI composition editor. A user opens an existing
MIDI file, sees the converted arrangement on a piano roll, assigns any usable
DOOM (2016) SnapMap speaker sound to each channel, previews the whole converted
song, seeks through it, and exports the current conversion as `rawmap.json`.

The original MIDI remains unchanged. Note blocks are a visual and transport
surface, not draggable composition data.

## One-screen layout

The application has one persistent workspace:

1. A traditional application menu bar with **File**, **Playback**, **Options**,
   and **View** menus. Menu items have familiar labels, ellipses where a dialog
   follows, and visible keyboard shortcuts.
2. A transport strip with one global Play/Pause button, current time, total
   time, and a scrubber.
3. A resizable track column on the left. Every MIDI channel, including
   percussion, is one row with its channel number, source program, sound
   assignment, inline stateful mute/solo icons, and click-to-focus editing state. Its divider trades width with the roll and
   preserves the chosen size across sessions.
4. A piano-roll surface on the right. Time runs horizontally, pitch vertically,
   notes are colored by channel, and a high-contrast playhead sweeps across the
   complete surface during playback.
5. A compact bottom control plane above the status bar. Notifications opens a
   dedicated inspector; Volume offsets the complete arrangement; Grid, Time
   signature, and Zoom control the roll view.

There are no Channels, Drums, Tuning, or Export tabs. Export is a File-menu and
toolbar action. Percussion is not a separate workspace.

## Traditional menus

The menu bar follows desktop conventions rather than rendering every command as
a rounded web button.

- **File**: Import MIDI... (`Ctrl+I`), Reopen MIDI, Export SnapMap... (`Ctrl+E`),
  Exit.
- **Playback**: Play/Pause (`Space`), Return to Start (`Home`).
- **Options**: Conversion Settings... (`Ctrl+,`), Refresh Audio Source.
- **View**: Light Theme, Dark Theme.

Only one menu may be open. Clicking outside it or pressing Escape closes it.
Disabled commands remain visible when no song is open so the menu does not
rearrange itself.

## Track sound assignment and full-game browser

Every channel opens the same modal assignment browser. The three meanings remain:

- **Automatic** preserves General MIDI family selection or the General MIDI percussion map.
- **Pitched instrument set** resolves each MIDI pitch through one of the 12 curated
  pitch-capable categories.
- **Exact sound** triggers one selected DOOM Play event for every note on the channel.

The exact-event layer is the installed game's full Play-event catalog, not only the shipped
SnapMap palette. It is loaded lazily from soundbanksinfo.events and augmented with XML duration
types. The reference retail install declares 7,589 Play events; 7,353 resolve through the
indexed retail banks to standalone media for local audition, while engine-only composites stay
selectable for export. Automatic mapping remains on the 890-name curated palette because the
rest of the game catalog has no dependable instrument or pitch model.

The modal follows the SnapMap Plus contract exactly: a fixed rgba(0,0,0,0.45) background
overlay, panel and border tokens, 10 px radius, and the shared 0 12px 34px shadow. The dialog
contains:

- a global search field matching readable names, exact event strings, folders, buses,
  environments, and numeric Wwise IDs;
- a left file tree derived from Wwise authoring paths, with Automatic and Pitched instruments
  as first-class choices above the installed folders;
- paginated exact-event rows with readable title, event string, path, bus, duration, loop
  behavior, preview availability, numeric ID, and a one-event audition control where available;
- Cancel and Use sound actions with the current choice summarized in the footer.

The UI humanizes installed event strings and overlays the 16 shipped curated ear labels; it
does not pretend to ship hand labels for thousands of game events. Numeric IDs are search and
diagnostic metadata. Export writes the exact Play string.

The result list never materializes the complete catalog at once. A bounded page keeps the DOM
small while search and the tree filter the in-memory metadata. Escape, the close control, or
the darkened backdrop cancels the modal.

An exact choice retains one Play event string across the channel. Curated or conservatively
detected roots enable MIDI-following semitone modifiers. Rejected events preserve natural
playback; the channel midpoint is retained only as an optional relative reference, and Follow
MIDI note is an explicit opt-in. Infinite and Mixed events receive paired stops so an infinite
branch cannot leak a speaker emitter.
Expressive one-shots use duration-reserved
isolated voices while neutral one-shots retain shared layering.

rawmap export contains references only to events used by the arrangement. It never embeds the
audio library. Preview reads the user's installed retail banks and decodes only an auditioned
event or sounds selected by the current arrangement.

## Full-song preview and transport

There is exactly one Play/Pause control. It schedules the converted note events,
not the source computer's General MIDI synthesizer, so preview and export answer
the same sound-assignment question.

Playback requirements:

- Pressing Play begins at the current position.
- Pressing the same control pauses without resetting position.
- Pressing Home returns to zero.
- The transport scrubber and the playhead are synchronized.
- Clicking a note pauses and opens Note expression. Clicking or dragging empty roll space
  moves the playhead; a seek begun during playback resumes from the new position.
- The playhead is one continuous vertical line spanning the ruler and complete
  note surface.
- Changing a channel assignment invalidates the old preview manifest and the
  next playback uses the new conversion.
- Playback ends at the song duration and returns to the paused state at zero.

The browser engine schedules current-song PCM samples with Web Audio. Python
provides the resolved converted-note manifest and only the samples it uses.
The page uses a look-ahead scheduler so a long song does not create thousands of
The manifest carries final dB after velocity-derived or user-set note volume, global volume, and the engine
clamp. JavaScript applies that resolved value and does not maintain a second loudness model.

live audio nodes at once.

## Piano roll

The piano roll is a rendered visualization optimized for thousands of notes.
A canvas is preferred over one DOM element per note.

- Horizontal axis: the complete song behind a native scrollbar. The ruler and
  grid use the source tempo map to place note-value subdivisions and measures.
- Vertical axis: all 128 MIDI pitches behind a native scrollbar, with a fixed
  piano-key ruler and every note named from C-1 through G9.
- Notes: imported MIDI pitch and source duration, colored consistently by MIDI channel, with
  4 px rounded corners and high-DPI Segoe UI labels when space permits. Pitch offset changes
  playback only and never moves a block.
- Note hover: only the note rectangle under the pointer receives a restrained
  bright glow. Hover remains available during playback, pause, and seeking;
  the playhead does not change note colors.
- Muted or solo-excluded tracks: visible in neutral gray but absent from preview and export.
- Focused track: editable at full opacity; other tracks remain visible but are not hit-testable.
- Playhead: accent-colored vertical stroke, always above notes and grid.
- Playback scrolling: automatic horizontal following owns time navigation,
  while vertical wheel navigation remains live across the full roll, including
  over the disabled horizontal scrollbar. The line sweeps across each visible
  passage and advances the viewport after crossing its leading threshold.

One exponential slider expands the time axis from 100% to 6400%, while pitch
rows grow to a capped 3x. The different caps allow close horizontal inspection
without turning each key into the height of the viewport. Zoom preserves the
blue playhead's screen position so the notes, grid, and ruler expand around the
current song position. During playback, the playhead sweeps through the visible
passage; following returns it near the left third only when the viewport advances.
At inspection sizes, notes carry pitch names. Source composition remains read-only:
notes cannot be created, deleted, moved in time, or resized. Clicking a note may edit only its
playback-only SnapMap pitch/volume expression in the right-side inspector. Clicking a channel
opens a separate inspector for settings shared by every note on that channel, beginning with its
Follow MIDI note mode.

The implementation separates the static roll from the playhead and hover overlays.
Whole-song overview uses a bounded full-height raster cache for cheap vertical
scrolling; inspection zoom queries pitch/time buckets and paints only overlapping
events. Tiny overview notes are batched without labels, timing geometry and theme
colors are cached, and backing canvases cap at 2x display density. These are visual
levels of detail only and never change note pitch, timing, channel, or export.

## Conversion settings inspector

Conversion settings are advanced engine constraints, not musical tuning. They
do not interrupt import. The MIDI opens and converts with safe defaults first;
warnings explain when a setting deserves attention.

The inspector slides in from the right over the same workspace:

- **Maximum speakers**: range slider plus exact integer field, 1-128.
- **Maximum polyphony**: an Enable limit checkbox, then range slider plus exact
  integer field. Disabled means unlimited.
- **Release**: range slider plus seconds field. **Hard stop** is a separate
  checkbox and disables the release control while active.
- **Sustain limit**: Enable checkbox, duration slider, and exact millisecond
  field. Disabled preserves written note lengths.
- **Bass duration limit**: Enable checkbox, duration slider, exact millisecond
  field, and a MIDI-note threshold shown with its note name.
- **Decaying behavior**: one row per sound category used by the current
  arrangement, with a Fire and forget checkbox and an optional per-category
  duration cap. It cannot be represented honestly by a slider.

Every control applies immediately after validation and refreshes statistics,
warnings, note visibility where thinning applies, and the next preview. A
**Restore defaults** action resets the whole conversion section.

## Bottom control plane and notifications

The warning sentence is not printed across the bottom of the workspace. That
space is a persistent control plane for workstation-level quality-of-life
tools. Its left edge starts with an icon-only Notifications button with the same
31-by-29 pixel bordered treatment as global Play/Pause. A warning-colored
triangle and compact count badge communicate state without competing with the
song surface. The adjacent Volume slider is a persisted -60 through +20 dB global
offset, defaults to 0 dB, and affects both full-song preview and rawmap export.

Notifications opens a nonblocking right-side inspector in the same position as Conversion,
Channel settings, and Note expression; opening one closes the others. The inspector shows the
complete warning array, one message per row, with the channel list's faint separators.
It has an explicit close button, toggles from its control-plane button, closes
with `Escape`, and shows a quiet empty state when the current conversion has no
warnings. The audio-source banner remains separate because it reports preview
availability rather than a conversion condition.

Grid, Time signature, and Zoom sit at the control plane's right edge. Grid
offers whole through thirty-second-note visual divisions. Time signature starts
from the source file and changes numbered bar grouping as a visual override.
Those view controls do not alter playback or source events. Zoom changes both
axes so the keys, measure ruler, grid, notes, playhead, and scrollbar travel
remain aligned.

## Import and audio discovery

Import never presents a tuning wizard. The existing workspace remains visible
with a progress state while the file is analyzed, then tracks and notes appear.

The workstation discovers and indexes an installed game's retail banks without
a setup step, then prepares only the unique samples used by the imported song.
A valid offline cache is a fallback. If neither source is available, conversion
and export still work and a non-blocking banner reports preview as unavailable.

## Visual language

The shell continues to use Snapmap Plus's exact light/dark tokens, Segoe UI and
Consolas typography, status bar, toast treatment, native frame, and window
controls. The shared workspace uses Snapmap Plus's 8 px panel radius. A curated
local Lucide sprite supplies only the symbols used by the window, transport,
channel mixer, notifications, inspectors, and sound browser at one normalized size; it introduces
no network or runtime dependency. The workstation layout and conventional menu
behavior are new; the product identity is not.

Motion is limited to the playhead, drawer, and small state transitions. The
reduced-motion preference disables decorative transitions but not the playhead,
because the playhead carries playback position rather than decoration.

### Frontend-design direction

The concrete subject is a DOOM (2016) SnapMap author translating an existing
MIDI arrangement. The screen's single job is to make the converted song
visible, audible, and assignable before export. It is not a generic dashboard
and not a MIDI composition suite.

The compact token plan is inherited rather than rebranded:

- **Plus canvas** `#eef0f3` / **night canvas** `#191a1d`
- **Plus chrome** `#f7f8fa` / **night chrome** `#232428`
- **work surface** `#ffffff` / **night surface** `#26272b`
- **selection blue** `#2f7ad6` / **night selection** `#4a9eff`
- **primary ink** `#1b1d21` / **night ink** `#e7e8ea`
- **warning brass** `#b58a1f` / **night warning** `#d7a944`

Segoe UI remains the application and control face; Consolas remains the utility
face for time, note names, channel numbers, and statistics. Introducing a new
display face would make this window less like Snapmap Plus, so the deliberately
characterful typography is confined to MIDI's own numeric notation.

```text
+-- desktop menus ----------------------------------------------------------+
| global transport + complete-song scrubber                                |
+-----------------------------+--------------------------------------------+
| unified channel assignments | converted piano roll                       |
| percussion included         | one full-height sweeping playhead          |
| full-game browser per row   | drag anywhere in time to seek              |
+-----------------------------+--------------------------------------------+
| [notifications] Volume [---] 0 dB   Grid [1/8] Time [4/4] Zoom [---] 100% |
+--------------------------------------------------------------------------+
| compact engine status                                                     |
+--------------------------------------------------------------------------+
```

The signature element is the full-height moving playhead: it turns the note
surface itself into the transport and makes this specifically a music
workstation. That is the one aesthetic risk. The self-critique removed tab
accents, dashboard cards, decorative gradients, and unrelated motion because
none encodes a fact about a MIDI-to-SnapMap conversion. Channel colors remain
only because they identify note ownership.
