# The MIDI workstation

Run the application with no subcommand:

```bash
snapmap-midi
```

The window is the normal way to choose sounds, hear the converted arrangement, tune the
SnapMap engine limits, and export. `snapmap-midi compile song.mid` remains the headless path
for scripts and for replaying a saved settings file.

The workstation does not edit the source MIDI. It visualizes the notes already in the file
and changes how those notes resolve to DOOM (2016) SnapMap sounds.

## One screen, one song

The application has no Channels, Drums, Tuning, or Export tabs. The persistent screen is:

```text
+--------------------------------------------------------------------------+
| snapmap-midi   File  Playback  Options  View                 _  []  X    |
+--------------------------------------------------------------------------+
| [Play/Pause]  0:00.0  |---------- song position ----------|  Conversion |
+-----------------------------+--------------------------------------------+
| Channels                    | time ruler                                  |
| 01  Piano       [sound] [M] |   == notes ==                               |
| 02  Violin      [sound] [M] |           == notes ==                       |
| 10  Percussion  [sound] [M] | | moving and draggable playhead             |
| ...                         |                                            |
+-----------------------------+--------------------------------------------+
| [notifications] Volume [---] 0 dB   Grid [1/8] Time [4/4] Zoom [---] 100% |
+--------------------------------------------------------------------------+
| status: notes, peak voices, long sustains, song length                    |
+--------------------------------------------------------------------------+
```

All MIDI channels are peers in the left column. Percussion is not sent to a separate
workspace. The right side is the converted piano roll. Source composition remains read-only,
while clicking a note can edit that note's conversion expression.

The shell deliberately matches Snapmap Plus: the same light and dark colors, Segoe UI and
Consolas type, 30 px menu bar, status bar, toast treatment, brand image, window controls,
8 px rounded workspace shell, native resize behavior, and native Windows snapping. Controls
use a bundled, purpose-trimmed Lucide SVG subset at consistent optical sizes; the application
does not download an icon font, contact a CDN, or ship Lucide's full catalog.

## Traditional menus

The menu bar keeps infrequent commands out of the note surface.

| Menu | Commands |
|---|---|
| **File** | Import MIDI, reopen the current file, export the map, exit |
| **Playback** | play or pause the complete song, return to the start |
| **Options** | open Conversion settings, refresh the installed-game audio source |
| **View** | light theme, dark theme, middle-C octave-label convention |

The main shortcuts are `Ctrl+I` to import, `Ctrl+E` to export, `Ctrl+R` to reopen, `Ctrl+,`
for Conversion settings, `Space` to play or pause, and `Home` to return to zero. Press
`Escape` to close an open menu, the sound browser, or the active Conversion, Notifications,
Channel settings, or Note expression inspector.

Drag an unused part of the top menu bar to move the window. The menu labels and window
buttons remain clickable rather than acting as drag handles. The invisible edge grips use
Windows' native resize loop, so Aero Snap and drag-to-maximize still work.

## Importing a MIDI file

Choose **File > Import MIDI...** or press `Ctrl+I`. Import analyzes the file and then fills
the channel list and piano roll. It does not open a tuning wizard and it does not make the
user approve guessed settings before seeing the song.

Safe compiler defaults are applied immediately. If the converted arrangement approaches a
SnapMap engine limit, the warning-colored Notifications control shows a count in the bottom
control plane. Opening it shows every warning without covering the channel list.

Opening another song clears channel sound/root choices, sparse note overrides, and
percussion-key overrides, because channel numbers and note ids in two files do not mean the
same parts. General conversion limits, output location, and optional baseline
remain session preferences. A valid sidecar beside the new MIDI is then applied.

## Control plane and notifications

A persistent control plane sits between the workspace and the status bar. It is reserved
for workstation-level controls, so quality-of-life tools do not shrink the transport or add
tabs. Its left edge starts with the icon-only **Notifications** button, drawn with the same
square button treatment as Play/Pause, followed by the unboxed **Volume** label, slider, and
right-aligned value. **Grid**, **Time signature**, and **Zoom** are grouped on the right as view
controls for the piano roll. Zoom uses the same label-slider-value order, sizing, and spacing as
Volume.

Volume is a global integer dB offset from -60 through +20, with 0 dB as the neutral default.
It is added after the current note and Track Volume levels, before the final SnapMap clamp. It
never rewrites or normalizes either underlying value. The control updates the complete preview
and exported timeline, persists in the settings sidecar, and is disabled until a song is open.

When warnings exist, the button uses the shared warning color and carries their count.
Clicking it opens a nonblocking inspector at the right side of the workstation. Every
warning is shown in full in its own row; faint separators match the channel list. Clicking
the button again, its close button, or `Escape` closes the inspector. With no warnings, the
same inspector reports that the current conversion has none.

Notifications, Conversion, Channel settings, and Note expression share the side-panel position and are
mutually exclusive. Opening the modal sound browser also closes an inspector so the surfaces
never stack. The audio-source banner remains separate because it reports preview availability
rather than a conversion warning.

Grid choices are `1`, `1/2`, `1/4`, `1/8`, `1/16`, and `1/32`. They select the musical note
value used for faint vertical subdivisions in both the piano roll and Track lanes. The marks use
the MIDI file's real tempo map, so they remain aligned when tempo changes. Grid is a view control: changing it does not
quantize, move, or resize a note.

Time signature starts from the source MIDI and offers common simple and compound meters.
It groups the ruler into numbered measures and moves the stronger bar lines. Changing it is
a visual override only; it does not rewrite the file's time-signature events or change
playback timing.

## Channels and the full DOOM sound catalog

Every channel row shows its one-based MIDI channel number, source General MIDI program,
sound assignment, and compact borderless mute and solo icons beside the channel title. The
speaker icon changes to a red muted-speaker icon when active; solo uses the application accent
color. A percussion channel is
labeled in the same list instead of moved to a Drums tab. The assignment control opens a modal
sound browser rather than a native dropdown.

Mute silences that channel. Solo is standard multi-solo: when one or more solo controls are
active, only those channels play and export, and more than one channel may be soloed. Mute wins
when the same channel is both muted and soloed. These choices are conversion state, not edits to
the source MIDI.

The browser has three kinds of choice:

- **Automatic** uses the General MIDI program-to-family mapping. On an automatically
  detected percussion channel it uses the General MIDI percussion map by note number.
- **Pitched instrument set** maps every MIDI pitch to the closest available sound in one of
  the 12 measured pitch-capable SnapMap categories.
- **Exact sound** triggers one selected DOOM event for every note on the channel.

With DOOM installed, the exact-sound view is built lazily from the game's own
soundbanksinfo.events hierarchy. The reference retail installation contains 7,589 Play
events, including weapons, monsters, ambience, voices, UI, music, SnapMap instruments, and
effects; 7,353 resolve to standalone media for local audition. The remaining engine-only
music/state/legacy/DLC events are still valid export choices and stay visible with their
preview limitation marked. Counts can vary with edition and localization. A folder tree
preserves Wwise's authoring organization. Search matches the event string, humanized name,
folder, bus, environment, numeric Wwise ID, and preview availability, and results are
paginated so opening the browser never creates thousands of live rows.

Each result shows a readable title, the exact Play event string, its folder and bus,
one-shot or looping behavior, preview availability, duration, and numeric ID. The Play event
string is what rawmap export writes. The numeric ID is useful for searching and diagnostics
but cannot replace the string in a SnapMap timeline sound call. A speaker button auditions
only that event; it is disabled for engine-only composites and is never another song transport.

The package does not ship thousands of hand-authored labels. It reads all event strings and
folders from the user's installed game, humanizes those names for display, and overlays the
16 curated ear labels shipped for misleading SnapMap palette names. Without an installed
event catalog, the exact-sound browser falls back to all 890 identifiers in the curated
24-category SnapMap palette.

Automatic conversion does not guess among the full event catalog. Most game events have no
instrument identity or chromatic coverage, so widening family selection would turn it into
arbitrary effects. Automatic and Pitched instrument set remain on the curated pitch index;
the full catalog is an explicit manual event override.

Selecting an exact event commits it immediately at natural playback without decoding or analyzing
its media. Analysis is opt-in through **Analyze sound**; manual calibration is opt-in through the
C4 reference and sample-tuning controls. Curated
palette names use their authoritative nominal pitch. Other direct-media events are decoded in
bounded memory, and every available leaf must agree before the event is marked pitchable. A
pitchable exact event keeps the same Play string on every note but receives a root-relative
SnapMap semitone modifier. Its detected natural note retains the measured octave so its audible
result matches the piano roll. Tonal media whose fundamental is ambiguous plays naturally rather
than accepting a false upper partial as a root. Speech, noise, impacts, and variable containers
also play naturally by default. The application never pretends that a grunt, impact, or spoken
line has an acoustic root. The analyzer reports failure honestly and still permits an intentional
manual reference or neutral-C4 pitch-following effect.

Installed Wwise duration metadata independently determines whether the event decays or needs a
paired stop. Mixed events are treated as looping so an infinite branch cannot leak a speaker
emitter. A decaying event that needs pitch or gain still receives an isolated speaker for its
measured tail.

Muted channels and channels excluded by an active solo remain on the piano roll in a restrained
gray treatment, so the score never appears to lose data. They are omitted from preview and
export without forgetting their assignments.

### Track settings and focus

Use a track's settings button to open **Track settings**. Everyday controls remain immediately
visible: **Track type**, **Drum keys** when applicable, **Follow MIDI note**, **Analyze sound**,
**Track transpose**, and **Track Volume**. **Advanced track settings** is collapsed by default and
contains manual sample calibration, Track Glide, Track Voices, Track Polyphony, Track Sustain
Limit, and Track Release. Collapsing this section changes only the presentation; its values still
persist and compile normally.

The first pitch setting is the track-wide **Follow MIDI note** checkbox. Automatic mappings and pitched instrument sets show
it checked and disabled because melodic pitch following is intrinsic to those mappings. Automatic
percussion shows it off and disabled because each MIDI key selects a dedicated drum sound instead.
Every exact event makes the checkbox editable. A trusted acoustic root enables it automatically;
without one, the event starts unchecked and plays unchanged. Enabling it explicitly uses a fixed
neutral C4 operational reference. **Analyze sound** refreshes the acoustic measurement and displays
its note, whole cents, whole MIDI value, and confidence. **Sample root or Follow MIDI reference**
shows the analyzer result or the root derived from tune-by-ear controls; before either exists, its
optional field remains blank rather than claiming an acoustic sample root. It accepts either a whole MIDI value
or a note name (sharps and flats are enharmonic input) as an advanced override for someone who
already knows the acoustic root; the raw detection remains available for comparison. This is a
calibration input: naming a higher natural sample note produces more downward compensation when
matching the same imported MIDI note. The inspector shows the exact semitone/cents correction at
MIDI 60 and the formula `imported MIDI note - natural sample note`, so this inverse compensation is
visible before playback. **Play C4 reference** generates a local 261.63-Hz sine tone for tuning by
ear and continues until **Stop C4 reference** is pressed or Track Settings is closed. It uses no
game asset, does not alter settings, and follows the selected C3/C4 display label while MIDI 60 and
its physical frequency remain fixed. **Track transpose** is the direct audible up/down control and adds -24 through +24
semitones. For a sound the analyzer cannot identify, **Coarse sample tuning** and **Sample tuning fine adjustment** directly
raise or lower the sample against the MIDI-60 reference. Moving either establishes a manual root,
enables Follow MIDI note, and leaves Track transpose free for later musical changes. The effective
readout reaccounts for both controls. None substitutes the channel's first note, range, midpoint, or median.
Per-note exceptions stay in Note expression.

**Clear pitch setup** removes the selected exact sound's analyzer result and any manual sample
calibration, turns off Follow MIDI note, and restores natural (zero root-relative) sample playback.
It intentionally leaves Track transpose and explicit per-note expression values alone, because
those are separate musical choices.

Turning **Follow MIDI note** back on without analyzing creates an internal MIDI-60 reference.
Its displayed octave name follows **View > Octave labels** (C4 by default, or C3 in the alternate
convention). That does not identify the sound as that note: the raw sample is left unchanged at
MIDI 60 and is shifted only by the interval to every other MIDI note. The optional sample-root
field remains blank until analysis or manual calibration supplies an actual root.

Other channels dim and stop accepting note clicks until focus is cleared, which makes dense
arrangements readable without changing what plays or exports. Click the focused row again to
restore all channels at equal emphasis. Closing the inspector leaves focus intact. Channel focus
and the open inspector are transient UI state and are not written to the settings sidecar.

The roll defaults to middle C = C4. **View > Octave labels** may instead show middle C = C3,
matching applications that number octaves one lower. The choice is local display state and
updates piano keys, channel ranges, and inspectors. MIDI numbers and conversion calculations
remain unchanged.

The divider between Channels and the piano roll is draggable in either direction. Moving it
right gives assignments more room; moving it left expands the song surface. Both panes retain
useful responsive minimum widths, and the chosen channel width is restored the next time the
application opens. Focus the divider and use Left/Right Arrow for precise adjustment, Home or
End for either limit, or double-click it to restore the default width.

### Part type and drum keys

**Part type** is `Automatic`, `Drum kit`, or `Melodic instrument`. Automatic reads MIDI
channel 10 as percussion and everything else as an instrument, which is the General MIDI
convention. The other two settings say so explicitly, for the two ordinary files the
convention gets wrong: a kit written to another channel, and a melodic part written to
channel 10.

A part read as a kit lists every percussion key it plays, one row each: the note name, the
General MIDI name for that key, how many times the song hits it, and the sound it plays.
Keys with no sound are called out rather than left silent to be discovered in game — the
shipped table covers 22 of the 47 named General MIDI keys, and a file using the others
plays nothing on them.

Clicking a row opens the sound browser for that key alone. It offers the curated percussion
pool first, then every installed event from the folders the game files itself use for
percussive material — impacts, footsteps, player foley, explosions, gore, the whole
interface branch, SnapMap's own object and gameplay sounds, and the struck instruments
(marimba, brass bells) plus the classic DOOM effects. Weapons, voice, music and ambience
are excluded, as are piano, guitar and horns: those are held notes, and a held note under
every hit is not a kit.

Two rules decide what appears, and both are needed. The folder is the only place the game
says what a sound is *for* — by length alone, a half-second event is as likely to be a
scope chirp as a drum hit. The soundbank's loop flag is the only thing that says whether
firing it as a one-shot is safe: a loop is never told to stop, so it holds its emitter open
until the engine recycles the slot out from under something else. Unknown counts as
looping. Each row leads with the sound's length, because that is what decides whether it
works as a hit — a three-second sample on a sixteenth-note hat leaks nothing, it just piles
up voices and turns to mush.

A hand-edited sidecar may still name any DOOM `Play_` event, including a looping one. The
document cannot check it: confirming a name exists needs the installed game, and settings
validation runs without it. A sound the *palette* knows is checked, so a palette loop or a
pitched palette sound is still refused by name.

**Apply to** decides where the choice is stored:

* **This song** writes `drum_keys` in the settings document, and travels with the song's
  sidecar.
* **Every song** writes your own percussion table, which lives beside the pitch profiles
  under `%LOCALAPPDATA%\snapmap-midi\`. Saving a default also drops this song's own choice
  for that key, so the change is audible immediately rather than stored under an override.

Three tables answer for a key, most specific first: the song's `drum_keys`, then your saved
table, then the shipped one. Each row says which answered. Both editable tables replace
wholesale, and an absent entry means "use the answer underneath" — which is why removal is
expressible at all. The shipped table is never written, so "back to the built-in default"
always has something to go back to.

A channel-level instrument set or exact sound still takes precedence over the percussion
map entirely: it makes the whole part play one sound.

## The piano roll and sweeping playhead

Time runs left to right and MIDI pitch runs bottom to top. The vertical surface is always the
complete MIDI range, note 0 (C-1) through note 127 (G9), rather than a crop derived from the
current song. Every pitch row has a note name in the piano-key column, black keys and rows are
visually distinct, and the axis remains fixed when a channel is muted or retimbred. On first
open, the vertical scrollbar centers the range actually used by the arrangement; every other
pitch remains reachable above or below it.

The time ruler, piano keys, note surface, and native scrollbars are separate synchronized
parts of one viewport. Vertical scrolling moves pitches while the piano keys remain fixed at
the left. Horizontal scrolling moves through the song while the measure ruler remains fixed
at the top. At higher zoom levels, note blocks show their pitch name when there is enough
room. Note blocks use the same 4 px corner language as Snapmap Plus controls. Labels are drawn
at up to 2x display density with high-quality smoothing, geometric text rendering, normal
kerning, and full-contrast Segoe UI text rather than faded canvas glyphs. Capping the backing
canvas at 2x retains crisp text without spending 4x or 9x the pixels on unusually dense displays.

The source MIDI End-of-Track time and the workstation's visible end are separate. If a DAW writes
End-of-Track partway through the final measure, the ruler completes that measure so its remaining
rests are visible. Note blocks still end at their actual note-off; the application never repairs a
short last note by stretching it. A naturally completed transport also leaves already-started
finite one-shots and release fades alone instead of hard-stopping them at the file boundary.
Starting again, pausing, seeking, changing the conversion, or opening another song intentionally
stops the old preview sources.

The control-plane Zoom slider uses a musical, exponential range from a 100% whole-song
overview to 6400% horizontal inspection. Increasing it makes pitch rows and note blocks
taller, spreads the song across substantially more horizontal space, and therefore makes the
playhead travel the correspondingly larger distance at the same musical speed. Pitch height
tops out at 3x so horizontal inspection can continue without reducing the viewport to one or
two enormous keys. Zoom is anchored to the blue playhead: its on-screen position stays fixed
while the notes, grid, and ruler expand or contract around the current song position. If the
playhead is outside the visible passage, zoom brings that position to the center first.

The piano roll is not a composition editor. Notes cannot be created, deleted, moved in time,
or resized; those edits belong in the MIDI program that authored the source file. Clicking a
note edits only its conversion expression, described below.

One accent-colored playhead spans the ruler and visible note surface. During playback it
sweeps across a zoomed passage. When it reaches the following threshold, the time viewport
advances and places the playhead back near the first third, then the line resumes sweeping.
This section-based following avoids repainting the whole static song surface for every audio
frame. The line still uses Web Audio's output timestamp and the same millisecond-to-screen
transform as seeking, so its position stays synchronized with what is audible.

Note color is independent of playback. The single note block under the pointer uses a restrained
glow while the song is playing or paused, and remains highlighted during a seek drag; the blue
line does not light notes as it crosses them. To seek:

- drag the transport scrubber;
- click or drag empty space in the piano roll; or
- drag the playhead across the piano roll.

Seeking while the song is playing pauses scheduling during the drag and resumes from the new
position when released. Dragging the playhead into either horizontal edge continuously pans
the timeline in that direction, so a seek is not limited to the currently visible passage.
`Home` returns to the beginning.

While the song is playing, the bottom horizontal scrollbar is covered by a distinct disabled
track: it does not highlight, click, or drag while automatic playback following owns the time
viewport. The right vertical scrollbar stays enabled because pitch navigation does not
conflict with playback following. The mouse wheel continues to move vertically even when its
pointer is over the disabled horizontal track. Native scroll events are coalesced into one queued
paint, keeping pitch navigation responsive in dense arrangements. The static grid and notes are
separate from the animated playhead and hover layers. At whole-song overview the static surface
is rasterized once within a fixed memory budget, so vertical scrolling copies only the visible
slice. At inspection zoom the renderer queries a pitch-and-time index and draws only events
overlapping the viewport. Pausing immediately restores the horizontal scrollbar.

## Editing note expression

Click a note block to pause playback and open **Note expression** in the same right-side panel
used by Conversion, Notifications, and Channel settings. The selected block receives an outline; hover glow remains
pointer-only. Clicking or dragging empty roll space still seeks. The inspectors and modal sound
browser are mutually exclusive, and `Escape` closes the active one.

The inspector presents the musical controls and resolved output without exposing raw velocity:

| Readout | Meaning |
|---|---|
| MIDI note | immutable note name and number from the imported file |
| Sound | exact Play event used by this note |
| Pitch | whole-semitone modifier for the active Manual or Follow MIDI mode |
| Note volume | current pre-master level; initially derived from imported MIDI velocity |
| Volume calculation | note volume + track volume + global volume = final SnapMap dB |
| Clamp notice | requested value and the -24..24 pitch or -60..20 volume limit applied |

**Pitch** is an integer -24 through 24 semitones and **Note volume** is an integral -60 through
20 dB. Fractional semitone math remains internal; visible tuning uses whole semitones and whole
cents. While Follow
MIDI note is enabled, an unedited note shows its resolved automatic pitch; editing the slider saves
a separate Follow MIDI value. While Follow MIDI is disabled, the slider shows that note's preserved
manual value, initially zero, and edits only the manual value. Toggling the channel option never
rewrites either state: disabling it restores prior manual work, and enabling it restores a saved
Follow MIDI adjustment or derives the automatic value when none exists. Pitch changes playback only
and never moves the note, changes its channel, or selects another curated sample. The root
calculation, detector confidence, and calibration basis remain internal. An unedited note volume
starts at its MIDI-velocity-derived level; editing replaces that level directly, so 0 dB is a
meaningful saved choice. Track Volume and Global Volume are added afterward and do not modify it.
**Reset note**
removes both pitch-mode values and the selected note's volume override, returning Follow MIDI to its
automatic value, Manual to zero, and volume to the imported velocity-derived level.

Only the final output is clamped. For example, a note saved at +2 dB with Track Volume at -4 dB
and Global Volume at +20 dB requests +18 dB. Returning either track or global volume to 0 dB
reveals the unchanged +2 dB note again; no normalization rewrites the note.

Notes are identified as `channel:source-pitch:occurrence` before mute or sound mapping, so an
edit stays attached while the channel is retimbred. The block remains on its imported MIDI row;
timing, duration, channel, and the source MIDI file are not changed.

## Previewing the song

There is exactly one transport Play/Pause control. It plays the entire converted
arrangement from the current position; pressing it again pauses without returning to zero.
There are no per-channel song controls. The sound browser's audition button plays one event
for identification and never starts a channel or arrangement.

Preview uses the same resolved sound/root, imported MIDI pitch, playback-only offsets,
current note volume, track volume, global volume, clamps, duration caps, polyphony thinning, channel mix state,
speaker allocation, voice stealing, hard stops, and releases as export. Web Audio
receives the final compiler values: `2 ** (pitch_modifier / 12)` playback rate and
`10 ** (volume_db / 20)` gain. When a later note reuses a SnapMap speaker, preview hard-cuts
the earlier note at that same point just as the exported timeline does.

Editing conversion controls does not stop the transport. The currently scheduled performance
continues while Python coalesces and rebuilds the settings changes and any newly required sample
is prepared. The new event list takes over after the existing audio look-ahead boundary; already
ringing notes are not cut and queued notes are not duplicated. Consequently, a control change is
heard on subsequent notes rather than by restarting the note already in progress.

The package contains no audio. When the workstation starts or imports a song, it finds the
user's DOOM installation and indexes the language-neutral retail banks plus one installed
localization in place. Opening the sound browser lazily reads the complete generated Play
event hierarchy and records which entries resolve to standalone media. Indexing reads metadata
and offsets; it does not decode or copy the full library. Python then decodes only an auditioned
event or the missing unique sounds used by the current converted arrangement into memory. Web
Audio reuses song buffers and schedules them with a rolling look-ahead. An engine-only event
is skipped in local song playback with a notification; export still writes its exact string.

**Options > Refresh Audio Source** repeats install discovery and source validation. There is no
required setup step, background download, or persistent audio copy. With installed metadata
the browser exposes the complete retail Play-event catalog. Without it, the 890-name curated
palette remains available for assignment and export.

If the game is absent or its banks are unsupported, a valid previously built offline cache can
still provide preview audio. Without either source, the song can still be opened, configured,
and exported; the nonblocking banner only reports that Play is unavailable. To deliberately
build the optional offline cache, run:

```bash
snapmap-midi extract
```

That command decodes all 890 palette sounds under
`%LOCALAPPDATA%\snapmap-midi\sounds`. The roughly 450 MB cache is resumable and safe to
delete. The workstation never invokes the command, and no decoded audio is shipped, downloaded,
embedded in a map, or committed to the repository.

## Conversion settings

**Options > Conversion Settings...**, `Ctrl+,`, and the gear button in the transport open the
same nonblocking inspector over the right side of the workstation. There is no import-time
tuning popup. Conversion warnings remain available from the Notifications control while
settings are adjusted.

Sliders are paired with exact numeric fields where a bounded number is meaningful:

| Control | Shape | Effect |
|---|---|---|
| **Global Voices** | slider + integer, 1-128 (default 32) | isolated voices available across the entire song to sustained notes and expressive one-shots |
| **Global Polyphony** | slider + integer, 1-128 (default 32) | strict held-note ceiling across all tracks, including shared-emitter notes; sample tails do not count |
| **Track Voices** | per-track enable checkbox + slider + integer | reserves no more than this track's share of Global Voices; later notes cut this track's older ringing notes |
| **Track Glide** | per-track slider + milliseconds field, 0-5000 | fixed-sound tracks slide from the prior pitch; 0 is immediate and Track Voices 1 is monophonic portamento |
| **Default Track Polyphony** | enable checkbox + slider + integer | default per-track note limit; a Track Polyphony override takes precedence |
| **Track Polyphony** | per-track enable checkbox + slider + integer | strict held-note ceiling per track; lower rejected notes remain as dashed hollow blocks in the piano roll and Track lanes |
| **Track Sustain Limit** | per-track enable checkbox + milliseconds pair | intentionally caps held-note length on one track without changing its voice count |
| **Hard stop notes** | checkbox | cuts at note-off instead of fading |
| **Default Track Release** | slider + seconds field | inherited note-off fade; disabled while Hard stop is on |
| **Default Track Sustain Limit** | enable checkbox + milliseconds pair | caps held notes on tracks without their own Sustain Limit |
| **Limit bass-note duration** | enable checkbox + milliseconds pair | caps notes below the selected MIDI threshold |
| **Below MIDI note** | integer + note name | defines bass for the preceding control |

The **Sound behavior** section lists categories used by the current conversion. These are
categorical choices rather than sliders:

- **Fire and forget** classifies the category as naturally decaying, so it receives no
  later note-off. A note that needs pitch or gain still uses an isolated, duration-reserved
  generic Timeline emitter; a neutral note stays on the shared Timeline path.
- **Sustain cap** gives that category its own maximum duration in milliseconds.

Every accepted change immediately rebuilds statistics, warnings, the preview manifest, and
the next playback. **Restore defaults** resets only conversion limits; it does not clear the
song or channel sound assignments.

These controls exist for the sound-emitter behavior documented in
[`limits.md`](limits.md). Sparse songs generally need no adjustment.

## Exporting

Choose **File > Export SnapMap...**, press `Ctrl+E`, or use the Export toolbar button. Export
writes `rawmap.json` to the current output directory, which defaults to the loader directory
`%LOCALAPPDATA%\snapmap-plus\`. The filename is fixed because that is the only filename the
loader reads. The window reports when an existing map was replaced.

The generated interactive is always named from the imported MIDI filename, including its `.mid`
extension. Saved probe names and the legacy sidecar `button` field cannot leak into a later export.
The master Timeline/Unknown is placed 64 units to the interactive's right, and auxiliary
Timeline/Unknown entities follow at 32-unit intervals. Large groups wrap only when the room boundary
requires another nearby column.

The exported map does **not** contain an audio library or a soundbank. It contains timeline
references only to event strings used by the current converted arrangement. DOOM already owns
the sound data and resolves those names when the map plays. Installed-bank preview and the
optional 890-sound offline cache are workstation-only audio sources.

Export also writes the current settings beside the MIDI. Open the song later and those
choices return automatically. `snapmap-midi compile song.mid --settings
song.mid.snapmap.json` reproduces them without opening the window.

## The settings sidecar

For `song.mid`, the sidecar is `song.mid.snapmap.json`. Every successful workstation settings edit
autosaves the complete validated document, and Export writes it again. It is ordinary JSON and may be
versioned with a project or edited by hand. A typical file is:

```json
{
  "version": 19,
  "midi": "D:/music/song.mid",
  "button": "snapmap-midi-song",
  "out_dir": null,
  "baseline": null,
  "channels": {
    "0": {"family": "ins_piano", "muted": false, "soloed": false},
    "1": {
      "family": null,
      "sound": "play_pianoc4",
      "muted": false,
      "soloed": true,
      "pitch_follow": true,
      "pitch_follow_preference": true,
      "root_midi": 60,
      "detected_root_midi": 60,
      "root_confidence": 1.0,
      "root_source": "palette_name",
      "pitch_transpose": 0
    },
    "2": {
      "family": null,
      "sound": "play_noise_crash",
      "muted": false,
      "soloed": true,
      "pitch_follow": false
    },
    "9": {"family": null, "muted": false, "soloed": false}
  },
  "drums": "auto",
  "notes": {
    "0:60:1": {
      "pitch_semitones": 1,
      "follow_pitch_semitones": -2,
      "volume_db": -3
    }
  },
  "drum_keys": {
    "38": "play_noise_clap"
  },
  "tuning": {
    "max_speakers": 32,
    "song_polyphony": 32,
    "master_volume_db": 0,
    "release_s": 0.1,
    "hard_stop": false,
    "max_poly": null,
    "cap_sustain_ms": null,
    "bass_pitch": 78,
    "bass_cap_ms": null,
    "decaying_families": [],
    "family_caps": {}
  }
}
```

Within a channel, `family` and `sound` are mutually exclusive. `family: null` with no
`sound` means Automatic. `muted` and `soloed` default to false. Exact sounds may also carry
`pitch_follow`, `root_midi` (0 through 127), `detected_root_midi`, `root_confidence` (0 through 1), and `root_source`
(`palette_name`, `detected`, `manual`, or `neutral`). Palette, detected, and manual roots identify
the sound's actual natural note in MIDI-number space. A `neutral` root is always MIDI 60/C4 and is
only an operational basis for an explicit Follow MIDI choice; it is not acoustic evidence.
`manual` records an explicit sample-natural-note correction. `pitch_transpose` is the track-wide
semitone shift. The backend still accepts legacy `fine_tune_cents` values and discloses any nonzero
value as a saved detune; the normal UI no longer creates them, and a new manual calibration clears
the legacy detune. Optional `voices`, `polyphony`, and
`sustain_ms` and `release_s` values override the corresponding song defaults for that track. `hard_stop`
is an optional per-track override of the song's immediate-stop choice. `attack_ms` is an optional
1–5000 ms note-on fade for that track; enabling it routes its notes through isolated emitters.
Channel `volume_db`
is an integer -60 through 20 dB track offset; zero is neutral and is omitted from normalized
sidecars.
Tonal ambiguity and clearly nonmusical sounds preserve natural playback by default. Legacy
`detected_octave` and `relative` references migrate to a safe disabled state because they could
preserve intervals while shifting absolute playback by an octave.

`pitch_follow_preference`, when present, records an explicit choice made in Channel settings.
Choosing a new exact sound resets it to false and clears the old sound's acoustic profile. The new
sound plays unchanged until the user explicitly analyzes it, enables Follow MIDI note, or moves a
manual calibration control. Pitched-family and Automatic assignments keep their intrinsic mapping.

The `notes` object is sparse. Its key is `channel:source-pitch:occurrence`, assigned from the
imported MIDI before mute or sound mapping so the edit survives retimbre. `pitch_semitones` is the
preserved manual-mode modifier; absent means zero. `follow_pitch_semitones` is an optional absolute
override used only while Follow MIDI note is enabled; absent means derive the automatic modifier.
Both accept backend decimal -24 through 24 SnapMap semitones for compatibility, but the UI writes
whole semitones. They coexist so toggling the channel mode cannot destroy the value belonging to
the other mode. `volume_db` is the absolute -60 through 20 pre-master
note level. Explicit zero values are preserved because they can be intentional edits. Legacy
sidecars may retain a relative `pitch_offset` as a compatibility fallback until the relevant mode is
edited. Pitch modifies playback but never the note's piano-roll row or curated sample selection.
Opening a different MIDI clears this section together with song-specific channel choices.

UI note patches merge by note id and field. Adjusting pitch never rewrites volume, adjusting
volume never replaces another note, and Reset note deletes only the selected note's sparse
record. Sound and expression changes are serialized through one update queue, preventing a later
sound-selection response from overtaking a slider edit that was already in flight.

Channel, note-id, and drum-key components are strings because JSON object keys are strings;
validation converts them back to integers for the MIDI parser. Version 1 and version 2 documents
migrate in memory with `master_volume_db` set to the neutral 0 dB default. Versions 1 through 3
rename legacy note `transpose` values to playback-only `pitch_offset`, and version 4 adds
`soloed`. Version 5 changes user-facing `volume_db` from a relative trim to the absolute note
level. Older relative values migrate to an internal `volume_trim_db` compatibility field so
they sound identical; editing that note replaces it with the absolute form. Version 6 disables
legacy relative and octave-fitted pitch references before compilation. Version 7 preserves the
visible version-6 Follow MIDI note choice as a channel preference and changes note updates from
whole-map replacement to sparse record merges. Version 8 adds the neutral opt-in reference and
absolute `pitch_semitones` overrides; legacy relative note pitch continues to compile identically
until edited. Version 9 makes the version-8 absolute value the preserved Manual state and adds a
separate `follow_pitch_semitones` override, so switching channel pitch mode is reversible. Version
13 adds `detected_root_midi`, `pitch_transpose`, `fine_tune_cents`, and fractional pitch export. Automatic
roots are revalidated against current acoustic evidence when the song opens; a stale result is
repaired in memory and saved on the next export. Manual roots and stored disabled states are retained.
Version 17 adds the neutral per-track volume offset; version-16 sidecars migrate with no audible
change. Version 18 adds optional per-track release; version-17 sidecars inherit the 0.1-second
default. Version 19 adds optional per-track Attack and Hard Stop; older sidecars inherit the song
defaults and keep their existing playback.

`master_volume_db` is an integer -60 through 20 dB and defaults to zero. `null` disables
optional duration and polyphony limits. `decaying_families` and
`family_caps` accept any real palette category. Unknown keys, malformed Play event
identifiers, incompatible family-and-sound pairs, impossible root/follow combinations, malformed
note ids, and out-of-range values are rejected by name rather than silently ignored. A
syntactically valid exact event remains loadable when DOOM has moved, so a sidecar is not coupled
to the current install path.

A broken sidecar never prevents the MIDI from opening. The workstation opens the song with
defaults and reports why that sidecar was ignored. A sidecar that cannot be written does not
invalidate a map that was exported successfully.

## Theme, status, and failure behavior

Light and dark themes use the exact Snapmap Plus token sets and persist locally. The status
bar reports only song-specific diagnostics: note count, peak speaker voices, long sustains, and
song length. Routine bridge readiness and preview-audio source labels are intentionally omitted;
audio failure still appears in the actionable preview banner. Warnings name the conversion
setting that can address the condition and open the inspector in context.

The page is loaded from a local `file:///` URI. Nothing is served, no port is opened, and no
network client participates. If WebView2 is unavailable, the launcher prints the runtime to
install instead of leaving a blank window.
