# snapmap-midi

**Open a desktop workstation for a standard MIDI file, then export it as a playable music map for
DOOM (2016)'s SnapMap editor.**

Feed it a `.mid`; it builds a room with a switch that plays the song. Seven real songs have
been verified end to end in game.

**This repo ships NO game data** — no declaration files, saved maps, event catalogs, or
audio. It ships a curated 890-name, 24-category palette for deterministic automatic MIDI
mapping. When DOOM is installed, the workstation reads the game's own named-event metadata
and retail soundbanks in place. The reference retail installation exposes all 7,589 named
Play events; 7,353 of those also resolve to standalone media for local audition. Complex
interactive-music, state, legacy, and DLC events remain valid in-game export choices and are
marked accordingly instead of being hidden. Counts can vary with game edition and installed
localization. The optional CLI-built offline cache remains limited to the curated 890-sound
palette.

Every line here is our own implementation, built from our own reverse-engineering of the map
format; no decompiled or copied content.

## Install

You need **Python 3.12 or newer**. Nothing else to find or configure — pip fetches the two
dependencies for you. `mido` reads MIDI files and is needed everywhere; `pywebview` is the
desktop workstation, and it is a plain dependency on Windows only. Elsewhere the window is the
`[ui]` extra, because the map loader this tool writes to is Windows-only and a window on
another platform has nowhere to hand its output. Check what you have:

```bash
python --version
```

If that says 3.11 or lower, or errors, get Python from [python.org](https://www.python.org/downloads/).
**On Windows, tick "Add python.exe to PATH" in the installer** — without it the commands below
will not be found.

### The short way

If you just want it working and do not mind installing into your main Python:

```bash
pip install git+https://github.com/doom-snapmap/snapmap-midi.git
```

Skip to [Open the UI](#open-the-ui). If that command errors with
`externally-managed-environment`, your Python does not allow it — use the isolated way below.

### The isolated way (recommended)

A *virtual environment* is a private folder holding this tool and its dependency, so it
cannot clash with anything else on your machine and you can delete it in one go. Nothing is
installed system-wide.

**1. Pick a folder to keep it in and go there.** Anywhere you like; this uses your home
folder.

```bash
cd %USERPROFILE%
```

<details>
<summary>PowerShell, macOS or Linux</summary>

```bash
cd ~
```
</details>

**2. Create the environment.** This makes a folder called `snapmap-midi-env`:

```bash
python -m venv snapmap-midi-env
```

**3. Activate it.** This is the step people miss — until you do it, `snapmap-midi` will not
be found. Pick the line for your shell:

| Shell | Command |
|---|---|
| Windows — Command Prompt | `snapmap-midi-env\Scripts\activate.bat` |
| Windows — PowerShell | `snapmap-midi-env\Scripts\Activate.ps1` |
| Windows — Git Bash | `source snapmap-midi-env/Scripts/activate` |
| macOS / Linux | `source snapmap-midi-env/bin/activate` |

Your prompt gains a `(snapmap-midi-env)` prefix. That prefix is how you know it is active.

<details>
<summary>PowerShell refuses with "running scripts is disabled on this system"</summary>

Windows blocks scripts by default. Allow them for your own account only:

```bash
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then run the activate line again.
</details>

**4. Install into it:**

```bash
pip install git+https://github.com/doom-snapmap/snapmap-midi.git
```

**5. Open it:**

```bash
snapmap-midi
```

The command with nothing after it opens the UI. Use `snapmap-midi --help` when you want the
command-line reference instead.

### Coming back later

The environment persists, but **activation does not** — it lasts only for that terminal
window. Next time, `cd` back and run the activate line from step 3 again. Then carry on.

## Update, find, remove

Same three commands either way — a virtual environment changes nothing about them. It only
changes *which* installation they act on, so **activate first if you used one** (step 3
above). Without that you will update or remove the copy in your main Python instead, or be
told it is not installed at all. `pip show -f` tells you which one you are talking to.

**Update to the latest version:**

```bash
pip install --upgrade git+https://github.com/doom-snapmap/snapmap-midi.git
```

**See where it is installed, and which version:**

```bash
pip show -f snapmap-midi
```

**Remove it:**

```bash
pip uninstall snapmap-midi
```

## Open the UI

```bash
snapmap-midi
```

That plain command is the application launcher; there is no audition command. Import a MIDI
file and the complete converted arrangement appears on one screen: every channel, including
percussion, lives in the left column and the piano roll fills the rest of the window. Choose
Automatic mapping, one of the pitched instrument sets, or open the searchable sound browser for
an exact event. With DOOM installed, that browser presents the complete retail Play-event catalog
as a folder tree and marks which events support local audition; without installed metadata it
falls back to the 890 curated SnapMap palette.

There is one Play/Pause control for the whole converted song. Its playhead sweeps across the
entire note surface and can be dragged to seek, as can the transport scrubber. The note under the
pointer brightens whether playback is running or paused; playback itself does not change note
colors. Clicking a note pauses playback and opens the Note expression inspector. It shows the
immutable MIDI note, selected event, whole-semitone pitch control, and current note volume. Pitch changes
playback without moving the block, changing its
channel, or selecting another sample. Note volume starts at the level derived from the imported
MIDI velocity and can be set directly, including back to 0 dB. The bottom-panel Volume control
offsets the whole arrangement without rewriting any note level. Exact sounds with a stable root
follow MIDI automatically. Other exact effects play unchanged by default, but their Channel settings
can explicitly enable Follow MIDI note from a fixed neutral C4 reference. That opt-in reference never
comes from the first note or the channel range and does not claim to identify the sound's acoustic
root. The Pitch control always shows the value used by preview and export in the active mode. With
Follow MIDI note enabled, an unedited note shows its automatic modifier; with it disabled, the note
shows its preserved manual value, initially zero. Moving the slider saves only the active mode's
value. Enabling Follow MIDI therefore leaves every manual edit intact, and disabling it restores
those edits instead of resetting the channel's notes to zero. A separately adjusted Follow MIDI
value is restored when that mode is enabled again. For an exact sound, Channel settings can rerun
the analyzer, show the detected note/whole cents/confidence, accept a manual whole MIDI-number or note-name
reference (including flats), transpose the whole track by semitones, and fine-tune it in cents.
The effective-pitch readout incorporates those controls immediately. Channel settings shows the resulting pitch mode,
while the Note expression inspector remains strictly per-note. Clicking or dragging empty roll space
continues to seek.

Changing a channel's sound is non-destructive. Choosing another exact sound, pitched family, or
Automatic mapping preserves every sparse note pitch/volume edit plus the channel's mute, solo,
and user-selected Follow MIDI note preference. Only acoustic metadata belonging to the old exact
sound is replaced: the new event receives its own detected root and capability result. Settings
changes are applied in order, so quickly moving a note slider and immediately choosing a sound
cannot lose the slider edit.

The piano roll defaults to scientific pitch notation (middle C = C4). **View > Octave labels**
can switch the display to middle C = C3 for DAWs that number octaves one lower. This changes
labels only; MIDI note numbers, pitch intervals, preview, and export remain identical.


The roll covers all 128 MIDI pitches with synchronized piano keys, measure ruler, vertical and
horizontal scrollbars, and section-based playback following. Its static grid and notes are cached
separately from the moving playhead, so vertical wheel navigation remains responsive during
playback, including when the pointer is over the disabled horizontal time scrollbar. Dragging the
channel/roll divider trades width between the two panes. Every channel row has compact inline
Mute and multi-Solo icons; active mute is red and active solo uses the accent color. Clicking the
rest of a row focuses its notes for editing without
changing the mix and opens its Channel settings inspector. Its first setting is the channel-wide
Follow MIDI note mode; automatic musical mappings show that behavior as built in, while exact
effects make it editable. Other channels remain visible but dimmed and cannot be selected until
focus is cleared. Muted and solo-excluded notes remain visible in neutral gray but do not preview
or export. Bottom controls set the global volume
modifier, visual note grid, time signature, and playhead-anchored pitch/time zoom. Only Volume
changes preview and export; the remaining controls do not change the source notes. Conversion
limits open in a nonblocking inspector instead of an import wizard or a
separate tab.

The workstation preserves the MIDI file's exact End-of-Track boundary and completes an
incomplete final measure on the ruler. That extra empty space is silence, not a longer note: note
blocks keep their real note-off times. Reaching the end naturally no longer kills a finite
one-shot or release tail, so local preview follows the same decay behavior as the exported map.

If DOOM is installed, preview indexes its retail soundbanks and generated event hierarchy in
place, including one installed localization, and prepares only the sounds selected by the
current song. There is no audio setup step; conversion and export continue to work when preview
audio is unavailable.

Exporting writes the map and, beside the song, a settings file holding every choice that
produced it: channel sounds, mute/solo state, pitch mode,
conversion limits, global
volume, and sparse per-note pitch/volume choices. Open that song again and the choices are already
there;
`snapmap-midi compile song.mid --settings song.mid.snapmap.json` replays them without the
window. Full detail is in [`docs/ui.md`](docs/ui.md).

## Compile a song

```bash
snapmap-midi compile song.mid
```

That is the whole command. It writes `rawmap.json` into the map loader's folder
(`%LOCALAPPDATA%\snapmap-plus\`), creating it if it isn't there yet. In game, open the
console with `~`, run `sh_rawmaps_on`, then open any map — yours loads instead. Walk to the
switch in front of you and press it. `sh_rawmaps_off` when you're done.

To keep a song rather than overwrite the one slot the loader reads, give it a folder. The
filename stays `rawmap.json`, because that is the only name the loader will open:

```bash
snapmap-midi compile song.mid --out-dir D:/songs/bach
```

## Documentation

| Doc | What's in it |
|---|---|
| [`docs/ui.md`](docs/ui.md) | the one-screen workstation, full-song preview, piano roll, conversion inspector, and settings file |
| [`docs/capabilities.md`](docs/capabilities.md) | every command, flag and tuning lever |
| [`docs/game-data.md`](docs/game-data.md) | what ships, what doesn't, and the optional overrides |
| [`docs/architecture.md`](docs/architecture.md) | how a MIDI file becomes a map |
| [`docs/limits.md`](docs/limits.md) | the engine limit worth knowing, and the byte-gate rule |
| [`docs/contributing.md`](docs/contributing.md) | fresh machine to open pull request |

## How it works

A MIDI file streams note-on and note-off events. snapmap-midi pairs them into stable,
velocity-bearing notes, maps each General MIDI program to a curated pitched family, and chooses
the nearest sample in that family. It then applies the residual semitone shift needed to make
that sample sound at the imported MIDI pitch. Automatic mapping remains constrained to the
curated sounds with known pitch coverage.

A manually chosen full-game event still triggers that exact event string for every note on its
channel. When its media has a stable musical root, snapmap-midi detects and caches that numeric
profile and preserves the measured octave. Tonal media whose fundamental is ambiguous, such as a
bell dominated by upper partials, plays naturally instead of accepting a false detected root.
Clearly nonmusical effects also play naturally by default. Follow MIDI note remains available as an
explicit creative choice for either kind of rootless event; it uses the same neutral C4 operational
reference for every channel rather than inventing acoustic evidence. Notes beyond SnapMap's -24
through +24 range clamp with a warning rather than silently shifting the whole channel by an octave.

MIDI velocity becomes each note's initial integral dB level. A per-note edit replaces that
starting level directly; the global volume offset is then added without changing the stored note
level, and only the output sent to SnapMap is clamped. An unedited Pitch control displays the
resolved automatic modifier in Follow MIDI mode and the preserved manual value otherwise. Editing
stores the active mode's exact per-note SnapMap value without overwriting the other mode,
independently of the MIDI row and curated sample choice.
SnapMap receives floating-point pitch in semitones (-24 through 24) and volume in dB (-60 through 20). The
preview uses the matching resampling rate: +12 semitones plays twice as fast and -12 plays at
half speed. One-shot emitter reservations use that pitch-adjusted duration, keeping preview and
export aligned. The arrangement then uses three scheduling paths:

- **Neutral decaying sounds** need no pitch or gain change. They stay on the cheap, fully
  polyphonic shared Timeline path.
- **Expressive decaying sounds** need independent pitch or gain. They receive isolated generic
  Timeline emitters reserved for the installed event duration, then decay naturally without a
  note-off.
- **Sustained notes** receive isolated Timeline emitters plus an explicit stop or release at note
  end.

The isolated voices enter one song-wide reusable emitter pool after each track's own limit is
applied. These are ordinary `idTarget_Timeline` entities, not SnapMap Speaker entities: live-engine
tests proved that `fadePitch` reaches the generic entity but not the Speaker override. Track Voices
1 is the monophonic option. On a fixed-sound track, Track Glide can ramp each new pitch from its
track-local predecessor; 0 ms keeps the proven immediate pitch-before-start order. Preview and
export share this same preparation and expression model. Empty time after the
last note needs no map event: the Timeline is already silent. The workstation may complete the
last visual measure, but export neither stretches the last note nor adds a synthetic sound event.

Track Sustain Limit is independent of that voice pool. It intentionally caps how long held notes
on one track may sound; the conversion-level Sustain Limit is the fallback for tracks without an
override. Voice stealing still shortens an older note only when a new attack needs an occupied
voice.

Global Polyphony is the separate musical-note ceiling. It counts held notes across every track
before routing them to the shared or isolated path, so one shared Timeline cannot hide a large
chord from the song-wide limit. Ringing sample tails do not count, preserving every attack in a
sequential melody.

The SnapMap editor's Timeline buffer is per entity. Export currently keeps one master Timeline and
one listener target even when its serialized size exceeds the conservative 1 MiB editor budget.
Such a map still loads and plays, but SnapMap may not be able to open that Timeline for editing;
the workstation warns when this happens. The automatic sharding implementation remains in the
codebase behind a disabled feature gate for possible later use.

### The map is built from nothing

The song is staged in a blank room the compiler writes itself: two portal caps, a player
spawn, a timeline, and the switch that fires it.

That timeline used to be the reason a *baseline map* was a required input. `idTarget_Timeline`
cannot be placed from the editor's entity palette, and that was read as "a timeline cannot be
created". It conflated two different things — making the engine **spawn** one at runtime,
which really is out of reach from outside the game, and **describing** one in a saved map,
which is just schema. In a saved map a timeline is an ordinary entity: class
`idTarget_Timeline`, stock inherit `snapmaps/unknown`, and no reference slots at all.

A map authored this way has been loaded into the live editor with every entity present at its
assigned id — the timeline included — and playtested through the editor → play → exit cycle
without a crash.

Pass `--baseline` if you want the song added to a map you already have instead. It is an
option now, not a prerequisite.

### The limit worth knowing about

The engine recycles sound emitter slots under load. A note whose slot is recycled can no
longer be stopped, so it plays to the end of its sample even though a stop was issued.
Sparse arrangements are unaffected. Dense ones need the tuning levers, which all reduce how
many sounds are live at once: `cap_sustain_ms`, `bass_cap_ms`, `max_poly`, `family_caps`,
`decaying_families` and `family_overrides`. Notes held under about a second reliably cut.

Full detail in [`docs/limits.md`](docs/limits.md).

## Use as a library

```python
from snapmap_midi.compile import compile_to_rawmap

raw, stats = compile_to_rawmap("song.mid")
```

The map-authoring core underneath knows nothing about music and is usable on its own — see
[`docs/architecture.md`](docs/architecture.md).

## Repository layout

Modules are grouped by subsystem, stacked lowest first. Each may use the layers below it and
never the ones above.

| Path | What |
|---|---|
| `src/snapmap_midi/rawmap/` | the map-authoring core — codec, value builders, documents, reference slots, the blank-map template |
| `src/snapmap_midi/sound/` | the game's sound surface — the palette, event calls, timeline authoring |
| `src/snapmap_midi/music/` | the MIDI domain — parsing, General MIDI tables, voice allocation |
| `src/snapmap_midi/audio/` | local preview — installed event catalog, bank discovery, Wwise decoding, optional offline cache |
| `src/snapmap_midi/ui/` | the desktop workstation — its session, preview manifest, Javascript bridge, native chrome, and markup |
| `src/snapmap_midi/data/` | the shipped sound palette, and curated ear-labels for it |
| `tools/` | maintainer scripts, not part of the installed package |
| `tests/` | the suite, its fixtures, and the MIDI-input generator |
| `docs/` | contributor documentation |

A test asserts each layer imports only downward, so `rawmap/` stays promotable to its own
distribution by a directory move.

## Tests

```bash
python -m pytest
```

Hermetic — a fresh clone runs green with nothing configured, including the headline byte
gate. Four tests compile *against* a saved map to prove that path still works; they carry
the `savedmap` marker and skip when none is configured.

The suite hides `SNAPMAP_MIDI_PATHS` from every test that has not asked for it, so your own
overrides cannot change the result. Without that, a contributor with a palette configured for
their game version ran a different suite than CI did.

Three byte-identical gates guard output, each paired with structural assertions so that when
bytes move you learn *what* moved. Bytes moving while structure holds is the signature of an
accidental key-order change — the map format preserves key insertion order rather than
sorting — and should be treated as a regression, not an improvement.

## License

MIT. See [`LICENSE`](LICENSE).
