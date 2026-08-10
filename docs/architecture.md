# Architecture

A contributor-orientation map of how a MIDI file becomes a playable map. For what the
tool does and every knob it exposes see [`capabilities.md`](capabilities.md); for the engine
limit that shapes the whole design see [`limits.md`](limits.md).

## The subsystems

Modules are grouped by subsystem and stacked. Each layer may use the ones below it and never
the ones above, and a test asserts exactly that.

```
   compile.py / cli.py / settings.py / ui/  the product surface
                  |
   music/     midi, gm, voices, analysis    notes: pairing, timbre, density
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

### `music/analysis.py` — the file as the user sees it

`parse_notes` cannot answer what a MIDI file contains. By the time it returns, a program
number has become a family and the channel's own identity — which instrument the composer
asked for — is gone. Choosing an instrument per channel needs the question asked before that
collapse, so this reads the file separately and reports per channel: the program and its
General MIDI name, a per-note histogram, the extremes, whether it is the kit, and the family
the automatic mapping would pick.

It keeps the whole histogram rather than only the extremes, because everything the window
draws is computed from it: how many notes a chosen family cannot reach, and the density strip
described in [`ui.md`](ui.md#reading-the-pitch-ruler). Lowest and highest alone draw the same
bar for two notes as for two thousand, so one stray low note makes a piano part look like it
spans the keyboard.

**The ruler's geometry is computed here, in Python, not in the window's Javascript.**
`ruler_segments` returns percentages. Every failure that geometry can have — an axis that
clips the one family it was built to showcase, a family sharing no note with the channel
drawn as a matter of degree, a drum channel plotted on a pitch axis — is a failure a test can
catch on this side of the bridge and nothing can catch on the other.

### `sound/palette.py` — the sound index

Builds an index of every sound a speaker can play. **The palette ships with the package**;
see [`game-data.md`](game-data.md) for where the line between identifiers and content is
drawn. Resolution is two-step: narrow to the family, then pick the sound whose nominal pitch
is nearest the note's, preferring the same pitch class in another octave over a nearer
absolute pitch that would be out of key.

#### Reading a pitch out of a name is ambiguous

A sound spells its note at the end of its name, and `b` is both a note and a flat marker. So
`play_fluteb4` reads two ways:

| Split | Reads as | Right? |
|---|---|---|
| `play_flute` + `b4` | B4 | yes |
| `play_flut` + `eb4` | E-flat 4 | no — but the pattern cannot tell |

Nothing in the name settles it. **The instrument stem does**, so pitch is resolved against the
palette rather than by pattern: the stem is chosen per category as the prefix that lets the
most names parse, and the note is read from what follows it.

This is not hypothetical. Matching the pattern alone read every wind `b` as a flat a tritone
away, and because the misreads collided with the genuine flats, `ins_flute` ended up holding
36 sounds for 39 names with B absent entirely. `play_clave1` likewise read as a pitched E off
the `e` in "clave". A name the palette knows and gives no pitch to is unpitched and is not
then guessed at; only a name the palette has never seen falls back to the pattern.

Reads are cached per source, because every surface that asks a question about sound asks this
module for the palette first, and a multi-layer compile used to re-parse it per layer.

The palette also answers which categories can play a pitch at all, which the window needs
before it can offer a choice. Twelve of the twenty-four can; `pitched_families` derives that
list from the pitch index rather than from the `ins_` prefix, because `ins_string` and
`ins_synth` carry the prefix and hold no pitched sound between them. A channel routed to one
resolves every note to nothing and vanishes from a map that still loads and plays.

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
returns finished map bytes. The retired `audition` command was a thin caller of it, and this
API is kept partly so that behaviour is still reachable from Python — see
[`ui.md`](ui.md#you-cannot-hear-a-sound-here) for the recipe.

`find_timeline` used to raise when a document had no timeline, with a message telling the
caller to go and find a baseline map containing one. It now authors one, and is called
`ensure_timeline` because it no longer only finds — `SnapMapDocument.find_timeline` keeps
that name for the pure query that returns `None`.

### `compile.py` — orchestration

Runs the stages above in order and returns `(bytes, statistics)`. The statistics dictionary
is not decoration: the byte gates assert on it, so a byte difference reports *what* changed
rather than only *that* something did.

Two of its numbers are there for the window and are worth naming. `long_sustains` counts
notes held past a second and `peak_voices` the largest allocation any layer reached, because
those are the two quantities [`limits.md`](limits.md) actually names. `events` is the biggest
number in the summary and the least useful one to judge a map by: it is dominated by decaying
one-shots, which hold no emitter slot and are immune.

### `settings.py` — one document, two surfaces

The window's whole state as a single JSON document, validated here and turned into keyword
arguments for `compile_to_rawmap`. Both surfaces read it — the window through its session,
the command line through `--settings` — so one document drives either of them and produces
the same bytes. A test compiles a default document and a bare `compile_to_rawmap` call and
compares the two.

It sits at the surface rather than under it because it validates against `sound/palette.py`
and hands arguments to `compile.py`, which are both at or above the layer it would otherwise
occupy. Its defaults mirror `compile_to_rawmap`'s own, named rather than imported, and the
byte gate is what keeps the two from drifting.

Validation is load-bearing rather than defensive: this file is meant to be hand-edited, and
every mistake a hand edit makes here is a quiet one. See
[`ui.md`](ui.md#the-settings-sidecar).

### `ui/` — the control window

A pywebview window over the library, in four files. `app.py` opens it and is the only module
that imports pywebview at all — inside a function, so importing the package still works on a
machine that will never open a window. `session.py` holds the loaded file, the settings
document and the analysis behind a lock, because bridge calls arrive on separate threads.
`api.py` is the class pywebview exposes to Javascript; every method returns
`{"ok": true, ...}` or `{"ok": false, "error": "..."}` and none of them raises, because an
exception crossing that boundary reaches Javascript as an opaque `Error` with nothing worth
showing. `web/` is hand-written HTML, CSS and Javascript — no framework, no bundler.

Nothing is served and nothing listens. The markup is loaded from the filesystem by path, so
the window has no address and no port; `test_product_has_no_network_client` still passes over
the whole package.

**The division of labour is the design.** Python decides everything, including the ruler's
geometry, so the only untestable surface is markup. Javascript positions percentages it is
handed and calls the bridge; it computes no position from a MIDI note and names no sound
family anywhere. Families come from the bridge's catalog, which derives them from the
palette. A family name written into the markup would be a second source of truth, and the
palette is the one that cannot be wrong.

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

It also carries **sixteen persistent integers** in its `variables` block. Those are not user
content that a fresh map legitimately has none of: every engine-saved map to hand carries
exactly sixteen, byte-identical, with the same default names and bounds, while every other
variable kind varies from map to map. That makes them part of the format. A stage authored
without them matched no engine-produced sample.

`allocCount` is emitted as zeros. Which slot counts which kind is **not** established — a
saved map with eighteen booleans carries the eighteen at index 2, not where the key order
would suggest — so the template claims nothing beyond "no names have been handed out", which
is true of a map with no user variables in it.

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
