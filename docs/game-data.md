# Game data — what ships, what doesn't

This tool ships no game content, and it never will. It also asks you for nothing. Those two
statements used to be in tension; this page is how they were reconciled. For what the tool
does with any of it see [`capabilities.md`](capabilities.md); for setup end to end see
[`contributing.md`](contributing.md).

## Nothing is required

A compile takes a MIDI file. That is the entire input list.

```bash
snapmap-midi compile song.mid
```

It used to take two more, both extracted from an installed copy of the game, and both
mandatory: a speaker declaration to resolve sounds against, and a saved map to inherit a
timeline entity from. A fresh install could not compile anything until someone went digging.

## The line: identifiers ship, content does not

| Ships with the package | Never ships |
|---|---|
| sound **names**, grouped by category | the speaker declaration itself |
| engine class names and stock declaration paths | any audio |
| the structural shape of a map | any saved map |

A sound name like `play_pianoc4` is an identifier. It is how the map format refers to a
sound the game already owns; it carries none of the sound. The General MIDI drum table in
`music/gm.py` has always listed twenty of these inline, and nobody considered that
redistribution — because it isn't. `data/sound_palette.json` is the same thing at full size:
890 names across 24 categories.

The declaration those names were read out of is game content and is not in this repository.
CI enforces that: a committed `.decl` fails the build, as does any JSON that looks like a
map.

### Preview reads the installed game in place

The MIDI workstation finds a copy of DOOM the user already owns, indexes the stock retail
soundbank tables, and decodes only the sounds selected by the current song. The banks remain
where Steam installed them and decoded samples remain in memory; normal preview creates no
audio library on disk. Nothing is downloaded, packaged, committed, or copied into an export.

The optional `snapmap-midi extract` command can still build a resumable offline cache under
`%LOCALAPPDATA%\snapmap-midi\sounds`. It is roughly 450 MB, safe to delete, and used only as
a fallback when the installed game is unavailable. The workstation never runs extraction as a
setup step.

No compile depends on either preview source. With no game and no valid offline cache, the only
missing capability is playing the complete converted song in the workstation. The sound pickers
still expose all 890 names and export still writes references to the sounds the arrangement uses.

Normal discovery is deliberately limited to `<DOOM>\base\sound\soundbanks\pc`. It does not
recursively scan `<DOOM>\mods`, so dynamically injected DoomForge banks cannot shadow a stock
event or media ID in workstation preview. Supporting custom mod sounds later requires an explicit
catalog, SnapMap-compatibility rules, and deterministic bank precedence rather than silently
merging every bank found under the game directory. See
[`ui.md`](ui.md#previewing-the-song) for source and fallback behaviour.

### Regenerating the palette

If your game version's sounds differ, regenerate from your own copy:

```bash
python tools/build_sound_palette.py path/to/speaker.decl
```

`tools/` is a maintainer directory and is not part of the installed package. The script
reads a declaration and writes the name list; it never copies the declaration anywhere.

## The map is authored, not inherited

The song is staged in a blank room the compiler writes itself — two portal caps, a player
spawn, a timeline and the switch that fires it. See
[`architecture.md`](architecture.md#the-blank-stage) for the shape and why each piece is
there.

The timeline was the whole reason a baseline map used to be mandatory. `idTarget_Timeline`
cannot be placed from the editor's entity palette, which was read as "a timeline cannot be
created". That conflated making the engine **spawn** one at runtime — genuinely out of reach
from outside the game — with **describing** one in a saved map, which is only schema. In a
saved map a timeline is an ordinary entity:

| Field | Value | Where it came from |
|---|---|---|
| `className` | `idTarget_Timeline` | observed in engine-saved maps |
| `inherit` | `snapmaps/unknown` | the portable stock declaration engine-saved maps settle on |
| reference slots | `(0, 0)` | read out of an engine-saved map; the cheapest entry in the table |

A map authored this way has been loaded into the live editor with every entity at its
assigned id, and playtested through the editor → play → exit cycle without a crash.

The same rule — match what the engine writes — decides the rest of the document. It is why
the blank stage carries sixteen persistent integers in its `variables` block: every
engine-saved map to hand carries exactly sixteen, byte-identical, while every other variable
kind varies between maps, so they are part of the format rather than one author's editor
history. See [`architecture.md`](architecture.md#the-blank-stage).

## The optional overrides

None of these is needed for ordinary use. They exist for people doing something unusual.

| Logical name | What it does | When you'd want it |
|---|---|---|
| `palette_decl` | read this declaration instead of the shipped palette | a game version whose sounds differ |
| `baseline_map` | add the song to this saved map instead of authoring a blank one | you have a level and want music in it |
| `groove_fixture` | the byte-identical regression artifact for the timeline API | one test, and it is not distributed |
| `doom_install` | read preview audio from this game directory instead of searching Steam | a portable, moved, or second-machine install |

Configure them with one environment variable, `SNAPMAP_MIDI_PATHS`, holding a JSON object.
Inline:

```bash
SNAPMAP_MIDI_PATHS='{"baseline_map": "/path/to/my-level.json"}'
```

Or a path to a file containing the same object:

```bash
SNAPMAP_MIDI_PATHS=/path/to/snapmap-midi-paths.json
```

```json
{
  "baseline_map": "D:/maps/my-level.json",
  "doom_install": "D:/SteamLibrary/steamapps/common/DOOM"
}
```

`baseline_map` also has a per-invocation flag, `--baseline`, which wins over the configured
value. Keys you leave out resolve to `None`, which is the ordinary state rather than an
error.

### `groove_fixture`

**Not distributed, and it will never resolve in a fresh checkout.**

It is a byte-identical artifact recorded from an arrangement that was verified in game — the
regression anchor for the timeline authoring API. It is derived from game content, so it
stays where it was made.

One test needs it. In a fresh checkout that test **skips, permanently, by design**. If you
see it skipping, nothing is broken. Two byte gates that need nothing at all cover the same
code paths and do run everywhere.

## Checking your setup

```python
from snapmap_midi import paths

print(paths.rawmap_destination())  # where a compiled map will be written
print(paths.baseline_map())  # None unless you configured one
print(paths.doom_install())  # explicit direct-preview override, or None for Steam discovery
print(paths.sound_cache())  # optional offline-cache location
print(paths.baseline_configured())  # what the savedmap-marked tests ask
```

`baseline_configured()` is what the test suite calls to decide whether to run the four
tests that compile against a saved map. A path that is set but points at a missing file
counts as unconfigured — the resolvers check existence, not just presence of the key.
