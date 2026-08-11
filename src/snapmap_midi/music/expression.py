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
    volume_trim_db: int
    master_volume_db: int
    automatic_pitch: int | None
    requested_pitch: int
    pitch_modifier: int
    pitch_limited: bool
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


def expression_for(
    source_pitch: int,
    velocity: int,
    root_pitch: float | None,
    pitch_offset: int = 0,
    volume_trim_db: int = 0,
    master_volume_db: int = 0,
) -> NoteExpression:
    """Resolve one note to the exact integral values SnapMap will receive.

    The source MIDI pitch never moves. With a trusted root or an explicit
    relative reference, the automatic modifier makes the sound follow that
    MIDI note and ``pitch_offset`` is added afterward. Without either basis,
    the sound keeps its natural playback pitch and ``pitch_offset`` is the only
    modifier. This keeps composition, sound choice, and playback tuning as
    separate decisions.
    """

    source_pitch = int(clamp(int(source_pitch), MIDI_MIN, MIDI_MAX))
    pitch_offset = int(clamp(int(pitch_offset), PITCH_MIN, PITCH_MAX))
    volume_trim_db = int(clamp(int(volume_trim_db), VOLUME_MIN, VOLUME_MAX))
    master_volume_db = int(clamp(int(master_volume_db), VOLUME_MIN, VOLUME_MAX))
    target_pitch = source_pitch

    if root_pitch is None:
        automatic_pitch = None
        requested_pitch = pitch_offset
    else:
        automatic_pitch = nearest_int(source_pitch - float(root_pitch))
        requested_pitch = automatic_pitch + pitch_offset
    pitch_modifier = int(clamp(requested_pitch, PITCH_MIN, PITCH_MAX))

    velocity = int(clamp(int(velocity), 1, MIDI_MAX))
    velocity_db = midi_velocity_db(velocity)
    requested_volume = velocity_db + master_volume_db + volume_trim_db
    volume_db = int(clamp(requested_volume, VOLUME_MIN, VOLUME_MAX))

    return NoteExpression(
        source_pitch=source_pitch,
        target_pitch=target_pitch,
        velocity=velocity,
        root_pitch=None if root_pitch is None else float(root_pitch),
        pitch_offset=pitch_offset,
        volume_trim_db=volume_trim_db,
        master_volume_db=master_volume_db,
        automatic_pitch=automatic_pitch,
        requested_pitch=requested_pitch,
        pitch_modifier=pitch_modifier,
        pitch_limited=pitch_modifier != requested_pitch,
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
