"""The shipped sound palette, its cache, and the override that can replace it.

The palette went from a file the user had to supply to package data, which
moved a whole class of failure from "it refuses to start" to "it quietly
resolves different sounds". These tests are about that class.
"""

from __future__ import annotations

import json

import pytest

from snapmap_midi import paths
from snapmap_midi.sound import palette


def test_the_shipped_palette_is_present_and_plausible():
    shipped = json.loads(palette._SHIPPED.read_text(encoding="utf-8"))
    categories = shipped["categories"]
    assert len(categories) == 24
    assert sum(len(v) for v in categories.values()) == 890
    # Declaration order is load-bearing: `audition` prints an index against
    # each sound, and re-sorting would renumber every legend anyone wrote down.
    assert categories["ins_noise"][0] == "play_noise_clap"


def test_a_trailing_b_is_a_note_not_a_flat_marker():
    """`play_fluteb4` is B4. Read by pattern alone it is also E-flat 4, by
    eating the `e` from "flute" -- and that is what it used to be read as,
    a tritone away. Only the instrument stem settles it.

    Every wind program in General MIDI routes to `ins_flute`, so this was
    every B in every clarinet, oboe, sax and piccolo part.
    """
    assert palette.shader_pitch("play_fluteb3") == 59
    assert palette.shader_pitch("play_fluteb4") == 71
    assert palette.shader_pitch("play_fluteb5") == 83
    assert palette.shader_pitch("play_fluteb6") == 95
    # The real flats still read as flats.
    assert palette.shader_pitch("play_fluteeb4") == 63
    assert palette.shader_pitch("play_flutebb4") == 70


def test_every_flute_sound_reaches_the_index():
    """The misread names collided with the real flats, so the index held
    fewer sounds than the category had, and B was absent entirely."""
    index = palette.build_note_index()
    flute = index["ins_flute"]
    assert len(flute) == len(palette.sounds_in_category("ins_flute"))
    assert flute[71] == "play_fluteb4"
    assert flute[63] == "play_fluteeb4"
    # Every pitch class present, so no note falls back to a neighbour.
    assert {pitch % 12 for pitch in flute} == set(range(12))


def test_a_known_unpitched_sound_is_not_guessed_at():
    """`play_clave1` ends in `e1` and read as a pitched E1. It is a wood
    block. A sound the palette knows and gives no pitch to is unpitched --
    it does not then get guessed at by pattern."""
    for sound in ("play_clave1", "play_clave4", "play_clave7"):
        assert palette.shader_pitch(sound) is None
    assert palette.shader_pitch("play_noise_kick_tight") is None


def test_an_unknown_name_still_falls_back_to_the_pattern():
    """A caller naming a sound of its own is the one case the pattern is
    right for."""
    assert palette.shader_pitch("play_madeupc4") == 60
    assert palette.shader_pitch("not a sound at all") is None


def test_every_pitched_category_parses_completely():
    """A category where some names parse and others do not means the stem was
    guessed wrong, and the ones that failed silently vanish from the index."""
    index = palette.build_note_index()
    for category, sounds in palette.load_palette().items():
        if category not in index:
            continue  # wholly unpitched, which is a real answer
        assert len(index[category]) == len(sounds), "%s: %d of %d sounds reached the index" % (
            category,
            len(index[category]),
            len(sounds),
        )


def test_load_palette_hands_out_a_copy():
    """The parse behind it is cached and shared. Handing out the cached object
    lets one caller's mutation change what every later compile resolves."""
    first = palette.load_palette()
    first["ins_piano"] = ["nonsense"]
    first["ins_noise"].clear()
    assert palette.load_palette()["ins_piano"] != ["nonsense"]
    assert palette.sounds_in_category("ins_noise"), "the shared parse was mutated"
    assert palette.build_note_index()["ins_piano"], "the shared parse was mutated"


def test_cache_clear_reparses_the_same_path(tmp_path, monkeypatch):
    """The cache is keyed on the SOURCE, not its contents. Regenerating a
    palette in place and reading it again must not return the old parse."""
    decl = tmp_path / "speaker.decl"

    def write(sound):
        decl.write_text(
            'sound = "%s"; text = "x"; desc = "y"; category = "#str_snap_3dsnd_ins_piano_title";'
            % sound,
            encoding="utf-8",
        )

    write("play_pianoc4")
    monkeypatch.setenv(paths.ENV_VAR, json.dumps({"palette_decl": str(decl)}))
    assert palette.sounds_in_category("ins_piano") == ["play_pianoc4"]

    write("play_pianod4")
    assert palette.sounds_in_category("ins_piano") == ["play_pianoc4"], "expected the cached parse"
    palette.cache_clear()
    assert palette.sounds_in_category("ins_piano") == ["play_pianod4"]


def test_the_override_actually_overrides(tmp_path, monkeypatch):
    decl = tmp_path / "speaker.decl"
    decl.write_text(
        'sound = "play_flutea9"; text = "x"; desc = "y"; '
        'category = "#str_snap_3dsnd_ins_flute_title";',
        encoding="utf-8",
    )
    monkeypatch.setenv(paths.ENV_VAR, json.dumps({"palette_decl": str(decl)}))
    palette.cache_clear()
    assert palette.categories() == ["ins_flute"]
    assert palette.sounds_in_category("ins_flute") == ["play_flutea9"]


def test_a_configured_but_missing_override_warns(tmp_path, monkeypatch):
    """Silence means a typo degrades into the shipped palette and the tool
    reports success while ignoring the thing you asked it to use."""
    monkeypatch.setenv(paths.ENV_VAR, json.dumps({"palette_decl": str(tmp_path / "nope.decl")}))
    with pytest.warns(RuntimeWarning, match="palette_decl"):
        assert paths.palette_decl() is None


def test_an_override_that_parses_to_nothing_raises(tmp_path, monkeypatch):
    """An empty index would compile to a silent map, which looks like success
    -- the exact failure PaletteUnavailableError exists to prevent."""
    decl = tmp_path / "empty.decl"
    decl.write_text("this file contains no sound declarations at all", encoding="utf-8")
    monkeypatch.setenv(paths.ENV_VAR, json.dumps({"palette_decl": str(decl)}))
    palette.cache_clear()
    with pytest.raises(palette.PaletteUnavailableError):
        palette.build_note_index()


def test_the_suite_does_not_read_the_ambient_override(monkeypatch):
    """The autouse fixture in conftest hides SNAPMAP_MIDI_PATHS. Without it a
    contributor with their own palette configured runs a different suite than
    CI does -- seven tests failed that way, none of them for a real reason."""
    import os

    assert os.environ.get(paths.ENV_VAR) is None
    assert paths.palette_decl() is None
    assert len(palette.categories()) == 24
