# snapmap-midi

**Compile a standard MIDI file into a playable music map for DOOM (2016)'s SnapMap editor.**

Feed it a `.mid` and a baseline map; it returns a map whose switch plays the song. Seven real
songs have been verified end to end in game.

**This repo ships NO game data.** The sound palette and the baseline map are inputs you
supply from your own installed copy — see [`docs/game-data.md`](docs/game-data.md). Every
line here is our own implementation, built from our own reverse-engineering of the map
format; no decompiled or copied content.

## Quick start

Python 3.12 or newer. `mido` is the only dependency and pip fetches it.

```bash
pip install git+https://github.com/doom-snapmap/snapmap-midi.git
```

Point it at the two inputs it needs from your game, once:

```bash
SNAPMAP_MIDI_PATHS='{"palette_decl": "/path/to/palette.decl", "baseline_map": "/path/to/baseline.json"}'
```

Then compile:

```bash
snapmap-midi compile song.mid --out song.json
```

Load the result in the editor and press the switch.

Not sure what a sound category actually contains? Build a map that plays every sound in it
in sequence and prints a numbered legend:

```bash
snapmap-midi audition ins_noise --out audition.json
```

## Documentation

| Doc | What's in it |
|---|---|
| [`docs/capabilities.md`](docs/capabilities.md) | every command, flag and tuning lever |
| [`docs/game-data.md`](docs/game-data.md) | the inputs you supply, and how to configure them |
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

raw, stats = compile_to_rawmap("song.mid", baseline_bytes, button_name="my-song")
```

The map-authoring core underneath knows nothing about music and is usable on its own — see
[`docs/architecture.md`](docs/architecture.md).

## Repository layout

| Path | What |
|---|---|
| `src/snapmap_midi/` | the package: the compile pipeline and the CLI |
| `src/snapmap_midi/rawmap/` | the map-authoring core — codec, value builders, documents, reference slots |
| `src/snapmap_midi/data/` | curated ear-labels for the sound palette (reference material) |
| `tests/` | the suite, its fixtures, and the MIDI-input generator |
| `docs/` | contributor documentation |

`rawmap/` is kept independently reusable; a test asserts it never imports the music layer.

## Tests

```bash
python -m pytest
```

Hermetic by default — a fresh clone runs green with no game data. Tests needing real game
data carry the `gamedata` marker and skip when none is configured.

Two byte-identical gates guard output: one rebuilds an arrangement verified in game, the
other a full compile. Both are paired with structural assertions, so when bytes move you
learn *what* moved. Bytes moving while structure holds is the signature of an accidental
key-order change — the map format preserves key insertion order rather than sorting — and
should be treated as a regression, not an improvement.

## License

MIT. See [`LICENSE`](LICENSE).
