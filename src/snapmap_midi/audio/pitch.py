"""Conservative fundamental-pitch analysis for decoded DOOM sound media.

The classifier intentionally prefers "unknown" to a plausible wrong octave.
Arbitrary game events include impacts, voices, ambience, random containers, and
interactive graphs; only stable periodic media whose leaves agree may claim an
acoustic root. A higher layer can still assign rejected media an explicit
relative natural-playback reference without mislabeling it as detected pitch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_ANALYSIS_RATE = 8000
_WINDOW = 1024
_MIN_FREQUENCY = 40.0
_MAX_FREQUENCY = 2000.0
_YIN_THRESHOLD = 0.15
_MIN_FRAME_CONFIDENCE = 0.82
_MIN_RMS = 0.003
_WINDOW_FRACTIONS = (0.08, 0.2, 0.35, 0.5, 0.65, 0.8)


@dataclass(frozen=True)
class PitchEstimate:
    root_midi: float
    confidence: float
    cents_spread: float
    frames: int


def frequency_to_midi(frequency: float) -> float:
    return 69.0 + 12.0 * math.log2(float(frequency) / 440.0)


def _downmix(per_channel) -> list[float]:
    channels = [list(channel) for channel in per_channel if channel]
    if not channels:
        return []
    length = min(len(channel) for channel in channels)
    scale = 1.0 / (32768.0 * len(channels))
    return [sum(channel[index] for channel in channels) * scale for index in range(length)]


def _downsample(samples: list[float], rate: int) -> tuple[list[float], float]:
    step = max(1, int(round(float(rate) / _ANALYSIS_RATE)))
    if step == 1:
        return samples, float(rate)
    reduced = [
        sum(samples[index : index + step]) / len(samples[index : index + step])
        for index in range(0, len(samples) - step + 1, step)
    ]
    return reduced, float(rate) / step


def _frame(samples: list[float], start: int, size: int) -> tuple[list[float], float]:
    values = samples[start : start + size]
    if not values:
        return [], 0.0
    mean = sum(values) / len(values)
    centered = [value - mean for value in values]
    rms = math.sqrt(sum(value * value for value in centered) / len(centered))
    if rms <= 0:
        return centered, 0.0
    # Hann taper reduces false minima where a window cuts a sustained period.
    last = max(1, len(centered) - 1)
    tapered = [
        value * (0.5 - 0.5 * math.cos(2.0 * math.pi * index / last))
        for index, value in enumerate(centered)
    ]
    return tapered, rms


def _yin(frame: list[float], rate: float) -> tuple[float, float] | None:
    if len(frame) < 64:
        return None
    min_tau = max(2, int(rate / _MAX_FREQUENCY))
    max_tau = min(int(rate / _MIN_FREQUENCY), len(frame) // 2)
    if max_tau <= min_tau + 2:
        return None

    difference = [0.0] * (max_tau + 1)
    length = len(frame)
    for tau in range(1, max_tau + 1):
        total = 0.0
        limit = length - tau
        for index in range(limit):
            delta = frame[index] - frame[index + tau]
            total += delta * delta
        difference[tau] = total

    cmnd = [1.0] * (max_tau + 1)
    running = 0.0
    for tau in range(1, max_tau + 1):
        running += difference[tau]
        cmnd[tau] = difference[tau] * tau / running if running > 0 else 1.0

    selected = None
    for tau in range(min_tau, max_tau):
        if cmnd[tau] < _YIN_THRESHOLD:
            while tau + 1 <= max_tau and cmnd[tau + 1] < cmnd[tau]:
                tau += 1
            selected = tau
            break
    if selected is None:
        selected = min(range(min_tau, max_tau + 1), key=cmnd.__getitem__)

    confidence = 1.0 - cmnd[selected]
    if confidence < _MIN_FRAME_CONFIDENCE:
        return None

    refined = float(selected)
    if 1 <= selected < max_tau:
        left, middle, right = cmnd[selected - 1 : selected + 2]
        denominator = left - 2.0 * middle + right
        if abs(denominator) > 1e-12:
            refined += 0.5 * (left - right) / denominator
    if refined <= 0:
        return None
    return rate / refined, confidence


def analyze_pcm(rate: int, per_channel) -> tuple[PitchEstimate | None, str]:
    """Return a stable root estimate and a reason code for one decoded medium."""

    samples = _downmix(per_channel)
    if not samples:
        return None, "empty"
    samples, analysis_rate = _downsample(samples, int(rate))
    window = min(_WINDOW, len(samples))
    if window < 256:
        return None, "too_short"

    candidates = []
    maximum_start = max(0, len(samples) - window)
    for fraction in _WINDOW_FRACTIONS:
        start = int(round(maximum_start * fraction))
        values, rms = _frame(samples, start, window)
        candidates.append((rms, values))
    candidates.sort(key=lambda item: item[0], reverse=True)

    if not candidates or candidates[0][0] < _MIN_RMS:
        return None, "silence"

    estimates = []
    for rms, values in candidates[:5]:
        if rms < max(_MIN_RMS, candidates[0][0] * 0.08):
            continue
        found = _yin(values, analysis_rate)
        if found is None:
            continue
        frequency, confidence = found
        estimates.append((frequency_to_midi(frequency), confidence))

    if not estimates:
        return None, "aperiodic"

    # Choose the strongest narrow cluster. A harmonic or octave error appears
    # as a separate cluster instead of being averaged into a fictional root.
    best = []
    best_weight = -1.0
    for center, _confidence in estimates:
        cluster = [item for item in estimates if abs(item[0] - center) <= 0.45]
        weight = sum(item[1] for item in cluster)
        if weight > best_weight:
            best, best_weight = cluster, weight

    needed = 1 if len(estimates) == 1 else max(2, math.ceil(len(estimates) * 0.6))
    if len(best) < needed:
        return None, "unstable"

    roots = [item[0] for item in best]
    spread = (max(roots) - min(roots)) * 100.0
    if spread > 45.0:
        return None, "unstable"

    weight = sum(item[1] for item in best)
    root = sum(item[0] * item[1] for item in best) / weight
    confidence = min(1.0, weight / len(best) * len(best) / len(estimates))
    if confidence < 0.75:
        return None, "low_confidence"
    return PitchEstimate(root, confidence, spread, len(best)), "pitched"


def analyze_sources(sources) -> dict:
    """Classify all decoded leaves of one Wwise event.

    Sources are mappings with media_id, rate, and per_channel keys. Every
    available leaf must be stable and agree with the others before the event is
    declared pitch-following.
    """

    sources = list(sources)
    if not sources:
        return {
            "classification": "unavailable",
            "pitchable": False,
            "root_midi": None,
            "confidence": 0.0,
            "cents_spread": None,
            "sources": 0,
            "reason": "no decodable media",
        }

    estimates = []
    reasons = []
    for source in sources:
        estimate, reason = analyze_pcm(source["rate"], source["per_channel"])
        reasons.append(reason)
        if estimate is not None:
            estimates.append(estimate)

    if len(estimates) != len(sources):
        classification = "variable" if estimates else "unpitched"
        return {
            "classification": classification,
            "pitchable": False,
            "root_midi": None,
            "confidence": 0.0,
            "cents_spread": None,
            "sources": len(sources),
            "reason": (
                "leaf classifications disagree" if estimates else ", ".join(sorted(set(reasons)))
            ),
        }

    rounded = {int(math.floor(estimate.root_midi + 0.5)) for estimate in estimates}
    roots = [estimate.root_midi for estimate in estimates]
    if len(rounded) != 1 or max(roots) - min(roots) > 0.5:
        return {
            "classification": "variable",
            "pitchable": False,
            "root_midi": None,
            "confidence": 0.0,
            "cents_spread": (max(roots) - min(roots)) * 100.0,
            "sources": len(sources),
            "reason": "event leaves have different roots",
        }

    weights = [estimate.confidence for estimate in estimates]
    root = sum(value * weight for value, weight in zip(roots, weights)) / sum(weights)
    return {
        "classification": "pitched",
        "pitchable": True,
        "root_midi": root,
        "confidence": min(weights),
        "cents_spread": max(
            [estimate.cents_spread for estimate in estimates] + [(max(roots) - min(roots)) * 100.0]
        ),
        "sources": len(sources),
        "reason": "stable periodic root",
    }
