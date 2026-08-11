"""Timeline event construction — the exact shapes the engine accepts.

Every field here is load-bearing and was established by trial against the
running game, so the shapes are not negotiable:

  - the sound argument is a NESTED declaration pointer, {"decl": {"sound": x}},
    never a flat wildcard form;
  - the argument-count key carries a leading newline in its name; and
  - channels are enum-keyed, not raw integers.

Channel choice decides whether a note can ever be stopped. A sound started on
the wildcard channel binds to no channel slot, so a later stop cannot find it
and the note rings its full sample. Sustained notes therefore start on a
CONCRETE channel and are cut with the wildcard; one-shots layered on a single
entity must use the wildcard to start, or they would cut each other off.
"""

from __future__ import annotations

#: Sustained notes start here so a later stop can find and free the handle.
START_CHANNEL = "SND_CHANNEL_MUSIC1"
#: Stops and fades use the wildcard, which matches any bound channel.
STOP_CHANNEL = "SND_CHANNEL_ANY"
#: Polyphonic one-shots on a shared entity must start unbound, or they would
#: make that entity monophonic per channel and cut each other off.
LAYERED_CHANNEL = "SND_CHANNEL_ANY"


def start(shader: str, time_ms: int, channel: str = START_CHANNEL) -> dict:
    """Begin playing a sound at `time_ms`."""
    return {
        "eventCall": {
            "\neventHandle_t eventDef": "startSoundShader",
            "args": {
                "\nnum": 2,
                "item[0]": {"decl": {"sound": shader}},
                "item[1]": {"soundChannel_t": channel},
            },
        },
        "eventTime": int(time_ms),
    }


def fade(
    time_ms: int, to_db: float = -60.0, over_s: float = 0.1, channel: str = STOP_CHANNEL
) -> dict:
    """Fade whatever is playing down to `to_db` over `over_s` seconds."""
    return {
        "eventCall": {
            "\neventHandle_t eventDef": "fadeSound",
            "args": {
                "\nnum": 3,
                "item[0]": {"soundChannel_t": channel},
                "item[1]": {"float": float(to_db)},
                "item[2]": {"float": float(over_s)},
            },
        },
        "eventTime": int(time_ms),
    }


def fade_pitch(
    time_ms: int,
    to_semitones: float,
    over_s: float = 0.0,
    channel: str = STOP_CHANNEL,
) -> dict:
    """Set the active sound's pitch in SnapMap semitones.

    The engine calls this event fadePitch even when the duration is zero.
    Native code forwards the value directly to the sound emitter as semitones.
    """
    return {
        "eventCall": {
            "\neventHandle_t eventDef": "fadePitch",
            "args": {
                "\nnum": 3,
                "item[0]": {"soundChannel_t": channel},
                "item[1]": {"float": float(to_semitones)},
                "item[2]": {"float": float(over_s)},
            },
        },
        "eventTime": int(time_ms),
    }


def stop(time_ms: int, channel: str = STOP_CHANNEL) -> dict:
    """Cut whatever is playing immediately."""
    return {
        "eventCall": {
            "\neventHandle_t eventDef": "stopSound",
            "args": {"\nnum": 1, "item[0]": {"soundChannel_t": channel}},
        },
        "eventTime": int(time_ms),
    }


def events_block(events) -> dict:
    """Wrap events into the indexed-plus-count form the format uses.

    The count key is inserted last, and key order is preserved on
    serialization, so it must stay last.
    """
    events = list(events)
    block = {"item[%d]" % i: e for i, e in enumerate(events)}
    block["num"] = len(events)
    return block
