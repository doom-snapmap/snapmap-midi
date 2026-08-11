# Limits and honesty rules

Two things that will not be obvious from the code, and that cost real time to rediscover.
For the levers named here see [`capabilities.md`](capabilities.md); for where they sit in
the pipeline see [`architecture.md`](architecture.md).

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
culprit. Pitch, velocity, and note trims are expression controls; they do not reduce density.

**The practical target: held notes under about a second cut reliably.** If you can get the long
tail of a sustained arrangement under that, the problem goes away. `cap_sustain_ms` truncates
across the board; `bass_cap_ms` targets just the low register, which is usually where the long
notes live.

Decay behavior no longer tells the whole allocation story:

- A neutral decaying note has no pitch or gain modifier and remains on the shared Timeline
  emitter. It holds no dedicated speaker and is effectively immune to this voice-pool limit.
- A decaying note with pitch or gain expression needs isolation. It reserves a speaker through
  installed-event duration, or 750 ms for drums and 1000 ms for other sounds when metadata is
  unavailable. Under pressure, a new attack can steal and shorten that tail.
- A sustained note reserves a speaker until its capped note end and receives a stop or release.

For an exact full-game assignment, installed Wwise metadata still decides decay behavior.
OneShot events decay naturally; Infinite and Mixed events use the sustained path and receive a
paired stop. If a valid manually entered Play event is absent from the current install,
compilation uses the conservative sustained path: an unnecessary stop is harmless, while an
unstopped loop can leak an emitter for the rest of the song.

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
