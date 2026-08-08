# snapmap-midi

**Compile a standard MIDI file into a playable music map for DOOM (2016)'s SnapMap editor.**

Feed it a `.mid`; it builds a room with a switch that plays the song. Seven real songs have
been verified end to end in game.

**This repo ships NO game data** — no declaration files, no saved maps, no audio. It ships
the *names* of the sounds the game already has, which is what lets it work out of the box.
Every line here is our own implementation, built from our own reverse-engineering of the map
format; no decompiled or copied content.

## Install

You need **Python 3.12 or newer**. Nothing else — `mido` is the only dependency and pip
fetches it for you. Check what you have:

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

Skip to [Compile a song](#compile-a-song). If that command errors with
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

**5. Check it worked:**

```bash
snapmap-midi --help
```

### Coming back later

The environment persists, but **activation does not** — it lasts only for that terminal
window. Next time, `cd` back and run the activate line from step 3 again. Then carry on.

## Update, find, remove

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

Not sure what a sound category actually contains? Build a map that plays every sound in it
in sequence and prints a numbered legend:

```bash
snapmap-midi audition ins_noise
```

## Documentation

| Doc | What's in it |
|---|---|
| [`docs/capabilities.md`](docs/capabilities.md) | every command, flag and tuning lever |
| [`docs/game-data.md`](docs/game-data.md) | what ships, what doesn't, and the optional overrides |
| [`docs/architecture.md`](docs/architecture.md) | how a MIDI file becomes a map |
| [`docs/limits.md`](docs/limits.md) | the engine limit worth knowing, and the byte-gate rule |
| [`docs/contributing.md`](docs/contributing.md) | fresh machine to open pull request |

## How it works

A MIDI file streams note-on and note-off events. snapmap-midi pairs them into notes, maps
each note's instrument program to a family of available sounds and its pitch to the nearest
sound in that family, then schedules the result as timed events on a timeline entity.

The arrangement then splits in two, because the halves must be scheduled differently:

- **Decaying sounds and drums** fade on their own. They are fired and forgotten, layered
  polyphonically on the timeline entity itself.
- **Sustained notes** hold at full volume until something stops them. Each gets a dedicated
  speaker voice so it *can* be stopped, and an explicit note-off when the note ends.

That distinction is the whole design. A sustained note with no note-off rings its entire
sample and smears into the next phrase.

Voices are allocated per layer, so one instrument can never steal another's voice or cut it
off mid-phrase.

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

raw, stats = compile_to_rawmap("song.mid", button_name="my-song")
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
