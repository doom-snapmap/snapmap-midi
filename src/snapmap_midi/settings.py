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
import re
from collections.abc import Mapping
from pathlib import Path

from snapmap_midi.sound import palette

#: Bumped when a document written by this build can no longer be read by the
#: previous one. `validate` refuses anything it does not recognise rather than
#: reading the half it understands.
SETTINGS_VERSION = 7

#: Mirrors `compile_to_rawmap`'s own default. Named here rather than imported,
#: because `compile` sits alongside this module rather than under it -- the byte
#: gate in the test suite is what keeps the two from drifting.
_DEFAULT_BUTTON = "snapmap-midi-song"

#: MIDI's own limits: sixteen channels, a note per key from 0 to 127.
_MAX_CHANNEL = 15
_MAX_NOTE = 127
_MIN_VOLUME_DB = -60
_MAX_VOLUME_DB = 20

#: One voice per MIDI pitch. Past that the lever stops limiting anything on any
#: arrangement that is not pathological, and a control that goes higher implies
#: there is something up there to find.
_MAX_SPEAKERS = 128

#: A release is a fade that begins at a note's end and runs into whatever comes
#: next, so a long one IS the smearing every other lever here exists to remove.
_MAX_RELEASE_S = 10.0

_DRUM_MODES = ("auto", "on", "off")
_CHANNEL_KEYS = frozenset(
    {
        "family",
        "sound",
        "muted",
        "percussion",
        "pitch_follow",
        "soloed",
        "root_midi",
        "root_confidence",
        "root_source",
    }
)
#: Whether a part is a drum kit. `auto` keeps the channel-10 heuristic, which
#: is right for nearly every file. The other two are the user saying so, and
#: they exist because the heuristic cannot be extended safely: `DRUM_MAP`'s
#: keys span B1 to F5, exactly where bass lines live, so guessing on other
#: channels would silently turn a bass part into drums.
_PERCUSSION_MODES = ("auto", "kit", "melodic")

_NOTE_KEYS = frozenset({"pitch_offset", "volume_db", "volume_trim_db"})
_ROOT_SOURCES = frozenset(
    {
        "palette_name",
        "detected",
        "detected_octave_pending",
        "manual",
        # A reference nobody measured. Following MIDI needs SOME note to call
        # the sound's own, and a sound with no musical root has none to find --
        # a door slam is not in any key. The engine will pitch it regardless, so
        # the choice is between refusing the effect and naming a convention.
        # This names it, and is labelled so the window can say the reference was
        # assumed rather than heard.
        "assumed",
    }
)

#: Stock event names measured from soundbanksinfo.events use this complete
#: alphabet and are at most 64 characters. Accepting the identifier rather than
#: requiring the installed catalog keeps a sidecar usable when DOOM is moved,
#: and permits an explicitly named mod event at compile time.
_PLAY_EVENT = re.compile(r"(?i)^play_[a-z0-9_-]{1,59}$")

#: The tuning levers the window may set, with the values `compile_to_rawmap`
#: uses when nobody sets them. `decaying_families` and `family_caps` are empty
#: containers where the compiler takes None, because JSON needs something to
#: hold and both are falsy, so the compile path is identical either way.
_TUNING_DEFAULTS = {
    "master_volume_db": 0,
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
        "notes": {},
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


def _part_key(key, what: str = "channel") -> str:
    """A `channels` key: a bare channel, or `track:channel` naming one part.

    Both shapes are permanent, and the bare one is not legacy debris. It means
    "every part on this channel" -- which is exactly what it meant back when a
    channel could only hold one part, so every settings document written before
    parts existed keeps its meaning without being rewritten. That is the whole
    migration: nothing to translate, because nothing changed underneath it.

    An explicit `track:channel` names one part and beats the wildcard, which is
    what lets a lead and a pad sharing channel 0 hold different instruments.

    Tracks have no upper bound the way channels do -- a file may hold as many as
    it likes -- so only the channel half is range-checked.
    """
    if isinstance(key, str) and ":" in key:
        track, _, channel = key.partition(":")
        try:
            number = int(track)
        except ValueError:
            raise SettingsError("%s %r does not start with a track number" % (what, key)) from None
        if number < 0:
            raise SettingsError("%s %r has a negative track" % (what, key))
        return "%d:%s" % (number, _index(channel, _MAX_CHANNEL, what))
    return _index(key, _MAX_CHANNEL, what)


def part_selector(key: str):
    """A validated `channels` key as the parser matches on it.

    A bare channel comes back as the channel number and applies to every part on
    it; a named part comes back as the `(track, channel)` pair. Keeping the two
    shapes distinguishable all the way down is what lets the specific entry win
    over the wildcard at the point a note is actually resolved.
    """
    if ":" in key:
        track, _, channel = key.partition(":")
        return (int(track), int(channel))
    return int(key)


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


def _number(value, what: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SettingsError("%s is %r, which is not a number" % (what, value))
    value = float(value)
    if not low <= value <= high:
        raise SettingsError("%s is %r; it has to be between %g and %g" % (what, value, low, high))
    return value


def _optional_number(value, what: str, low: float, high: float) -> float | None:
    return None if value is None else _number(value, what, low, high)


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
    """Validate per-channel automatic, family, or exact event choices.

    The UI offers the installed catalog's named Play events and marks local
    preview availability separately. Validation is intentionally
    install-independent: settings files must still load when the game moves,
    and a custom Play event can be compiled for a modded game.
    """
    section = _mapping(section, "channels")
    out = {}
    for key, entry in section.items():
        channel = _part_key(key, "channel")
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
        if sound is not None and (
            not isinstance(sound, str)
            or (sound not in sounds and _PLAY_EVENT.fullmatch(sound) is None)
        ):
            raise SettingsError(
                "channel %s: %r is not a valid DOOM Play_ event identifier" % (channel, sound)
            )
        if family is not None and sound is not None:
            raise SettingsError(
                "channel %s: choose a pitched family or one exact sound, not both" % channel
            )
        percussion = entry.get("percussion", "auto")
        if percussion not in _PERCUSSION_MODES:
            raise SettingsError(
                "channel %s: percussion is %r; it has to be one of %s"
                % (channel, percussion, ", ".join(_PERCUSSION_MODES))
            )
        normalized = {
            "family": family,
            "percussion": percussion,
            "muted": _flag(entry.get("muted", False), "channel %s: muted" % channel),
            "soloed": _flag(entry.get("soloed", False), "channel %s: soloed" % channel),
        }
        if sound is not None:
            normalized["sound"] = sound
            expression_fields = _CHANNEL_KEYS - {"family", "sound", "muted", "soloed"}
            if any(key in entry for key in expression_fields):
                pitch_follow = _flag(
                    entry.get("pitch_follow", False),
                    "channel %s: pitch_follow" % channel,
                )
                root_midi = _optional_number(
                    entry.get("root_midi"),
                    "channel %s: root_midi" % channel,
                    0,
                    _MAX_NOTE,
                )
                if pitch_follow and root_midi is None:
                    raise SettingsError(
                        "channel %s: pitch_follow needs a root_midi between 0 and 127" % channel
                    )
                normalized["pitch_follow"] = pitch_follow
                if root_midi is not None:
                    normalized["root_midi"] = root_midi
                    normalized["root_confidence"] = _number(
                        entry.get("root_confidence", 1.0),
                        "channel %s: root_confidence" % channel,
                        0,
                        1,
                    )
                    root_source = entry.get("root_source", "manual")
                    if root_source not in _ROOT_SOURCES:
                        raise SettingsError(
                            "channel %s: root_source is %r; it has to be one of %s"
                            % (channel, root_source, ", ".join(sorted(_ROOT_SOURCES)))
                        )
                    if pitch_follow and root_source == "detected_octave_pending":
                        raise SettingsError(
                            "channel %s: an old octave-fitted root must be re-analyzed "
                            "before pitch_follow can be enabled" % channel
                        )
                    normalized["root_source"] = root_source
        out[channel] = normalized
    return out


def _note_id(value) -> str:
    if not isinstance(value, str):
        raise SettingsError("note id %r is not text" % (value,))
    pieces = value.split(":")
    if len(pieces) != 3:
        raise SettingsError("note id %r must be channel:source-pitch:occurrence" % value)
    _index(pieces[0], _MAX_CHANNEL, "note channel")
    _index(pieces[1], _MAX_NOTE, "note source pitch")
    try:
        occurrence = int(pieces[2])
    except ValueError:
        occurrence = 0
    if occurrence < 1 or str(occurrence) != pieces[2]:
        raise SettingsError("note id %r has an invalid occurrence" % value)
    return value


def _notes(section) -> dict:
    """Validate sparse per-note playback-pitch and volume choices.

    The key is generated from source MIDI identity, not conversion output, so
    changing an instrument or root profile cannot move an edit to another note.
    volume_db is the absolute note level before global volume and therefore
    preserves an explicit zero. volume_trim_db is retained only so migrated
    version-4 sidecars keep their exact sound until that note is edited.
    Empty/default records are otherwise dropped to keep sidecars compact.
    """
    section = _mapping(section, "notes")
    out = {}
    for raw_id, entry in section.items():
        note_id = _note_id(raw_id)
        entry = _mapping(entry, "note %s" % note_id)
        unknown = sorted(set(entry) - _NOTE_KEYS)
        if unknown:
            raise SettingsError("note %s: unknown setting(s): %s" % (note_id, ", ".join(unknown)))
        pitch_offset = _whole(
            entry.get("pitch_offset", 0), "note %s: pitch_offset" % note_id, -24, 24
        )
        if "volume_db" in entry and "volume_trim_db" in entry:
            raise SettingsError(
                "note %s: volume_db and legacy volume_trim_db cannot both be set" % note_id
            )
        normalized = {}
        if pitch_offset:
            normalized["pitch_offset"] = pitch_offset
        if "volume_db" in entry:
            volume_db = _whole(
                entry["volume_db"],
                "note %s: volume_db" % note_id,
                _MIN_VOLUME_DB,
                _MAX_VOLUME_DB,
            )
            normalized["volume_db"] = volume_db
        if "volume_trim_db" in entry:
            volume_trim_db = _whole(
                entry["volume_trim_db"],
                "note %s: volume_trim_db" % note_id,
                _MIN_VOLUME_DB,
                _MAX_VOLUME_DB,
            )
            if volume_trim_db:
                normalized["volume_trim_db"] = volume_trim_db
        if normalized:
            out[note_id] = normalized
    return out


def _drum_keys(section) -> dict:
    """Percussion keys mapped to sounds, checked as far as they can be checked.

    Two different questions, because two different things can be named here.

    A sound the PALETTE knows is checked against `drum_sound_pool` and nothing
    else, because for those the answer is available and definite: the unpitched
    half of the palette is mostly ambience, a pitched sound would play one fixed
    note under every hit, and a looping ambience is never told to stop -- it
    holds its emitter open until the engine recycles the slot out from under
    something else.

    A name the palette has never heard of is a full-game event, and there is
    nothing here to check it against: the installed catalog needs the game, and
    this runs on machines that do not have it. Accepted on the shape of the name
    alone, exactly as an exact channel sound is. The window only ever offers
    events the soundbank reports as one-shots from the percussive folders; a
    hand-written sidecar can still name a loop, and that stays the sidecar's
    risk rather than a reason to refuse every event in the game.
    """
    section = _mapping(section, "drum_keys")
    out = {}
    for key, sound in section.items():
        drum_key = _index(key, _MAX_NOTE, "drum key")
        problem = palette.drum_sound_problem(sound)
        if problem is not None:
            raise SettingsError("drum key %s: %s" % (drum_key, problem))
        out[drum_key] = sound
    return out


def _decaying_families(value, families) -> list:
    """Families classified as naturally decaying instead of sustained.

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
    out["master_volume_db"] = _whole(
        out["master_volume_db"], "master_volume_db", _MIN_VOLUME_DB, _MAX_VOLUME_DB
    )
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


def _migrate(doc: dict) -> dict:
    """Upgrade older sidecars while preserving their stored user choices.

    Version 6 removes two pitch references that could preserve intervals while
    shifting absolute playback by an octave. A legacy channel-centered
    relative reference returns to natural playback. An enabled octave-fitted
    detection is disabled and marked for acoustic re-analysis by the UI; this
    also makes direct command-line compilation safe when game media is absent.

    Version 5 makes a note's volume_db its absolute pre-master level.
    Versions 1 through 4 used the same name for a relative velocity trim, so
    migration gives that value an explicit legacy name. The expression engine
    continues to honor it exactly, and the UI replaces it with an absolute
    value when the user next edits that note.

    Version 4 separates the written MIDI note from a playback-only pitch
    offset. Versions 2 and 3 called the same integer ``transpose``. Renaming
    that sparse user value preserves its intent while allowing
    the piano roll and curated sample selection to stay faithful to the MIDI.
    Version 1 had no note-expression section.
    """

    version = doc.get("version", SETTINGS_VERSION)
    if isinstance(version, bool) or version not in (1, 2, 3, 4, 5, 6):
        return doc

    migrated = copy.deepcopy(doc)
    if version <= 4:
        notes = migrated.get("notes")
        if notes is None and version == 1:
            migrated["notes"] = {}
        elif isinstance(notes, Mapping):
            rewritten = {}
            for note_id, raw_entry in notes.items():
                if isinstance(raw_entry, Mapping):
                    entry = dict(raw_entry)
                    if "transpose" in entry:
                        if "pitch_offset" in entry and entry["pitch_offset"] != entry["transpose"]:
                            raise SettingsError(
                                "note %s has conflicting transpose and pitch_offset values"
                                % note_id
                            )
                        entry["pitch_offset"] = entry.pop("transpose")
                    if "volume_db" in entry:
                        if "volume_trim_db" in entry:
                            raise SettingsError(
                                "note %s has conflicting volume_db and volume_trim_db values"
                                % note_id
                            )
                        entry["volume_trim_db"] = entry.pop("volume_db")
                    rewritten[note_id] = entry
                else:
                    rewritten[note_id] = raw_entry
            migrated["notes"] = rewritten

    channels = migrated.get("channels")
    if isinstance(channels, Mapping):
        rewritten_channels = {}
        for channel, raw_entry in channels.items():
            if isinstance(raw_entry, Mapping):
                entry = dict(raw_entry)
                source = entry.get("root_source")
                if source == "relative":
                    entry["pitch_follow"] = False
                    entry.pop("root_midi", None)
                    entry.pop("root_confidence", None)
                    entry.pop("root_source", None)
                elif source == "detected_octave":
                    if entry.get("pitch_follow") is True:
                        entry["pitch_follow"] = False
                        entry["root_source"] = "detected_octave_pending"
                    else:
                        # A disabled automatic profile is a user choice, so do
                        # not silently re-enable it during startup repair. Its
                        # fitted value was never an absolute acoustic root and
                        # is therefore discarded instead of relabelled.
                        entry.pop("root_midi", None)
                        entry.pop("root_confidence", None)
                        entry.pop("root_source", None)
                rewritten_channels[channel] = entry
            else:
                rewritten_channels[channel] = raw_entry
        migrated["channels"] = rewritten_channels
    migrated["version"] = SETTINGS_VERSION
    return migrated


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

    doc = _migrate(doc)
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
    out["notes"] = _notes(doc.get("notes", {}))
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
                _part_key(channel, "channel"): entry
                for channel, entry in _mapping(merged.get("channels", {}), "channels").items()
            }
            for channel, entry in _mapping(value, "channels").items():
                channel = _part_key(channel, "channel")
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
        "master_volume_db": tuning["master_volume_db"],
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
            part_selector(channel): entry["family"]
            for channel, entry in channels.items()
            if entry["family"] is not None
        },
        "channel_sounds": {
            part_selector(channel): entry["sound"]
            for channel, entry in channels.items()
            if entry.get("sound") is not None
        },
        "channel_pitch_profiles": {
            part_selector(channel): {
                "pitch_follow": entry.get("pitch_follow", False),
                "root_midi": entry.get("root_midi"),
                "root_confidence": entry.get("root_confidence"),
                "root_source": entry.get("root_source"),
            }
            for channel, entry in channels.items()
            if entry.get("sound") is not None
        },
        "part_percussion": {
            part_selector(c): entry["percussion"]
            for c, entry in channels.items()
            if entry.get("percussion", "auto") != "auto"
        },
        "note_overrides": copy.deepcopy(doc["notes"]),
        # Mappings, not sets: only a mapping can say that one named part is NOT
        # muted while its channel is, which is what lets a part key beat the
        # channel-wide wildcard. The parser accepts either spelling.
        "channel_mutes": {part_selector(c): entry["muted"] for c, entry in channels.items()},
        "channel_solos": {part_selector(c): entry["soloed"] for c, entry in channels.items()},
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
