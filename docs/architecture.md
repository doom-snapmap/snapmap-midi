# Architecture

A contributor-orientation map of how a MIDI file becomes a playable map. For what the
tool does and every knob it exposes see [`capabilities.md`](capabilities.md); for the engine
limit that shapes the whole design see [`limits.md`](limits.md).

## The pipeline

A compile is a straight line. Each stage owns one module, and each hands the next a plain
Python value rather than a shared mutable context.

```
song.mid
   |
   |  midi.py        parse the file, pair note-on with note-off
   v
notes  (start, end, pitch, channel, program)
   |
   |  gm.py          program number -> sound family; channel 9 -> percussion
   |  palette.py     family + pitch -> the nearest available sound
   v
notes  (+ shader, + family, + sustained?)
   |
   |  voices.py      allocate a speaker voice per sustained layer; thin polyphony
   v
notes  (+ voice)
   |
   |  events.py      build the engine event calls: start, stop, fade
   |  timeline.py    write them onto a timeline entity; add the trigger switch
   v
   |  compile.py     orchestrate the above, return bytes + statistics
   v
song.json
```

### `midi.py` — parse and pair

Reads the file with `mido` and pairs each note-on with its matching note-off, producing a
list of notes with a start and an end. An unmatched note-on is closed at the end of the
track rather than dropped: a stuck note is audible and diagnosable, a missing one is not.

Percussion is detected here too. MIDI reserves channel 9 for drums, where the note number
selects an instrument rather than a pitch.

### `gm.py` — the General MIDI tables

Two lookup tables and one set. A program number maps to a sound family; a channel-9 note
number maps to a percussion sound; and a set names which families sustain rather than decay.
These are data, not logic — the module has no behaviour worth testing beyond the tables
being well-formed.

### `palette.py` — the sound index

Builds an index of every sound a speaker can play, read from the palette declaration the
user supplies (see [`game-data.md`](game-data.md)). Resolution is two-step: narrow to the
family, then pick the sound whose nominal pitch is nearest the note's.

Raises `PaletteUnavailableError` when no palette has been configured, rather than returning
an empty index. An empty index would compile to a silent map, which looks like success.

### The split that defines the design

Every note goes down one of two paths, and the choice is the single most important decision
in the compiler.

- **Decaying sounds and drums** fade on their own. They are fired and forgotten, layered
  polyphonically onto the timeline entity itself. They need no voice and no note-off.
- **Sustained notes** hold at full volume until something stops them. Each one gets a
  dedicated speaker voice so that it *can* be stopped, plus an explicit note-off event when
  the note ends.

A sustained note with no note-off rings its entire sample and smears into the next phrase.
That is the failure this split exists to prevent.

### `voices.py` — allocation and thinning

Allocates a speaker voice per sustained layer. Allocation is per layer, not global, so one
instrument can never steal another's voice or cut it off mid-phrase.

Thinning drops notes when too many would be live at once. It is the mechanism behind
`max_poly` and the family caps; see [`limits.md`](limits.md) for why a dense arrangement
needs it.

### `events.py` — event construction

Builds the engine's event calls: start a sound, stop it, fade it. Nothing here knows about
MIDI; it takes a sound name and a time and emits the call structure.

### `timeline.py` — the authoring API

Writes events onto a timeline entity and adds the switch that triggers it. This is the
reusable layer: `author_sound_timeline` takes baseline bytes and a list of
`(sound, milliseconds)` pairs and returns finished map bytes. `audition.py` uses the same
API, which is why there is no second copy of the recipe.

The baseline map is required because the timeline class cannot be placed from the palette.
Authoring fills an existing timeline rather than creating one.

### `compile.py` — orchestration

Runs the stages above in order and returns `(bytes, statistics)`. The statistics dictionary
is not decoration: the byte gates assert on it, so a byte difference reports *what* changed
rather than only *that* something did.

## The authoring core

`src/snapmap_midi/rawmap/` is a general SnapMap document library. It knows nothing about
music.

| Module | Responsibility |
|---|---|
| `codec.py` | serialize and deserialize the map format |
| `values.py` | the `Vec3`, `Mat2D`, `Mat3`, `Pointer` value builders |
| `refs.py` | reference-slot authoring and the unbound sentinels |
| `document.py` | `SnapMapDocument` — entities, speakers, connections, cloning |
| `palette_refs.py` | the reference-slot counts for the three entity kinds this tool authors |

**A test enforces the layering.** `test_core_does_not_import_the_music_layer` asserts that
nothing under `rawmap/` imports `midi`, `gm`, `timeline`, `compile`, `voices`, `events`,
`palette`, `audition` or `cli`.

That is not tidiness for its own sake. A future non-music tool should be able to depend on
this core as an ordinary library, and promoting it to its own distribution should be a
directory move. That stays true only if the layering is proven rather than assumed.

### Reference slots, and why they are injected

The engine validates every entity's reference-bucket sizes against the counts recorded for
its inherit path. A mismatch is not a soft failure — the map is rejected at load.

`SnapMapDocument` takes its table as a constructor argument rather than baking one in, and
an unknown inherit raises `UnknownInheritError` instead of defaulting to zero slots. A
silent zero authors a map the engine refuses to open, with nothing in the tool's output to
say why.

`palette_refs.py` is deliberately small — this tool authors exactly three kinds of entity —
and documents which of its pairs are observed in engine-saved maps and which are inference.
