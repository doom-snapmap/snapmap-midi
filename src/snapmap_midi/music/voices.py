"""Voice allocation and density thinning.

A speaker is monophonic per channel: starting a second note on one cuts the
first. So overlapping sustained notes need separate speakers, and "how many
speakers does this layer need" is exactly an interval-graph colouring.

Both functions here exist because of the same underlying limit: the engine
recycles sound emitter slots under load, and a note whose slot is recycled can
no longer be stopped, so it rings its whole sample. Fewer simultaneous notes
means fewer chances to lose that race.
"""

from __future__ import annotations

import heapq

from snapmap_midi.sound.palette import shader_pitch


def allocate_voices(notes, max_speakers: int) -> int:
    """Assign each note a voice so no two overlap on one. Returns voices used.

    Greedy by start time, reusing the first voice that has freed up. Past
    `max_speakers` it steals the voice that frees earliest, which truncates
    that note rather than dropping this one -- losing the tail of an older
    note is less audible than a missing attack.
    """
    notes.sort(key=lambda n: n.start)
    free_at: list[int] = []
    for note in notes:
        voice = next((i for i, t in enumerate(free_at) if t <= note.start), None)
        if voice is None:
            if len(free_at) < max_speakers:
                voice = len(free_at)
                free_at.append(0)
            else:
                voice = min(range(len(free_at)), key=lambda i: free_at[i])
        note.voice = voice
        free_at[voice] = note.end
    return len(free_at)


#: One past the highest pitch a sound name can encode. The octave is a single
#: digit, so the ceiling is octave 9's B: (9 + 1) * 12 + 11.
_PITCH_CEILING = (9 + 1) * 12 + 11 + 1


def thin_polyphony(notes, max_poly: int):
    """Keep at most `max_poly` simultaneous notes, preferring higher pitches.

    Melody and upper harmony carry the tune; inner doublings are what a
    listener misses least. Kept notes retain their FULL length -- this reduces
    how many notes sound at once, not how long each one lasts, so stops still
    land while sustain stays natural.

    Implemented as a sweep rather than the obvious nested scan. The obvious
    one asks, for every note, how many of ALL the others overlap it, which is
    quadratic -- and it ran on the densest arrangements, because a dense
    arrangement is the only reason to reach for `max_poly` at all. A five
    thousand note file took two thirds of a second here and milliseconds
    everywhere else in the compiler.

    The sweep walks onsets in order, keeping a live count of sounding notes
    per pitch. Pitches are bounded by the naming scheme, so "how many sounding
    notes are higher than this one" is a short fixed-width sum instead of a
    pass over the arrangement.

    `tests/test_voices.py` pins this against the original implementation over
    randomised inputs, including the cases that make it subtle: chords, ties
    in pitch, zero-length notes, and unpitched sounds that all collapse onto
    the same pitch.
    """
    ordered = sorted(notes, key=lambda n: n.start)
    pitches = [shader_pitch(n.shader) or 0 for n in ordered]

    sounding = [0] * (_PITCH_CEILING + 1)
    ending: list[tuple[int, int]] = []  # min-heap of (end, index), the live notes
    kept = []
    index, total = 0, len(ordered)

    while index < total:
        onset = ordered[index].start

        # Every note that starts at this instant joins the live set. They must
        # join BEFORE the eviction below, so that a zero-length note is added
        # and immediately removed rather than lingering.
        group_end = index
        while group_end < total and ordered[group_end].start == onset:
            sounding[pitches[group_end]] += 1
            heapq.heappush(ending, (ordered[group_end].end, group_end))
            group_end += 1

        # Anything that has finished by now is no longer sounding. A note is
        # sounding at `onset` only while start <= onset < end, so an end
        # exactly at `onset` is already over.
        while ending and ending[0][0] <= onset:
            _, finished = heapq.heappop(ending)
            sounding[pitches[finished]] -= 1

        for i in range(index, group_end):
            # Strictly higher, so the note itself and anything at its own
            # pitch are both excluded -- ties are kept, as they always were.
            if sum(sounding[pitches[i] + 1 :]) < max_poly:
                kept.append(ordered[i])

        index = group_end

    return kept
