"""The shared document surface, and the layering rules that keep it separable."""

from __future__ import annotations

import pathlib
import re

import pytest

from snapmap_midi.rawmap.document import SPEAKER_INHERIT, SnapMapDocument
from snapmap_midi.rawmap.palette_refs import PRODUCT_PALETTE_REFS
from snapmap_midi.rawmap.refs import UnknownInheritError

# The installed package, NOT the repository root. Pointing this at the root
# would make the layering scan below rglob a directory that does not exist --
# passing vacuously while testing nothing -- and would make the network scan
# walk a contributor's .venv and fail for a reason unrelated to the code.
_PRODUCT_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src" / "snapmap_midi"
_TESTS_DIR = pathlib.Path(__file__).resolve().parent

assert (_PRODUCT_ROOT / "rawmap" / "codec.py").is_file(), (
    "product root is wrong for this file's location"
)


def _doc(minimal_map) -> SnapMapDocument:
    return SnapMapDocument(data=minimal_map, palette_refs=PRODUCT_PALETTE_REFS)


# ---- protected surface ----


def test_protected_surface_is_public():
    """Subclasses compose their own entity kinds out of these three. Renaming
    one breaks a downstream author silently, so the names are contract."""
    for name in ("build_simple_entity", "extend_instance_entities", "add_entity_refs"):
        assert callable(getattr(SnapMapDocument, name))
        assert not name.startswith("_")


# ---- queries ----


def test_max_uid_counts_connection_sources(minimal_map):
    doc = _doc(minimal_map)
    doc.data["targets"]["connections"] = [-64, 12]
    # -64 encodes source 63, which outranks the raw target 12.
    assert doc.max_uid() == 63
    assert doc.next_safe_uid() == 64


def test_lookup_of_absent_id_is_not_an_error(minimal_map):
    assert _doc(minimal_map).lookup_class_and_inherit(999) == (None, None)


def test_find_entity_raises_for_absent_id(minimal_map):
    with pytest.raises(KeyError):
        _doc(minimal_map).find_entity(999)


# ---- speakers ----


def test_add_speaker_registers_everywhere_it_must(minimal_map):
    doc = _doc(minimal_map)
    uid = doc.add_speaker(sound="play_pianoc4", position=(1.0, 0.0, 2.0))
    assert doc.find_entity(uid)["entityDef"]["inherit"] == SPEAKER_INHERIT
    assert uid in doc.data["instanceEntities"]["values"]
    assert len(doc.data["references"]["entityEntRefs"]["keyValues"]) >= uid + 2


def test_speaker_position_is_zero_elided(minimal_map):
    doc = _doc(minimal_map)
    uid = doc.add_speaker(position=(0.0, 0.0, 0.0))
    edit = doc.find_entity(uid)["entityDef"]["state"]["edit"]
    assert "spawnPosition" not in edit
    assert "spawnOrientation" in edit


def test_authoring_without_a_table_raises(minimal_map):
    """None means no table, never 'an empty table, treat everything as zero'."""
    doc = SnapMapDocument(data=minimal_map)
    with pytest.raises(UnknownInheritError):
        doc.add_speaker()


# ---- connections ----


def test_connection_encoding_biases_the_source(minimal_map):
    doc = _doc(minimal_map)
    doc.add_connection(62, 63)
    assert doc.data["targets"]["connections"] == [-63, 63]


def test_second_target_joins_the_existing_run(minimal_map):
    doc = _doc(minimal_map)
    doc.add_connection(62, 63)
    doc.add_connection(62, 64)
    assert doc.data["targets"]["connections"] == [-63, 63, 64]
    assert doc.get_connections_for_source(62) == [63, 64]


def test_connection_rejects_a_non_positive_source(minimal_map):
    with pytest.raises(ValueError):
        _doc(minimal_map).add_connection(0, 5)


# ---- clone ----


def test_clone_preserves_the_concrete_class(minimal_map):
    """Naming a class here would either degrade a subclass on clone or invert
    the dependency; type(self) does neither."""

    class Subclass(SnapMapDocument):
        pass

    original = Subclass(data=minimal_map, palette_refs=PRODUCT_PALETTE_REFS)
    copied = original.clone()
    assert type(copied) is Subclass
    assert copied.palette_refs == PRODUCT_PALETTE_REFS
    copied.data["entities"].append({"uniqueId": 7})
    assert original.data["entities"] == []


# ---- layering ----


# The subsystem stack, lowest first. A package may import from itself and from
# anything BELOW it, never from anything above. `paths` is deliberately absent:
# it imports nothing internal, so it is a leaf every layer may use.
_LAYERS = ["rawmap", "sound", "music"]

#: Product-surface modules, which sit above every subsystem.
_SURFACE = ["compile", "audition", "cli"]


def _forbidden_imports_for(layer_index: int) -> re.Pattern:
    """Everything the layer at `layer_index` is not allowed to import."""
    above = _LAYERS[layer_index + 1 :] + _SURFACE
    return re.compile(
        r"^\s*(from|import)\s+snapmap_midi\.(%s)\b" % "|".join(above),
        re.M,
    )


@pytest.mark.parametrize("index,layer", list(enumerate(_LAYERS)))
def test_subsystem_imports_only_downward(index, layer):
    """Each subsystem stays independently usable: `rawmap` must not drag in a
    MIDI compiler, and `sound` must be usable to place sounds by hand with no
    music layer present.

    This is the layering that makes the packages meaningful rather than
    decorative. Promoting `rawmap/` to its own distribution should be a
    directory move, and that stays true only if it is proven.
    """
    banned = _forbidden_imports_for(index)
    files = list((_PRODUCT_ROOT / layer).rglob("*.py"))
    assert files, "layer %r has no modules; the layout moved" % layer
    for f in files:
        hit = banned.search(f.read_text(encoding="utf-8"))
        assert not hit, "%s imports upward: %s" % (f, hit.group(0).strip())


def test_every_subsystem_package_exists():
    """A renamed or deleted package would make the scan above vacuous."""
    for layer in _LAYERS:
        assert (_PRODUCT_ROOT / layer / "__init__.py").is_file(), layer


def test_product_does_not_import_the_host():
    """The whole point: snapmap-midi depends on nothing in the repository that
    currently hosts it, so extraction is a directory move.

    A plain import ban is not enough -- sys.path mutation, importlib, and
    __import__ all reach the host without matching an import statement, and
    the original code used exactly the first of those. Banned here so a
    regression fails rather than being caught only by someone remembering to
    run the extraction by hand.
    """
    banned = re.compile(
        r"^\s*(from|import)\s+(src|tools|tests|doomforge)\b"
        r"|sys\.path\s*\.\s*(insert|append)"
        r"|importlib\.import_module"
        r"|\b__import__\s*\(",
        re.M,
    )
    for f in _PRODUCT_ROOT.rglob("*.py"):
        assert not banned.search(f.read_text(encoding="utf-8")), f


def test_no_shipped_text_file_names_a_host_directory():
    """Covers what rglob('*.py') cannot see: markdown, JSON and any other
    shipped text that could hardcode a host path."""
    host_dirs = re.compile(r"\b(?:corpus|reference|doomforge|active|binaries)/")
    for f in _PRODUCT_ROOT.rglob("*"):
        if not f.is_file() or _TESTS_DIR in f.parents:
            continue
        if f.suffix.lower() not in {".py", ".md", ".json", ".txt", ".toml", ".cfg"}:
            continue
        assert not host_dirs.search(f.read_text(encoding="utf-8", errors="replace")), f


def test_product_has_no_network_client():
    """Pushing a built map to a running game is host tooling, not product
    code. Scans shipped modules only -- this file holds the banned literals in
    its own pattern, so including the test tree would fail on itself."""
    banned = re.compile(r"\b(urllib|http\.client|requests|socket)\b|127\.0\.0\.1|localhost")
    for f in _PRODUCT_ROOT.rglob("*.py"):
        if _TESTS_DIR in f.parents:
            continue
        assert not banned.search(f.read_text(encoding="utf-8")), f
