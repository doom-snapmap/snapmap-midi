"""Test-session layer for the snapmap-midi product suite.

Hermetic by default. Every test here runs with no host repository and no game
assets: documents are built in code, the sound palette ships with the package,
and maps are authored from nothing. The only remaining external input is a
saved map to compile AGAINST, which a few tests use to prove that adding a song
to an existing map still works. Those carry the `savedmap` marker and skip when
none is configured.

Run standalone:

    .venv/Scripts/python.exe -m pytest tests
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PRODUCT_ROOT = Path(__file__).resolve().parents[1] / "src" / "snapmap_midi"

# Exact identity check. A wrong depth would not fail loudly -- it would quietly
# mis-resolve and disable things while the suite still went green. Checking a
# file INSIDE the package also proves the src/ layout is intact, which a check
# against this file's own path would not.
assert (_PRODUCT_ROOT / "rawmap" / "codec.py").is_file(), (
    "product root is wrong for this file's location"
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "savedmap: needs a saved baseline map to compile against; skipped when none is configured",
    )


def pytest_collection_modifyitems(config, items):
    from snapmap_midi import paths

    if paths.baseline_configured():
        return
    skip = pytest.mark.skip(reason="no baseline map configured (see snapmap_midi.paths)")
    for item in items:
        if item.get_closest_marker("savedmap"):
            item.add_marker(skip)


#: Overrides a `savedmap`-marked test is allowed to see. Deliberately NOT
#: `palette_decl`: every byte gate in this suite is recorded against the
#: SHIPPED palette, so letting a contributor's own palette through would make
#: those gates compare output to a golden built from different sounds.
_SAVEDMAP_KEYS = frozenset({"baseline_map", "groove_fixture"})


@pytest.fixture(autouse=True)
def hermetic_environment(request, monkeypatch, tmp_path_factory):
    """Hide the override table from every test that has not asked for it.

    `SNAPMAP_MIDI_PATHS` is ambient process state, and letting it through
    means a contributor who configured `palette_decl` for their own game
    version runs a DIFFERENT suite from the one CI runs. The shipped-palette
    assertions stop describing the shipped palette, and every byte gate
    compares against a golden built from sounds it is no longer using. Nine
    tests failed that way, none of them for a real reason.

    `savedmap`-marked tests see the map overrides, because compiling against a
    supplied map is the entire point of them -- and nothing else.

    The palette cache is cleared either way: it is keyed on the source path,
    and the source path is exactly what this fixture moves.

    `LOCALAPPDATA` moves for the same reason. A contributor who saved their own
    percussion table in the window would otherwise run a suite where key 36 is
    whatever they picked, and every assertion about the SHIPPED table would be
    describing their taste instead. A test that wants a user table writes one
    into this directory itself.

    The game install is hidden for the same reason once more, and this one was
    the expensive omission. `locate.doom_install` reads Steam's own registry
    key, which no environment variable moves, so a machine with DOOM installed
    fed real soundbank durations into `compile_to_rawmap`'s voice reservations.
    Different reservations pack notes onto different emitters and author
    different bytes, so four byte gates failed on a developer machine and
    passed in CI -- for no reason a diff could explain. `gamedata`-marked tests
    see the install, because reading the real game is the entire point of them.
    """
    import json

    from snapmap_midi import paths
    from snapmap_midi.audio import library, locate
    from snapmap_midi.sound import palette

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path_factory.mktemp("localappdata")))

    if request.node.get_closest_marker("gamedata") is None:
        monkeypatch.setattr(locate, "doom_install", lambda: None)
        library.reset_source()

    if request.node.get_closest_marker("savedmap") is None:
        monkeypatch.delenv(paths.ENV_VAR, raising=False)
    else:
        kept = {k: v for k, v in paths._config().items() if k in _SAVEDMAP_KEYS}
        monkeypatch.setenv(paths.ENV_VAR, json.dumps(kept))
    palette.cache_clear()
    yield
    palette.cache_clear()
    library.reset_source()


def _blank_document() -> dict:
    """The smallest document the authoring core can operate on.

    Both reference tables are prefix-sum indexed by unique id and must be
    readable one past the id being authored, so `instanceEntities.keyValues`
    carries two entries rather than one.
    """
    return {
        "entities": [],
        "instanceEntities": {"keyValues": [0, 0], "values": []},
        "instances": [{"moduleName": "maps/modules/test/blank.decl"}],
        "references": {
            "entityEntRefs": {"keyValues": [0], "values": []},
            "entityVarRefs": {"keyValues": [0], "values": []},
        },
        "targets": {"connections": []},
    }


@pytest.fixture
def minimal_map() -> dict:
    return _blank_document()


@pytest.fixture
def minimal_timeline_map() -> dict:
    """A blank document plus one timeline entity for the authoring API to fill."""
    doc = _blank_document()
    doc["entities"].append(
        {
            "uniqueId": 1,
            "entityDef": {
                "className": "idTarget_Timeline",
                "inherit": "snapmaps/logic/timeline",
                "state": {
                    "edit": {
                        "componentTimeLine": {
                            "entityEvents": {
                                "item[0]": {"entity": "0_blank/timeline_1", "events": {"num": 0}},
                                "num": 1,
                            }
                        }
                    }
                },
            },
        }
    )
    return doc
