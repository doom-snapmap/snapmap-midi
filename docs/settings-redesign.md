# Proposal: the density controls are one idea wearing seven hats

Not implemented. This is a design note for whoever picks up the conversion settings panel,
written immediately after fixing four bugs in it, while the reasons are still fresh.

The bugs are fixed. What follows is the part that was **not** a bug: the controls are
correct and still nearly unusable, and no further bug fixing will change that.

## What the panel asks now

| Control | Question it really asks |
|---|---|
| Voices | how many notes at once |
| Limit maximum polyphony | how many notes at once |
| Hard stop notes | how a note ends |
| Release | how a note ends |
| Limit sustained-note duration | how long a note lasts |
| Limit bass-note duration | how long a note lasts |
| Per-instrument cap box | how long a note lasts |

Seven controls. Three questions.

The two in the first group are the worst offenders. After the fixes on this branch they give
**identical answers** on every case tested — a melody survives whole under both, a chord thins
from the bottom under both. They are two names, two sliders and two settings keys for one
concept, and a user reasonably assumes two controls must do two different things.

## The deeper problem: a per-track limit on a merged view

This is the one to fix first, because it makes the others unreadable.

Both limits apply **per track**. `compile.py` applies them inside the per-part loop, so three
tracks at polyphony 4 permit twelve notes at once, and the default of 32 speakers authors up
to 32 entities *per track*.

The piano roll draws **every track onto one surface**. See `docs/ui.md`: the left column lists
the parts, the right side is a single shared grid.

So the user watches a merged wall of notes and adjusts a limit that applies to one track at a
time. There is no way to see which notes belong to which track, which means there is no way to
see why a limit did or did not act. Everything downstream of this reads as random:

- Lower the limit on a song whose tracks are each monophonic and nothing happens, correctly,
  because no single track ever holds two notes — but the merged view is visibly stacked, so it
  looks like the control is dead.
- Lower it on a dense track and notes vanish out of what looks like the same wall.

Two identical-looking situations, two opposite outcomes, and the information that explains the
difference is not on screen. `type0_three_channels.mid` is the reproducer: three monophonic
channels that look like a chord-heavy song in the merged roll.

Fix this and the sliders may need no redesign at all. Fix the sliders without this and they
will still be confusing.

### Solo and mute should remove notes from the roll, not shade them

The cheapest useful step, and it does not touch the compiler at all.

Today `app.js` treats muted and solo-excluded notes as `inactive` and draws them in the muted
palette colour. They stay on the grid at full size, underneath everything else. Soloing a track
therefore does not isolate it — it just recolours its neighbours, and the notes a user is
trying to read are still buried under the notes they just tried to remove.

Solo should draw **only** the soloed tracks. Mute should draw **nothing** for that track. That
is what solo and mute mean in every other sequencer, and it gives a per-track view immediately
without building one: solo a track and the roll becomes that track's roll.

It also makes the density limits legible for free, since a per-track limit can finally be
watched against a single track.

Editing is the sharper version of the same complaint. Notes from different tracks overlap on
the grid, so clicking a note to edit its conversion means clicking into a stack and hoping. A
roll that honours solo and mute is the difference between that and pointing at the note.

### The real shape is per-track lanes

Longer term the roll wants to be per-track lanes — MIDI clips, one strip per track, the way a
DAW arranges them — rather than one shared grid with everything drawn on it. That is what the
left column already implies and the right side contradicts.

Solo-and-mute filtering is the cheap approximation and should come first. It is worth doing
even if lanes are built later, because it is small, it is independently correct, and it is what
users expect those two buttons to do regardless of how the roll is laid out.

## Suggested shape

Three controls for three questions:

- **Notes at once** — per track, merging `max_speakers` and `max_poly`.
- **Maximum note length** — merging `cap_sustain_ms` and `bass_cap_ms`, keeping the
  per-instrument override. The override is the real answer to a long sample, such as a
  sustained string patch that rings far past its written note; the global slider is the blunt
  version of the same thing.
- **How notes end** — hard stop or release.

Plus a readout, which is the cheapest item here and probably the highest value:

```
Piano    holds 1 · limit 4      (greyed: nothing to remove)
Strings  holds 5 · limit 4      (active: one note dropped)
```

Per row, in the track list that already exists. It makes a limit that is correctly doing
nothing visibly distinct from a broken one — the single complaint that generated this note.
`session.py` already computes the peak count per part; nothing new needs measuring.

## Constraints on doing it

**Settings migration is required.** Merging keys changes the document shape, so
`SETTINGS_VERSION` must rise and `_migrate` must gain a rung. `validate` refuses unrecognized
keys, so a saved file from an older version fails to load rather than degrading. Decide what a
merged value means when the two old keys disagreed — the lower of the two is the honest
reading, since it is the one that was actually binding.

**Byte goldens will not protect this.** `max_poly` is off by default and no golden sets it, so
the density path is invisible to all three gates. Structural assertions on the statistics
summary are the only cover; add cases before touching it.

**One behaviour to keep or kill deliberately.** A decaying note with no pitch or volume change
stays on the shared Timeline entity rather than taking a speaker, and `prepare_voice_layers`
returns it in `shared_decaying` — a list that goes straight to the output without passing
through either thinning function. Those notes ignore both limits entirely. That is defensible,
since they hold no speaker and cannot exhaust the pool, but it means the sliders do not
describe the whole arrangement and nothing says so. Whatever the redesign does, it should say
which notes a limit governs.

## Two traps, paid for already

**Do not count ringing sample tails as held notes.** A 124 ms note can trigger a 4-second
sample. Measuring the tail makes a melody playing one note at a time read as a seven-note
chord, and a limit of one then deletes six notes that never overlapped anything. This was
fixed twice on this branch, in `thin_simultaneous` and again in `thin_polyphony`, because the
first fix left the identical bug in the other lever. A tail does not block the next note; it
gets cut by it, exactly like retriggering a monosynth.

Written note ends answer "how many keys are held down." The tail belongs to the speaker count
and the duration caps, and nowhere else.

**Test with a descending line.** In an ascending line every note is the new highest and
survives whatever the rule is, so an ascending test passes against broken code. That is
precisely how the first version of this fix was verified and shipped wrong. The regression
tests in `tests/test_voices.py` descend on purpose.

A related gap worth knowing: the randomised equivalence test for `thin_polyphony` never caught
the tail bug, because its generator does not set `voice_end` — the fast path and its oracle
were only ever compared on inputs where they could not disagree.

## Unverified

The emitter-recycling limit in `docs/limits.md` is inherited from earlier work and was not
confirmed against the game. The speaker default of 32 rests on it. Confirm it before treating
that number as meaningful, and before choosing a default for a merged control.
