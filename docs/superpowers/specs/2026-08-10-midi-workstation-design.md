# snapmap-midi workstation redesign

Status: approved direction, 2026-08-10.

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
   assignment, and mute control. Its divider trades width with the roll and
   preserves the chosen size across sessions.
4. A piano-roll surface on the right. Time runs horizontally, pitch vertically,
   notes are colored by channel, and a high-contrast playhead sweeps across the
   complete surface during playback.
5. A compact bottom control plane above the status bar. Notifications opens a
   dedicated inspector; Grid, Time signature, and Zoom control the roll view.

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

## Track sound assignment

The current product exposes only twelve pitched families to melodic channels
and seventy percussion choices to drum keys. The workstation exposes the full
shipped SnapMap speaker palette in one grouped picker on every channel.

Each selection has one of three meanings:

- **Automatic** preserves General MIDI family selection, or the General MIDI
  percussion map for an automatically detected percussion channel.
- **Pitched instrument set** resolves every MIDI pitch to the closest available
  sound in that palette category.
- **Exact sound** triggers that same SnapMap sound for every note on the channel.

The picker groups choices for navigation, but grouping never removes a sound.
Percussion may still use its automatic per-key map; an advanced per-key override
may remain available through the track inspector, never through a separate tab.

`rawmap.json` contains references only to sounds the arrangement actually uses.
It never embeds the audio library. Preview indexes the user's installed retail
banks and decodes only the sounds selected by the current arrangement.

## Full-song preview and transport

There is exactly one Play/Pause control. It schedules the converted note events,
not the source computer's General MIDI synthesizer, so preview and export answer
the same sound-assignment question.

Playback requirements:

- Pressing Play begins at the current position.
- Pressing the same control pauses without resetting position.
- Pressing Home returns to zero.
- The transport scrubber and the playhead are synchronized.
- Clicking or dragging anywhere across the piano roll moves the playhead and
  playback position. Dragging while playing continues from the new position.
- The playhead is one continuous vertical line spanning the ruler and complete
  note surface.
- Changing a channel assignment invalidates the old preview manifest and the
  next playback uses the new conversion.
- Playback ends at the song duration and returns to the paused state at zero.

The browser engine schedules current-song PCM samples with Web Audio. Python
provides the resolved converted-note manifest and only the samples it uses.
The page uses a look-ahead scheduler so a long song does not create thousands of
live audio nodes at once.

## Piano roll

The piano roll is a rendered visualization optimized for thousands of notes.
A canvas is preferred over one DOM element per note.

- Horizontal axis: the complete song behind a native scrollbar. The ruler and
  grid use the source tempo map to place note-value subdivisions and measures.
- Vertical axis: all 128 MIDI pitches behind a native scrollbar, with a fixed
  piano-key ruler and every note named from C-1 through G9.
- Notes: original pitch and duration, colored consistently by MIDI channel,
  with 4 px rounded corners and high-DPI Segoe UI labels when space permits.
- Note hover: only the note rectangle under the pointer receives a restrained
  bright glow. Hover remains available during playback, pause, and seeking;
  the playhead does not change note colors.
- Muted tracks: hidden or heavily dimmed.
- Selected track: full opacity; other tracks remain visible at lower opacity.
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
At inspection sizes, notes carry pitch names. The piano roll remains read-only;
note editing is outside this product.

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
tools. Its left control is an icon-only Notifications button with the same
31-by-29 pixel bordered treatment as global Play/Pause. A warning-colored
triangle and compact count badge communicate state without competing with the
song surface.

Notifications opens a nonblocking right-side inspector in the same position as
Conversion; opening one closes the other. The inspector shows the complete
warning array, one message per row, with the channel list's faint separators.
It has an explicit close button, toggles from its control-plane button, closes
with `Escape`, and shows a quiet empty state when the current conversion has no
warnings. The audio-source banner remains separate because it reports preview
availability rather than a conversion condition.

Grid, Time signature, and Zoom sit at the control plane's right edge. Grid
offers whole through thirty-second-note visual divisions. Time signature starts
from the source file and changes numbered bar grouping as a visual override.
Neither control alters playback or source events. Zoom changes both axes so the
keys, measure ruler, grid, notes, playhead, and scrollbar travel remain aligned.

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
local Lucide sprite supplies only the eight symbols used by the window,
transport, notifications, and inspectors at one normalized size; it introduces
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
| full palette per row        | drag anywhere in time to seek              |
+-----------------------------+--------------------------------------------+
| [notifications]        Grid [1/8]  Time signature [4/4]  Zoom [---] 100%   |
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
