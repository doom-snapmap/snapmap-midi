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

import json
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

# Modules whose every test needs a configured saved map.
_SAVEDMAP_MODULES = frozenset()


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
        module = Path(str(item.fspath)).stem
        if module in _SAVEDMAP_MODULES or item.get_closest_marker("savedmap"):
            item.add_marker(skip)


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


@pytest.fixture
def minimal_timeline_map_bytes(minimal_timeline_map) -> bytes:
    return json.dumps(minimal_timeline_map).encode("utf-8")
