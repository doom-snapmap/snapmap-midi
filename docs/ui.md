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
| warnings / audio setup                                                    |
+--------------------------------------------------------------------------+
| status: notes, peak voices, long sustains, song length                    |
+--------------------------------------------------------------------------+
```

All MIDI channels are peers in the left column. Percussion is not sent to a separate
workspace. The right side is a read-only piano roll for the converted song.

The shell deliberately matches Snapmap Plus: the same light and dark colors, Segoe UI and
Consolas type, 30 px menu bar, status bar, toast treatment, brand image, window controls,
native resize behavior, and native Windows snapping.

## Traditional menus

The menu bar keeps infrequent commands out of the note surface.

| Menu | Commands |
|---|---|
| **File** | Import MIDI, reopen the current file, export the map, exit |
| **Playback** | play or pause the complete song, return to the start |
| **Options** | open Conversion settings, set up local preview audio |
| **View** | light theme, dark theme |

The main shortcuts are `Ctrl+I` to import, `Ctrl+E` to export, `Ctrl+R` to reopen, `Ctrl+,`
for Conversion settings, `Space` to play or pause, and `Home` to return to zero. Press
`Escape` to close an open menu or the Conversion inspector.

Drag an unused part of the top menu bar to move the window. The menu labels and window
buttons remain clickable rather than acting as drag handles. The invisible edge grips use
Windows' native resize loop, so Aero Snap and drag-to-maximize still work.

## Importing a MIDI file

Choose **File > Import MIDI...** or press `Ctrl+I`. Import analyzes the file and then fills
the channel list and piano roll. It does not open a tuning wizard and it does not make the
user approve guessed settings before seeing the song.

Safe compiler defaults are applied immediately. If the converted arrangement approaches a
SnapMap engine limit, a warning appears below the workspace and opens the Conversion
inspector when clicked.

Opening another song clears channel sound choices and percussion-key overrides, because
channel numbers in two files do not mean the same parts. General conversion limits, output
location, button name, and optional baseline remain session preferences. A valid sidecar
beside the new MIDI is then applied.

## Channels and the complete sound palette

Every channel row shows its one-based MIDI channel number, source General MIDI program,
sound assignment, and mute control. A percussion channel is labeled in the same list instead
of moved to a Drums tab.

Each sound picker has three kinds of choice:

- **Automatic** uses the General MIDI program-to-family mapping. On an automatically
  detected percussion channel it uses the General MIDI percussion map by note number.
- **Pitched instrument set** maps every MIDI pitch to the closest available sound in one of
  the 12 pitch-capable SnapMap categories.
- **Exact sound** triggers the selected sound for every note on the channel. All 890 sounds
  in all 24 shipped palette categories are available, including percussion, ambience,
  effects, interface sounds, and the pitched samples themselves.

An exact sound is intentionally exact: choosing one piano sample does not retune it across
the keyboard. Choose the piano instrument set when the melody should follow MIDI pitch;
choose one exact sound when every note should trigger that same SnapMap sound.

Mute removes the channel from preview and export without forgetting its assignment. Click a
channel row to emphasize that channel's notes on the piano roll; click it again to show all
channels at equal emphasis.

Advanced per-key percussion overrides remain valid in the settings sidecar. They are not a
second instrument screen: Automatic percussion applies them before falling back to the
built-in General MIDI drum map. A channel-level instrument set or exact sound takes
precedence over the percussion map.

## The piano roll and sweeping playhead

Time runs left to right and MIDI pitch runs bottom to top. Notes are colored consistently by
channel. C notes are labeled, black-key rows are shaded, and the time grid adapts to the
length of the complete song.

The piano roll is a visualization and transport surface, not a composition editor. Notes
cannot be moved, resized, created, or deleted here; those edits belong in the MIDI program
that authored the source file.

One accent-colored playhead spans the ruler and entire note surface. During playback it
sweeps continuously across the song. To seek:

- drag the transport scrubber;
- click anywhere in the piano roll; or
- drag the playhead across the piano roll.

Seeking while the song is playing pauses scheduling during the drag and resumes from the new
position when released. `Home` returns to the beginning.

## Previewing the song

There is exactly one transport Play/Pause control. It plays the entire converted
arrangement from the current position; pressing it again pauses without returning to zero.
There are no per-channel or per-sound Play buttons.

Preview uses the same resolved notes, sound assignments, duration caps, polyphony thinning,
speaker allocation, voice stealing, hard stops, and releases as export. It is not the
computer's General MIDI synthesizer. When a later note reuses a SnapMap speaker, preview
hard-cuts the earlier note at that same point just as the exported timeline does.

The package contains no audio. If the local cache is missing, the song can still be opened,
configured, and exported. A nonblocking banner offers **Set up audio**; the same operation is
available under **Options > Set Up Audio...** or from the command line:

```bash
snapmap-midi extract
```

Setup reads the user's own DOOM installation and decodes all 890 palette sounds to
`%LOCALAPPDATA%\snapmap-midi\sounds`. The cache is about 450 MB, resumable, safe to delete,
and never shipped, downloaded, embedded in a map, or committed to the repository.

Playback does not send that whole cache to the window. For each conversion, Python returns
only the WAV data for sounds the current song actually uses; Web Audio decodes those samples
and schedules them with a rolling look-ahead.

## Conversion settings

**Options > Conversion Settings...**, `Ctrl+,`, the Conversion toolbar button, and warning
messages all open the same nonblocking inspector over the right side of the workstation.
There is no import-time tuning popup.

Sliders are paired with exact numeric fields where a bounded number is meaningful:

| Control | Shape | Effect |
|---|---|---|
| **Maximum speakers** | slider + integer, 1-128 | speaker voices available to each sustained channel layer |
| **Limit maximum polyphony** | enable checkbox + slider + integer | keeps at most this many simultaneous notes in a layer, preferring higher notes |
| **Hard stop notes** | checkbox | cuts at note-off instead of fading |
| **Release** | slider + seconds field | note-off fade; disabled while Hard stop is on |
| **Limit sustained-note duration** | enable checkbox + milliseconds pair | caps every sustained note |
| **Limit bass-note duration** | enable checkbox + milliseconds pair | caps notes below the selected MIDI threshold |
| **Below MIDI note** | integer + note name | defines bass for the preceding control |

The **Sound behavior** section lists categories used by the current conversion. These are
categorical choices rather than sliders:

- **Fire and forget** forces the category onto the decaying one-shot path, where no speaker
  has to remain allocated for a later note-off.
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

The exported map does **not** contain the 890-sound audio library. It contains timeline
references only to sounds used by the current converted arrangement. DOOM already owns the
sound data and resolves those names when the map plays. The optional local audio cache is
for workstation preview only.

Export also writes the current settings beside the MIDI. Open the song later and those
choices return automatically. `snapmap-midi compile song.mid --settings
song.mid.snapmap.json` reproduces them without opening the window.

## The settings sidecar

For `song.mid`, the sidecar is `song.mid.snapmap.json`. It is ordinary JSON and may be
versioned with a project or edited by hand. A typical file is:

```json
{
  "version": 1,
  "midi": "D:/music/song.mid",
  "button": "snapmap-midi-song",
  "out_dir": null,
  "baseline": null,
  "channels": {
    "0": {"family": "ins_piano", "muted": false},
    "1": {"family": null, "sound": "play_noise_hat", "muted": false},
    "9": {"family": null, "muted": false}
  },
  "drums": "auto",
  "drum_keys": {
    "38": "play_noise_clap"
  },
  "tuning": {
    "max_speakers": 32,
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
`sound` means Automatic. `muted` defaults to false. Channel and drum-key keys are strings
because JSON object keys are strings; validation converts them back to integers for the MIDI
parser.

`null` disables optional duration and polyphony limits. `decaying_families` and
`family_caps` accept any real palette category, including unpitched categories used by exact
sound assignments. Unknown keys, nonexistent sounds, incompatible family-and-sound pairs,
and out-of-range values are rejected by name rather than silently ignored.

A broken sidecar never prevents the MIDI from opening. The workstation opens the song with
defaults and reports why that sidecar was ignored. A sidecar that cannot be written does not
invalidate a map that was exported successfully.

## Theme, status, and failure behavior

Light and dark themes use the exact Snapmap Plus token sets and persist locally. The status
bar reports bridge readiness, optional audio readiness, note count, peak speaker voices,
long sustains, and song length. Warnings name the conversion setting that can address the
condition and open the inspector in context.

The page is loaded from a local `file:///` URI. Nothing is served, no port is opened, and no
network client participates. If WebView2 is unavailable, the launcher prints the runtime to
install instead of leaving a blank window.
