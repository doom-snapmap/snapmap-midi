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
3. A fixed track column on the left. Every MIDI channel, including percussion,
   is one row with its channel number, source program, sound assignment, and
   mute control.
4. A piano-roll surface on the right. Time runs horizontally, pitch vertically,
   notes are colored by channel, and a high-contrast playhead sweeps across the
   complete surface during playback.
5. A compact status/warning strip. Warnings open the conversion inspector in
   context instead of sending the user to another page.

There are no Channels, Drums, Tuning, or Export tabs. Export is a File-menu and
toolbar action. Percussion is not a separate workspace.

## Traditional menus

The menu bar follows desktop conventions rather than rendering every command as
a rounded web button.

- **File**: Import MIDI... (`Ctrl+I`), Reopen MIDI, Export SnapMap... (`Ctrl+E`),
  Exit.
- **Playback**: Play/Pause (`Space`), Return to Start (`Home`).
- **Options**: Conversion Settings... (`Ctrl+,`), Set Up Audio....
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
It never embeds the audio library. The local preview cache may contain all 890
speaker-palette WAVs extracted from the user's own game install.

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

The browser engine schedules cached PCM samples with Web Audio. Python provides
the resolved converted-note manifest and only the samples used by that manifest.
The page uses a look-ahead scheduler so a long song does not create thousands of
live audio nodes at once.

## Piano roll

The piano roll is a rendered visualization optimized for thousands of notes.
A canvas is preferred over one DOM element per note.

- Horizontal axis: milliseconds across the whole song, with adaptive time/bar
  grid marks.
- Vertical axis: the occupied MIDI pitch range with a small margin and C-note
  labels.
- Notes: original pitch and duration, colored consistently by MIDI channel.
- Muted tracks: hidden or heavily dimmed.
- Selected track: full opacity; other tracks remain visible at lower opacity.
- Playhead: accent-colored vertical stroke, always above notes and grid.

The first implementation fits the complete song and occupied pitch range. Zoom
and note editing are outside this redesign.

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

## Import and audio setup

Import never presents a tuning wizard. The existing workspace remains visible
with a progress state while the file is analyzed, then tracks and notes appear.

If the local audio cache is absent, conversion and export still work. Playback
shows a non-blocking setup banner and **Set Up Audio...** action. Extracting game
audio may show progress, but it is not a tuning decision and does not prevent
the song from opening.

## Visual language

The shell continues to use Snapmap Plus's exact light/dark tokens, Segoe UI and
Consolas typography, status bar, toast treatment, native frame, and window
controls. The workstation layout and conventional menu behavior are new; the
product identity is not.

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
| contextual warning + compact engine status                               |
+--------------------------------------------------------------------------+
```

The signature element is the full-height moving playhead: it turns the note
surface itself into the transport and makes this specifically a music
workstation. That is the one aesthetic risk. The self-critique removed tab
accents, dashboard cards, decorative gradients, and unrelated motion because
none encodes a fact about a MIDI-to-SnapMap conversion. Channel colors remain
only because they identify note ownership.
