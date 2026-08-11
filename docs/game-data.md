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
| the curated 890 sound identifiers used for automatic MIDI mapping | the complete game event catalog |
| category, pitch, drum-map, and 16 curated ear-label records | the speaker declaration or Wwise metadata |
| engine class names and stock declaration paths | any audio or soundbank |
| the structural shape of a map | any saved map |

A sound name such as play_pianoc4 is an identifier. It is how the map format refers to a
sound the game already owns; it carries none of the sound. The General MIDI drum table has
always listed a small set of these identifiers inline. The shipped sound_palette.json applies
the same rule at the conversion layer: 890 names across 24 categories, enough to provide a
stable pitch index and deterministic automatic mapping on a machine with no game installed.

The complete catalog is not copied into this package. When the user opens the sound browser,
snapmap-midi reads the installed game's own soundbanksinfo.events file for event strings,
Wwise folders, buses, environments, durations, and numeric IDs. The generated
soundbanksinfo.xml overlay identifies Infinite and Mixed duration types. This is metadata read
in place from the user's installation, not redistributed package data.

CI enforces the boundary: a committed declaration fails the build, as does JSON that looks
like a saved map. Audio and soundbank files are never accepted.

### Preview and the full catalog read the installed game in place

The workstation finds a copy of DOOM the user already owns and indexes the language-neutral
retail banks plus one installed localization. It does not recursively ingest every language
or mod bank. Every catalog event whose string starts with Play is offered because that string
is a valid game-side SnapMap timeline choice. Stop, Pause, Resume, and Set records are controls
rather than channel sounds and remain excluded.

On the reference retail installation, 7,649 metadata records contain 7,589 unique Play events.
Of those, 7,353 resolve through HIRC to a standalone medium that snapmap-midi can decode for
local audition. The other 236 are mostly interactive music graphs, state transitions, legacy
references, or DLC entries: the game can execute their event strings, but there is no single
local sample for this decoder to render. The explorer marks that distinction and disables
only the audition control. The exact counts can vary with edition and localization.

The event string is the value written into a SnapMap timeline sound call. The numeric Wwise ID
is shown for search and diagnostics, but it cannot replace the event string in rawmap export.

The banks remain where Steam installed them. Opening the browser reads names and hierarchy;
audition, root analysis, and full-song preview decode only requested media into memory. Root
analysis examines every available leaf of a selected exact event and rejects leaves that do not
agree on a stable musical pitch.

Normal use creates no audio library on disk. It may create
`%LOCALAPPDATA%\snapmap-midi\pitch-profiles-v1.json`, a small numeric cache containing event
identity, media signature, root/confidence, and rejection state. It contains no PCM, Wwise
payload, event catalog, or other game content, and can be deleted safely; it is rebuilt lazily.
Nothing is downloaded, packaged, committed, or copied into an export.

The optional `snapmap-midi extract` command can still build a resumable offline audio cache
under `%LOCALAPPDATA%\snapmap-midi\sounds`. It is roughly 450 MB, safe to delete, and
intentionally contains only the 890 curated palette sounds. Expanding it to the full catalog
would recreate the multi-gigabyte duplication this direct-bank design avoids. The workstation
never runs extraction as a setup step.

No compile depends on either preview source or on the numeric profile cache. With no game and
no valid offline cache, the browser falls back to the curated 890-name palette, assignments and
export still work, and only audio preview and new arbitrary-event root detection are unavailable.
Relative pitch references still work because they are derived from the imported MIDI range.
A sidecar containing a valid Play event string or an already saved root/reference remains
loadable if DOOM is later moved or temporarily absent. If an installed in-game-only event is
assigned to a channel, full-song preview skips that event and raises a notification while export
keeps the exact requested string.

Normal discovery is deliberately limited to the retail soundbank directory under the DOOM
base directory. It does not recursively scan the mods directory, so dynamically injected
DoomForge banks cannot shadow a stock event or media ID in workstation preview. Supporting
custom mod sounds later requires an explicit catalog, SnapMap-compatibility rules, and
deterministic bank precedence rather than silently merging every bank found under the game
directory. See the UI documentation for source and fallback behavior.

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
print(paths.pitch_profile_cache())  # small numeric root-profile cache; never audio
print(paths.baseline_configured())  # what the savedmap-marked tests ask
```

`baseline_configured()` is what the test suite calls to decide whether to run the four
tests that compile against a saved map. A path that is set but points at a missing file
counts as unconfigured — the resolvers check existence, not just presence of the key.
