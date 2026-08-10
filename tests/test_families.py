"""Which families can play a pitch, and what a drum key may be given instead.

The picker exists so a user can override the automatic General MIDI mapping.
That makes the list of choices load-bearing in a way it never was before: every
family the window offers is a family someone will pick, and a family that
cannot play a pitch compiles to silence rather than to an error. These tests
pin the two lists apart from each other, and pin the drum pool to sounds that
are actually a kit hit.
"""

from __future__ import annotations

import pytest

from snapmap_midi.sound import palette


def test_pitched_families_are_the_ones_that_can_play_a_note():
    """Offering an unpitched category as an instrument compiles to silence.

    `decl_for` returns None for every note of a category with no pitch index,
    so the channel drops out entirely -- a map that loads, runs, and plays
    nothing where the part used to be. Nothing downstream reports it, because
    nothing downstream can tell the difference between "no sound for this
    note" and "the user wanted no sound".
    """
    families = palette.pitched_families()
    assert "ins_noise" not in families
    assert "amb_air" not in families
    assert "ins_square" in families
    assert "ins_tri" in families
    # The automatic mapping can never choose this one. It is the whole reason
    # the window has a picker at all.
    assert "ins_brass_bells" in families


def test_ins_string_is_never_offered():
    """`ins_string` is the trap: it is named like an instrument, it is listed
    in `SUSTAINED` beside the violins, and it has zero pitched sounds. A user
    scanning a dropdown picks it for the string part and gets silence plus a
    held voice allocation for notes that never sound.
    """
    assert "ins_string" not in palette.pitched_families()
    assert palette.family_range("ins_string") is None
    assert "ins_string" in palette.unpitched_categories()


def test_declaration_order_is_preserved():
    """The palette's own order, filtered -- not sorted.

    Re-sorting would renumber every legend anyone wrote down against
    `sounds_in_category`, which is the same reason the shipped palette keeps
    declaration order in the first place.
    """
    families = palette.pitched_families()
    assert families == [c for c in palette.categories() if c in families]


def test_family_range_reports_what_the_family_can_actually_reach():
    """The number the range warning is computed against.

    A wrong bound here is worse than no bound: it tells a user their part fits
    when a third of it is about to be transposed into another octave.
    """
    assert palette.family_range("ins_piano") == (21, 108)
    assert palette.family_range("ins_sine") == (36, 67)
    # The one that reaches past the old ruler axis.
    assert palette.family_range("ins_brass_bells") == (72, 112)


def test_family_range_is_none_where_there_is_no_pitch_to_report():
    """None rather than a zero-width span, so a caller cannot draw a bar at
    note 0 for a category that has no notes at all."""
    assert palette.family_range("ins_noise") is None
    assert palette.family_range("amb_air") is None
    assert palette.family_range("no_such_category") is None


def test_unpitched_categories_are_the_exact_complement():
    """Between them the two lists are the palette, with nothing counted twice
    and nothing lost. A category in neither list is a category no surface can
    ever show, which is how a sound quietly stops being reachable."""
    pitched = palette.pitched_families()
    unpitched = palette.unpitched_categories()
    assert set(pitched).isdisjoint(unpitched)
    assert sorted(pitched + unpitched) == sorted(palette.categories())
    assert unpitched == [c for c in palette.categories() if c in unpitched]


def test_the_drum_pool_is_percussion_not_every_unpitched_sound():
    """Revision 1 offered every sound in every unpitched category -- 365
    options including `amb_scape_wind_distortion_2d_lp`, a LOOP. Firing a loop
    as a one-shot with no stop is the emitter-recycling failure by
    construction, and the picker would have been its most convenient source."""
    pool = palette.drum_sound_pool()
    assert "play_noise_hat" in pool
    assert "play_clave1" in pool
    assert not any("_lp" in s for s in pool)
    assert not any(s.startswith("play_amb_") for s in pool)
    assert len(pool) < 100


def test_the_drum_pool_offers_each_sound_once():
    """A duplicated option in a dropdown reads as two different sounds, and
    the second one silently does nothing new."""
    pool = palette.drum_sound_pool()
    assert len(pool) == len(set(pool))


def test_every_sound_the_drum_table_already_uses_is_in_the_pool():
    """Otherwise a user cannot restore a key to its default by picking it."""
    from snapmap_midi.music.gm import DRUM_MAP

    assert set(DRUM_MAP.values()) <= set(palette.drum_sound_pool())


def test_family_range_accepts_a_prebuilt_index():
    """`build_note_index` is 1.3ms and returns a fresh mutable defaultdict, so
    it is deliberately not cached -- `load_palette` copies for the same reason.
    Callers in a loop pass the index in instead."""
    index = palette.build_note_index()
    assert palette.family_range("ins_piano", index) == palette.family_range("ins_piano")
    # And the argument is read, rather than accepted and ignored -- which is
    # what an unused parameter would look like from the test above alone.
    index["ins_piano"] = {60: "play_pianoc4"}
    assert palette.family_range("ins_piano", index) == (60, 60)


def test_the_note_index_is_never_shared_between_callers():
    """The guard on caching `build_note_index`.

    It returns a mutable defaultdict, so a cache would hand every later caller
    the object an earlier one edited -- `load_palette` returns a copy to avoid
    exactly this. A cache here would also make the picker's list depend on
    whichever surface built the index first.
    """
    index = palette.build_note_index()
    index["ins_piano"].clear()
    index["ins_noise"][60] = "nonsense"
    assert palette.family_range("ins_piano") == (21, 108)
    assert palette.family_range("ins_noise") is None
    assert "ins_noise" not in palette.pitched_families()


def test_labels_read_back_and_the_note_key_is_stripped():
    """`_note` is a message to whoever edits the file, not a sound. Leaving it
    in puts a row called `_note` in the drum picker."""
    labels = palette.sound_labels()
    assert "_note" not in labels
    assert not any(key.startswith("_") for key in labels)
    assert labels["ins_noise"]["play_noise_hat"]["role"] == "hihat"


def test_a_category_nobody_has_labelled_is_simply_absent():
    """Labels are a hint someone earned by listening, so most categories have
    none. Callers get an empty mapping and show the sound name."""
    assert palette.sound_labels().get("ins_percussion", {}) == {}


def test_labels_that_cannot_be_read_cost_a_hint_and_not_a_compile(tmp_path, monkeypatch):
    """Unlike the palette, absent labels are survivable: the picker shows sound
    names instead of ear-notes. Raising `PaletteUnavailableError` here would
    take down a window over a decoration."""
    monkeypatch.setattr(palette, "_LABELS", tmp_path / "not_written.json")
    palette.sound_labels.cache_clear()
    assert palette.sound_labels() == {}

    broken = tmp_path / "broken.json"
    broken.write_text("[not a mapping at all", encoding="utf-8")
    monkeypatch.setattr(palette, "_LABELS", broken)
    palette.sound_labels.cache_clear()
    assert palette.sound_labels() == {}


def test_cache_clear_forgets_the_labels_too(tmp_path, monkeypatch):
    """`cache_clear`'s docstring promises to forget everything the module has
    parsed. A cache it misses is a stale read that survives regenerating the
    file it was read from, for the life of the process."""
    assert palette.sound_labels(), "expected the shipped labels"
    monkeypatch.setattr(palette, "_LABELS", tmp_path / "gone.json")
    assert palette.sound_labels(), "expected the cached labels, not a re-read"
    palette.cache_clear()
    assert palette.sound_labels() == {}


@pytest.mark.parametrize("name", ["pitched_families", "unpitched_categories", "drum_sound_pool"])
def test_the_list_helpers_hand_out_a_fresh_list(name):
    """Each is a menu a surface may filter in place. Returning a shared list
    would let one panel's edit change what the next one offers."""
    getter = getattr(palette, name)
    first = getter()
    first.clear()
    assert getter(), "%s handed out a shared list" % name
