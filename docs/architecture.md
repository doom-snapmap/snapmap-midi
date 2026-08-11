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
   audio/     locate, wwise, library        installed catalog, direct preview, fallback
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

### sound/palette.py — the curated pitch index

The shipped palette is the deterministic conversion vocabulary, not a claim that only 890
sounds exist in DOOM. It contains 890 event identifiers across 24 categories and records the
pitch relationships automatic MIDI conversion needs. Resolution is two-step: narrow to a
family, then pick the sound whose nominal pitch is nearest the note, preferring the same pitch
class in another octave over a nearer absolute pitch that would be out of key.

#### Reading a pitch out of a name is ambiguous

A sound spells its note at the end of its name, and b is both a note and a flat marker. For
example, play_fluteb4 can split as play_flute plus b4, which is B4, or play_flut plus eb4,
which is the wrong E-flat interpretation. The instrument stem settles it. The stem is chosen
per category as the prefix that lets the most names parse, and the note is read from what
follows it.

Matching the suffix alone previously read every wind B as a flat a tritone away and treated
play_clave1 as a pitched E from the final letter of clave. A name the curated palette knows
and gives no pitch is unpitched and is not guessed again.

The palette also derives which categories can play a pitch at all. Twelve of the 24 can.
Names such as ins_string and ins_synth look instrument-like but contain no usable pitch index,
so prefix-based classification would silently route an entire channel to nothing.

The installed full-game catalog is deliberately separate. It supplies thousands of exact
manual choices, but those events generally have no instrument family or chromatic coverage.
Automatic mapping therefore remains on the curated index. Selecting an exact full-game event
bypasses pitch resolution and repeats that same event for every MIDI note on the channel.

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
returns finished map bytes. It keeps direct sound-map authoring available without coupling
that job to MIDI parsing or the desktop UI.

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

Exact palette names are accepted directly. Other channel sound assignments must match the
measured Play-event alphabet and maximum length, but validation does not require the current
game install. That keeps sidecars loadable after DOOM moves and permits an explicit mod event;
the UI itself offers the Play events declared by the installed retail catalog.

Validation is load-bearing rather than defensive: this file is meant to be hand-edited, and
every mistake a hand edit makes here is a quiet one. See
[`ui.md`](ui.md#the-settings-sidecar).

### audio/ — installed catalog and optional local preview

This layer supplies local sound metadata to the UI and preview bytes to Web Audio; rawmap
authoring still does not embed or copy audio. locate.py finds a usable DOOM install from the
explicit override or Steam records. wwise.py indexes the language-neutral retail banks and
one localization, resolves event hashes through HIRC to the first available medium, and
decodes the measured Wwise IMA ADPCM format without an external codec.

HIRC stores hashes rather than names, so it cannot enumerate a sound browser. The generated
soundbanksinfo.events file supplies event strings, Wwise paths, buses, environments, numeric
IDs, and compact duration data. The larger soundbanksinfo.xml overlay distinguishes Mixed
duration events from ordinary one-shots. DoomSounds joins the two metadata sources and keeps
every Play event string while separately recording whether it resolves to a standalone local
medium. The reference retail installation contains 7,589 Play events across 7,649 catalog
records; 7,353 support local decoding.

library.py exposes that full catalog lazily, overlays the small curated label set, and falls
back to the shipped 890-name palette when installed metadata is absent. Direct audition and
song preview decode only requested sounds. Engine-only composite events remain exportable,
have a disabled audition control, and are skipped with a warning if used in song preview. The
explicit extract command remains a 890-sound, versioned offline cache; expanding it to every
event would defeat the in-place architecture.

The decoder remains rooted at the retail base soundbank directory and never recursively merges
runtime-injected mod banks, preventing a colliding mod event or media ID from overriding stock
content. Every decoded byte is derived on the user's machine, preview failure cannot stop the
editor or change a compile, and synthetic tests cover parser, provider, localization, fallback,
and mod isolation without redistributing game data.

### `ui/` — the MIDI workstation

A pywebview window over the library. `app.py` opens it and is the only module
that imports pywebview at all — inside a function, so importing the package still works on a
machine that will never open a window. `session.py` holds the loaded file, the settings
document, analysis, statistics, and resolved preview manifest behind a lock, because bridge
calls arrive on separate threads.
`api.py` is the class pywebview exposes to Javascript; every method returns
`{"ok": true, ...}` or `{"ok": false, "error": "..."}` and none of them raises, because an
exception crossing that boundary reaches Javascript as an opaque `Error` with nothing worth
showing. `chrome.py` removes the drawn Windows caption while retaining the native resize,
snap, taskbar and system-menu behaviour. `web/` is hand-written HTML, CSS and Javascript —
no framework, no bundler — and its shared tokens and shell primitives are the exact Snapmap
Plus design contract. Its purpose-trimmed Lucide symbols are embedded as a local SVG sprite; the full icon library
and any runtime dependency stay out of the package, while the upstream license ships beside
the web assets.

Nothing is served and nothing listens. The markup is loaded from the filesystem through a
`file:///` URI, so the window has no address and no port;
`test_product_has_no_network_client` still passes over the whole package.

**The division of labour is the design.** Python decides every conversion fact: which sound
each note resolves to, whether it is sustained, which duration caps and polyphony rules keep
it, which speaker voice it receives, when reuse cuts it off, and which audio samples the
current conversion may request. The same settings document feeds both the preview manifest
and `compile_to_rawmap`.

Javascript owns presentation and transport: it virtualizes the full 0-127 pitch range and
song duration behind native scrollbars, draws synchronized pitch and measure rulers, converts
MIDI ticks through the supplied tempo map, moves and auto-follows the single playhead against
Web Audio's output timestamp rather than its ahead-of-output scheduling clock, schedules
decoded buffers with a rolling look-ahead, and forwards settings changes to the bridge.

Rendering is split by update frequency. The base canvas holds pitch rows, timing lines, notes,
labels, and channel emphasis; separate pointer-transparent canvases hold the moving playhead and
the one hovered note. A playback animation therefore clears and paints only the overlays until
the viewport actually changes. Note glow is pointer-only and remains available while playing;
the playhead never starts an all-events active-note scan.

The preview events are normalized once into 128 pitch buckets sorted by start time. Each bucket
also stores prefix maximum end times, allowing two binary searches to reject events outside the
visible time range before geometry is built. At 100% whole-song overview, the full static roll is
rasterized once when its high-DPI allocation fits a fixed 16-million-pixel budget; vertical wheel
scrolling then blits the visible crop. At inspection zoom, only indexed events overlapping the
visible pitches and time range are drawn. Tiny overview notes are batched as simple paths, while
rounded blocks, outlines, and labels are reserved for geometry large enough to show them.

Theme values, normalized tempo changes, timing-line geometry, and unchanged rulers are cached.
Tempo lookup is binary, grid density is bounded by viewport pixels instead of a fixed thousands-
of-ticks loop, and canvas backing density is capped at 2x. Current-time text updates at its visible
tenth-second precision and the native scrubber at roughly 30 Hz. Scroll and pointer requests are
still coalesced through one pending animation frame. The disabled horizontal-scrollbar cover
retains pointer interception for click and drag, while its non-passive wheel handler forwards
vertical deltas to the pitch viewport. Playback follows in sections: the line sweeps through the
passage and advances the viewport only after crossing its leading threshold, avoiding a static
canvas repaint on every audio frame.

Zoom captures the playhead's viewport coordinate before resizing and restores that coordinate
against the new time scale. The draggable pane separator stores only the preferred channel
width in local browser storage, clamps it against dynamic channel/roll minimums, and resizes the
high-DPI canvases on the next animation frame. Grid, meter, zoom, pane width, and hover are view
state and never enter the conversion settings document. JavaScript names no palette family or game event in source. The small startup catalog comes
from the curated palette; the full installed event catalog crosses a separate lazy bridge only
when the modal opens. Results are folder-indexed and paginated so thousands of events do not
become thousands of live DOM controls.

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
