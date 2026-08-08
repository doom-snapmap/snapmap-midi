# Architecture

A contributor-orientation map of how a MIDI file becomes a playable map. For what the
tool does and every knob it exposes see [`capabilities.md`](capabilities.md); for the engine
limit that shapes the whole design see [`limits.md`](limits.md).

## The subsystems

Modules are grouped by subsystem and stacked. Each layer may use the ones below it and never
the ones above, and a test asserts exactly that.

```
   compile.py / audition.py / cli.py        the product surface
                  |
   music/     midi, gm, voices              notes: pairing, timbre, density
                  |
   sound/     palette, events, timeline     sounds: names, event calls, scheduling
                  |
   rawmap/    codec, values, refs,          maps: bytes, entities, tables
              document, template
```

That is not tidiness for its own sake. A future non-music tool should be able to depend on
`rawmap/` as an ordinary library, and promoting it to its own distribution should be a
directory move. Someone placing sounds by hand should be able to use `sound/` with no MIDI
compiler present. Both stay true only if the layering is proven rather than assumed.

`paths.py` sits outside the stack: it imports nothing internal, so any layer may use it.

## The pipeline

A compile is a straight line. Each stage owns one module, and each hands the next a plain
Python value rather than a shared mutable context.

```
song.mid
   |
   |  music/midi.py     parse the file, pair note-on with note-off
   v
notes  (start, end, pitch, channel, program)
   |
   |  music/gm.py       program number -> sound family; channel 9 -> percussion
   |  sound/palette.py  family + pitch -> the nearest available sound
   v
notes  (+ shader, + family, + sustained?)
   |
   |  music/voices.py   allocate a speaker voice per sustained layer; thin polyphony
   v
notes  (+ voice)
   |
   |  rawmap/template.py  author the blank stage the song is played in
   |  sound/events.py     build the engine event calls: start, stop, fade
   |  sound/timeline.py   write them onto the timeline; add the trigger switch
   v
   |  compile.py          orchestrate the above, return bytes + statistics
   v
rawmap.json
```

### `music/midi.py` — parse and pair

Reads the file with `mido` and pairs each note-on with its matching note-off, producing a
list of notes with a start and an end. An unmatched note-on is closed at the end of the
track rather than dropped: a stuck note is audible and diagnosable, a missing one is not.

Percussion is detected here too. MIDI reserves channel 9 for drums, where the note number
selects an instrument rather than a pitch.

### `music/gm.py` — the General MIDI tables

Two lookup tables and one set. A program number maps to a sound family; a channel-9 note
number maps to a percussion sound; and a set names which families sustain rather than decay.
These are data, not logic — the module has no behaviour worth testing beyond the tables
being well-formed, and one test that every name in them exists in the shipped palette.

### `sound/palette.py` — the sound index

Builds an index of every sound a speaker can play. **The palette ships with the package**;
see [`game-data.md`](game-data.md) for where the line between identifiers and content is
drawn. Resolution is two-step: narrow to the family, then pick the sound whose nominal pitch
is nearest the note's, preferring the same pitch class in another octave over a nearer
absolute pitch that would be out of key.

Reads are cached per source, because both the compiler and the audition builder ask for the
palette and a multi-layer compile used to re-parse it per layer.

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

### `music/voices.py` — allocation and thinning

Allocates a speaker voice per sustained layer. Allocation is per layer, not global, so one
instrument can never steal another's voice or cut it off mid-phrase.

Thinning drops notes when too many would be live at once. It is the mechanism behind
`max_poly` and the family caps; see [`limits.md`](limits.md) for why a dense arrangement
needs it.

### `sound/events.py` — event construction

Builds the engine's event calls: start a sound, stop it, fade it. Nothing here knows about
MIDI; it takes a sound name and a time and emits the call structure.

### `sound/timeline.py` — the authoring API

Writes events onto a timeline entity and adds the switch that triggers it. This is the
reusable layer: `author_sound_timeline` takes a list of `(sound, milliseconds)` pairs and
returns finished map bytes. `audition.py` uses the same API, which is why there is no second
copy of the recipe.

`find_timeline` used to raise when a document had no timeline, with a message telling the
caller to go and find a baseline map containing one. It now authors one.

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
| `document.py` | `SnapMapDocument` — entities, speakers, timelines, connections, cloning |
| `template.py` | the blank map authored from nothing, and the timeline entity |
| `palette_refs.py` | the reference-slot counts for every entity kind this tool authors |

### The blank stage

`template.py` authors a complete, loadable map containing nothing but somewhere to stand.

| Piece | id | Why it is there |
|---|---|---|
| two portal caps | 56, 57 | a module's portals must be joined or capped; uncapped, the map is rejected |
| player start | 61 | somewhere to spawn, and the anchor the switch is placed next to |
| timeline | 62 | the scheduler the song is written onto |

The ids are fixed rather than allocated because `doorsAndCaps` refers to the caps by id, and
because keeping them where an engine-saved map puts them keeps the document comparable to
one.

Building a map from nothing was previously called impractical, on the grounds that the
editor generates cap entities and populates the reference tables when it SAVES and does not
reconstruct them when it LOADS. That is still true. It is an argument for authoring those
tables explicitly, which is what this module does, not for demanding a saved map.

### Reference slots, and why they are injected

The engine validates every entity's reference-bucket sizes against the counts recorded for
its inherit path. A mismatch is not a soft failure — the map is rejected at load.

`SnapMapDocument` takes its table as a constructor argument rather than baking one in, and
an unknown inherit raises `UnknownInheritError` instead of defaulting to zero slots. A
silent zero authors a map the engine refuses to open, with nothing in the tool's output to
say why.

`palette_refs.py` documents which of its pairs are observed in engine-saved maps and which
are inference. Every pair except the switch is observed.

## Proof

The from-scratch path is not only tested; it has been run against the game. A compiled map
was loaded into the live editor with all seven authored entities present at their assigned
ids — including the timeline at 62 — and playtested through the editor → play → exit cycle
without a crash.

Three byte gates guard the output. See [`limits.md`](limits.md#the-byte-gate-honesty-rule).
