"""Reference-slot authoring and the injected count table."""

from __future__ import annotations

import pytest

from snapmap_midi.rawmap import refs
from snapmap_midi.rawmap.palette_refs import (
    LISTENER_ON_USE_INHERIT,
    PRODUCT_PALETTE_REFS,
    SPEAKER_INHERIT,
    SWITCH_INHERIT,
)


def _doc() -> dict:
    return {
        "references": {
            "entityEntRefs": {"keyValues": [0], "values": []},
            "entityVarRefs": {"keyValues": [0], "values": []},
        }
    }


def test_injected_table_drives_slot_counts():
    data = _doc()
    refs.add_entity_refs(data, 0, "x/button", {"x/button": (1, 0)})
    assert data["references"]["entityEntRefs"]["values"] == [refs.ENT_REF_UNBOUND]
    assert data["references"]["entityVarRefs"]["values"] == []


def test_variable_slots_use_their_own_sentinel():
    data = _doc()
    refs.add_entity_refs(data, 0, "x/listener", {"x/listener": (0, 2)})
    assert data["references"]["entityVarRefs"]["values"] == [refs.VAR_REF_UNBOUND] * 2


def test_key_table_is_readable_one_past_the_authored_id():
    data = _doc()
    refs.add_entity_refs(data, 5, "x/button", {"x/button": (1, 0)})
    assert len(data["references"]["entityEntRefs"]["keyValues"]) >= 7


def test_later_keys_are_bumped_by_the_inserted_count():
    data = _doc()
    data["references"]["entityEntRefs"]["keyValues"] = [0, 0, 0]
    refs.add_entity_refs(data, 0, "x/button", {"x/button": (2, 0)})
    assert data["references"]["entityEntRefs"]["keyValues"][1:3] == [2, 2]


def test_unknown_inherit_is_an_error_not_a_silent_zero():
    """Defaulting a miss to (0, 0) authors an entity the engine rejects at
    load, silently and far from the guess. Fail at author time instead."""
    with pytest.raises(refs.UnknownInheritError):
        refs.add_entity_refs(_doc(), 0, "x/unknown", {"x/button": (1, 0)})


def test_table_covers_every_inherit_the_product_authors():
    """Any inherit a product code path passes to the writer must be present,
    or that path raises the moment it runs."""
    assert set(PRODUCT_PALETTE_REFS) == {
        SPEAKER_INHERIT,
        LISTENER_ON_USE_INHERIT,
        SWITCH_INHERIT,
    }


def test_switch_pair_matches_the_value_proven_in_game():
    """This pair was hand-copied into two separate modules because no
    extracted table had an entry for it. Changing it moves serialized bytes
    and needs re-proving in game, not a fixture refresh."""
    assert PRODUCT_PALETTE_REFS[SWITCH_INHERIT] == (1, 0)
    assert PRODUCT_PALETTE_REFS[SPEAKER_INHERIT] == (0, 0)
    assert PRODUCT_PALETTE_REFS[LISTENER_ON_USE_INHERIT] == (0, 1)
