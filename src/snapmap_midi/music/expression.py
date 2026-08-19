"""Pitch and loudness math shared by map export and browser preview.

SnapMap's Timeline stores pitch as a floating-point semitone modifier. Keeping
every conversion in this module prevents the UI, compiler, and tests from
growing slightly different rounding and clamping rules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PITCH_MIN = -24
PITCH_MAX = 24

#: How far the automatic octave fold may reach, in octaves. MIDI spans a little
#: over ten octaves, so nothing legitimate needs more than this and a runaway
#: root cannot send a part somewhere absurd.
OCTAVE_FOLD_LIMIT = 10
VOLUME_MIN = -60
VOLUME_MAX = 20
MIDI_MIN = 0
MIDI_MAX = 127


@dataclass(frozen=True)
class NoteExpression:
    """The complete derived expression state for one imported MIDI note."""

    source_pitch: int
    target_pitch: int
    velocity: int
    root_pitch: float | None
    pitch_offset: float
    pitch_semitones: float | None
    track_transpose: float
    octave_shift: int
    fine_tune_cents: float
    volume_trim_db: int
    note_volume_db: int
    track_volume_db: int
    master_volume_db: int
    automatic_pitch: float | None
    requested_pitch: float
    pitch_modifier: float
    pitch_limited: bool
    playback_rate: float
    velocity_db: int
    requested_volume_db: int
    volume_db: int
    volume_limited: bool


def clamp(value, low, high):
    return max(low, min(high, value))


def clean_float(value: float) -> float:
    """Keep JSON and UI readouts stable after decimal semitone arithmetic."""

    value = round(float(value), 6)
    return 0.0 if value == 0 else value


def nearest_int(value: float) -> int:
    """Round halves away from zero rather than with Python's even-number rule."""

    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def octave_fold(root_pitch, lowest, highest, extra_semitones: float = 0.0) -> int:
    """How many octaves to move a part so its notes fit the engine's range.

    SnapMap's pitch modifier stops at +/-24 semitones. A sound whose natural
    note sits further than that from the music does not merely play badly: every
    note past the limit clamps to the SAME modifier, so a melody collapses onto
    one pitch. A sample calibrated to C7 under a part written around C4 asks for
    -36 on every note and gets -24 on every note.

    Moving by whole OCTAVES is what makes this safe. Twelve is an integer, so a
    fold shifts the register while preserving the pitch class exactly -- and,
    because it is added to a fractional reference rather than replacing it, a
    calibration of "C7 -7 cents" stays seven cents flat after the fold. Folding
    by anything other than an octave would transpose the part.

    `extra_semitones` carries whatever the track already adds on top of the
    reference -- transpose and fine tune. Including it is what makes this
    idempotent: someone who has ALREADY corrected an out-of-range sound by hand
    with +24 of transpose measures as in-range here and is not shifted a second
    time.

    The smallest fit wins, because that is the one closest to the written
    octave. A part whose own span exceeds the engine's 48-semitone window
    cannot fit at any offset; it is centered instead, leaving the ordinary
    clamp to handle the extremes rather than pretending they were solved.
    """

    if root_pitch is None or lowest is None or highest is None:
        return 0
    low = float(lowest) - float(root_pitch) + float(extra_semitones)
    high = float(highest) - float(root_pitch) + float(extra_semitones)
    if PITCH_MIN <= low and high <= PITCH_MAX:
        return 0
    smallest = math.ceil((PITCH_MIN - low) / 12.0)
    largest = math.floor((PITCH_MAX - high) / 12.0)
    if smallest <= largest:
        # 0 is not among them -- an in-range part returned above.
        fold = smallest if smallest > 0 else largest
    else:
        fold = nearest_int(-(low + high) / 24.0)
    return int(clamp(fold, -OCTAVE_FOLD_LIMIT, OCTAVE_FOLD_LIMIT))


def midi_velocity_db(velocity: int) -> int:
    """Convert MIDI velocity to SnapMap dB with a squared-amplitude response."""

    velocity = int(clamp(int(velocity), 1, MIDI_MAX))
    db = 40.0 * math.log10(velocity / MIDI_MAX)
    return int(clamp(nearest_int(db), VOLUME_MIN, 0))


def db_gain(db: float) -> float:
    """A dB modifier as a linear Web Audio gain multiplier."""

    return 10.0 ** (float(db) / 20.0)


def pitch_playback_rate(semitones: float) -> float:
    """SnapMap/Wwise voice pitch as a sample-playback speed multiplier.

    Voice pitch is ordinary resampling, not independent time stretching: an
    octave up plays twice as fast and an octave down takes twice as long. The
    finalized, clamped SnapMap modifier is the input so preview scheduling and
    exported voice allocation cannot disagree at the engine limits.
    """

    return 2.0 ** (float(semitones) / 12.0)


def pitched_duration_ms(duration_ms: int, semitones: float) -> int:
    """Natural one-shot duration after SnapMap applies ``semitones``."""

    return max(1, nearest_int(float(duration_ms) / pitch_playback_rate(semitones)))


def expression_for(
    source_pitch: int,
    velocity: int,
    root_pitch: float | None,
    pitch_offset: float = 0,
    pitch_semitones: float | None = None,
    track_transpose: float = 0,
    octave_shift: int = 0,
    fine_tune_cents: float = 0,
    volume_trim_db: int = 0,
    note_volume_db: int | None = None,
    track_volume_db: int = 0,
    master_volume_db: int = 0,
) -> NoteExpression:
    """Resolve one note to the exact values SnapMap will receive.

    The source MIDI pitch never moves. With a trusted or manually calibrated
    playback reference, the automatic modifier makes the sound follow that
    MIDI note, including the reference's fractional cents. A legacy
    pitch_offset is added afterward; a pitch_semitones value instead replaces
    that per-note result. Track transpose and fine tune are then added to every
    note, including manually edited ones. Without a playback reference,
    natural playback is zero and the same track/note controls remain direct
    playback modifiers.

    MIDI velocity supplies the initial note volume. An absolute
    ``note_volume_db`` replaces that initial value. Track volume and then
    master volume are always added afterward. ``volume_trim_db`` exists only to replay migrated
    settings from builds that stored note edits as relative offsets. This keeps
    composition, sound choice, and playback tuning as separate decisions.
    """

    source_pitch = int(clamp(int(source_pitch), MIDI_MIN, MIDI_MAX))
    pitch_offset = clean_float(clamp(float(pitch_offset), PITCH_MIN, PITCH_MAX))
    if pitch_semitones is not None:
        pitch_semitones = clean_float(clamp(float(pitch_semitones), PITCH_MIN, PITCH_MAX))
    track_transpose = clean_float(clamp(float(track_transpose), PITCH_MIN, PITCH_MAX))
    octave_shift = int(clamp(int(octave_shift), -OCTAVE_FOLD_LIMIT, OCTAVE_FOLD_LIMIT))
    fine_tune_cents = clean_float(clamp(float(fine_tune_cents), -100.0, 100.0))
    volume_trim_db = int(clamp(int(volume_trim_db), VOLUME_MIN, VOLUME_MAX))
    track_volume_db = int(clamp(int(track_volume_db), VOLUME_MIN, VOLUME_MAX))
    master_volume_db = int(clamp(int(master_volume_db), VOLUME_MIN, VOLUME_MAX))
    target_pitch = source_pitch

    if root_pitch is None:
        automatic_pitch = None
        requested_pitch = pitch_offset
    else:
        automatic_pitch = clean_float(source_pitch - float(root_pitch))
        requested_pitch = automatic_pitch + pitch_offset
    if pitch_semitones is not None:
        requested_pitch = pitch_semitones
    # The octave fold joins transpose and fine tune rather than moving
    # `root_pitch`, so the reference stays the honest natural note of the
    # recording in every readout and every saved sidecar. It is a playback
    # decision about where the part sits, not a claim about the sample.
    requested_pitch = clean_float(
        requested_pitch + track_transpose + fine_tune_cents / 100.0 + 12 * octave_shift
    )
    pitch_modifier = clean_float(clamp(requested_pitch, PITCH_MIN, PITCH_MAX))
    playback_rate = pitch_playback_rate(pitch_modifier)

    velocity = int(clamp(int(velocity), 1, MIDI_MAX))
    velocity_db = midi_velocity_db(velocity)
    if note_volume_db is None:
        # Version-4 sidecars stored a relative trim. Keep its uncapped sum so
        # global volume produces exactly the same result after migration.
        note_volume = velocity_db + volume_trim_db
    else:
        note_volume = int(clamp(int(note_volume_db), VOLUME_MIN, VOLUME_MAX))
        volume_trim_db = note_volume - velocity_db
    requested_volume = note_volume + track_volume_db + master_volume_db
    volume_db = int(clamp(requested_volume, VOLUME_MIN, VOLUME_MAX))

    return NoteExpression(
        source_pitch=source_pitch,
        target_pitch=target_pitch,
        velocity=velocity,
        root_pitch=None if root_pitch is None else float(root_pitch),
        pitch_offset=pitch_offset,
        pitch_semitones=pitch_semitones,
        track_transpose=track_transpose,
        octave_shift=octave_shift,
        fine_tune_cents=fine_tune_cents,
        volume_trim_db=volume_trim_db,
        note_volume_db=note_volume,
        track_volume_db=track_volume_db,
        master_volume_db=master_volume_db,
        automatic_pitch=automatic_pitch,
        requested_pitch=requested_pitch,
        pitch_modifier=pitch_modifier,
        pitch_limited=pitch_modifier != requested_pitch,
        playback_rate=playback_rate,
        velocity_db=velocity_db,
        requested_volume_db=requested_volume,
        volume_db=volume_db,
        volume_limited=volume_db != requested_volume,
    )


def annotate(note, expression: NoteExpression, **metadata):
    """Attach expression metadata without changing Note's serialized fields."""

    for field, value in expression.__dict__.items():
        setattr(note, field, value)
    note.pitch = expression.target_pitch
    for field, value in metadata.items():
        setattr(note, field, value)
    return note
