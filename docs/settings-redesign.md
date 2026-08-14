# Proposal: the density controls are one idea wearing seven hats

Not implemented. This is a design note for whoever picks up the conversion settings panel,
written immediately after fixing four bugs in it, while the reasons are still fresh.

The bugs are fixed. What follows is the part that was **not** a bug: the controls are
correct and still nearly unusable, and no further bug fixing will change that.

## What the panel asks now

| Control | Question it really asks |
|---|---|
| Voices | how many notes at once, and what gives when there are more |
| Limit maximum polyphony | how many notes at once, and what gives when there are more |
| Hard stop notes | how a note ends |
| Release | how a note ends |
| Limit sustained-note duration | how long a note lasts |
| Limit bass-note duration | how long a note lasts |
| Per-instrument cap box | how long a note lasts |

Seven controls. Three questions.

**The first two are NOT redundant, and an earlier version of this note was wrong to say so.**
That claim was made after testing only block chords and single-note melodies, where the two
happen to agree. On notes that overlap without sharing an onset — a held chord built up one
note at a time, which is most sustained writing — they do completely different things:

| | Mechanism | What a listener hears |
|---|---|---|
| Polyphony | drops notes past the limit | extra notes never sound; survivors keep full length |
| Voices (speakers) | steals the oldest speaker | every note sounds; the older one is cut short |

Four held notes entering 200 ms apart, limit of one: polyphony keeps the top note and deletes
the other three. Voices keeps all four and truncates each as the next arrives. Note-dropping
versus voice-stealing — the two things real synths do when they run out, and both worth having.

So the pair should stay two controls. What they lack is names that say which is which, and
the readout described below.

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

Today `app.js` treats muted and solo-excluded notes as `inactive` and draws them in the muted
palette colour. They stay on the grid at full size, underneath everything else, so soloing a
track does not isolate it — it recolours its neighbours and leaves them stacked on top of the
one being read. Clicking a note to edit its conversion means clicking into a pile of
overlapping tracks and hoping.

**Filtering the roll by solo and mute is not the fix.** It was proposed here first and it is
the wrong answer: hiding notes is not what the user wants, and a roll that shows one track at
a time only when you remember to solo it is still a single shared grid with a workaround
bolted on.

### The fix is two levels of view

One shared grid is the wrong surface. The window should work the way a DAW arrangement does —
Ableton Live is the direct reference:

- **The main view is per-track lanes.** One horizontal strip per track, each holding a
  bird's-eye block of that track's MIDI — enough to see where the notes are, how dense the
  part is, and where it sits against the others. Tracks stay side by side vertically, never
  drawn on top of each other.
- **Double-clicking a block opens the piano roll.** That is the grid that exists today, scoped
  to the track you opened, at note-editing detail.

Overview for arranging, detail on demand for editing. Nothing is hidden at either level; the
information is separated by track instead of overlaid.

This is a surface change rather than a compiler change — the manifest already carries `part`
on every event, so the data to split by track is present. It is the largest item in this note
and the one that makes everything else legible, because a per-track voice limit can finally be
watched against a single track's lane.

**Solo and mute should keep the shading they have today.** Greying a muted or solo-excluded
track was never the problem — the problem was that it was the only separation on offer, on a
surface where every track was drawn over every other one. Once tracks have their own lanes,
shading reads correctly: it marks a track as silent while leaving its notes where they are, in
its own strip, still visible and still editable.

They go back to meaning *audibility* and stop being asked to substitute for a view.

## The limits are per track but the controls are global

Worth fixing early, because it is small and it is the reason the panel feels like the wrong
place to be.

Both limits are applied **per track**. Each track gets its own speakers and its own note-count
limit. But both sliders live in a global settings panel titled "SnapMap engine limits", so
there is one number for every track in the song.

That is the worst of both arrangements:

- A busy drum track and a sparse melody get the same limit, applied separately to each. You
  cannot turn one down without turning the other down with it.
- The number is not the song's total either, so it says nothing about the whole song. Three
  tracks set to 4 allow twelve notes at once.

Nobody appears to have decided between the two readings. The panel's title says global, the
code says per track, and the mismatch was never resolved.

**Suggested: move them onto the track rows.** Each track carries its own limit, next to its
mute and solo buttons. The global panel keeps one value as the default for new tracks. This
matches what the compiler already does, and it lets someone cap a dense drum part without
touching the piano.

The alternative is making them genuinely global — one budget for the song, divided across
tracks. That matches the panel's title, but it is a much larger compiler change and the result
gives less control than exists today. Not recommended.

## Suggested shape

- **Voices** (`max_speakers`) — per track. How many notes can sound at once; a new note past
  the limit steals the oldest speaker and cuts it short. This is the lever that fixes a long
  sample ringing under the next note, because stealing is what silences the previous one.
- **Note limit** (`max_poly`) — how many notes are allowed to sound at once at all; extras are
  dropped rather than cut. An editorial thinner for dense writing, and off by default.
- **Maximum note length** — merging `cap_sustain_ms` and `bass_cap_ms`, keeping the
  per-instrument override. The override is the real answer to a long sample, such as a
  sustained string patch that rings far past its written note; the global slider is the blunt
  version of the same thing.
- **How notes end** — hard stop or release.

The first two keep separate keys and separate sliders. The naming is the fix: "voices" and
"note limit" say which one cuts and which one deletes, where "speakers" and "polyphony" said
neither.

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
