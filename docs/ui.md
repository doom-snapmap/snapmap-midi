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
same parts. General conversion limits, output location, button name, and optional baseline
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
It is added to every current note volume before the final SnapMap clamp. It never rewrites or
normalizes the note values themselves. The control updates the complete preview and exported
timeline, persists in the settings sidecar, and is disabled until a song is open.

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
value used for faint vertical subdivisions. The marks use the MIDI file's real tempo map, so
they remain aligned when tempo changes. Grid is a view control: changing it does not
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

Selecting an exact event analyzes its local media root before committing the choice. Curated
palette names use their authoritative nominal pitch. Other direct-media events are decoded in
bounded memory, and every available leaf must agree before the event is marked pitchable. A
pitchable exact event keeps the same Play string on every note but receives a root-relative
SnapMap semitone modifier. Its detected natural note retains the measured octave so its audible
result matches the piano roll. Tonal media whose fundamental is ambiguous plays naturally rather
than accepting a false upper partial as a root. Speech, noise, impacts, and variable containers
also play naturally by default. The application never pretends that a grunt, impact, or spoken
line has an acoustic root, and the normal UI does not ask users to calibrate one.

Installed Wwise duration metadata independently determines whether the event decays or needs a
paired stop. Mixed events are treated as looping so an infinite branch cannot leak a speaker
emitter. A decaying event that needs pitch or gain still receives an isolated speaker for its
measured tail.

Muted channels and channels excluded by an active solo remain on the piano roll in a restrained
gray treatment, so the score never appears to lose data. They are omitted from preview and
export without forgetting their assignments.

### Channel settings and focus

Click a channel row to focus its notes and open **Channel settings**. The first setting is the
channel-wide **Follow MIDI note** checkbox. Automatic mappings and pitched instrument sets show
it checked and disabled because melodic pitch following is intrinsic to those mappings. Automatic
percussion shows it off and disabled because each MIDI key selects a dedicated drum sound instead.
An exact event with trustworthy pitch evidence makes the checkbox editable. An exact event
without that evidence shows the checkbox disabled and plays unchanged. Channel settings exposes
only this useful outcome; it does not show a natural-note number, an Unknown state, detector
confidence, pitch math, or a manual calibration prompt. It never substitutes the channel's lowest
note, highest note, midpoint, median, or any other property of the imported song. Per-note
exceptions stay in Note expression.

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

Advanced per-key percussion overrides remain valid in the settings sidecar. They are not a
second instrument screen: Automatic percussion applies them before falling back to the
built-in General MIDI drum map. A channel-level instrument set or exact sound takes
precedence over the percussion map.

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
| Pitch adjustment | optional user adjustment in semitones; automatic conversion math stays internal |
| Note volume | current pre-master level; initially derived from imported MIDI velocity |
| Volume calculation | note volume + global volume = final SnapMap dB |
| Clamp notice | requested value and the -24..24 pitch or -60..20 volume limit applied |

**Pitch adjustment** is an integral -24 through 24 semitones and **Note volume** is an integral
-60 through 20 dB. An unedited note starts at its MIDI-velocity-derived level; editing the
control replaces that level directly, so 0 dB is a meaningful saved choice. Global volume is
added afterward and does not modify it. The pitch adjustment changes playback only: it never moves the note, changes its
channel, or causes a different curated sample to be selected. With a detected or manually
calibrated root, it is added after the automatic MIDI-following shift. With natural
playback, it is the complete SnapMap pitch modifier. The subtraction formula, detector confidence,
and calibration basis are intentionally not shown. **Reset note** removes only the selected note's
sparse pitch adjustment and volume override, returning volume to the imported
velocity-derived level.

Only the final output is clamped. For example, a note saved at +2 dB with global volume at
+20 dB requests +22 dB and plays/exports at SnapMap's +20 dB limit. Returning global volume to
0 dB reveals the unchanged +2 dB note again; no normalization rewrites the note.

Notes are identified as `channel:source-pitch:occurrence` before mute or sound mapping, so an
edit stays attached while the channel is retimbred. The block remains on its imported MIDI row;
timing, duration, channel, and the source MIDI file are not changed.

## Previewing the song

There is exactly one transport Play/Pause control. It plays the entire converted
arrangement from the current position; pressing it again pauses without returning to zero.
There are no per-channel song controls. The sound browser's audition button plays one event
for identification and never starts a channel or arrangement.

Preview uses the same resolved sound/root, imported MIDI pitch, playback-only offsets,
current note volume, global volume, clamps, duration caps, polyphony thinning, channel mix state,
speaker allocation, voice stealing, hard stops, and releases as export. Web Audio
receives the final compiler values: `2 ** (pitch_modifier / 12)` playback rate and
`10 ** (volume_db / 20)` gain. When a later note reuses a SnapMap speaker, preview hard-cuts
the earlier note at that same point just as the exported timeline does.

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
| **Maximum speakers** | slider + integer, 1-128 | isolated voices available per channel to sustained notes and expressive one-shots |
| **Limit maximum polyphony** | enable checkbox + slider + integer | keeps at most this many simultaneous notes in a layer, preferring higher notes |
| **Hard stop notes** | checkbox | cuts at note-off instead of fading |
| **Release** | slider + seconds field | note-off fade; disabled while Hard stop is on |
| **Limit sustained-note duration** | enable checkbox + milliseconds pair | caps every sustained note |
| **Limit bass-note duration** | enable checkbox + milliseconds pair | caps notes below the selected MIDI threshold |
| **Below MIDI note** | integer + note name | defines bass for the preceding control |

The **Sound behavior** section lists categories used by the current conversion. These are
categorical choices rather than sliders:

- **Fire and forget** classifies the category as naturally decaying, so it receives no
  later note-off. A note that needs pitch or gain still uses an isolated, duration-reserved
  speaker; a neutral note stays on the shared Timeline path.
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

The exported map does **not** contain an audio library or a soundbank. It contains timeline
references only to event strings used by the current converted arrangement. DOOM already owns
the sound data and resolves those names when the map plays. Installed-bank preview and the
optional 890-sound offline cache are workstation-only audio sources.

Export also writes the current settings beside the MIDI. Open the song later and those
choices return automatically. `snapmap-midi compile song.mid --settings
song.mid.snapmap.json` reproduces them without opening the window.

## The settings sidecar

For `song.mid`, the sidecar is `song.mid.snapmap.json`. It is ordinary JSON and may be
versioned with a project or edited by hand. A typical file is:

```json
{
  "version": 6,
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
      "root_midi": 60,
      "root_confidence": 1.0,
      "root_source": "palette_name"
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
    "0:60:1": {"pitch_offset": 1, "volume_db": -3}
  },
  "drum_keys": {
    "38": "play_noise_clap"
  },
  "tuning": {
    "max_speakers": 32,
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
`pitch_follow`, `root_midi` (0 through 127), `root_confidence` (0 through 1), and
`root_source` (`palette_name`, `detected`, or `manual`). The value always identifies the sound's
actual natural note in MIDI-number space. `manual` is a settings-file/library integration option,
not a control in the normal UI. Tonal ambiguity and clearly nonmusical sounds preserve natural
playback. Legacy `detected_octave` and `relative`
references migrate to a safe disabled state because they could preserve intervals while shifting
absolute playback by an octave.

The `notes` object is sparse. Its key is `channel:source-pitch:occurrence`, assigned from
the imported MIDI before mute or sound mapping so the edit survives retimbre. `pitch_offset` is
an integer -24 through 24 semitones and `volume_db` is the absolute pre-master note level,
an integer -60 through 20 dB. A `volume_db` value of zero is preserved because it explicitly
replaces a quieter velocity-derived default; neutral pitch adjustments are omitted. The pitch adjustment
modifies playback but never the note's piano-roll row or curated sample selection. Opening a
different MIDI clears this section together with song-specific channel choices.

Channel, note-id, and drum-key components are strings because JSON object keys are strings;
validation converts them back to integers for the MIDI parser. Version 1 and version 2 documents
migrate in memory with `master_volume_db` set to the neutral 0 dB default. Versions 1 through 3
rename legacy note `transpose` values to playback-only `pitch_offset`, and version 4 adds
`soloed`. Version 5 changes user-facing `volume_db` from a relative trim to the absolute note
level. Older relative values migrate to an internal `volume_trim_db` compatibility field so
they sound identical; editing that note replaces it with the absolute form. Version 6 disables
legacy relative and octave-fitted pitch references before compilation. Automatic roots are
revalidated against current acoustic evidence when the song opens; a stale result is repaired in
memory and saved on the next export. Manual roots and stored disabled choices are preserved.

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
