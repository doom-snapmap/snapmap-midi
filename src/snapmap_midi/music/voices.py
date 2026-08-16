"""Voice allocation, glide ancestry, and density thinning.

A concrete-channel Timeline emitter is monophonic: starting a second note on
one prevents the first from overlapping. So overlapping adjusted or sustained
notes need separate emitters, and "how many emitters does this layer need" is
exactly an interval-graph colouring.

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
    part_glide_ms: dict | None = None,
    part_attack_ms: dict | None = None,
    part_voices: dict | None = None,
    part_sustain_ms: dict | None = None,
):
    """Apply duration policy and build the isolated per-track voice layers.

    Neutral one-shots remain on the shared timeline entity. Notes that need a
    pitch or volume modifier must use an emitter voice of their own, so they
    reserve it for the installed event duration (or a conservative fallback).
    A Sustain Limit that would cut a one-shot's natural ring also routes that
    note through an emitter: a shared Timeline start has no per-note stop.
    A glide-enabled exact-sound track reserves all of its one-shots as well:
    its zero-offset root note still has to travel through the same voice lane as
    the adjusted notes around it. Any track that explicitly sets Track Voices
    also routes every one-shot through that lane; otherwise a neutral root note
    could escape to the shared path and overlap even when Track Voices is 1.
    This function is shared by map export and browser preview so their cutoffs
    cannot drift apart.
    """

    family_caps = family_caps or {}
    part_sustain_ms = part_sustain_ms or {}
    part_glide_ms = part_glide_ms or {}
    part_attack_ms = part_attack_ms or {}
    part_voices = part_voices or {}

    # Cache the installed duration by Play event. Exact sounds commonly repeat
    # hundreds of times in a part; querying Wwise metadata for every note made
    # an otherwise simple cap slider feel needlessly expensive.
    durations = {}

    def one_shot_end(note):
        if note.shader not in durations:
            durations[note.shader] = (
                duration_lookup(note.shader) if duration_lookup is not None else None
            )
        duration = durations[note.shader]
        if duration is None:
            duration = 750 if note.fam == "drums" else 1000
        return note.start + pitched_duration_ms(duration, getattr(note, "pitch_modifier", 0))

    if cap_sustain_ms or bass_cap_ms or family_caps or part_sustain_ms:
        for note in sustained + decaying:
            # Most-specific duration wins: a track override, then its sound
            # category, then the song's default. The bass cap remains an
            # additional ceiling because it deliberately targets register,
            # independent of which track or instrument produced the note.
            cap = _part_value(part_sustain_ms, note, None)
            if cap is None:
                cap = family_caps.get(note.fam, cap_sustain_ms)
            pitch = _note_pitch(note)
            if bass_cap_ms and pitch < bass_pitch:
                cap = min(cap, bass_cap_ms) if cap is not None else bass_cap_ms
            if cap is None:
                continue

            cap_end = note.start + cap
            # A looping sound's duration is governed by MIDI note-off. A
            # one-shot keeps playing after note-off, so compare its installed
            # ring instead. Its scheduled end deliberately becomes the cap
            # even when the written block is shorter; `midi_end` remains the
            # visual/source note-off while this end is the audible stop.
            current_end = note.end if note.sustained else one_shot_end(note)
            if current_end > cap_end:
                note.end = cap_end
                note.sustain_limited = True

    expressive = [
        note
        for note in decaying
        if note.pitch_modifier != 0
        or note.volume_db != 0
        or (
            _part_value(part_glide_ms, note, 0) > 0
            and bool(getattr(note, "uses_exact_sound", False))
        )
        or _part_value(part_attack_ms, note, 0) > 0
        or _part_value(part_voices, note, None) is not None
        or bool(getattr(note, "sustain_limited", False))
    ]
    expressive_ids = {id(note) for note in expressive}
    shared = [note for note in decaying if id(note) not in expressive_ids]

    for note in expressive:
        natural_end = one_shot_end(note)
        # Wwise voice pitch changes playback speed. Reserving the unpitched
        # duration makes low notes steal speakers too early while high notes
        # reserve a silent tail. A deliberate sustain cap frees the isolated
        # lane at that cap instead of at the now-inaudible natural tail.
        note.voice_end = min(natural_end, note.end) if getattr(
            note, "sustain_limited", False
        ) else natural_end

    # Keyed by PART -- (track, channel) -- so per-track polyphony can be
    # applied before the resulting isolated notes join the one global voice
    # pool. A MIDI channel is not an identity: two tracks can write to it.
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

    When two voices would free at the SAME moment -- which is the ordinary case,
    since notes written to end together end together -- the one carrying the
    OLDEST sound gives way. Without that rule the winner was decided by slot
    order, so a note could hold one voice for the whole song while every other
    note took turns being chopped on the next: five notes entering 200 ms apart
    kept the second one intact and cut the third, which is neither the oldest
    nor the newest and answers to nothing musical. Oldest-first is what a
    hardware synth does, and it is a sentence that can be put in front of a user:
    the longest-running sound is the one that gives way.

    This makes the outcome deterministic and protects the melody. It does NOT
    make the model right for chords: see `docs/limits.md` -- a note that cannot
    get a speaker at its onset is truncated to zero length, so it is silent
    while still being drawn as a shortened note rather than a deleted one.
    """
    notes.sort(key=lambda n: (n.start, _note_pitch(n), _voice_tie_key(n)))
    free_at: list[int] = []
    # When each voice's current sound began, so a tie on free time can be
    # settled by age rather than by which slot happens to come first.
    began: list[int] = []
    for note in notes:
        voice = next((i for i, t in enumerate(free_at) if t <= note.start), None)
        if voice is None:
            if len(free_at) < max_speakers:
                voice = len(free_at)
                free_at.append(0)
                began.append(0)
            else:
                voice = min(range(len(free_at)), key=lambda i: (free_at[i], began[i]))
        note.voice = voice
        free_at[voice] = _allocation_end(note)
        began[voice] = note.start
    return len(free_at)


def apply_voice_cap(notes, max_voices: int):
    """Apply a track's voice budget before notes enter the global pool.

    A cap has two effects. Chord notes beyond it cannot start and are omitted;
    later notes still start, but take a virtual voice from an older note in the
    same track. ``voice_cap_end`` records that local steal so the later global
    allocation and the event writer cannot accidentally let this track consume
    spare speakers from the rest of the song.
    """
    kept = thin_simultaneous(notes, max_voices)
    allocate_voices(kept, max_voices)
    by_voice = {}
    for note in kept:
        # Global allocation below intentionally overwrites ``voice``. Keep the
        # track-local lane: glide follows the previous note in this lane, not
        # whichever unrelated track last occupied the physical emitter.
        note.part_voice = note.voice
        by_voice.setdefault(note.voice, []).append(note)
    for voice_notes in by_voice.values():
        voice_notes.sort(key=lambda note: note.start)
        for index, note in enumerate(voice_notes[:-1]):
            next_note = voice_notes[index + 1]
            if next_note.start < _allocation_end(note):
                note.voice_cap_end = next_note.start
    return kept


def apply_glides(notes, part_glide_ms: dict | None = None):
    """Annotate each exact-sound note with its track-local glide start.

    A physical emitter is a song-wide implementation detail and can move from
    one track to another as the allocator reuses it. ``part_voice`` is the
    musical lane. Following that lane makes Track Voices = 1 a conventional
    monophonic portamento path, while wider tracks glide each voice
    independently. Different shaders are never interpolated: automatic
    pre-tuned instruments are separate recordings, not two pitch values of one
    sample.
    """
    part_glide_ms = part_glide_ms or {}
    previous = {}
    ordered = sorted(notes, key=lambda n: (n.start, _note_pitch(n), _voice_tie_key(n)))
    for note in ordered:
        note.glide_ms = 0
        glide_ms = int(_part_value(part_glide_ms, note, 0) or 0)
        lane = (
            getattr(note, "track", 0),
            note.chan,
            getattr(note, "part_voice", getattr(note, "voice", 0)),
        )
        prior = previous.get(lane)
        if (
            glide_ms > 0
            and prior is not None
            and bool(getattr(note, "uses_exact_sound", False))
            and bool(getattr(prior, "uses_exact_sound", False))
            and prior.shader == note.shader
            and prior.pitch_modifier != note.pitch_modifier
        ):
            note.glide_ms = glide_ms
            note.glide_from_pitch = prior.pitch_modifier
        previous[lane] = note
    return notes


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
        # Track/channel/note identity makes equal pitches deterministic too.
        kept.extend(sorted(group, key=lambda n: (-_note_pitch(n), _voice_tie_key(n)))[:max_voices])
    return kept


def thin_global_polyphony(notes, max_poly: int):
    """Admit at most ``max_poly`` written notes across the whole song.

    This is deliberately strict and path-agnostic: a neutral one-shot on the
    shared Timeline counts exactly like a sustained or pitch-controlled note on
    an isolated emitter. Notes already playing retain their written duration;
    when fewer slots remain than notes beginning together, the highest new
    pitches are admitted and the rest never start.

    Unlike voice stealing, a later note does not cut an earlier one short. That
    distinction is what makes this a polyphony limit rather than another voice
    allocator.
    """
    if not max_poly:
        return list(notes)

    ordered = sorted(notes, key=lambda n: (n.start, -_note_pitch(n), _voice_tie_key(n)))
    active_ends: list[int] = []
    kept = []
    index = 0
    while index < len(ordered):
        onset = ordered[index].start
        while active_ends and active_ends[0] <= onset:
            heapq.heappop(active_ends)

        group_end = index
        while group_end < len(ordered) and ordered[group_end].start == onset:
            group_end += 1
        group = ordered[index:group_end]
        available = max(0, max_poly - len(active_ends))
        for note in group[:available]:
            kept.append(note)
            if note.end > onset:
                heapq.heappush(active_ends, note.end)
        index = group_end
    return kept


def _note_pitch(note) -> int:
    pitch = getattr(note, "pitch", None)
    if pitch is not None:
        return int(pitch)
    return shader_pitch(note.shader) or 0


def _allocation_end(note) -> int:
    """When a voice is available again, including a track-level steal."""
    natural_end = getattr(note, "voice_end", note.end)
    return min(natural_end, getattr(note, "voice_cap_end", natural_end))


def _voice_tie_key(note):
    """A reproducible last tie-break for same-pitch simultaneous notes."""
    return (getattr(note, "track", 0), getattr(note, "chan", 0), str(getattr(note, "id", "")))


def _part_value(mapping, note, default=None):
    """Most-specific part setting without importing MIDI and creating a cycle."""
    track = getattr(note, "track", 0)
    part = (track, note.chan)
    if part in mapping:
        return mapping[part]
    return mapping.get(note.chan, default)


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
