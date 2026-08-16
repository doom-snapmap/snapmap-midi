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
  emitter. It holds no dedicated pitch-controlled emitter and is effectively immune to this
  voice-pool limit. Native pre-tuned shaders can form chords on this shared wildcard path.
- A decaying note with pitch or gain expression needs isolation. It reserves a generic Timeline
  emitter through
  installed-event duration, or 750 ms for drums and 1000 ms for other sounds when metadata is
  unavailable.

**Global Voices (`max_speakers`) is a song-wide voice count.** Notes from every track share the
same isolated-emitter pool. Notes that start together beyond the limit are thinned from the bottom,
keeping the highest notes; later overlapping notes reuse the emitter that frees first and cut its prior tail
short. This is deterministic, so the same MIDI always keeps the same notes. A kept note
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
4-second sample, so notes a beat apart are still both sounding — they just share one emitter
instead of needing two.
- A sustained note reserves an emitter until its capped note end and receives a stop or release.

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
| **Global Voices** (`max_speakers`) | a song-wide ceiling after every track's own cap; the isolated pool reuses the emitter that frees soonest | prevents the map from authoring too many pitch-controlled emitters overall |
| **Global Polyphony** (`song_polyphony`) | admits a fixed number of held notes across all tracks before shared/isolated routing | shared-emitter chords and isolated notes consume the same musical-note budget; sample tails do not count |
| **Track Voices** (per track `voices`) | caps one track's virtual emitters before it joins the global pool; at 1 it is monophonic | later notes play and older tails on that track stop early; oversized chords keep their highest notes |
| **Polyphony** (`max_poly`, per track `polyphony`) | notes past the limit are refused | those notes never sound; the ones that do keep their full length |
| **Sustain Limit** (`cap_sustain_ms`, per track `sustain_ms`) | intentionally caps a sound's audible duration; a track value overrides the song default | looping notes and long one-shot rings end at the chosen duration even when voices remain available |

A block chord cannot tell them apart — both keep the top of it. The case that separates them is
notes overlapping *without* sharing an onset, which is most sustained writing. Four held notes
entering 200 ms apart at a limit of one: polyphony keeps the top note and mutes three; voices
keeps all four and truncates each as the next arrives.

Neither edits the MIDI. A note that polyphony refuses is still drawn on the roll, dimmed, the
same as a muted track — `converted: false` in the preview manifest.

**Voices is the lever for a long sample ringing under the next note**, because stealing is what
silences the previous one. Polyphony would only delete notes and leave the ringing.

**Sustain Limit is the deliberate note-length lever.** It does not change how many voices exist.
Use it when notes should end sooner even without voice pressure; use Voices when each new attack
should be preserved and an older sound may give way only when the track is full.

**Global Voices is for the entire song.** It limits the dedicated Timeline emitters authored in the map,
regardless of which track requested them. **Track Voices and Polyphony remain per track.** Use
Track Voices to stop one instrument monopolising the pool while keeping later attacks, or use
Polyphony when a deliberate chord reduction is preferable. Global Voices then enforces the
overall isolated-emitter budget after those track decisions.

**Global Polyphony is also song-wide, but counts notes rather than emitters.** It runs before the
shared/isolated split, so C-E-G layered on one shared Timeline still consumes three of its slots.
Notes already playing are never shortened by this control. If a new simultaneous group is larger
than the remaining capacity, its highest notes are admitted. Ringing sample tails are excluded;
counting them is the retired behavior that made sequential melodies lose later attacks.

**Track Glide is for a fixed/exact sound.** Automatic instruments can choose a separately tuned
recording for each key, so there is no single sample pitch to interpolate between. A fixed-sound
track does have one sample and one pitch coordinate system. Its glide value (0–5000 ms) ramps each
track-local voice from its prior pitch; use Track Voices 1 for conventional monophonic portamento.

## The editor's timeline size ceiling

**A timeline past about 1 MB serialized loads and plays correctly, but the SnapMap editor
cannot open it.** The editor says "could not open this timeline" and nothing else. The map is
fine. The music is fine. Only editing is lost.

Export currently keeps one master Timeline and one listener target. If that master exceeds the
editor budget, the map still loads and plays but the editor may refuse to open its Timeline, and
the workstation warns accordingly. Automatic Timeline sharding is retained behind the disabled
`ENABLE_TIMELINE_SHARDING` feature gate for possible later use; it is not part of current export
behavior.

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
