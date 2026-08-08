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

from snapmap_midi.palette import shader_pitch


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


def thin_polyphony(notes, max_poly: int):
    """Keep at most `max_poly` simultaneous notes, preferring higher pitches.

    Melody and upper harmony carry the tune; inner doublings are what a
    listener misses least. Kept notes retain their FULL length -- this reduces
    how many notes sound at once, not how long each one lasts, so stops still
    land while sustain stays natural.
    """
    ordered = sorted(notes, key=lambda n: n.start)
    pitch = {id(n): (shader_pitch(n.shader) or 0) for n in ordered}
    kept = []
    for note in ordered:
        # How many notes sounding at this one's onset are higher?
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
