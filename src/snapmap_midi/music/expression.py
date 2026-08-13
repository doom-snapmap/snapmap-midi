"""Pitch and loudness math shared by map export and browser preview.

SnapMap exposes integral semitone and dB modifiers. Keeping every conversion in
this module prevents the UI, compiler, and tests from growing slightly different
rounding and clamping rules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PITCH_MIN = -24
PITCH_MAX = 24
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
    pitch_offset: int
    pitch_semitones: int | None
    volume_trim_db: int
    note_volume_db: int
    master_volume_db: int
    automatic_pitch: int | None
    requested_pitch: int
    pitch_modifier: int
    pitch_limited: bool
    playback_rate: float
    velocity_db: int
    requested_volume_db: int
    volume_db: int
    volume_limited: bool


def clamp(value, low, high):
    return max(low, min(high, value))


def nearest_int(value: float) -> int:
    """Round halves away from zero rather than with Python's even-number rule."""

    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


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
    pitch_offset: int = 0,
    pitch_semitones: int | None = None,
    volume_trim_db: int = 0,
    note_volume_db: int | None = None,
    master_volume_db: int = 0,
) -> NoteExpression:
    """Resolve one note to the exact integral values SnapMap will receive.

    The source MIDI pitch never moves. With a trusted or manually calibrated
    playback reference, the automatic modifier makes the sound follow that
    MIDI note. A legacy pitch_offset is added afterward; an absolute
    pitch_semitones value instead replaces the automatic result so the note
    control always represents the exact SnapMap modifier it will export.
    Without a playback reference, natural playback is zero and either kind of
    note edit remains playback-only.

    MIDI velocity supplies the initial note volume. An absolute
    ``note_volume_db`` replaces that initial value, while master volume is
    always added afterward. ``volume_trim_db`` exists only to replay migrated
    settings from builds that stored note edits as relative offsets. This keeps
    composition, sound choice, and playback tuning as separate decisions.
    """

    source_pitch = int(clamp(int(source_pitch), MIDI_MIN, MIDI_MAX))
    pitch_offset = int(clamp(int(pitch_offset), PITCH_MIN, PITCH_MAX))
    if pitch_semitones is not None:
        pitch_semitones = int(clamp(int(pitch_semitones), PITCH_MIN, PITCH_MAX))
    volume_trim_db = int(clamp(int(volume_trim_db), VOLUME_MIN, VOLUME_MAX))
    master_volume_db = int(clamp(int(master_volume_db), VOLUME_MIN, VOLUME_MAX))
    target_pitch = source_pitch

    if root_pitch is None:
        automatic_pitch = None
        requested_pitch = pitch_offset
    else:
        automatic_pitch = nearest_int(source_pitch - float(root_pitch))
        requested_pitch = automatic_pitch + pitch_offset
    if pitch_semitones is not None:
        requested_pitch = pitch_semitones
    pitch_modifier = int(clamp(requested_pitch, PITCH_MIN, PITCH_MAX))
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
    requested_volume = note_volume + master_volume_db
    volume_db = int(clamp(requested_volume, VOLUME_MIN, VOLUME_MAX))

    return NoteExpression(
        source_pitch=source_pitch,
        target_pitch=target_pitch,
        velocity=velocity,
        root_pitch=None if root_pitch is None else float(root_pitch),
        pitch_offset=pitch_offset,
        pitch_semitones=pitch_semitones,
        volume_trim_db=volume_trim_db,
        note_volume_db=note_volume,
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
