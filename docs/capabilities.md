# Capabilities

Everything the tool exposes. For how the pieces fit together see
[`architecture.md`](architecture.md); for the engine limit most of the tuning exists to work
around see [`limits.md`](limits.md).

## Commands

The bare command is the normal application launcher. Preview reads an installed game's retail
soundbanks directly when available; `extract` exists only to build an optional offline fallback.
Compiling and editing need neither source. The `ui` subcommand is only a shortcut for preloading
a song or an explicit settings file.

```bash
snapmap-midi                     # open the MIDI workstation
snapmap-midi compile song.mid    # compile without a window
snapmap-midi extract             # build the optional local preview cache
```

The name with nothing after it opens the window, because the window is where an instrument
gets chosen and this command line is where a choice already made gets replayed. Where there
is no display — CI, a container, a shell over a remote connection — it prints the usage text
instead. `webview.start()` blocks until the window closes, and a window nobody can see never
closes, so the alternative is a command that hangs having printed nothing.

All of them also run as a module, which is handy when the package is installed but its
scripts directory is not on `PATH`:

```bash
python -m snapmap_midi compile song.mid
```

## Where the map goes

**The map loader reads exactly one file: `rawmap.json`, in `%LOCALAPPDATA%\snapmap-plus\`.**
Not a directory it scans, not a name you give it — one hardcoded path.

So that is where a compile writes, and where the window's Export button writes, and the
folder is created if it isn't there yet. The loader creates it too, the first time it runs;
doing it here as well means compiling works on a machine where that hasn't happened.

One file means every export replaces the last one. The window says when it has, because a
button invites repeated use in a way a typed command did not.

`--out-dir` moves the folder. It does not rename the file, because a map named anything else
cannot be loaded without being renamed first:

```bash
snapmap-midi compile song.mid --out-dir D:/songs/bach
```

The old `--out` flag is gone. It let you write `song.json`, which looked like a finished
build and was not loadable by anything — you had to know, from somewhere else, to rename it.
Choosing that name was never a real choice.

To play a compiled map: open the console with `~`, run `sh_rawmaps_on`, then open any map.
Yours loads instead of it. Run `sh_rawmaps_off` when you're done.

### `compile` — a MIDI file to a playable map

| Flag | Type | Default | What it does |
|---|---|---|---|
| `midi` | path | *required* | the `.mid` to compile |
| `--out-dir` | path | the loader's folder | write to this folder instead (filename stays `rawmap.json`) |
| `--baseline` | path | none | add the song to this saved map instead of authoring a blank room |
| `--settings` | path | none | take every lever from this settings file (see [`ui.md`](ui.md)) |
| `--button` | text | legacy compatibility | accepted for older scripts; MIDI exports always name the interactive from the `.mid` filename |
| `--remap` | text | none | retimbre families, e.g. `ins_guitar=ins_piano`; comma-separate several |
| `--drums` | `auto` / `on` / `off` | `auto` | `auto` includes drums when the file has a channel-9 track |
| `--max-speakers` | int | `32` | ceiling on dedicated speaker voices |
| `--release` | seconds | `0.1` | note-off fade time |
| `--hard-stop` | flag | off | cut notes instead of fading them |
| `--max-events` | int | none | cap the number of one-shot events |

On success it prints the statistics summary and the output path. The summary is worth
reading: `voices`, `decaying`, `sustained` and `notes` tell you at a glance whether the
arrangement is inside the engine's comfortable range.

**`--settings` and the flags resolve in one order: built-in defaults, then the file, then
whatever you typed.** A settings file is a decision made earlier and saved; a flag is a
decision being made right now, so the flag goes last. Setting one lever in the file does not
reset the other forty. A file that does not validate prints `settings: <message>` naming the
offending key and exits `2` — the window writes that file and editing it by hand is expected,
so a bad one is an ordinary event rather than a bug. See
[`ui.md`](ui.md#the-settings-sidecar) for the schema.

### `extract` — build an optional offline preview cache

| Flag | Type | Default | What it does |
|---|---|---|---|
| `--install` | path | automatic search | read this DOOM install instead of searching Steam |
| `--force` | flag | off | re-decode sounds already present in the current cache |

The command decodes the 890 palette sounds from the user's own game into WAV files under
`%LOCALAPPDATA%\snapmap-midi\sounds`. Existing complete files are skipped, so an interrupted
run resumes. This is an explicit offline-cache operation; the workstation does not call it and
normally reads installed banks in place. Exit `0` means every palette sound was cached, `1`
means one or more sounds could not be decoded, and `2` means there was no usable install. No
audio is shipped or downloaded.

### Bare command — the MIDI workstation

Run `snapmap-midi`, then use **File > Import MIDI...** in the window. That is the ordinary
launch path; the retired `audition` command has no alias or compatibility mode.
For scripts that need to preload files, `snapmap-midi ui song.mid --settings settings.json`
accepts these arguments:

| Flag | Type | Default | What it does |
|---|---|---|---|
| `midi` | path | none | open on this song |
| `--settings` | path | none | open with these settings |

The workstation is one persistent surface: a unified channel list, a full-range piano roll,
one global Play/Pause transport, a draggable sweeping playhead, and mutually exclusive
Conversion, Notifications, Channel settings, and Note expression inspectors. Source composition stays read-only:
notes cannot be created, deleted, moved, or resized. Clicking a note instead edits playback-only
Pitch and its absolute Note volume. Note volume begins at the level derived from imported velocity
and may be set directly to any -60 through 20 dB value. Its MIDI row, channel, id, and curated sample
stay fixed. Clicking empty space seeks.

The roll has synchronized pitch/time axes, native two-dimensional scrolling,
playhead-anchored zoom, source-tempo-aware grid divisions, selectable visual meter, rounded
high-resolution note labels, pointer-only note glow during playback and pause, and section-based
playback following. The static roll, animated playhead, and hover/selection feedback are separate
layers. Whole-song overview scrolling reuses a bounded raster cache; inspection zoom queries
only notes overlapping the visible pitch and time ranges. Vertical wheel input remains active
over the disabled horizontal scrollbar. A persistent draggable divider trades width between the
channel list and roll while preserving useful minimums for both.
If source End-of-Track falls inside its final measure, the workstation completes that measure as
empty grid space without extending the final note. Natural completion does not hard-stop finite
one-shots or release fades already in progress.

Percussion stays with the other channels. Every channel can use Automatic mapping, one of the
12 pitched instrument sets, or an exact event from the installed full-game sound browser. The
browser falls back to the 890 curated palette names when installed metadata is unavailable.
Compact stateful icons provide mute and standard multi-solo; mute wins when both are active.
Clicking the rest of a channel row focuses its notes without changing the mix and opens Channel
settings. Its first control is the channel-wide Follow MIDI note mode; automatic musical
mappings show it as built in, while exact effects make it editable.
Muted and solo-excluded notes remain visible in neutral gray but do not preview or export.
Export writes the map and versioned settings beside the song, so global volume, mixer state,
channel roots, and sparse per-note expression edits return in the next session.

It needs pywebview, which is an ordinary dependency on Windows and the `[ui]` extra
everywhere else. [`ui.md`](ui.md) covers the complete workstation and the settings document
both surfaces share.

### The full-game sound browser

The exact-event catalog is loaded only when the modal opens. Installed event strings are read
from soundbanksinfo.events and organized by their Wwise authoring paths. Search covers names,
readable labels, folders, buses, environments, numeric IDs, and preview availability. Results
are paginated. Direct-media events can be auditioned one at a time; engine-only composite
entries remain selectable for export and are clearly marked.

The reference retail installation contains 7,589 Play events, of which 7,353 support local
preview; those counts can vary with localization and edition. Exact assignment repeats the
chosen event string for every note. Selection itself preserves natural playback and performs no
pitch analysis. When the user explicitly presses **Analyze sound**, a conservative all-leaf analysis accepts a
root only for stable pitched media. Accepted roots keep their measured octave so MIDI pitch remains
absolute. Tonal but root-ambiguous and nonmusical events keep natural playback by default. Users may
explicitly enable Follow MIDI note for those events; the fallback is a fixed neutral C4 operational
reference, not a claimed acoustic root or a value inferred from channel notes. Channel settings can
explicitly refresh analysis, show its note/cents/confidence, and replace the playback reference when
the detector is wrong. Infinite and Mixed Wwise events use the sustained path and
receive a stop. One-shots with non-zero pitch or gain use duration-reserved generic Timeline
emitters; neutral one-shots retain the shared fire-and-forget path. The full catalog remains a
manual layer and does not widen General MIDI automatic mapping.

### Channel pitch mode

Channel settings owns the pitch basis shared by every note on a channel. Automatic mappings and
pitched instrument sets always follow MIDI through their curated samples; automatic percussion
uses dedicated per-key sounds and has no channel-wide pitch mode. Exact events expose
**Follow MIDI note** for every exact sound. A trusted acoustic root enables it automatically;
otherwise the sound stays at natural playback until the user opts in, at which point a stable neutral
C4 reference supplies predictable relative semitones. The analyzer button refreshes cached evidence;
the playback reference accepts either MIDI-number or note-name input, including enharmonic flats.
Track transpose applies a whole-note interval and Fine tune adds cents to every note. Neither uses a
first-note, midpoint, or median fallback.

### Per-note pitch and dynamics

Clicking a rendered note pauses transport and opens the Note expression inspector. It shows the
immutable MIDI note, channel, exact event, Pitch, current note volume, and any clamp.
The resolved automatic value retains the analyzer's exact backend pitch. The interface presents
that value as a whole note/MIDI number plus whole cents rather than a decimal semitone.

- **Pitch** is an integer -24 through 24 semitones and affects playback only. The control displays
  the active mode's nearest whole-semitone modifier: automatic pitch (or its separate user adjustment) while Follow
  MIDI note is enabled, and the note's preserved manual value while it is disabled. Editing saves
  only the active mode. Toggling Follow MIDI never rewrites the other value, so disabling it restores
  prior manual work rather than resetting notes to zero. Pitch never moves the MIDI block or changes
  which curated sample was selected.
- **Global volume** is an integer -60 through 20 dB, defaults to 0, and offsets every note.
  Its slider sits beside Notifications in the bottom control plane and never rewrites note
  values.
- **Note volume** is an integer -60 through 20 dB. MIDI velocity first maps through
  `40 * log10(velocity / 127)` to provide the initial value; a user edit replaces that value
  directly. Global volume is added afterward.
- **Reset note** removes both pitch-mode values and the note-volume override, restoring automatic
  pitch, a zero manual pitch, and the imported velocity-derived level.

Final pitch is clamped to SnapMap's -24 through 24 semitone range and final volume to -60
through 20 dB. The notification/inspector readouts expose a requested value that was limited.
Edits are keyed by `channel:source-pitch:occurrence`; they survive sound changes but never
modify the source MIDI, change note verticality, change channel identity, or participate in
curated sample selection. Changing the sound also preserves mute, solo, and an explicit channel-wide
Follow MIDI note preference. Only the selected sound's acoustic root evidence is recalculated.
Sparse note writes and sound assignments run in order, so rapid edits cannot replace one another
with stale full-document snapshots.

### The palette's categories

24 of them, and the split matters more than the count.

**12 can play a pitch** and are the families a melodic channel may be routed to:
`ins_brass_bells`, `ins_flute`, `ins_guitar`, `ins_horns`, `ins_marimba`, `ins_piano`,
`ins_pulse`, `ins_sine`, `ins_square`, `ins_tri`, `ins_trumpet`, `ins_violin`. Only nine of
those are reachable by the automatic General MIDI mapping; `ins_square`, `ins_tri` and
`ins_brass_bells` can be chosen but never guessed.

**12 have no pitched sound at all**: `amb_air`, `amb_hellish`, `amb_hums`,
`dlc1_ui_user_defined`, `dlc2_classicsfx`, `eff_explosions`, `eff_gore`,
`eff_miscellaneous`, `ins_noise`, `ins_percussion`, `ins_string`, `ins_synth`. Two of those
carry the `ins_` prefix and are still silent for every note — `ins_string` is named like the
other pitched instruments and holds twelve unpitched effect samples instead.
**Never split the list by name prefix.** `pitched_families()` derives it from which
categories actually have a pitch index, which is the only version that cannot be wrong.

`ins_noise` and `ins_percussion` together are the 70 sounds a drum key may be remapped to.
The rest of the unpitched half is ambience, gore and interface noise, and a looping ambience
fired as a one-shot is never told to stop — see [`limits.md`](limits.md).

The workstation can play the entire converted arrangement directly from an installed game's
retail soundbanks, with a valid 890-sound offline cache as fallback. The same direct source
auditions full-catalog events in the browser. Preview receives the compiler's resolved sound,
automatic root-relative pitch or natural-playback state, the exact per-note SnapMap pitch, current
note volume, global volume, duration, and voice-cut facts. Web Audio
applies the final semitones and dB without recalculating them. It decodes only samples the
current song uses. See
[`ui.md`](ui.md#previewing-the-song) for transport and source behavior.

## Tuning, routing, and expression arguments

The duration/polyphony controls reduce how many sounds are live at once because the engine
recycles emitter slots under load. Read [`limits.md`](limits.md) before changing them—a sparse
arrangement needs none. Routing and expression arguments answer a different question: which
sound a note uses and how that note is pitched or amplified.

Some are on the command line, some are represented by the versioned UI sidecar, and the rest
remain library-only arguments to `compile_to_rawmap`.

| Lever | CLI | Type | Reach for it when |
|---|---|---|---|
| `max_speakers` | `--max-speakers` | int | too many sustained or expressive voices across the song; the global isolated-emitter limit |
| `song_polyphony` | — | int | too many held MIDI notes across all tracks, including shared-emitter notes; defaults to 32 |
| `part_voices` | — | dict | one track is monopolising the global pool; cap that track while preserving later attacks |
| `part_sustain_ms` | — | dict | one track's held notes need an intentional maximum length independent of voice stealing |
| `part_glide_ms` | — | dict | a fixed-sound track should slide from its previous pitch; pair with Track Voices 1 for monophonic portamento |
| `part_attack_ms` | — | dict | one track needs a controlled fade-in at each note-on; optional because it uses isolated emitters |
| `part_hard_stop` | — | dict | one track should stop immediately while other tracks retain their release fades |
| `master_volume_db` | -- | int | the whole arrangement is too quiet or loud; offsets every note before the final clamp |
| `release_s` | `--release` | seconds | note-offs sound abrupt, or notes bleed together |
| `hard_stop` | `--hard-stop` | flag | a fade is still audible under the next phrase; cuts instead |
| `max_events` | `--max-events` | int | the timeline is too dense overall |
| `family_overrides` | `--remap` | dict | an instrument picked the wrong-sounding family |
| `drums` | `--drums` | mode | percussion is dominating, or is wanted and absent |
| `max_poly` | — | int | a chord-heavy passage overruns the emitter budget |
| `cap_sustain_ms` | — | ms | default audible-duration cap, including long one-shot rings, for tracks without a per-track override |
| `bass_cap_ms` | — | ms | only the low register rings on; pairs with `bass_pitch` |
| `bass_pitch` | — | note | where "bass" starts for `bass_cap_ms`; defaults to 78 |
| `min_sustain_ms` | — | ms | very short sustained notes are wasting voices |
| `drop_sustain_over_ms` | — | ms | drop sustained notes longer than this outright |
| `family_caps` | — | dict | one instrument is monopolising voices; cap per family |
| `decaying_families` | — | set | classify a family as naturally decaying; expression can still require an isolated voice |
| `channel_families` | — | dict | override the family for a whole MIDI channel |
| `channel_sounds` | — | dict | trigger one exact DOOM Play event for every note on a MIDI channel |
| `channel_pitch_profiles` | — | dict | enable exact-sound pitch following from acoustic roots or the explicit neutral reference |
| `note_overrides` | — | dict | sparse absolute playback pitch and note-volume values keyed by stable source-note id |
| `channel_mutes` | — | set | silence whole channels; the notes are not counted as dropped |
| `channel_solos` | — | set | standard multi-solo; when non-empty, only unmuted members are audible |
| `drop_shaders` | — | set | one specific sound is wrong; exclude it |
| `drum_overrides` | — | dict | retimbre whatever the drum table picked, keyed by sound |
| `drum_key_overrides` | — | dict | give one percussion key a sound; wins over the table |
| `low_split` | — | — | split the low register onto its own family |
| `note_index` | — | index | supply a prebuilt palette index instead of resolving one |

`drum_key_overrides` is keyed by MIDI key and `drum_overrides` by resolved sound, which is
why the per-key choice is applied first and the shader table only ever post-processes the
table's own answer. Applied the other way round it silently replaced the sound somebody had
just picked.

The bottom control plane exposes `master_volume_db`. The Conversion inspector exposes
`max_speakers`, `song_polyphony`, `release_s`, `hard_stop`, `max_poly`, `cap_sustain_ms`, `bass_pitch`,
`bass_cap_ms`, `decaying_families`, and `family_caps`. Channel rows expose family/sound
selection, mute, multi-solo, and click-to-focus inspection. Selecting an exact sound records a
trusted pitch when available. Root-ambiguous and clearly nonmusical sounds keep natural playback
unless Follow MIDI note is explicitly enabled from the neutral C4 reference. Clicking a note exposes
sparse playback-only `note_overrides`; Channel settings shows only the useful pitch mode and never
exposes raw calibration data. The imported note, curated sample choice, and piano-roll row remain
unchanged.

Automatic percussion still obeys `drums` and `drum_key_overrides` restored from a sidecar,
but percussion is not a separate UI mode. The rest stay sidecar or library controls.
`max_events` is deliberately not in the inspector: the compiler slices the chronological
one-shot list, so the drums stop partway through the song rather than thinning out. Behind a
slider that reads as a density limit, that is a trap.

Notes held under about a second cut reliably. That is the practical target when tuning.

## Library use

The whole compiler is importable. `compile_to_rawmap` is bytes-out and touches neither the
network nor the filesystem beyond reading the MIDI path you hand it.

```python
from snapmap_midi.compile import compile_to_rawmap

raw, stats = compile_to_rawmap("song.mid", max_poly=8)
```

Pass baseline bytes as the second argument to add the song to a map you already have:

```python
raw, stats = compile_to_rawmap("song.mid", my_level_bytes)
```

The timeline layer is usable on its own when you want to place sounds directly rather than
compile a file:

```python
from snapmap_midi.sound.timeline import author_sound_timeline

raw = author_sound_timeline(
    [("play_noise_kick_tight", 0), ("play_noise_hat", 400)],
    button_name="my-groove",
)
```

The palette answers what a sound is and which one plays a pitch:

```python
from snapmap_midi.sound.palette import build_note_index, decl_for, sounds_in_category

index = build_note_index()
decl_for("ins_piano", 60, index)  # 'play_pianoc4'
sounds_in_category("ins_noise")  # every noise sound, in declaration order
```

And the authoring core knows nothing about music, so it can build any map:

```python
from snapmap_midi.rawmap.document import SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.rawmap.template import blank_map

doc = SnapMapDocument(data=blank_map(), palette_refs=PRODUCT_PALETTE_REFS)
uid = doc.add_speaker(sound="play_pianoc4", position=(0.0, 0.0, 0.0))
```
