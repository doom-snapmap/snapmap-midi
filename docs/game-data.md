# Game data — the inputs you supply

This tool ships no game data, and it never will. For what it does with these inputs see
[`capabilities.md`](capabilities.md); for setup end to end see
[`contributing.md`](contributing.md).

## Why nothing is bundled

Two of the three inputs below are files from an installed copy of the game. They are the
game's content, not ours, and redistributing them is not ours to do. So the tool hardcodes
no location for any of them: it names each one logically and asks you where it is.

The practical upside is that nothing resolves against a fixed layout. The package runs the
same wherever it is installed, on any machine, with your files wherever you keep them.

## The three inputs

| Logical name | What it is | Needed for |
|---|---|---|
| `palette_decl` | the declaration listing every sound a speaker may play | compiling anything |
| `baseline_map` | a saved map containing a timeline entity | compiling anything |
| `groove_fixture` | a byte-identical regression artifact for the timeline API | one test only |

### `palette_decl`

The sound palette. `palette.py` reads it once and builds the index that maps a family and a
pitch to an actual sound name. Without it, `PaletteUnavailableError` — deliberately, rather
than an empty index that would compile to a silent map and look like success.

### `baseline_map`

Any saved map that already contains a timeline entity.

It is required, and the reason is structural rather than incidental: the timeline class is
special and cannot be placed from the palette. Authoring therefore fills an existing
timeline instead of creating one. Make a map in the editor, drop a timeline in it, save it,
and point at that file.

### `groove_fixture`

**Not distributed, and it will never resolve in a fresh checkout.**

It is a byte-identical artifact recorded from an arrangement that was verified in game — the
regression anchor for the timeline authoring API. It is derived from game content, so it
stays where it was made.

One test needs it. In a fresh checkout that test **skips, permanently, by design**. If you
see it skipping, nothing is broken. The hermetic byte gate covers the same code path with
synthetic data and does run everywhere, so the suite still has real teeth without it.

## Configuring them

One environment variable, `SNAPMAP_MIDI_PATHS`, holding a JSON object. Inline:

```bash
SNAPMAP_MIDI_PATHS='{"palette_decl": "/path/to/palette.decl", "baseline_map": "/path/to/baseline.json"}'
```

Or a path to a file containing the same object, which is easier to live with:

```bash
SNAPMAP_MIDI_PATHS=/path/to/snapmap-midi-paths.json
```

```json
{
  "palette_decl": "D:/games/doom/.../2dspeakerdeclinspector.decl",
  "baseline_map": "D:/maps/timeline-baseline.json"
}
```

Keys you leave out simply resolve to `None`. Every resolver returns `None` rather than
raising, so a partially configured setup degrades to skipped tests instead of a crash.

You can skip configuration entirely and pass `--baseline` per invocation, but the palette
has no flag — compiling needs `palette_decl` configured.

## Checking your setup

```python
from snapmap_midi import paths

print(paths.palette_decl())  # None if unset or the file is missing
print(paths.baseline_map())
print(paths.gamedata_configured())  # True when both of the above resolve
```

`gamedata_configured()` is what the test suite calls to decide whether to run the game-data
tests or skip them. A path that is set but points at a missing file counts as unconfigured —
the resolvers check existence, not just presence of the key.
