"""Conservative root-pitch classification for decoded soundbank media."""

from __future__ import annotations

import math

import pytest

from snapmap_midi.audio import pitch
from snapmap_midi.audio.pitch import analyze_pcm, analyze_sources, octave_fitted_reference

_RATE = 8000


def _tone(frequency: float, seconds: float = 1.0) -> list[int]:
    return [
        round(12000 * math.sin(2 * math.pi * frequency * index / _RATE))
        for index in range(round(_RATE * seconds))
    ]


def _source(media_id: int, frequency: float) -> dict:
    return {
        "media_id": media_id,
        "rate": _RATE,
        "per_channel": [_tone(frequency)],
    }


def test_yin_resolves_a_concert_a_root():
    estimate, reason = analyze_pcm(_RATE, [_tone(440.0)])
    assert reason == "pitched"
    assert estimate is not None
    assert estimate.root_midi == pytest.approx(69.0, abs=0.15)
    assert estimate.confidence >= 0.75


def test_silence_is_never_given_a_plausible_root():
    estimate, reason = analyze_pcm(_RATE, [[0] * _RATE])
    assert estimate is None
    assert reason == "silence"


def test_agreeing_event_leaves_produce_one_numeric_profile():
    profile = analyze_sources([_source(1, 440.0), _source(2, 440.0)])
    assert profile["classification"] == "pitched"
    assert profile["pitchable"] is True
    assert profile["root_midi"] == pytest.approx(69.0, abs=0.15)
    assert profile["sources"] == 2


def test_random_container_leaves_with_different_roots_are_variable():
    profile = analyze_sources([_source(1, 440.0), _source(2, 523.251)])
    assert profile["classification"] == "variable"
    assert profile["pitchable"] is False
    assert profile["root_midi"] is None
    assert profile["reason"] == "event leaves have different roots"


def test_one_pitched_and_one_silent_leaf_is_not_accepted():
    profile = analyze_sources(
        [
            _source(1, 440.0),
            {"media_id": 2, "rate": _RATE, "per_channel": [[0] * _RATE]},
        ]
    )
    assert profile["classification"] == "variable"
    assert profile["pitchable"] is False
    assert profile["reason"] == "leaf classifications disagree"


def test_no_decodable_media_is_an_unavailable_profile():
    profile = analyze_sources([])
    assert profile == {
        "classification": "unavailable",
        "pitchable": False,
        "root_midi": None,
        "confidence": 0.0,
        "cents_spread": None,
        "sources": 0,
        "reason": "no decodable media",
    }


def test_a_detected_root_is_octave_fitted_without_changing_its_pitch_class():
    assert octave_fitted_reference(83.0, 36, 83) == 59.0
    assert octave_fitted_reference(60.125, 48, 72) == pytest.approx(60.125)


def test_a_high_partial_is_not_promoted_to_the_sound_root(monkeypatch):
    monkeypatch.setattr(pitch, "_yin", lambda frame, rate: (1000.0, 0.95))
    monkeypatch.setattr(pitch, "_dominant_frequency", lambda frame, rate: 500.0)

    estimate, reason = pitch.analyze_pcm(_RATE, [_tone(1000.0)])
    assert estimate is None
    assert reason == "harmonic_ambiguity"

    profile = pitch.analyze_sources([_source(1, 1000.0)])
    assert profile["classification"] == "ambiguous"
    assert profile["pitchable"] is False
    assert profile["root_midi"] is None
    assert profile["relative_recommended"] is True


def test_full_four_octave_range_fits_without_clamping_at_a_centered_reference():
    reference = octave_fitted_reference(83.0, 36, 83)
    assert [round(note - reference) for note in range(36, 84)] == list(range(-23, 25))
