"""Pure pitch and loudness math shared by preview and map export."""

from __future__ import annotations

import pytest

from snapmap_midi.music.expression import (
    db_gain,
    expression_for,
    midi_velocity_db,
    nearest_int,
    pitch_playback_rate,
    pitched_duration_ms,
)


def test_rounding_is_symmetric_at_half_steps():
    assert nearest_int(2.5) == 3
    assert nearest_int(-2.5) == -3


def test_snapmap_pitch_uses_resampling_speed_and_changes_one_shot_duration():
    assert pitch_playback_rate(12) == pytest.approx(2.0)
    assert pitch_playback_rate(-12) == pytest.approx(0.5)
    assert pitched_duration_ms(1000, 12) == 500
    assert pitched_duration_ms(1000, -12) == 2000


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


def test_natural_sample_note_compensates_inversely_but_transpose_is_direct():
    # A D-sharp sample has to be pitched down three semitones to produce MIDI C.
    calibrated = expression_for(60, 127, 63)
    assert calibrated.automatic_pitch == -3
    assert calibrated.pitch_modifier == -3

    # Track Transpose is the musician-facing audible direction control.
    raised = expression_for(60, 127, 63, track_transpose=2)
    assert raised.pitch_modifier == -1


def test_fractional_root_track_transpose_and_cents_survive_without_rounding():
    expression = expression_for(
        60,
        127,
        60.25,
        track_transpose=2,
        fine_tune_cents=50,
    )

    assert expression.automatic_pitch == -0.25
    assert expression.track_transpose == 2
    assert expression.fine_tune_cents == 50
    assert expression.requested_pitch == 2.25
    assert expression.pitch_modifier == 2.25
    assert expression.playback_rate == pytest.approx(2 ** (2.25 / 12))


def test_fractional_manual_note_pitch_is_clamped_without_integer_coercion():
    expression = expression_for(60, 127, None, pitch_semitones=-3.75)

    assert expression.pitch_semitones == -3.75
    assert expression.pitch_modifier == -3.75


def test_absolute_note_pitch_replaces_automatic_pitch_without_moving_the_note():
    expression = expression_for(64, 127, 60, pitch_semitones=-3)
    assert expression.source_pitch == 64
    assert expression.target_pitch == 64
    assert expression.automatic_pitch == 4
    assert expression.pitch_semitones == -3
    assert expression.requested_pitch == -3
    assert expression.pitch_modifier == -3
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


def test_a_legacy_note_trim_keeps_its_original_uncapped_sum():
    quiet = expression_for(60, 1, 60, volume_trim_db=-60)
    assert quiet.velocity_db == -60
    assert quiet.note_volume_db == -120
    assert quiet.requested_volume_db == -120
    assert quiet.volume_db == -60
    assert quiet.volume_limited is True

    loud = expression_for(60, 127, 60, volume_trim_db=20)
    assert loud.note_volume_db == 20
    assert loud.volume_db == 20
    assert loud.volume_limited is False


def test_absolute_note_volume_replaces_velocity_as_the_editable_starting_level():
    expression = expression_for(60, 64, 60, note_volume_db=0, master_volume_db=8)

    assert expression.velocity_db == -12
    assert expression.note_volume_db == 0
    assert expression.master_volume_db == 8
    assert expression.volume_trim_db == 12
    assert expression.requested_volume_db == 8
    assert expression.volume_db == 8


def test_an_unedited_note_uses_its_midi_derived_level():
    expression = expression_for(60, 64, 60, master_volume_db=3)

    assert expression.velocity_db == -12
    assert expression.note_volume_db == -12
    assert expression.requested_volume_db == -9
    assert expression.volume_db == -9


def test_track_volume_is_added_between_note_and_global_volume():
    expression = expression_for(
        60, 64, 60, note_volume_db=-3, track_volume_db=-6, master_volume_db=4
    )

    assert expression.note_volume_db == -3
    assert expression.track_volume_db == -6
    assert expression.master_volume_db == 4
    assert expression.requested_volume_db == -5
    assert expression.volume_db == -5


def test_absolute_note_volume_can_raise_the_quietest_velocity_to_the_maximum():
    expression = expression_for(60, 1, 60, note_volume_db=20)

    assert expression.velocity_db == -60
    assert expression.note_volume_db == 20
    assert expression.volume_trim_db == 80
    assert expression.volume_db == 20


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
