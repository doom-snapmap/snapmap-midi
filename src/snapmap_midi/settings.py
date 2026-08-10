"""One document holding every choice a compile makes, in a form that survives.

The window changes one thing at a time -- a family here, a mute there -- and
each change has to become a complete set of compiler arguments again. Sending
only the changed field would let the compiler's own defaults stand in for
everything already chosen, so what is kept is the whole document and what is
handed to `compile_to_rawmap` is the whole document. `merge` is how a single
change gets in without disturbing the rest.

It is stored as JSON beside the song, because it is the only record of an
afternoon's tuning and someone will open it in an editor. That makes validation
load-bearing rather than defensive: a hand edit is an ordinary way for this file
to change, and the mistakes a hand edit makes are quiet ones. An unpitched
family compiles to silence with no error anywhere. A lever name that no longer
exists reads as applied and does nothing. `{"channels": {"0": "ins_piano"}}` is
the shape everyone writes first. Each of those is refused here, by name, rather
than surviving into a map that loads and plays the wrong thing.

The defaults are the compiler's own, to the byte. The window opens on this
document before anyone has touched a control, so a default that disagrees with
`compile_to_rawmap` would mean exporting from the window and typing the command
produce different maps for a lever nobody set. `tests/test_settings.py` compiles
both and compares the bytes.

`max_events` is deliberately absent. `compile.py` implements it as
`decaying_events[:max_events]`, which truncates the one-shot list in TIME order
-- the drums stop partway through the song and stay stopped. Behind a control
that reads as a density limit, that is a trap; it stays a command-line flag.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path

from snapmap_midi.sound import palette

#: Bumped when a document written by this build can no longer be read by the
#: previous one. `validate` refuses anything it does not recognise rather than
#: reading the half it understands.
SETTINGS_VERSION = 1

#: Mirrors `compile_to_rawmap`'s own default. Named here rather than imported,
#: because `compile` sits alongside this module rather than under it -- the byte
#: gate in the test suite is what keeps the two from drifting.
_DEFAULT_BUTTON = "snapmap-midi-song"

#: MIDI's own limits: sixteen channels, a note per key from 0 to 127.
_MAX_CHANNEL = 15
_MAX_NOTE = 127

#: One voice per MIDI pitch. Past that the lever stops limiting anything on any
#: arrangement that is not pathological, and a control that goes higher implies
#: there is something up there to find.
_MAX_SPEAKERS = 128

#: A release is a fade that begins at a note's end and runs into whatever comes
#: next, so a long one IS the smearing every other lever here exists to remove.
_MAX_RELEASE_S = 10.0

_DRUM_MODES = ("auto", "on", "off")
_CHANNEL_KEYS = frozenset({"family", "sound", "muted"})

#: The tuning levers the window may set, with the values `compile_to_rawmap`
#: uses when nobody sets them. `decaying_families` and `family_caps` are empty
#: containers where the compiler takes None, because JSON needs something to
#: hold and both are falsy, so the compile path is identical either way.
_TUNING_DEFAULTS = {
    "max_speakers": 32,
    "release_s": 0.1,
    "hard_stop": False,
    "max_poly": None,
    "cap_sustain_ms": None,
    "bass_pitch": 78,
    "bass_cap_ms": None,
    "decaying_families": [],
    "family_caps": {},
}

#: Levers that used to look like candidates and are not. Named so the refusal
#: explains itself instead of reading as a typo.
_NOT_LEVERS = {
    "max_events": "max_events truncates the one-shot list in time order, so the drums stop "
    "partway through the song rather than thinning out; it is a command-line flag only",
}


class SettingsError(ValueError):
    """A settings document that cannot be honoured, with the offender named.

    A `ValueError` so a caller that has not heard of this module still catches
    it, and one class rather than several because every consumer does the same
    thing with it: shows the message. The message is the part that has to be
    good -- these are read by someone looking at their own hand-edited file.
    """


def defaults(midi=None) -> dict:
    """A document that compiles exactly what `compile_to_rawmap` compiles alone.

    Deep-copied rather than shared. `dict(_TUNING_DEFAULTS)` is a shallow copy,
    which would put the SAME empty list and empty dict inside every document
    the process ever builds -- one song's decaying families would appear in the
    next song's document, and nothing would explain where they came from.

    Key order is the order the file is written in, so two sessions that made
    the same choices produce the same file and a diff shows a decision rather
    than how a dict happened to be built.
    """
    return {
        "version": SETTINGS_VERSION,
        "midi": None if midi is None else str(midi),
        "button": _DEFAULT_BUTTON,
        "out_dir": None,
        "baseline": None,
        "channels": {},
        "drums": "auto",
        "drum_keys": {},
        "tuning": copy.deepcopy(_TUNING_DEFAULTS),
    }


def _mapping(value, what) -> dict:
    """A section as a plain dict, or a refusal that says what was found."""
    if not isinstance(value, Mapping):
        raise SettingsError("%s: expected a group of settings, got %r" % (what, value))
    return dict(value)


def _index(key, limit: int, what: str) -> str:
    """A numeric key checked against its range and normalised to a string.

    JSON has no integer keys, so the file spells channels and drum keys as
    strings while every caller in Python reaches for the number. Both are
    accepted and both come back as the string the file will hold, because a
    document built in memory and the same document read back from disk have to
    compare equal -- otherwise the session sees a change nobody made.

    `bool` is rejected explicitly: it is an `int` subclass, so `True` would
    quietly become channel 1.
    """
    if isinstance(key, str):
        try:
            number = int(key)
        except ValueError:
            raise SettingsError("%s %r is not a number" % (what, key)) from None
    elif isinstance(key, int) and not isinstance(key, bool):
        number = key
    else:
        raise SettingsError("%s %r is not a number" % (what, key))
    if not 0 <= number <= limit:
        raise SettingsError("%s %r is outside 0-%d" % (what, key, limit))
    return str(number)


def _flag(value, what: str) -> bool:
    if not isinstance(value, bool):
        raise SettingsError("%s is %r, which is neither true nor false" % (what, value))
    return value


def _whole(value, what: str, low: int, high=None) -> int:
    """A whole number inside its bounds. `bool` is not one, for all that it is."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise SettingsError("%s is %r, which is not a whole number" % (what, value))
    if value < low or (high is not None and value > high):
        limit = "at least %d" % low if high is None else "between %d and %d" % (low, high)
        raise SettingsError("%s is %r; it has to be %s" % (what, value, limit))
    return value


def _optional_whole(value, what: str, low: int) -> int | None:
    """A whole number or None, which is how each of these spells "off".

    Zero is not the same as off and is refused: `thin_polyphony(notes, 0)`
    keeps no notes at all, and a cap of zero truncates every note it touches to
    nothing. Both are silence that looks like a setting.
    """
    return None if value is None else _whole(value, what, low)


def _text(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsError("%s is %r; it has to be a name" % (what, value))
    return value


def _optional_text(value, what: str):
    if value is None:
        return None
    if isinstance(value, Path):
        return str(value)
    if not isinstance(value, str) or not value:
        raise SettingsError("%s is %r; it has to be a path or null" % (what, value))
    return value


def _known_family(family: str, what: str, families) -> str:
    """A family the picker offers, or a refusal that says what the wrong one does."""
    if family in families:
        return family
    raise SettingsError(
        "%s: %r has no sound for any pitch, so every note routed to it would resolve to "
        "nothing and the part would vanish with no error anywhere. Pick one of: %s"
        % (what, family, ", ".join(families))
    )


def _channels(section, families, sounds) -> dict:
    section = _mapping(section, "channels")
    out = {}
    for key, entry in section.items():
        channel = _index(key, _MAX_CHANNEL, "channel")
        entry = _mapping(entry, "channel %s" % channel)
        unknown = sorted(set(entry) - _CHANNEL_KEYS)
        if unknown:
            raise SettingsError(
                "channel %s: unknown setting(s): %s" % (channel, ", ".join(unknown))
            )
        family = entry.get("family")
        if family is not None:
            _known_family(family, "channel %s" % channel, families)
        sound = entry.get("sound")
        if sound is not None and sound not in sounds:
            raise SettingsError(
                "channel %s: %r is not a sound in the shipped SnapMap speaker palette"
                % (channel, sound)
            )
        if family is not None and sound is not None:
            raise SettingsError(
                "channel %s: choose a pitched family or one exact sound, not both" % channel
            )
        normalized = {
            "family": family,
            "muted": _flag(entry.get("muted", False), "channel %s: muted" % channel),
        }
        # Preserve the shape of old sidecars until an exact sound is selected.
        if sound is not None:
            normalized["sound"] = sound
        out[channel] = normalized
    return out


def _drum_keys(section) -> dict:
    """Percussion keys mapped to sounds, checked against the kit.

    Checked against `drum_sound_pool` rather than "any unpitched sound",
    because the unpitched half of the palette is mostly ambience: a pitched
    sound would play one fixed note under every hit, and a looping ambience is
    never told to stop, so it holds its emitter open until the engine recycles
    the slot out from under something else.
    """
    section = _mapping(section, "drum_keys")
    pool = palette.drum_sound_pool()
    out = {}
    for key, sound in section.items():
        drum_key = _index(key, _MAX_NOTE, "drum key")
        if sound not in pool:
            raise SettingsError(
                "drum key %s: %r is not one of the %d percussion sounds. A pitched sound "
                "plays one fixed note under every hit, and a looping ambience is never "
                "stopped -- it holds its emitter until the engine recycles the slot out "
                "from under something else." % (drum_key, sound, len(pool))
            )
        out[drum_key] = sound
    return out


def _decaying_families(value, families) -> list:
    """Families forced down the fire-and-forget path.

    Sorted rather than kept in the order given, because a caller may hand this
    over as a set and two sessions that chose the same families have to write
    the same file.
    """
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set, frozenset)):
        raise SettingsError("decaying_families is %r; it has to be a list of family names" % value)
    return sorted({_known_family(f, "decaying_families", families) for f in value})


def _family_caps(section, families) -> dict:
    """Per-family sustain caps in milliseconds.

    The keys are checked because the compiler reads them with `.get`, so a name
    that is not a family is a cap that reads as set and never matches anything.
    """
    section = _mapping(section, "family_caps")
    out = {}
    for family, cap in section.items():
        _known_family(family, "family_caps", families)
        out[family] = _whole(cap, "family_caps[%s]" % family, 1)
    return {family: out[family] for family in sorted(out)}


def _tuning(section, families) -> dict:
    section = _mapping(section, "tuning")
    unknown = sorted(set(section) - set(_TUNING_DEFAULTS))
    if unknown:
        reasons = [_NOT_LEVERS[name] for name in unknown if name in _NOT_LEVERS]
        raise SettingsError(
            "unknown tuning lever(s): %s%s"
            % (", ".join(unknown), "".join(" -- " + reason for reason in reasons))
        )
    out = copy.deepcopy(_TUNING_DEFAULTS)
    out.update(section)
    out["max_speakers"] = _whole(out["max_speakers"], "max_speakers", 1, _MAX_SPEAKERS)
    out["release_s"] = _release(out["release_s"])
    out["hard_stop"] = _flag(out["hard_stop"], "hard_stop")
    out["max_poly"] = _optional_whole(out["max_poly"], "max_poly", 1)
    out["cap_sustain_ms"] = _optional_whole(out["cap_sustain_ms"], "cap_sustain_ms", 1)
    out["bass_pitch"] = _whole(out["bass_pitch"], "bass_pitch", 0, _MAX_NOTE)
    out["bass_cap_ms"] = _optional_whole(out["bass_cap_ms"], "bass_cap_ms", 1)
    out["decaying_families"] = _decaying_families(out["decaying_families"], families)
    out["family_caps"] = _family_caps(out["family_caps"], families)
    return out


def _release(value) -> float:
    """The note-off fade, in seconds.

    Accepts a whole number as well as a fraction, because JSON writes `0` for a
    float that happens to be whole and reads it back as an int -- refusing that
    would make a file this module itself wrote unloadable. Negative is refused:
    it goes straight into the map as the fade's duration.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SettingsError("release_s is %r, which is not a number of seconds" % value)
    if not 0.0 <= value <= _MAX_RELEASE_S:
        raise SettingsError(
            "release_s is %r; it has to be between 0 and %g seconds" % (value, _MAX_RELEASE_S)
        )
    return float(value)


def validate(doc) -> dict:
    """Check a document and return it complete, normalised, and safe to compile.

    Missing keys are filled in from `defaults`, because absence is not this
    file's failure mode -- someone deleting a line means they are not setting
    it, and refusing the whole document over one absent lever would lose the
    other forty. A WRONG value is the failure mode, and every one of them is
    refused by name.

    A version this build does not know is refused outright rather than
    half-read. Reading the keys that happen to still parse is how a document
    from a later build silently loses the settings that build added.

    Returns a new document; the one passed in is never edited. The session
    applies a patch and keeps the result only if this returned, so a validator
    that edited in place would leave it holding a half-applied document after a
    refusal.
    """
    doc = _mapping(doc, "settings")
    unknown = sorted(set(doc) - set(defaults()))
    if unknown:
        raise SettingsError("unknown setting(s): %s" % ", ".join(unknown))

    version = doc.get("version", SETTINGS_VERSION)
    if version != SETTINGS_VERSION:
        raise SettingsError(
            "this document says version %r; this build reads and writes version %d only"
            % (version, SETTINGS_VERSION)
        )

    # Built once and handed down. `pitched_families` parses the whole palette
    # each time, for the same reason `build_note_index` is not cached, and
    # three sections need the same list.
    families = palette.pitched_families()
    sounds = frozenset(palette.all_sounds())

    out = defaults(_optional_text(doc.get("midi"), "midi"))
    out["button"] = _text(doc.get("button", out["button"]), "button")
    out["out_dir"] = _optional_text(doc.get("out_dir"), "out_dir")
    out["baseline"] = _optional_text(doc.get("baseline"), "baseline")
    out["channels"] = _channels(doc.get("channels", {}), families, sounds)
    drums = doc.get("drums", out["drums"])
    if drums not in _DRUM_MODES:
        raise SettingsError("drums is %r; it has to be one of %s" % (drums, ", ".join(_DRUM_MODES)))
    out["drums"] = drums
    out["drum_keys"] = _drum_keys(doc.get("drum_keys", {}))
    # Exact sounds retain their palette category as ``Note.fam``. Conversion
    # behavior can therefore be tuned for every category, not only the twelve
    # categories that contain pitched samples.
    out["tuning"] = _tuning(doc.get("tuning", {}), palette.categories())
    return out


def merge(base, patch) -> dict:
    """Apply a patch to a document and validate the result.

    `channels` and `tuning` deep-merge, one channel and one lever at a time,
    because the window sends what changed and nothing else. "Mute channel 1"
    arrives as `{"channels": {"1": {"muted": true}}}` and must not take channel
    1's instrument with it; capping the sustain must not reset the release.

    `drum_keys` and `family_caps` replace wholesale: the caller sends the
    complete map, and an entry absent from it is gone. They are values rather
    than records -- a drum key's setting IS its sound, and a cap IS its number,
    so there is no second field for a deep merge to preserve. That asymmetry is
    the only thing that makes removal expressible. Validation demands a real
    sound name, so `null` cannot mean "put this key back to the table's
    answer", and under a deep merge nothing else could either: every patch
    would only ever add, and a key given a sound by mistake could never be
    taken back. `family_caps` gets this for free by sitting inside `tuning`,
    where the merge is per lever and a lever's value replaces the old one.

    Neither argument is edited. A merge that wrote into `base` would leave the
    caller holding a half-applied document when validation refuses the rest.
    """
    merged = copy.deepcopy(_mapping(base, "settings"))
    for key, value in _mapping(patch, "patch").items():
        if key == "channels":
            # Both sides are keyed the way `validate` will key them, or a patch
            # written as `{0: ...}` would not find the entry the file spells
            # `"0"` -- it would add a second one, and the deep merge that is the
            # whole point of this branch would silently not happen.
            channels = {
                _index(channel, _MAX_CHANNEL, "channel"): entry
                for channel, entry in _mapping(merged.get("channels", {}), "channels").items()
            }
            for channel, entry in _mapping(value, "channels").items():
                channel = _index(channel, _MAX_CHANNEL, "channel")
                existing = _mapping(channels.get(channel, {}), "channel %s" % channel)
                existing.update(_mapping(entry, "channel %s" % channel))
                channels[channel] = existing
            merged["channels"] = channels
        elif key == "tuning":
            tuning = _mapping(merged.get("tuning", {}), "tuning")
            tuning.update(_mapping(value, "tuning"))
            merged["tuning"] = tuning
        else:
            merged[key] = value
    return validate(merged)


def to_compile_kwargs(doc) -> dict:
    """The document as keyword arguments for `compile_to_rawmap`.

    Only arguments that function actually takes: they are splatted into the
    call, so a key it has never heard of is a `TypeError` at export time, after
    the window has already said it is working. The song, the output folder and
    the baseline are not here -- the compiler is bytes-out and takes the MIDI
    path positionally, and where the result is written is the caller's problem.

    Channel and drum keys come back as integers, because `parse_notes` compares
    them against mido's own `msg.channel` and `msg.note`. A string key never
    matches, and the mute would silently do nothing at all.
    """
    doc = validate(doc)
    tuning = doc["tuning"]
    channels = doc["channels"]
    return {
        "button_name": doc["button"],
        "drums": {"auto": "auto", "on": True, "off": False}[doc["drums"]],
        "max_speakers": tuning["max_speakers"],
        "release_s": tuning["release_s"],
        "hard_stop": tuning["hard_stop"],
        "cap_sustain_ms": tuning["cap_sustain_ms"],
        "bass_pitch": tuning["bass_pitch"],
        "bass_cap_ms": tuning["bass_cap_ms"],
        "max_poly": tuning["max_poly"],
        "decaying_families": set(tuning["decaying_families"]),
        "family_caps": dict(tuning["family_caps"]),
        "channel_families": {
            int(channel): entry["family"]
            for channel, entry in channels.items()
            if entry["family"] is not None
        },
        "channel_sounds": {
            int(channel): entry["sound"]
            for channel, entry in channels.items()
            if entry.get("sound") is not None
        },
        "channel_mutes": {int(channel) for channel, entry in channels.items() if entry["muted"]},
        "drum_key_overrides": {int(key): sound for key, sound in doc["drum_keys"].items()},
    }


def load(path) -> dict:
    """Read a settings document, or say what is wrong with the file.

    Every failure arrives as `SettingsError` naming the path, including a file
    that is not there. The caller is a command line printing one line or a
    window showing one message, and neither has anywhere useful to put a
    traceback about a file the user chose.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SettingsError("could not read the settings file %s (%s)" % (path, exc)) from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise SettingsError("the settings file %s is not valid JSON (%s)" % (path, exc)) from exc
    return validate(payload)


def save(doc, path) -> None:
    """Write a settings document where a person can read and edit it.

    Validated before anything is opened, so an invalid document cannot reach
    the disk. Writing one would move the failure to the NEXT session, against a
    file this tool wrote itself, with nothing to point at.

    Indented, because this file is meant to be edited by hand. One long line is
    not a file anybody edits; it is a file they overwrite.
    """
    text = json.dumps(validate(doc), indent=2) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def sidecar_path(midi) -> Path:
    """Where a song's settings live: beside the song, named after it.

    A dialog would mean two more error paths and a file the user has to keep
    track of. The song is the thing they already have open, and a settings file
    that travels with it is one nobody has to find again.

    Appended to the whole name rather than replacing the extension, because
    `bach.mid` and `bach.midi` are two different songs and would otherwise
    share one settings file -- silently giving the second one the first one's
    instruments.
    """
    return Path(str(midi) + ".snapmap.json")
