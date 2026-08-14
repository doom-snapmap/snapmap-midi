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
from collections.abc import Callable

from snapmap_midi.music.expression import pitched_duration_ms
from snapmap_midi.sound.palette import shader_pitch


def prepare_voice_layers(
    decaying,
    sustained,
    *,
    cap_sustain_ms: int | None = None,
    bass_pitch: int = 78,
    bass_cap_ms: int | None = None,
    family_caps: dict | None = None,
    duration_lookup: Callable[[str], int | None] | None = None,
):
    """Apply duration policy and build the isolated per-channel voice layers.

    Neutral one-shots remain on the shared timeline entity. Notes that need a
    pitch or volume modifier must use a speaker of their own, so they reserve a
    voice for the installed event duration (or a conservative fallback). This
    function is shared by map export and browser preview so their cutoffs cannot
    drift apart.
    """

    family_caps = family_caps or {}
    if cap_sustain_ms or bass_cap_ms or family_caps:
        for note in sustained:
            cap = family_caps.get(note.fam, cap_sustain_ms or 10**9)
            pitch = _note_pitch(note)
            if bass_cap_ms and pitch < bass_pitch:
                cap = min(cap, bass_cap_ms)
            if note.duration > cap:
                note.end = note.start + cap

    expressive = [note for note in decaying if note.pitch_modifier != 0 or note.volume_db != 0]
    expressive_ids = {id(note) for note in expressive}
    shared = [note for note in decaying if id(note) not in expressive_ids]

    durations = {}
    for note in expressive:
        if note.shader not in durations:
            durations[note.shader] = (
                duration_lookup(note.shader) if duration_lookup is not None else None
            )
        duration = durations[note.shader]
        if duration is None:
            duration = 750 if note.fam == "drums" else 1000
        # Wwise voice pitch changes playback speed. Reserving the unpitched
        # duration makes low notes steal speakers too early while high notes
        # reserve a silent tail.
        duration = pitched_duration_ms(duration, note.pitch_modifier)
        note.voice_end = note.start + duration

    # Keyed by PART -- (track, channel) -- and not by channel alone. A MIDI
    # channel is not an identity: two tracks can write to the same one, and the
    # window shows them as two rows because they are two parts. Keying the pool
    # by channel put both rows in one pool, so one part's notes stole the
    # other's speakers and each looked like it was being cut by the other's
    # music. Same song exported with the second part on channel 2 instead of
    # channel 1 then behaved completely differently, which is the bug report
    # this comes from.
    layers = {}
    for note in sustained + expressive:
        layers.setdefault((getattr(note, "track", 0), note.chan), []).append(note)
    return shared, expressive, layers


def allocate_voices(notes, max_speakers: int) -> int:
    """Assign each note a voice so no two overlap on one. Returns voices used.

    Greedy by start time, reusing the first voice that has freed up. Past
    `max_speakers` it steals the voice that frees earliest, which truncates
    that note rather than dropping this one -- losing the tail of an older
    note is less audible than a missing attack.

    Notes that START TOGETHER are ordered by pitch, LOWEST first, and that tie
    break is load-bearing rather than tidiness. Sorting on `start` alone is a
    stable sort, so a chord kept whatever order the FILE happened to list its
    notes in -- and which notes won a speaker followed from that. The same
    five-note chord under two speakers gave C3+G3, or G4+E4, or C4+C3, purely
    from how the exporter ordered its events. Two exports of one arrangement
    sounded different for no musical reason, which is what this was reported as.

    Lowest-first because among notes that start together the LAST one allocated
    to a voice is the one that keeps it -- every earlier note on that voice is
    truncated by the next. Ascending pitch therefore leaves the top note
    holding a speaker, which is the note a listener would miss.

    This makes the outcome deterministic and protects the melody. It does NOT
    make the model right for chords: see `docs/limits.md` -- a note that cannot
    get a speaker at its onset is truncated to zero length, so it is silent
    while still being drawn as a shortened note rather than a deleted one.
    """
    notes.sort(key=lambda n: (n.start, _note_pitch(n)))
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
        free_at[voice] = getattr(note, "voice_end", note.end)
    return len(free_at)


def thin_simultaneous(notes, max_voices: int):
    """Drop only what cannot physically sound: more notes STARTING AT ONCE
    than there are voices. Highest kept, as a synth does.

    This is deliberately not `thin_polyphony`. That one counts every note still
    SOUNDING, tails included, which is right for an editorial density lever and
    catastrophically wrong for a voice count: a plain descending melody, one
    note at a time and nothing overlapping, lost seven of its eight notes at one
    voice, because each note's 4-second sample tail was still ringing when the
    next arrived and the next was lower.

    A ringing tail does not stop the next note from playing. It gets CUT by it
    -- one speaker, retriggered, exactly like a monosynth. Only notes that
    begin together are competing for a speaker at the same instant, and only
    they can be genuinely unplayable.

    So: notes that share an onset are capped here, and everything else is left
    to `allocate_voices` to steal and truncate as it always did.
    """
    if not max_voices:
        return list(notes)
    by_start: dict = {}
    for note in notes:
        by_start.setdefault(note.start, []).append(note)
    kept = []
    for group in by_start.values():
        if len(group) <= max_voices:
            kept.extend(group)
            continue
        # Ties on pitch keep their existing order, which allocate_voices then
        # sorts deterministically anyway.
        kept.extend(sorted(group, key=lambda n: -_note_pitch(n))[:max_voices])
    return kept


def _note_pitch(note) -> int:
    pitch = getattr(note, "pitch", None)
    if pitch is not None:
        return int(pitch)
    return shader_pitch(note.shader) or 0


#: One past the highest pitch a sound name can encode. The octave is a single
#: digit, so the ceiling is octave 9's B: (9 + 1) * 12 + 11.
_PITCH_CEILING = (9 + 1) * 12 + 11 + 1


def thin_polyphony(notes, max_poly: int):
    """Keep at most `max_poly` notes held at once, preferring higher pitches.

    Melody and upper harmony carry the tune; inner doublings are what a
    listener misses least. Kept notes retain their FULL length -- this reduces
    how many notes sound at once, not how long each one lasts, so stops still
    land while sustain stays natural.

    "At once" means keys held together, measured on written note ends. It used
    to measure the sample's ringing tail (`voice_end`) instead, on the reasoning
    that a tail still occupies an emitter -- which is true, and still the wrong
    thing for this lever. A 124 ms note can trigger a 4-second sample, so a
    plain melody a beat apart read as a seven-note chord and `max_poly=1`
    deleted six notes that never overlapped anything. A density lever that
    empties a monophonic line is not a density lever.

    The tail limit is real; it belongs to the speaker count and the duration
    caps, which is where it now lives exclusively. Note that this also makes
    this function agree exactly with the naive oracle in `tests/test_voices.py`,
    which always compared written ends.

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
    pitches = [_note_pitch(note) for note in ordered]

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
            # The WRITTEN end, not `voice_end`. Polyphony is how many keys are
            # held down at once, which is what a player sees on the roll and
            # what they set this lever from. Measuring the sample's ringing
            # tail instead made a plain melody look like a chord: seven notes
            # a beat apart, nothing overlapping, and `max_poly=1` deleted six
            # of them because each 124 ms note sat on a 4-second sample.
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
