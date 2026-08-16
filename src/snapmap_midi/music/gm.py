"""General MIDI mapping tables — program to family, percussion key to sound.

A MIDI file names instruments by program number, not by the sounds this game
actually has. These tables are the translation layer, and they are a taste
call as much as a technical one: several distinct programs collapse onto one
family because the palette has nothing closer.

Families split into two groups that are scheduled completely differently.
DECAYING samples fade on their own and are fired and forgotten. SUSTAINED
samples hold at full volume until something stops them, so they need a
dedicated voice and an explicit note-off. Getting a family into the wrong
group is audible: a sustained note with no note-off rings its whole sample.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

#: Families whose samples hold at full volume and must be stopped explicitly.
SUSTAINED = {
    "ins_violin",
    "ins_horns",
    "ins_trumpet",
    "ins_flute",
    "ins_string",
}

#: MIDI reserves channel 10 (zero-indexed 9) for percussion.
DRUM_CHANNEL = 9


def gm_to_family(program: int) -> str:
    """Map a General MIDI program number to a palette family."""
    p = program
    if p < 8:
        return "ins_piano"
    if p < 16:
        return "ins_marimba"
    if p < 24:
        return "ins_horns"
    if p < 32:
        return "ins_guitar"
    if p < 40:
        return "ins_pulse"
    if p < 56:
        return "ins_violin"
    if p < 64:
        return "ins_trumpet"
    if p < 80:
        return "ins_flute"
    if p < 88:
        return "ins_sine"
    if p < 96:
        return "ins_violin"
    if p < 104:
        return "ins_sine"
    if p < 120:
        return "ins_guitar"
    return "ins_marimba"


#: General MIDI reserves channel 10 for percussion and gives the program
#: number a different meaning there: it selects a KIT rather than an
#: instrument. Reading it as an instrument is how a drum part came to be
#: labelled "Acoustic Guitar (nylon)" -- program 24, which is a nylon guitar
#: everywhere except the one channel where it is the Electronic kit.
_DRUM_KITS = {
    0: "Standard Kit",
    8: "Room Kit",
    16: "Power Kit",
    24: "Electronic Kit",
    25: "TR-808 Kit",
    32: "Jazz Kit",
    40: "Brush Kit",
    48: "Orchestra Kit",
    56: "Sound FX Kit",
}


def gm_drum_kit_name(program: int) -> str:
    """The kit a percussion channel's program number selects.

    Files routinely leave channel 10 on a program nobody chose, and the
    standard names only the nine listed above. Anything else is reported as
    plain percussion rather than invented, because a kit name nobody picked
    reads as a decision.
    """
    return _DRUM_KITS.get(program, "Percussion")


#: Percussion key to sound, as shipped. Read from data rather than written
#: inline because it is no longer the only answer: `drum_table()` is what
#: everything actually plays from, and this is its floor. Keeping the shipped
#: taste call in a file the app never writes is what makes "put it back" mean
#: something -- a user table edited over the top can always be thrown away.
#:
#: Exotic keys are absent rather than guessed at, and land in the compile
#: statistics as `dropped`.
def _load_shipped_drum_map() -> dict:
    path = Path(__file__).resolve().parents[1] / "data" / "drum_map.json"
    return {int(key): sound for key, sound in json.loads(path.read_text(encoding="utf-8")).items()}


DRUM_MAP = _load_shipped_drum_map()


def user_drum_table() -> dict:
    """The user's own percussion table, or an empty one.

    Unreadable is treated as absent. This file is a convenience -- a saved
    preference for which kick is "the" kick -- and refusing to open a song
    because a preference file got truncated would trade a small loss for a
    total one. The window says so rather than staying silent about it.
    """
    from snapmap_midi import paths

    path = paths.drum_map_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    table = {}
    for key, sound in raw.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        if 0 <= index <= 127 and isinstance(sound, str) and sound:
            table[index] = sound
    return table


def drum_table() -> dict:
    """What a percussion key actually plays: the shipped table, then the user's.

    Read fresh rather than cached. The window writes this file while a song is
    open, and a cached table would leave the preview playing the old kick until
    the app restarted -- the one moment the change has to be audible.

    Overlay rather than replacement, so a user who renamed one kick still gets
    every other key. A saved table is an opinion about a few keys, never a
    complete kit.
    """
    table = dict(DRUM_MAP)
    table.update(user_drum_table())
    return table


def save_user_drum_table(mapping) -> dict:
    """Replace the user's table, and answer with what was stored.

    Replaces wholesale for the same reason the song's `drum_keys` does: an
    entry absent from the map is the shipped answer, and no value can say that,
    because every value has to name a real sound.

    Sounds are checked against the percussion pool here rather than trusted
    from the window, because this file outlives the session that wrote it. A
    pitched sound would hold one fixed note under every hit and a looping
    ambience is never stopped, and finding that out on the next song -- with no
    memory of having chosen it -- is worse than being refused now.
    """
    from snapmap_midi import paths
    from snapmap_midi.sound import palette

    table = {}
    for key, sound in dict(mapping).items():
        index = int(key)
        if not 0 <= index <= 127:
            raise ValueError("drum key %r is outside 0-127" % key)
        problem = palette.drum_sound_problem(sound)
        if problem is not None:
            raise ValueError("drum key %d: %s" % (index, problem))
        table[index] = sound
    path = paths.drum_map_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if table:
        path.write_text(
            json.dumps({str(k): table[k] for k in sorted(table)}, indent=2) + "\n",
            encoding="utf-8",
        )
    elif path.exists():
        # An empty table is "back to shipped", and the file's absence says that
        # more durably than a file holding `{}` -- which a later reader has to
        # decide the meaning of all over again.
        path.unlink()
    return table


@lru_cache(maxsize=1)
def _gm_names() -> dict:
    """The General MIDI name tables, read once.

    Shipped as data rather than written inline because 128 names in a source
    file is a wall nobody reads, and unlike the tables above these are a
    published specification rather than a taste call.
    """
    path = Path(__file__).resolve().parents[1] / "data" / "gm_programs.json"
    return json.loads(path.read_text(encoding="utf-8"))


def gm_program_name(program: int) -> str:
    """The General MIDI name for a program number.

    Raises past 127 rather than clamping. A program number out of range means
    the caller has a bug, and naming it "Gunshot" hides that behind a plausible
    answer -- the same failure the retired `--out` flag produced.
    """
    names = _gm_names()["programs"]
    if not 0 <= program < len(names):
        raise IndexError("no General MIDI program %r" % program)
    return names[program]


def gm_drum_name(key: int) -> str:
    """The General MIDI percussion name for a key, or the bare key number.

    Unlike programs, keys outside the standard set are ordinary -- files use
    them and `DRUM_MAP` drops them. Showing the number is what lets someone
    find that row in the picker and give it a sound.
    """
    return _gm_names()["percussion"].get(str(key), "Key %d" % key)
