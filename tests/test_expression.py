"""Pure pitch and loudness math shared by preview and map export."""

from __future__ import annotations

import pytest

from snapmap_midi.music.expression import (
    db_gain,
    expression_for,
    midi_velocity_db,
    nearest_int,
)


def test_rounding_is_symmetric_at_half_steps():
    assert nearest_int(2.5) == 3
    assert nearest_int(-2.5) == -3


def test_midi_velocity_is_monotonic_and_full_velocity_is_unity():
    velocities = [1, 16, 32, 64, 96, 127]
    levels = [midi_velocity_db(value) for value in velocities]
    assert levels == sorted(levels)
    assert levels[-1] == 0
    assert midi_velocity_db(64) == -12


def test_a_trusted_root_follows_the_target_note():
    expression = expression_for(72, 127, 60)
    assert expression.source_pitch == 72
    assert expression.target_pitch == 72
    assert expression.automatic_pitch == 12
    assert expression.requested_pitch == 12
    assert expression.pitch_modifier == 12
    assert expression.pitch_limited is False


def test_a_fixed_pitch_sound_treats_the_note_trim_as_a_direct_modifier():
    expression = expression_for(60, 127, None, transpose=-7)
    assert expression.automatic_pitch is None
    assert expression.target_pitch == 53
    assert expression.pitch_modifier == -7


def test_target_midi_and_snapmap_pitch_are_clamped_independently():
    expression = expression_for(126, 127, 60, transpose=24)
    assert expression.transpose == 24
    assert expression.applied_transpose == 1
    assert expression.target_pitch == 127
    assert expression.requested_pitch == 67
    assert expression.pitch_modifier == 24
    assert expression.pitch_limited is True


def test_velocity_and_note_trim_share_the_engine_db_limits():
    quiet = expression_for(60, 1, 60, volume_trim_db=-60)
    assert quiet.velocity_db == -60
    assert quiet.requested_volume_db == -120
    assert quiet.volume_db == -60
    assert quiet.volume_limited is True

    loud = expression_for(60, 127, 60, volume_trim_db=20)
    assert loud.volume_db == 20
    assert loud.volume_limited is False


@pytest.mark.parametrize(
    ("db", "gain"),
    [
        (0, 1.0),
        (-6, 0.501187),
        (20, 10.0),
    ],
)
def test_db_gain_matches_web_audio_amplitude(db, gain):
    assert db_gain(db) == pytest.approx(gain, rel=1e-5)
