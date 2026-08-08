"""The shared document surface, and the layering rules that keep it separable."""

from __future__ import annotations

import ast
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


_PACKAGE = "snapmap_midi"


def imported_modules(source: str, package: tuple) -> set:
    """Every module `source` imports, as absolute dotted names.

    Parsed rather than pattern-matched. A regex over import LINES is the
    obvious way to do this and it silently missed most of the real forms --
    `from snapmap_midi import music` (the style this very package uses for
    `paths`), a name in an import list, and every relative import. A guard
    that cannot see the codebase's own idiom is not a guard.

    `package` is the dotted package the source lives in, needed to resolve
    relative imports to absolute names.
    """
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            # import a.b.c [as d]
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # from .x import y / from ..x import y
                base = package[: len(package) - node.level + 1]
                parts = base + ((node.module,) if node.module else ())
            else:
                parts = tuple((node.module or "").split("."))
            module = ".".join(parts)
            found.add(module)
            # `from p import m` imports p.m when m is a submodule, and the
            # name alone tells us nothing -- so record both readings.
            found.update("%s.%s" % (module, alias.name) for alias in node.names)
    return found


def _reaches_upward(source: str, package: tuple, forbidden) -> set:
    """The forbidden subsystems `source` imports, if any."""
    hit = set()
    for module in imported_modules(source, package):
        for name in forbidden:
            if module == "%s.%s" % (_PACKAGE, name) or module.startswith(
                "%s.%s." % (_PACKAGE, name)
            ):
                hit.add(name)
    return hit


def _forbidden_above(layer_index: int) -> list:
    """Everything the layer at `layer_index` is not allowed to import."""
    return _LAYERS[layer_index + 1 :] + _SURFACE


@pytest.mark.parametrize("index,layer", list(enumerate(_LAYERS)))
def test_subsystem_imports_only_downward(index, layer):
    """Each subsystem stays independently usable: `rawmap` must not drag in a
    MIDI compiler, and `sound` must be usable to place sounds by hand with no
    music layer present.

    This is the layering that makes the packages meaningful rather than
    decorative. Promoting `rawmap/` to its own distribution should be a
    directory move, and that stays true only if it is proven.
    """
    forbidden = _forbidden_above(index)
    files = list((_PRODUCT_ROOT / layer).rglob("*.py"))
    assert files, "layer %r has no modules; the layout moved" % layer
    for f in files:
        package = (_PACKAGE,) + f.relative_to(_PRODUCT_ROOT).parts[:-1]
        upward = _reaches_upward(f.read_text(encoding="utf-8"), package, forbidden)
        assert not upward, "%s imports upward into %s" % (f, sorted(upward))


@pytest.mark.parametrize(
    "line",
    [
        "from snapmap_midi.music.midi import parse_notes",
        "import snapmap_midi.music.midi",
        "import snapmap_midi.music.midi as m",
        "from snapmap_midi import music",
        "from snapmap_midi import paths, music",
        "from snapmap_midi import music as m",
        "from ..music import gm",
        "from ..music.gm import DRUM_MAP",
        "from snapmap_midi import compile",
        "from snapmap_midi.compile import compile_to_rawmap",
        "def f():\n    from snapmap_midi import music",
    ],
)
def test_the_layering_guard_catches_every_import_form(line):
    """The guard has to be checked against real upward imports, or it passes
    because it sees nothing rather than because there is nothing to see.

    Its predecessor missed five of these eleven, including the two forms this
    package actually writes.
    """
    package = (_PACKAGE, "rawmap")
    assert _reaches_upward(line, package, _forbidden_above(0)), "not caught: %r" % line


@pytest.mark.parametrize(
    "line",
    [
        "from snapmap_midi.rawmap.codec import serialize",
        "from snapmap_midi import paths",
        "from .refs import add_entity_refs",
        "import json",
        "from typing import Optional",
    ],
)
def test_the_layering_guard_allows_downward_and_sideways(line):
    """The other half: a guard that flags everything is no more use than one
    that flags nothing."""
    package = (_PACKAGE, "rawmap")
    assert not _reaches_upward(line, package, _forbidden_above(0)), "false alarm: %r" % line


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
