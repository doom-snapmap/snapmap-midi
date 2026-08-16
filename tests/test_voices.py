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
from snapmap_midi.music.voices import (
    allocate_voices,
    apply_glides,
    apply_voice_cap,
    prepare_voice_layers,
    thin_global_polyphony,
    thin_polyphony,
    thin_simultaneous,
)
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


def _tailed(start, pitch_name, octave, *, duration=124, tail=4000):
    """A short note on a long sample -- the shape that caused the regression."""
    note = Note(start, start + duration, "play_piano%s%d" % (pitch_name, octave), False, 0, "p")
    note.voice_end = start + tail
    return note


def test_simultaneous_thinning_keeps_a_sequential_line_whole():
    """The voice limit must never delete a note that plays on its own.

    This is the regression that made the speaker slider unusable. A descending
    melody, one note at a time and nothing overlapping in written time, lost
    seven of its eight notes at one voice -- because thinning counted every
    note still SOUNDING, and a 124 ms note on a 4-second sample is still
    ringing when the next one starts.

    A ringing tail does not block the next note. It gets CUT by it, exactly
    like retriggering a monosynth. Descending pitches matter here: with an
    ascending line every note is the new highest and survives whatever the
    rule is, which is what made an earlier version of this test pass while the
    bug was live.
    """
    line = [_tailed(i * 250, name, 5) for i, name in enumerate(["b", "a", "g", "f", "e", "d", "c"])]
    for voices in (7, 4, 2, 1):
        assert len(thin_simultaneous(list(line), voices)) == 7


def test_simultaneous_thinning_caps_a_chord_from_the_top():
    """Notes that begin together DO compete, and the top of the chord wins."""
    chord = [_tailed(0, name, octave) for name, octave in [("c", 3), ("g", 3), ("c", 4), ("e", 4)]]
    kept = thin_simultaneous(chord, 2)
    assert {n.shader for n in kept} == {"play_pianoc4", "play_pianoe4"}


def test_global_polyphony_strictly_caps_a_cross_track_chord_from_the_top():
    chord = [_tailed(0, name, octave) for name, octave in [("c", 3), ("g", 3), ("c", 4), ("e", 4)]]
    for track, note in enumerate(chord):
        note.track = track

    kept = thin_global_polyphony(chord, 2)

    assert {note.shader for note in kept} == {"play_pianoc4", "play_pianoe4"}


def test_global_polyphony_refuses_a_later_note_instead_of_stealing_a_held_one():
    held = Note(0, 1000, "play_pianoc3", True, 0, "ins_piano")
    later = Note(200, 800, "play_pianoc6", True, 1, "ins_piano")

    assert thin_global_polyphony([held, later], 1) == [held]


def test_track_voice_cap_cuts_its_own_ringing_notes_before_global_allocation():
    """A track cap is not polyphony: staggered notes still start, but each new
    note steals this track's virtual voice and frees it for the global pool."""
    notes = [
        Note(0, 1000, "play_pianoc4", True, 0, "ins_piano"),
        Note(200, 1200, "play_pianoe4", True, 0, "ins_piano"),
        Note(400, 1400, "play_pianog4", True, 0, "ins_piano"),
    ]

    kept = apply_voice_cap(notes, 1)

    assert kept == notes
    assert [getattr(note, "voice_cap_end", None) for note in kept] == [200, 400, None]
    assert allocate_voices(kept, 32) == 1


def test_simultaneous_thinning_ignores_the_order_the_file_listed_the_chord_in():
    """Two exports of one arrangement must drop the same notes."""
    spec = [("c", 3), ("g", 3), ("c", 4), ("e", 4), ("g", 4)]
    for voices in (1, 2, 3, 4):
        forward = thin_simultaneous([_tailed(0, n, o) for n, o in spec], voices)
        backward = thin_simultaneous([_tailed(0, n, o) for n, o in reversed(spec)], voices)
        assert sorted(n.shader for n in forward) == sorted(n.shader for n in backward)


def test_global_voice_tie_break_uses_track_identity_not_midi_order():
    """Equal-pitch notes have no musical priority, so their stable part key
    decides the global-cap survivor instead of the order a MIDI exporter wrote
    the tracks. The lower track number is predictable and repeatable."""
    def kept_track(order):
        notes = []
        for track in order:
            note = _tailed(0, "c", 4)
            note.track = track
            note.id = "%d:60:1" % track
            notes.append(note)
        return thin_simultaneous(notes, 1)[0].track

    assert kept_track([2, 1]) == kept_track([1, 2]) == 1


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


def test_a_tie_on_free_time_steals_the_oldest_sound():
    """Notes written to end together end together, so the tie is the ordinary
    case rather than a corner one, and slot order used to settle it.

    Four notes entering 200 ms apart on two voices: the first gives way to the
    third, then the second gives way to the fourth. Each note in turn is the
    longest-running one when the next arrives.

    Before this, slot 1 kept whatever landed on it for the whole song while slot
    0 was recycled over and over -- so the SECOND note survived intact and the
    THIRD was cut, which is neither the oldest nor the newest and answers to
    nothing a listener could predict.
    """
    notes = [Note(step * 200, 2000, "play_piano%d" % step, True, 0, "p") for step in range(4)]
    allocate_voices(notes, max_speakers=2)

    def stops_at(note):
        later = [o.start for o in notes if o.voice == note.voice and o.start > note.start]
        return min(later) if later else note.end

    assert stops_at(notes[0]) == 400  # oldest, gives way to the third
    assert stops_at(notes[1]) == 600  # now oldest, gives way to the fourth
    assert stops_at(notes[2]) == 2000
    assert stops_at(notes[3]) == 2000


def test_decaying_voice_reservation_controls_allocation_but_not_polyphony():
    """The sample's tail decides SPEAKERS. It must not decide POLYPHONY.

    These two notes do not overlap as written -- 0..100 and 200..300 -- but
    each reserves a speaker for a full second, so they genuinely need two
    speakers. That is `allocate_voices`, and it still sees the reservation.

    `max_poly` is the other question: how many keys are down together. Here the
    answer is one, at every instant, so a limit of one must keep both notes.
    It used to keep only the first, because it measured the tail as well -- the
    bug that let a one-note-at-a-time melody be emptied by a density slider.
    """
    first = Note(0, 100, "play_noise_one", False, 0, "ins_noise")
    first.pitch = 72
    first.voice_end = 1000
    second = Note(200, 300, "play_noise_two", False, 0, "ins_noise")
    second.pitch = 60
    second.voice_end = 1200

    notes = [first, second]
    assert allocate_voices(notes, max_speakers=8) == 2
    assert thin_polyphony(notes, max_poly=1) == [first, second]


def test_track_sustain_limit_overrides_family_and_song_defaults():
    note = Note(0, 2000, "play_pianoc4", True, 0, "ins_piano")
    note.track = 2
    note.chan = 3

    _shared, _expressive, layers = prepare_voice_layers(
        [],
        [note],
        cap_sustain_ms=1200,
        family_caps={"ins_piano": 900},
        part_sustain_ms={(2, 3): 650},
    )

    assert layers[(2, 3)] == [note]
    assert note.end == 650
    assert note.sustain_limited is True


def test_bass_limit_remains_an_additional_ceiling_on_track_sustain():
    note = Note(0, 2000, "play_pianoc3", True, 0, "ins_piano")
    note.track = 1
    note.chan = 0

    prepare_voice_layers(
        [],
        [note],
        bass_pitch=78,
        bass_cap_ms=400,
        part_sustain_ms={(1, 0): 900},
    )

    assert note.end == 400


def test_polyphony_never_empties_a_line_that_plays_one_note_at_a_time():
    """The headline symptom, pinned. Seven notes a beat apart on a 4-second
    sample: nothing overlaps, so every note survives every setting."""
    line = [_tailed(i * 250, name, 5) for i, name in enumerate(["b", "a", "g", "f", "e", "d", "c"])]
    for limit in (7, 4, 2, 1):
        assert len(thin_polyphony(list(line), limit)) == 7


@pytest.mark.parametrize(("pitch_modifier", "voice_end"), [(12, 500), (-12, 2000)])
def test_decaying_voice_reservation_tracks_pitch_changed_playback_speed(pitch_modifier, voice_end):
    note = Note(0, 100, "play_noise_one", False, 0, "exact")
    note.pitch_modifier = pitch_modifier
    note.volume_db = 0

    shared, expressive, layers = prepare_voice_layers(
        [note],
        [],
        duration_lookup=lambda _sound: 1000,
    )

    assert shared == []
    assert expressive == [note]
    # Keyed by PART -- (track, channel) -- because a channel is not an identity:
    # two tracks can write to one channel and they are two rows, two pools. This
    # bare Note carries no track, so it reads as track 0.
    assert layers == {(0, 0): [note]}
    assert note.voice_end == voice_end


def test_neutral_decaying_note_stays_on_the_shared_timeline():
    note = Note(0, 100, "play_noise_one", False, 0, "exact")
    note.pitch_modifier = note.volume_db = 0
    shared, expressive, layers = prepare_voice_layers([note], [])
    assert (shared, expressive, layers) == ([note], [], {})


def test_sustain_limit_routes_a_capped_one_shot_to_an_isolated_voice():
    """A shared Timeline can start a one-shot but cannot stop just that note."""
    note = Note(0, 100, "play_noise_one", False, 0, "exact")
    note.pitch_modifier = note.volume_db = 0

    shared, expressive, layers = prepare_voice_layers(
        [note], [], cap_sustain_ms=300, duration_lookup=lambda _sound: 1000
    )

    assert shared == []
    assert expressive == [note]
    assert layers == {(0, 0): [note]}
    assert note.sustain_limited is True
    assert note.end == note.voice_end == 300


def test_track_voice_setting_routes_neutral_notes_through_its_voice_lane():
    note = Note(0, 100, "play_pianoc4", False, 0, "ins_piano")
    note.track = 3
    note.pitch_modifier = note.volume_db = 0

    shared, isolated, layers = prepare_voice_layers(
        [note], [], part_voices={(3, 0): 1}
    )

    assert shared == []
    assert isolated == [note]
    assert layers == {(3, 0): [note]}


def test_glide_keeps_an_exact_sounds_zero_pitch_note_in_its_voice_lane():
    note = Note(0, 100, "play_pianoc4", False, 0, "exact")
    note.track = 2
    note.pitch_modifier = note.volume_db = 0
    note.uses_exact_sound = True

    shared, expressive, layers = prepare_voice_layers(
        [note], [], part_glide_ms={(2, 0): 250}
    )

    assert shared == []
    assert expressive == [note]
    assert layers == {(2, 0): [note]}


def test_monophonic_glide_follows_the_tracks_previous_local_voice():
    first = Note(0, 100, "play_pianoc4", False, 0, "exact")
    second = Note(200, 300, "play_pianoc4", False, 0, "exact")
    for note, pitch in ((first, 0.0), (second, 2.0)):
        note.track = 1
        note.pitch_modifier = pitch
        note.volume_db = 0
        note.voice_end = note.start + 1000
        note.uses_exact_sound = True

    kept = apply_voice_cap([first, second], 1)
    allocate_voices(kept, 32)
    apply_glides(kept, {(1, 0): 180})

    assert first.part_voice == second.part_voice == 0
    assert first.glide_ms == 0
    assert second.glide_ms == 180
    assert second.glide_from_pitch == 0.0


def test_two_tracks_on_one_channel_get_their_own_speaker_pools():
    """A MIDI channel is not an identity, so it cannot be the layer key.

    Two exports of the same music -- one with the second part on channel 1, one
    on channel 2 -- behaved completely differently: on the shared channel both
    parts collapsed into one preparation layer. The window shows two rows either
    way, because rows are parts; the compiler applies per-track polyphony before
    both layers enter the one global speaker pool.
    """
    a = Note(0, 100, "play_noise_one", False, 0, "exact")
    b = Note(0, 100, "play_noise_two", False, 0, "exact")
    a.track, b.track = 1, 2          # two tracks ...
    a.chan = b.chan = 0              # ... writing to ONE channel
    for note in (a, b):
        note.pitch_modifier = 0
        note.volume_db = 0

    _shared, _expressive, layers = prepare_voice_layers([], [a, b])

    assert set(layers) == {(1, 0), (2, 0)}, "two parts collapsed into one pool"
    assert layers[(1, 0)] == [a]
    assert layers[(2, 0)] == [b]


def test_one_track_per_channel_is_unchanged():
    """The ordinary case keeps one pool per part, which is one per channel."""
    a = Note(0, 100, "play_noise_one", False, 0, "exact")
    b = Note(0, 100, "play_noise_two", False, 1, "exact")
    a.track = b.track = 1
    for note in (a, b):
        note.pitch_modifier = 0
        note.volume_db = 0

    _shared, _expressive, layers = prepare_voice_layers([], [a, b])

    assert set(layers) == {(1, 0), (1, 1)}


def test_simultaneous_notes_do_not_depend_on_the_order_the_file_lists_them():
    """A chord must not sound different because the exporter reordered events.

    `sort(key=start)` is stable, so a chord kept the file's own order and the
    notes that won a speaker followed from it. The same five-note chord under
    two speakers gave C3+G3, G4+E4, or C4+C3 depending only on how the events
    were written. Two exports of one arrangement then sounded different.
    """
    pitches = [48, 55, 60, 64, 67]  # C3 G3 C4 E4 G4

    def audible_for(order):
        notes = [Note(0, 2000, "s%d" % p, True, 0, "f") for p in order]
        for note, pitch in zip(notes, order):
            note.pitch = pitch
        allocate_voices(notes, 2)  # sorts in place
        # Among notes starting together, the last one on a voice keeps it.
        last = {}
        for note in notes:
            last[note.voice] = note.pitch
        return sorted(last.values())

    low_high = audible_for(pitches)
    high_low = audible_for(list(reversed(pitches)))
    scrambled = audible_for([60, 48, 67, 55, 64])

    assert low_high == high_low == scrambled, "file order still decides the mix"
    # And the top note is one of the survivors -- it is the one a listener
    # would miss, so it must not be the one that gets stolen from.
    assert 67 in low_high
