# Limits and honesty rules

Two things that will not be obvious from the code, and that cost real time to rediscover.
For the levers named here see [`capabilities.md`](capabilities.md); for where they sit in
the pipeline see [`architecture.md`](architecture.md). For why there are too many of them and
what to do about it, see [`settings-redesign.md`](settings-redesign.md).

## The emitter-recycling limit

**The engine recycles sound emitter slots under load. A note whose slot has been recycled
can no longer be stopped.**

The stop event still fires. It just arrives at a slot that now belongs to a different sound,
so the original note plays to the end of its sample regardless. There is no error, nothing
in the log, and nothing in the compiler's output to warn you.

What it sounds like: a held note that should have ended keeps ringing under the next phrase,
usually in a dense passage, usually inconsistently between playthroughs. Chasing it as a
compiler bug is a dead end — the map is correct and the events are correct.

**Sparse arrangements never hit it.** If your song is not dense, none of this matters.

**Dense ones need the density levers.** Start with `max_speakers` and `max_poly`,
which are global and blunt, then reach for duration or per-family caps if one instrument is the
culprit. Pitch, note volume, and global volume are expression controls; they do not
reduce density.

**The practical target: held notes under about a second cut reliably.** If you can get the long
tail of a sustained arrangement under that, the problem goes away. `cap_sustain_ms` truncates
across the board; `bass_cap_ms` targets just the low register, which is usually where the long
notes live.

Decay behavior no longer tells the whole allocation story:

- A neutral decaying note has no pitch or gain modifier and remains on the shared Timeline
  emitter. It holds no dedicated speaker and is effectively immune to this voice-pool limit.
- A decaying note with pitch or gain expression needs isolation. It reserves a speaker through
  installed-event duration, or 750 ms for drums and 1000 ms for other sounds when metadata is
  unavailable.

**`max_speakers` is a voice count, and it applies to notes that START TOGETHER.** Those are the
only notes competing for a speaker at one instant, so they are the only ones that can be
genuinely unplayable. A chord wider than the voice count is thinned from the bottom, keeping
the highest notes, which is what a hardware synth does when it runs out of voices. A kept note
rings its full tail; a dropped one does not play and the roll dims it.

A note that arrives over an earlier note's ringing tail is a different case, and it is **not**
dropped. It cuts that tail short and plays, exactly like retriggering a monosynth. So a melody
that plays one note at a time survives whole even at a single voice — every note sounds, each
one ended by the next.

Two bugs here are fixed, and both are worth knowing because the symptoms look nothing alike:

- A note that could not get a speaker used to be handed one anyway and truncated by the next
  note on it — to *zero length* when they started together. It was silent but drawn as a
  shortened note rather than a dropped one, so a five-note chord on two speakers played two
  notes and drew five blocks. Which two survived followed the order the exporter happened to
  write the events in, so two exports of one arrangement sounded different.
- The first fix for that thinned by notes still *sounding*, tails included. That counts a
  ringing tail as a live voice, so a descending melody with nothing overlapping lost seven of
  its eight notes at one voice. Thinning now looks at shared onsets only.

Both are pinned in `tests/test_voices.py`. The second test uses a *descending* line
deliberately: in an ascending line every note is the new highest and survives whatever the rule
is, which is exactly how the broken version passed its first test.

None of this stops sustained notes being shortened by the duration caps, which are a separate
lever: **your notes do not overlap, but their sounds do.** A 124 ms note can trigger a
4-second sample, so notes a beat apart are still both sounding — they just share one speaker
instead of needing two.
- A sustained note reserves a speaker until its capped note end and receives a stop or release.

For an exact full-game assignment, installed Wwise metadata still decides decay behavior.
OneShot events decay naturally; Infinite and Mixed events use the sustained path and receive a
paired stop. If a valid manually entered Play event is absent from the current install,
compilation uses the conservative sustained path: an unnecessary stop is harmless, while an
unstopped loop can leak an emitter for the rest of the song.

## Voices and polyphony are different levers

Both answer "how many notes at once". They differ in **what gives** when there are more, and
that difference is the whole reason both exist.

| | Mechanism | What a listener hears |
|---|---|---|
| **Voices** (`max_speakers`, per track `voices`) | a new note takes the speaker of whichever sound is closest to finishing | every note plays; the older one stops early |
| **Polyphony** (`max_poly`, per track `polyphony`) | notes past the limit are refused | those notes never sound; the ones that do keep their full length |

A block chord cannot tell them apart — both keep the top of it. The case that separates them is
notes overlapping *without* sharing an onset, which is most sustained writing. Four held notes
entering 200 ms apart at a limit of one: polyphony keeps the top note and mutes three; voices
keeps all four and truncates each as the next arrives.

Neither edits the MIDI. A note that polyphony refuses is still drawn on the roll, dimmed, the
same as a muted track — `converted: false` in the preview manifest.

**Voices is the lever for a long sample ringing under the next note**, because stealing is what
silences the previous one. Polyphony would only delete notes and leave the ringing.

**Both are per track**, and both always were — each layer is allocated separately, so the
song-wide sliders were never a song-wide budget, only the same number applied to every track.
A track that sets neither uses the song's. `tests/test_compile.py` pins that a per-track limit
touches only that track, and that voices leaves the event count alone while polyphony reduces it.

## The editor's timeline size ceiling

**A timeline past about 1 MB serialized loads and plays correctly, but the SnapMap editor
cannot open it.** The editor says "could not open this timeline" and nothing else. The map is
fine. The music is fine. Only editing is lost.

The two paths are different, which is why every symptom points away from the cause. Loading a
map streams the whole document in and builds entities, with no per-entity buffer anywhere.
Opening a timeline asks the engine to hand that **one entity back out as text**, and that call
writes into a fixed buffer. Past the buffer it returns nothing — not a length, not an error,
just zero, which is also what a genuine failure looks like.

Bisected in game over eight loads, measuring the timeline entity through this project's own
serializer, so the numbers compare directly with `stats["timeline_bytes"]`:

| Serialized timeline | Editor |
|---|---|
| 1,081,338 bytes | opens |
| 1,091,628 bytes | refuses |

That is 1.036x one MiB, consistent with a 1 MiB buffer on the engine's side and this project's
compact JSON running a few percent fatter than what the engine writes.

`TIMELINE_SERIALIZE_BUDGET` in `compile.py` is set at **one MiB**, below every size proven to
open, leaving roughly 32 KB for the difference between the two serializers. Every compile
reports `timeline_bytes` against it, and the session warns when a song goes over.

**Enlarging the buffer on the reading side cannot help.** That was the first fix attempted, and
it grew from 1 MB to 32 MB, doubling six times, with every attempt returning zero. The evidence
is a proven-good control in the same session: 25 other entities serialized on the first try
while the timeline refused at every size.

To bring a song under: shorten it, mute a track, or cap the note count. Nothing about the
density levers helps — they change how many notes sound at once, not how many events the
timeline carries.

## The byte-gate honesty rule

Three tests compare compiler output against a recorded artifact, byte for byte. Each is
paired with structural assertions on the statistics summary, so a failure tells you *what*
moved rather than only *that* something did.

| Gate | Covers | Runs |
|---|---|---|
| from-scratch | a full compile with no inputs: shipped palette, authored stage, synthesized timeline | everywhere |
| hermetic | a full compile against a synthetic in-code baseline | everywhere |
| groove | the timeline API against an arrangement verified in game | only with a saved map configured |

The from-scratch gate is the widest of the three, because the default path now builds the
whole map. It is the only one that would notice the stage itself changing — a cap losing its
rotation, the player start moving out of reach of the switch, a reference table sized
differently. Every one of those is silent in a structural assertion and fatal in game.

### Bytes moving while structure holds is a regression

Not an improvement. Not a wash. A regression.

The map format **preserves key insertion order rather than sorting**. So a refactor that is
structurally identical — reordering dataclass fields, rebuilding a dict, swapping a
comprehension for a loop — changes the serialized bytes while every structural assertion
still passes. That combination is the signature of an accidental key-order change, and it is
the exact failure the paired assertions exist to isolate.

When you see it: find the reordered structure and restore its declaration order. Do not
re-record the fixture.

### Re-recording a golden

Sometimes output genuinely should change. When it does, the bar is:

1. The commit touches the compiler, not only the fixture.
2. The commit message states the intended semantic change in words.
3. The commit shows the structural delta — which statistics moved, and by how much.

A commit that updates a fixture and nothing else is not a fix. It is the record of a
regression being overwritten, and it removes the only evidence that anything changed.

### Why the gates that need nothing matter most

Two of the three need no configuration, so they run in CI, on a fresh clone, and on a
contributor's machine with nothing set up. During the extraction that produced this
repository the hermetic gate was the single piece of evidence that a rename and a whole-tree
reformat had changed no behaviour — because it was the one gate that survived leaving its
original repository. The from-scratch gate was added for the same reason: the default path
must be covered by something that always runs.

Keep it that way. A gate that only runs on the maintainer's machine is a gate that is not
running.
