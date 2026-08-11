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


def test_a_trusted_root_follows_the_imported_midi_note():
    expression = expression_for(72, 127, 60)
    assert expression.source_pitch == 72
    assert expression.target_pitch == 72
    assert expression.automatic_pitch == 12
    assert expression.requested_pitch == 12
    assert expression.pitch_modifier == 12
    assert expression.pitch_limited is False


def test_natural_playback_treats_the_note_offset_as_a_direct_modifier():
    expression = expression_for(60, 127, None, pitch_offset=-7)
    assert expression.automatic_pitch is None
    assert expression.target_pitch == 60
    assert expression.pitch_offset == -7
    assert expression.requested_pitch == -7
    assert expression.pitch_modifier == -7


def test_pitch_offset_never_moves_the_imported_note_and_engine_pitch_clamps():
    expression = expression_for(126, 127, 60, pitch_offset=24)
    assert expression.source_pitch == 126
    assert expression.target_pitch == 126
    assert expression.pitch_offset == 24
    assert expression.automatic_pitch == 66
    assert expression.requested_pitch == 90
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


def test_master_volume_offsets_every_note_before_the_engine_clamp():
    expression = expression_for(60, 64, 60, volume_trim_db=3, master_volume_db=8)

    assert expression.velocity_db == -12
    assert expression.master_volume_db == 8
    assert expression.volume_trim_db == 3
    assert expression.requested_volume_db == -1
    assert expression.volume_db == -1


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
