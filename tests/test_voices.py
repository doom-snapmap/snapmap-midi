"""Voice allocation and polyphony thinning.

`thin_polyphony` was rewritten from a quadratic scan to a sweep. The headline
test here is an equivalence check against the original implementation, kept
verbatim below as an oracle: the rewrite is only worth having if it decides
exactly the same notes, and no byte gate covers this path because `max_poly`
is a library-only lever the goldens do not use.
"""

from __future__ import annotations

import random

import pytest

from snapmap_midi.music.midi import Note
from snapmap_midi.music.voices import allocate_voices, thin_polyphony
from snapmap_midi.sound.palette import shader_pitch


def _thin_polyphony_naive(notes, max_poly: int):
    """The original O(n^2) implementation, kept as the equivalence oracle.

    Do not 'improve' this. Its only job is to be obviously correct so the fast
    one can be checked against it.
    """
    ordered = sorted(notes, key=lambda n: n.start)
    pitch = {id(n): (shader_pitch(n.shader) or 0) for n in ordered}
    kept = []
    for note in ordered:
        higher = sum(
            1
            for other in ordered
            if other is not note
            and other.start <= note.start < other.end
            and pitch[id(other)] > pitch[id(note)]
        )
        if higher < max_poly:
            kept.append(note)
    return kept


_NAMES = ["c", "db", "d", "eb", "e", "f", "gb", "g", "ab", "a", "bb", "b"]


def _random_notes(rng, count):
    notes, t = [], 0
    for i in range(count):
        t += rng.choice([0, 0, 1, 40, 120, 500])  # zero gaps make chords and ties
        duration = rng.choice([0, 1, 200, 900, 2500])  # zero-length notes included
        shader = "play_piano%s%d" % (rng.choice(_NAMES), rng.randint(1, 7))
        if rng.random() < 0.1:
            shader = "play_noise_kick_tight"  # unpitched, resolves to 0
        notes.append(Note(t, t + duration, shader, True, i % 16, "ins_piano"))
    return notes


@pytest.mark.parametrize("seed", range(12))
def test_thinning_matches_the_naive_implementation(seed):
    """Randomised equivalence, including the cases that make this subtle:
    chords (equal start), ties in pitch, zero-length notes, and unpitched
    sounds that all collapse to the same pitch."""
    rng = random.Random(seed)
    notes = _random_notes(rng, rng.randint(1, 160))
    for max_poly in (1, 2, 4, 8):
        fast = thin_polyphony(list(notes), max_poly)
        slow = _thin_polyphony_naive(list(notes), max_poly)
        assert [id(n) for n in fast] == [id(n) for n in slow], (
            "seed=%d max_poly=%d: kept a different set or a different order" % (seed, max_poly)
        )


def test_thinning_is_not_quadratic():
    """A dense arrangement is exactly when `max_poly` gets used, so the slow
    path was the one that ran on the biggest inputs. Quadratic growth would
    show up here as roughly 16x for 4x the notes."""
    import time

    def elapsed(count):
        rng = random.Random(1)
        notes = _random_notes(rng, count)
        start = time.perf_counter()
        thin_polyphony(notes, 8)
        return time.perf_counter() - start

    small = max(elapsed(500), 1e-4)
    large = elapsed(4000)
    # 8x the notes. Linearithmic lands near 8-10x; quadratic lands near 64x.
    assert large / small < 25, "growth looks quadratic: %.4fs -> %.4fs" % (small, large)


def test_thinning_keeps_highest_voices():
    notes = [
        Note(0, 1000, "play_pianoc4", True, 0, "ins_piano"),
        Note(0, 1000, "play_pianoe4", True, 0, "ins_piano"),
        Note(0, 1000, "play_pianog4", True, 0, "ins_piano"),
    ]
    kept = thin_polyphony(notes, max_poly=2)
    assert {n.shader for n in kept} == {"play_pianoe4", "play_pianog4"}
    # Full length retained: this cuts density, not duration.
    assert all(n.end == 1000 for n in kept)


def test_thinning_keeps_everything_when_nothing_overlaps():
    notes = [Note(i * 1000, i * 1000 + 500, "play_pianoc4", True, 0, "f") for i in range(20)]
    assert len(thin_polyphony(notes, max_poly=1)) == 20


def test_allocate_voices_overlap_vs_sequential():
    overlap = [Note(0, 500, "a", True, 0, "f"), Note(100, 600, "b", True, 0, "f")]
    assert allocate_voices(overlap, max_speakers=8) == 2
    sequential = [Note(0, 500, "a", True, 0, "f"), Note(500, 900, "b", True, 0, "f")]
    assert allocate_voices(sequential, max_speakers=8) == 1


def test_allocate_voices_steals_the_earliest_free_voice_at_the_ceiling():
    """Past `max_speakers` an older note loses its tail rather than a new note
    losing its attack -- a missing attack is far more audible."""
    notes = [Note(i * 10, 5000, "a", True, 0, "f") for i in range(6)]
    assert allocate_voices(notes, max_speakers=3) == 3
    assert sorted({n.voice for n in notes}) == [0, 1, 2]
