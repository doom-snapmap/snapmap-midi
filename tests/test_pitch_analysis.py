"""Conservative root-pitch classification for decoded soundbank media."""

from __future__ import annotations

import math

import pytest

from snapmap_midi.audio.pitch import analyze_pcm, analyze_sources

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
