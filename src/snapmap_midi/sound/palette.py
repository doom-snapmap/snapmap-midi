"""The curated conversion palette and the sound that plays a given pitch.

The palette is the stable musical subset used by automatic mapping, grouped
into categories. The installed full-game browser is deliberately broader.
Pitched instrument sounds encode their note in the name --
`play_violindb6` is D-flat in octave 6 -- so the pitch index is built by
parsing names rather than from any separate table.

**The palette ships with this package.** It used to be an extracted game file
the user had to find and configure a path to, which made a fresh install
useless until someone went digging, and made the tool unusable for anyone
without a copy of the extraction. What ships is the list of sound NAMES:
identifiers, not audio, and exactly the kind of data the General MIDI drum
table has always carried inline.

`paths.palette_decl()` remains as an override for the one case that still
needs it -- a game version whose palette differs from the shipped one. Point
it at a speaker declaration and it is parsed in place of the shipped list.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Optional

from snapmap_midi import paths

#: The shipped palette, alongside the rest of the package's data.
_SHIPPED = Path(__file__).resolve().parents[1] / "data" / "sound_palette.json"

#: Ear-labels for sounds whose names misdescribe them. Optional: see
#: `sound_labels` for why a missing file is not an error here.
_LABELS = Path(__file__).resolve().parents[1] / "data" / "soundfont_labels.json"

# sound = "<decl>"; text = "..."; desc = "..."; category = "<category>";
_ITEM = re.compile(
    r'sound\s*=\s*"([^"]+)";\s*text\s*=\s*"[^"]*";\s*desc\s*=\s*"[^"]*";\s*category\s*=\s*"([^"]+)";',
    re.S,
)
#: A trailing note name: letter, optional flat, octave digit. Ambiguous on its
#: own -- see `shader_pitch` -- and used only as a fallback for names the
#: palette does not contain.
_NOTE = re.compile(r"([a-g])(b?)(\d)$")

#: The same, anchored at BOTH ends, for what follows a known instrument stem.
#: Anchoring both ends is what removes the ambiguity.
_NOTE_EXACT = re.compile(r"^([a-g])(b?)(\d)$")
_PITCH_CLASS = {
    "c": 0,
    "db": 1,
    "d": 2,
    "eb": 3,
    "e": 4,
    "f": 5,
    "gb": 6,
    "g": 7,
    "ab": 8,
    "a": 9,
    "bb": 10,
    "b": 11,
}


class PaletteUnavailableError(RuntimeError):
    """Raised when no palette can be read at all.

    In an intact install this cannot happen -- the palette is package data.
    It means either a broken install or an override path that does not parse.
    """


def note_to_midi(letter: str, accidental: str, octave: str) -> int:
    """Note name components to a MIDI note number."""
    return (int(octave) + 1) * 12 + _PITCH_CLASS[letter + accidental]


def _category_stem(sounds) -> str:
    """The instrument prefix a category's sounds share, e.g. `play_flute`.

    Chosen as the prefix length that lets the MOST names parse as a note,
    longest wins on a tie -- not simply the longest common prefix. A category
    whose sounds happen to share a note letter would have that letter absorbed
    into the common prefix, leaving a bare octave digit behind.
    """
    if not sounds:
        return ""
    low, high = min(sounds), max(sounds)
    common = len(low)
    for i, ch in enumerate(low):
        if i >= len(high) or ch != high[i]:
            common = i
            break

    best_length, best_parsed = 0, -1
    for length in range(common + 1):
        parsed = sum(1 for s in sounds if _NOTE_EXACT.match(s[length:]))
        if parsed >= best_parsed:  # >= so the longest wins a tie
            best_length, best_parsed = length, parsed
    return low[:best_length]


def _pitch_of(sound: str, stem: str) -> Optional[int]:
    """The pitch a sound name spells after its instrument prefix."""
    m = _NOTE_EXACT.match(sound[len(stem) :])
    return note_to_midi(m.group(1), m.group(2), m.group(3)) if m else None


@lru_cache(maxsize=None)
def _pitches(override: Optional[Path]) -> dict:
    """{sound name: pitch} for every sound in the palette that has one."""
    table = {}
    for sounds in _load(override).values():
        stem = _category_stem(sounds)
        for sound in sounds:
            pitch = _pitch_of(sound, stem)
            if pitch is not None:
                table[sound] = pitch
    return table


def shader_pitch(shader: str) -> Optional[int]:
    """The MIDI pitch a sound name spells, or None if it is unpitched.

    Percussion has no pitch in its name, which is exactly how the compiler
    tells a drum hit from a melodic note after the fact.

    Resolved against the palette rather than by pattern alone, because the
    pattern alone is ambiguous and was getting it wrong. A trailing `b` is
    both a note and a flat marker, so `play_fluteb4` reads as either B4 or --
    by eating the `e` from "flute" -- E-flat 4. Only knowing that the
    instrument is spelled `play_flute` settles it. It used to read every wind
    B as an E-flat a tritone away, and every `play_claveN` as a pitched E.

    A sound the palette KNOWS and gives no pitch to is unpitched, full stop --
    it does not then get guessed at. Only a name the palette has never heard of
    falls back to the pattern, which is right for the one case that reaches
    here: a caller naming a sound of its own.
    """
    override = paths.palette_decl()
    table = _pitches(override)
    if shader in table:
        return table[shader]
    if shader in _known_sounds(override):
        return None
    m = _NOTE.search(shader)
    return note_to_midi(m.group(1), m.group(2), m.group(3)) if m else None


@lru_cache(maxsize=None)
def _known_sounds(override: Optional[Path]) -> frozenset:
    """Every sound name the palette contains, pitched or not."""
    return frozenset(s for sounds in _load(override).values() for s in sounds)


def _parse_decl(path: Path) -> dict:
    """A speaker declaration to {category: [sound names in order]}."""
    grouped: dict[str, list[str]] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for sound, category in _ITEM.findall(text):
        category = category.replace("#str_snap_3dsnd_", "").replace("_title", "")
        grouped.setdefault(category, []).append(sound)
    if not grouped:
        raise PaletteUnavailableError("parsed no sounds from the palette override at %s" % path)
    return grouped


@lru_cache(maxsize=None)
def _load(override: Optional[Path]) -> dict:
    """The palette, read once per distinct source.

    Cached because every surface that asks about sound asks for it first, and
    a compile with several layers used to re-read and re-parse the whole file
    for each one.
    """
    if override is not None:
        return _parse_decl(override)
    try:
        payload = json.loads(_SHIPPED.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PaletteUnavailableError(
            "the shipped sound palette at %s could not be read (%s); the install is "
            "incomplete" % (_SHIPPED, exc)
        ) from exc
    return payload["categories"]


def load_palette(decl_path: Optional[Path] = None) -> dict:
    """{category: [sound names]}, in declaration order.

    Reads the shipped palette unless an override is given here or configured
    as `palette_decl`.

    Returns a COPY. The parse behind it is cached and shared, so handing the
    cached object out would let one caller's `palette["ins_piano"].pop()`
    silently change what every later compile in the process resolves.
    """
    return {category: list(sounds) for category, sounds in _shared(decl_path).items()}


def _shared(decl_path: Optional[Path] = None) -> dict:
    """The cached parse itself. Internal: callers must not mutate it."""
    return _load(decl_path or paths.palette_decl())


def cache_clear() -> None:
    """Forget the parsed palette.

    Needed because the cache is keyed on the SOURCE, not its contents: after
    regenerating the shipped palette, or pointing `palette_decl` at a rewritten
    file at the same path, the old parse would otherwise be returned for the
    life of the process. The test suite also calls this between tests, since
    the key depends on ambient environment.

    The ear-labels go with it. They are a second file under the same package
    data, held by the same kind of cache, and stale for the same reason.
    """
    _load.cache_clear()
    _pitches.cache_clear()
    _known_sounds.cache_clear()
    sound_labels.cache_clear()


def categories() -> list:
    """Every category name, in declaration order."""
    return list(_shared())


def sounds_in_category(category: str, decl_path: Optional[Path] = None) -> list:
    """Every sound in a category, in declaration order."""
    return list(_shared(decl_path).get(category, ()))


def sound_categories(decl_path: Optional[Path] = None) -> dict:
    """Every palette sound to the category that owns it.

    Exact track assignments still need their category for scheduling and for
    the grouped workstation picker. This inverse index keeps the declaration
    itself as the only classification table.
    """
    return {sound: category for category, sounds in _shared(decl_path).items() for sound in sounds}


def all_sounds(decl_path: Optional[Path] = None) -> list:
    """Every speaker-palette sound, preserving declaration order."""
    return [sound for sounds in _shared(decl_path).values() for sound in sounds]


def build_note_index(decl_path: Optional[Path] = None) -> dict:
    """The pitch index: {category: {midi_note: sound}}.

    Only sounds whose name encodes a note appear. Percussion and effects have
    no pitch, so they are absent by construction rather than by exclusion.
    """
    index: dict = defaultdict(dict)
    for category, sounds in _shared(decl_path).items():
        stem = _category_stem(sounds)
        for sound in sounds:
            pitch = _pitch_of(sound, stem)
            if pitch is not None:
                index[category][pitch] = sound
    return index


def decl_for(category: str, midi_note: int, index: Mapping) -> Optional[str]:
    """The best sound in `category` for a pitch.

    Exact match wins. Otherwise prefer the same pitch class in another octave
    -- an octave displacement keeps the melody recognisable, where the nearest
    absolute pitch would bend it out of key. Fall back to nearest only when
    the pitch class is absent entirely.
    """
    available = index.get(category)
    if not available:
        return None
    if midi_note in available:
        return available[midi_note]
    pitch_class = midi_note % 12
    same_class = [m for m in available if m % 12 == pitch_class]
    pool = same_class or list(available)
    return available[min(pool, key=lambda m: abs(m - midi_note))]


def pitched_families() -> list:
    """Every category a melodic channel can be routed to, in declaration order.

    A category with no pitch index is not a quieter instrument, it is silence:
    `decl_for` returns None for every note in it, the channel drops out, and
    the map still loads and runs. Nothing downstream can report that, because
    nothing downstream can tell it apart from a part the user silenced on
    purpose -- so the filtering has to happen where the choice is offered.

    `ins_string` is the one that makes this necessary rather than tidy. It is
    named like an instrument, but holds twelve unpitched effect samples.

    Filtered, never sorted. Declaration order is the palette's own, and a list
    that reorders itself moves the option someone is reaching for.
    """
    index = build_note_index()
    return [category for category in categories() if index.get(category)]


def family_range(family: str, index: Optional[Mapping] = None) -> Optional[tuple]:
    """The lowest and highest MIDI note a family has a sound for.

    `index` is injectable because `build_note_index` is a full parse of the
    palette and is deliberately NOT cached: it returns a mutable defaultdict,
    for the same reason `load_palette` returns a copy, so it cannot hand the
    same object to two callers. Asking this for every family in a loop would
    otherwise reparse the palette once per family.

    Returns None where the family has no pitches at all, rather than a
    zero-width span, so a caller cannot draw a range at note 0 for a category
    that has no notes anywhere.
    """
    if index is None:
        index = build_note_index()
    pitches = index.get(family)
    if not pitches:
        return None
    return (min(pitches), max(pitches))


def unpitched_categories() -> list:
    """The exact complement of `pitched_families`, in declaration order.

    Derived rather than written out, because two hand-kept lists drift: a
    palette version that adds a category would leave it out of both, and a
    category in neither list is one no surface can offer and nobody notices
    is gone.
    """
    index = build_note_index()
    return [category for category in categories() if not index.get(category)]


#: The two unpitched categories that are a drum kit. The rest of the unpitched
#: half is ambience, gore, explosions and interface noise.
_DRUM_CATEGORIES = ("ins_noise", "ins_percussion")


#: Installed-catalog folders a percussion key may also draw from, on top
#: of the palette pool below. Curated by folder rather than by a duration
#: or loudness rule, because neither survives contact with this catalog: a
#: half-second event is as likely to be a scope chirp or a `Play_Stop_`
#: trigger as a drum hit, and the folder is the only place the game says
#: what a sound is FOR.
#:
#: These are things striking things -- impacts, footsteps, foley, and the
#: whole interface branch, whose blips and object pick-up/put-down sounds
#: are the shortest transients in the game. Weapons, voice, music and
#: ambience are deliberately absent.
#:
#: Membership is necessary, not sufficient: the window still offers only
#: the events the soundbank reports as one-shots, because a loop fired as
#: a drum hit is never told to stop.
DRUM_EVENT_FOLDERS = (
    # Things striking things.
    "effects/effects/impacts",
    "projectile/projectile/impacts",
    "footsteps/footsteps",
    "player/player/foley",
    # Things bursting. Longer than a hit -- these run two to three seconds --
    # so they read as crashes and stingers rather than kicks. The picker shows
    # each sound's length first, which is what makes that judgeable at a glance
    # rather than after an export.
    "effects/effects/explosions",
    "effects/effects/gore",
    "effects/effects/electricity_sparks",
    "snapmaps/effects",
    # The whole interface branch. Its blips, pick-ups, put-downs and reticle
    # clicks are the shortest transients in the game -- `ui/ui/snapmap/new_ui`
    # alone has a median length of a fifth of a second.
    "ui/ui",
    # SnapMap's own object and gameplay sounds, which are what this tool's
    # output shares a map with.
    "snapmaps/gameplay",
    "snapmaps/points",
    "doom_dlc1_sfx/SnapMaps/interactable",
    "doom_dlc1_sfx/SnapMaps/pickups",
    "doom_dlc1_sfx/SnapMaps/props",
    "doom_dlc1_sfx/hack_modules",
    "doom_dlc2_sfx/hack modules",
    "doom_dlc1_sfx/kineticMine",
    # The shortest transients in the game: this set runs from four hundredths
    # of a second, which is shorter than anything in the curated pool.
    "doom_dlc1_sfx/SnapMaps/ui_user_defined",
    # Demon voices and hell atmosphere. Two to five seconds, so these read as
    # atmosphere over a bar rather than as hits -- included because they are
    # one-shots a SnapMap author reaches for, not because they are drums.
    "doom_dlc1_sfx/SnapMaps/hellOneShots",
    # The only melodic folders here, and both earn it: a marimba and a bell are
    # struck, and the classic DOOM effects are almost all short transients.
    # Piano, guitar and horns are deliberately absent -- they are held notes,
    # and a held note under every hit is not a kit.
    "doom_dlc2_sfx/ClassicSFX",
    "doom_dlc2_sfx/instruments/Marimba",
    "doom_dlc2_sfx/instruments/Brass Bells",
)


#: A DOOM Play event identifier. Shape only -- the installed catalog is the
#: only thing that could confirm a name exists, and it needs the game.
_PLAY_EVENT_NAME = re.compile(r"(?i)^play_[a-z0-9_-]{1,59}$")


def drum_sound_problem(sound) -> Optional[str]:
    """Why this sound cannot be a percussion key, or None if it can.

    Two different questions, because two different things can be named.

    A sound the PALETTE knows is checked against `drum_sound_pool` and
    nothing else, because for those the answer is definite: the unpitched
    half of the palette is mostly ambience, a pitched sound would play one
    fixed note under every hit, and a looping ambience is never told to stop
    -- it holds its emitter until the engine recycles the slot out from
    under something else.

    A name the palette has never heard of is a full-game event, and there is
    nothing here to check it against: the catalog needs the game installed
    and this runs on machines that do not have it. Accepted on the shape of
    the name alone, exactly as an exact channel sound is. The window only
    ever offers events the soundbank reports as one-shots from the folders
    in `DRUM_EVENT_FOLDERS`; a hand-written sidecar can still name a loop,
    and that stays its own risk rather than a reason to refuse every event
    in the game.

    Returns a reason rather than raising so each caller can raise its own
    error type -- the settings document and the saved table have different
    ones, and they used to disagree about the rule itself.
    """
    if not isinstance(sound, str) or _PLAY_EVENT_NAME.fullmatch(sound) is None:
        return "%r is not a valid DOOM Play_ event identifier" % (sound,)
    pool = drum_sound_pool()
    if sound in all_sounds() and sound not in pool:
        return (
            "%r is a palette sound but not one of the %d percussion sounds. A "
            "pitched sound plays one fixed note under every hit, and a looping "
            "ambience is never stopped -- it holds its emitter until the engine "
            "recycles the slot out from under something else." % (sound, len(pool))
        )
    return None


def drum_sound_pool() -> list:
    """Every sound a percussion key may be remapped to.

    Not "every unpitched sound". That is 365 of them and it includes the
    looping ambience -- names ending `_lp`, and the whole `amb_` half of the
    palette. A loop fired as a one-shot is never told to stop, so it holds its
    emitter open until the engine recycles the slot out from under something
    else. That recycling is the failure this tool schedules its whole output
    around, and a picker offering those sounds would be its easiest source.

    A superset of `DRUM_MAP`'s own values, which is what lets someone put a key
    back the way they found it after trying something else.
    """
    pool = []
    for category in _DRUM_CATEGORIES:
        pool.extend(sounds_in_category(category))
    return pool


@lru_cache(maxsize=1)
def sound_labels() -> dict:
    """{category: {sound: label}} -- what someone actually heard, by ear.

    The names are the game's own and several of them lie about their contents:
    `play_noise_tom` is a knock on a wooden door, `play_noise_crash` is a
    shaker. A picker showing only names sends people to the tom for a tom.

    Returns {} on any failure to read the file, and deliberately does not
    raise. Unlike the palette, absent labels cost a hint and not a compile, so
    `PaletteUnavailableError` here would take a whole window down over a
    decoration. The guard is broad rather than narrowed to the two obvious
    errors because this file is meant to be hand-edited, and a half-finished
    edit fails in whatever way the editor left it.

    Keys beginning `_` are notes to whoever edits the file, not sounds.
    Leaving them in puts a row called `_note` in the drum picker.

    Hands out the cached dict itself rather than a copy: these are display
    hints, and a caller that mutates them costs itself a wrong tooltip, where
    a mutated palette would change which sounds a compile resolves.
    """
    try:
        payload = json.loads(_LABELS.read_text(encoding="utf-8"))
        return {key: value for key, value in payload.items() if not key.startswith("_")}
    except Exception:
        return {}
