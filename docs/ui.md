# The control window

Choosing an instrument for each channel, remapping the drum kit, and seeing what a compile
will produce before writing it. For the command line and every tuning lever see
[`capabilities.md`](capabilities.md); for the engine limit the Tuning panel exists to work
around see [`limits.md`](limits.md).

The window decides nothing the command line cannot. Both read the same settings document, and
`snapmap-midi compile song.mid --settings song.mid.snapmap.json` produces the bytes the
window's Export button would have written. The window is where a choice gets made; the
command line is where a choice already made gets replayed.

## Opening it

```bash
snapmap-midi
```

The name with nothing after it opens the window. To open on a song, or on a settings file
you already have:

```bash
snapmap-midi ui song.mid
snapmap-midi ui song.mid --settings D:/songs/bach.mid.snapmap.json
```

`snapmap-midi compile song.mid` is unchanged and needs no window.

Where the package is installed but its scripts folder is not on `PATH`, the module form works
the same: `python -m snapmap_midi`.

A bad path still opens. `snapmap-midi ui missing.mid` gives you a window that says what went
wrong and an Open button, because a person who came for a window has no console to read a
traceback in.

### What it needs installed

The window is pywebview hosting local markup in the platform's own browser engine. **On
Windows it is an ordinary dependency and pip has already fetched it.** Everywhere else it is
the `[ui]` extra:

```bash
pip install "snapmap-midi[ui]"
```

That split is deliberate. The map loader this tool writes to is Windows-only, so a window on
another platform has nowhere to hand its output; the extra exists for anyone who wants it
anyway. If pywebview is missing, the window says so and names that command rather than
printing an import error.

On a fresh Windows machine there is a second thing to install and it fails differently:
pywebview imports perfectly cleanly without the **Microsoft Edge WebView2 runtime** and fails
when the window tries to open. That message names the runtime, because a stack trace is not
an answer for someone who had to be told to tick "Add python.exe to PATH".

Nothing is served and nothing listens. The markup is loaded from the filesystem by path, so
the window has no address and no port.

Where there is no display at all — CI, a container, a shell over a remote connection — a bare
`snapmap-midi` prints the usage text instead of opening. `webview.start()` blocks until the
window closes, and a window nobody can see never closes, so the alternative is a command that
hangs forever having printed nothing.

## The four panels

### Channels

One row per channel that plays a note, in channel order. The row names the channel, the
General MIDI instrument the file asked for, and how many notes it plays; then it offers an
instrument, a mute, and the ruler described below.

The instrument dropdown's first entry is **Automatic**, naming the family the General MIDI
mapping would pick. It is selected until you choose something else, and choosing it again is
the way back — without it, reopening the file would be the only way to undo a pick.

**Only 12 of the palette's 24 categories can play a pitch, so only those 12 are offered.**

| Family | Reach |
|---|---|
| `ins_piano` | 21–108 |
| `ins_brass_bells` | 72–112 |
| `ins_marimba` | 36–96 |
| `ins_violin` | 55–100 |
| `ins_flute` | 59–97 |
| `ins_trumpet` | 52–87 |
| `ins_guitar` | 40–82 |
| `ins_horns` | 34–77 |
| `ins_pulse`, `ins_sine`, `ins_square`, `ins_tri` | 36–67 |

Three of those — `ins_square`, `ins_tri` and `ins_brass_bells` — are unreachable by the
automatic mapping. No General MIDI program resolves to any of them, so the picker is the only
way to address them at all. That is most of the argument for having a picker.

**`ins_string` and `ins_synth` are not offered, and their names are why that has to be said
out loud.** Both carry the `ins_` prefix; `ins_string` is even listed among the sustained
families beside the violins. Neither holds a single sound with a pitch in its name.
Route a channel to one and every note resolves to nothing, the part disappears, and the map
still loads and plays — with no error anywhere, because nothing downstream can tell a family
that had no sound from a part somebody muted on purpose. Splitting families by name prefix
gets this exactly wrong. The list is derived from which categories actually have a pitch
index, which is why it cannot be wrong.

Mute silences a channel without deleting anything. A muted note is a note you asked for, so
it is not counted as `dropped` — that number is for notes the palette had no sound for, which
is a different problem and worth reporting.

### Drums

MIDI reserves channel 9 for percussion, where the note number picks an instrument rather than
a pitch. The panel's one switch decides whether this file's channel 9 is a kit: **Automatic**
uses the same heuristic the compiler does, and On and Off override it. Changing it re-reads
the file, so the Channels row for channel 9 and the compile never describe different
arrangements.

Below that is one row per drum key the file actually uses — not all 128 — naming the key, its
General MIDI percussion name, and the sound it will play. The default entry restores the
built-in table's own answer for that key. A key the table has no sound for is marked, and a
key with no sound plays nothing.

**The picker offers 70 sounds: `ins_noise` plus `ins_percussion`, and nothing else.** The
unpitched half of the palette is 365 sounds, and most of it is ambience, gore and interface
noise. A pitched sound would play one fixed note under every hit. A looping ambience — the
names ending `_lp` — is fired as a one-shot and never told to stop, so it holds its emitter
open until the engine recycles the slot out from under something else. That recycling is the
failure this tool schedules its whole output around ([`limits.md`](limits.md)), and a picker
offering those sounds would have been its easiest source.

**16 of the 70 carry an ear-label, and all 16 are in `ins_noise`.** The labels exist because
the names lie: `play_noise_tom` is a knock on a wooden door, `play_noise_crash` is a shaker.
A picker showing only names sends people to the tom for a tom. The other 54 sounds show their
names, which is all anybody knows about them — see [below](#you-cannot-hear-a-sound-here) for
why adding to that list is now a Python job.

### Tuning

Every lever here reduces how many sounds are live at the same moment, which is the only thing
they have in common and the reason they exist. **Read [`limits.md`](limits.md) before
touching any of them** — a sparse arrangement needs none, and a dense one usually needs one.

Max speakers, release and hard stop are global. Max polyphony and cap sustain thin and
truncate across the board. Bass pitch and bass cap target the low register, which is usually
where the long notes are; they are two halves of one lever and are shown together for that
reason.

The lower half lists the families this song actually uses, each with a decaying switch and a
cap. Moving a family to the decaying path is the strongest single move available: a decaying
sound holds no emitter slot at all, so it is immune to the recycling limit outright. It also
stops being stoppable, which is the trade.

**`max_events` is not here and will not be.** The compiler implements it as
`decaying_events[:max_events]`, which truncates the one-shot list in time order — the drums
stop partway through the song and stay stopped. Behind a control that reads as a density
limit that is a trap, so it stays a command-line flag where you have to type it on purpose.

### Export

The button label, the output folder and an optional baseline map, then the statistics, then
Dry run and Export map.

Dry run compiles without writing anything. It runs on every change anyway; the button is for
when you want to be sure the numbers on screen are the numbers for what is on screen now.

The statistics are the same ones `snapmap-midi compile` prints:

| Number | What it tells you |
|---|---|
| notes, decaying, sustained | the shape of the arrangement |
| dropped | notes the palette had no sound for — a real problem, not a tuning choice |
| long sustains | notes held longer than a second, the ones exposed to the emitter limit |
| peak voices / max speakers | how close the densest passage came to the ceiling |
| events | total timeline events; dominated by one-shots, which are immune |

`events` is listed last on purpose. It is the biggest number and the least informative one: a
drum-heavy song can have an enormous event count and be nowhere near the limit, because every
one of those one-shots holds no emitter slot. An earlier draft of this window warned on that
number, which fired on songs that could not fail and stayed silent on the three-voice pad that
would.

Export writes `rawmap.json`, and it says whether it replaced a map that was already there.
The loader reads exactly one file at one hardcoded path, so a button that writes it invites
repeated use in a way a typed command did not.

## Warnings

The strip under the panels carries problems rather than observations, and each one names a
cause, the number that decides whether to care, and the lever that changes it. Nothing will
play because every channel is muted. So many notes have no sound, and which drum keys are
unmapped. So many sustained notes hold longer than a second. The busiest channel used every
speaker it had, so its densest passages were thinned.

**The thresholds are [`limits.md`](limits.md)'s, not invented here.** That is the whole
reason this list is short. An earlier draft warned on total event count, which is dominated
by decaying one-shots — the ones that hold no emitter slot and are immune — so it fired on
drum-heavy songs that could not hit the limit and stayed silent on the three-voice pad that
would.

Channels you have muted are skipped. Telling you that a part you just silenced cannot reach
its notes is noise about a decision already made.

Past three affected channels the range sentences collapse into the worst one plus a count,
ranked by how many notes are actually displaced. Sixteen near-identical sentences in a status
bar is not information, and each row's ruler already carries its own detail.

## Reading the pitch ruler

Each melodic channel gets a strip. **Every strip uses the same axis, MIDI note 0 to 127**, so
two rows can be compared by eye — a lead sitting an octave above the bass looks like it. The
C-octave gridlines are labelled once beneath the list, in note names, because the warnings
speak note names too and the window should have one vocabulary rather than two.

Three things are drawn on it.

**The cells are the channel's notes.** One per distinct pitch, and the opacity carries how
often that pitch is played. That density is the point. A bar drawn from lowest to highest
draws the same rectangle for two notes as for two thousand, so one stray low note makes a
piano part look like it spans the keyboard; the strip shows where the part actually sits.

**The hatched track behind them is the chosen family's reach** — the lowest and highest note
that family has a sound for. It moves when you change the instrument.

**Amber cells are notes outside that reach.** They are not lost notes. The resolver never
fails outside a range: it prefers the same pitch class an octave away, and falls back to the
nearest pitch it has when that class is absent entirely. So an amber cell is a note that will
play, and will not be the note that was written. The sentence under the row says how many, out
of how many.

**A red outline around the track means the family shares no note with the channel at all.**
That is a different thing from overhang and must not read as more of it. Zero overlap means
every note in the part is transposed and the melody is gone, so it is drawn as a state rather
than as a darker shade of a warning.

The percussion channel has no ruler. Its lowest and highest are key numbers rather than
pitches — on channel 9 a note number picks an instrument — so drawing them on a pitch axis
would assert something false about what the channel plays. Its row shows the key count and how
many of them are unmapped instead.

## The settings sidecar

Everything the window holds is one JSON document: the song, the switch label, the output
folder, the per-channel instruments and mutes, the drum keys, and every tuning lever. Both
surfaces read it, so one document drives either of them and produces the same bytes:

```bash
snapmap-midi ui song.mid --settings song.mid.snapmap.json
snapmap-midi compile song.mid --settings song.mid.snapmap.json
```

**Where the file belongs is a convention, and `settings.sidecar_path` is the one place that
spells it:** beside the song, named after it.

```
D:/songs/bach.mid
D:/songs/bach.mid.snapmap.json
```

A convention rather than a Save As, because a dialog means two more error paths and a file
you have to keep track of. The song is the thing you already have open, and a settings file
that travels beside it is one nobody has to find again. The name is the song's
whole filename with a suffix, not its stem — `bach.mid` and `bach.midi` are two different
songs and would otherwise silently share one set of instruments.

**Nothing writes it for you yet.** Export writes `rawmap.json` and nothing else, so closing
the window loses the choices in it. Until the window saves the document itself, a settings
file is one you write — by hand against the schema below, or from Python:

```python
from snapmap_midi import settings

doc = settings.merge(
    settings.defaults("D:/songs/bach.mid"),
    {"channels": {"0": {"family": "ins_marimba"}}, "tuning": {"max_speakers": 8}},
)
settings.save(doc, settings.sidecar_path("D:/songs/bach.mid"))
```

`save` validates before it opens anything, so an invalid document cannot reach the disk.
Writing one would move the failure to the next session, against a file this tool wrote
itself, with nothing to point at.

**A flag you type wins over the file; the file wins over the built-in defaults.** Three
sources in one order, and the order is the feature: a settings file is a decision made
earlier and saved, a flag is a decision being made right now. An earlier draft had argparse's
own defaults win, which meant `max_speakers: 8` in a file someone had deliberately loaded
compiled at 32 with no flag anywhere on the command line.

### The schema

```json
{
  "version": 1,
  "midi": "song.mid",
  "button": "snapmap-midi-song",
  "out_dir": null,
  "baseline": null,
  "channels": {
    "0": {"family": "ins_marimba", "muted": false},
    "3": {"family": null, "muted": true}
  },
  "drums": "auto",
  "drum_keys": {"38": "play_noise_clap"},
  "tuning": {
    "max_speakers": 32,
    "release_s": 0.1,
    "hard_stop": false,
    "max_poly": null,
    "cap_sustain_ms": null,
    "bass_pitch": 78,
    "bass_cap_ms": null,
    "decaying_families": [],
    "family_caps": {}
  }
}
```

`channels` and `drum_keys` are shown filled in; both are empty in a fresh document. Every
other value above is the default, and **the defaults are `compile_to_rawmap`'s own to the
byte.** A test compiles a default document and a bare `compile_to_rawmap` call and compares
the two, because a default that disagreed would mean exporting from the window and typing the
command produced different maps for a lever nobody had touched.

`family: null` leaves the automatic choice alone, which is what lets a channel be muted
without also being given an instrument. Channel and drum-key numbers are strings because JSON
has no integer keys. `drums` is `auto`, `on` or `off`.

**This file is meant to be edited by hand, which is why validation is load-bearing rather
than defensive.** It is written indented for that reason. Missing keys take their defaults,
because deleting a line means you are not setting it. A *wrong* value is refused by name,
because every mistake a hand edit makes here is a quiet one: an unpitched family compiles to
silence, a lever name that no longer exists reads as applied and does nothing, and
`{"channels": {"0": "ins_piano"}}` — the shape everybody writes first — is not a channel
entry at all. `snapmap-midi compile --settings` prints the message and exits 2 rather than
raising.

A `version` this build does not know is refused outright rather than half-read. Reading the
keys that still happen to parse is how a document from a later build silently loses the
settings that build added.

`drum_keys` replaces wholesale on every change while `channels` and `tuning` merge key by
key. That asymmetry is what makes *removal* expressible: a channel's entry has two fields and
a merge has to preserve the one you did not touch, but a drum key's setting is its sound and
nothing else, so a key given a sound by mistake could never be taken back under a deep merge.

## You cannot hear a sound here

**The window plays nothing, and nothing in it replaces `audition`.** That command is gone. It
built a map that played every sound in a category in sequence and printed a numbered legend,
and that map was the only way to find out what `play_noise_tom` actually is.

What the window gives you instead is not a substitute for it. The ruler tells you how many of
a channel's notes a family cannot reach, and the dry run tells you how many notes hold past a
second and how close the arrangement runs to its speaker ceiling. Auditioning told you none of
that. But none of this tells you what a sound sounds like, and no amount of range readout ever
will.

**The workflow that is genuinely gone is comparing two candidate families by ear without
exporting twice.** Auditioning let you hear what a family holds on its own, away from any
song. The only way to hear one now is to compile the song with it, load the map, press the
switch, come back, choose the other one and do all of it again. Two exports and two trips
into the game to answer a question that used to be answered by listening once.

If that is the question you are asking — and curating the ear-labels in
`data/soundfont_labels.json` is exactly that question, 54 unlabelled percussion sounds of it —
then the recipe below is the honest answer, not the window.

`sound/timeline.py:author_sound_timeline` is the API the audition command was built on. It is
unchanged and stays supported for this reason, so what was removed is a command and not a
capability:

```python
from snapmap_midi.sound.palette import sounds_in_category
from snapmap_midi.sound.timeline import author_sound_timeline

raw = author_sound_timeline(
    [(s, i * 1500) for i, s in enumerate(sounds_in_category("ins_percussion"))],
    button_name="listen",
)
```

That is the whole of what the command did: every sound in the category, spaced 1500 ms apart,
on a switch. Write the bytes where the loader reads them and press it, with
`sounds_in_category("ins_percussion")` printed beside you as the legend — the list is in
declaration order and so is the map, so the nth sound you hear is the nth name:

```python
from snapmap_midi import paths

destination = paths.rawmap_destination()
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_bytes(raw)
```

That is five more lines than typing a command, and it is Python rather than a command line,
which for some people means it is gone. Saying so is cheaper than pretending the ruler
covers it.
