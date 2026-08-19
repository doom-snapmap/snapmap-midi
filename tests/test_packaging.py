"""Packaging metadata, and the one thing that decides whether anyone gets a fix.

`pip install --upgrade` compares versions. If the version does not move, pip
concludes the installed copy is current and does nothing -- silently, exit 0,
"Requirement already satisfied". A whole release can ship and reach nobody.

That is not hypothetical: it happened. Every change from a baseline-free
compile to the flute-pitch fix went out under 0.1.0, and users who ran the
documented upgrade command kept the old code.
"""

from __future__ import annotations

import pathlib
import tomllib

import snapmap_midi

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_two_version_declarations_agree():
    """`pyproject.toml` decides what pip installs and compares; `__version__`
    is what a user or a bug report reads back. They are written in separate
    files and nothing but this test connects them."""
    assert snapmap_midi.__version__ == _pyproject()["project"]["version"]


def test_the_version_is_ahead_of_the_release_that_could_not_be_upgraded_to():
    """0.1.0 is burned. It named both the original release and every change
    after it, so pip cannot tell those apart and `--upgrade` is a no-op
    between them. Anything shipped from here has to carry a higher number.
    """
    from packaging.version import Version

    assert Version(snapmap_midi.__version__) > Version("0.1.0")


def test_every_subpackage_is_declared_for_packaging():
    """setuptools is given an explicit package list rather than a find
    directive, so a new subpackage is only shipped if someone remembers to
    add it. Forgetting means the wheel installs and then fails on import.
    """
    declared = set(_pyproject()["tool"]["setuptools"]["packages"])
    source = _ROOT / "src" / "snapmap_midi"
    on_disk = {"snapmap_midi"} | {
        "snapmap_midi.%s" % p.name
        for p in source.iterdir()
        if p.is_dir() and (p / "__init__.py").is_file()
    }
    assert declared == on_disk, "declared %s, on disk %s" % (
        sorted(declared),
        sorted(on_disk),
    )


def test_the_shipped_data_is_declared_as_package_data():
    """The palette is a .json inside the package. Without a package-data
    entry the wheel omits it and every compile raises PaletteUnavailableError
    on a machine that installed rather than cloned."""
    patterns = _pyproject()["tool"]["setuptools"]["package-data"]["snapmap_midi"]
    assert any(p.startswith("data/") for p in patterns), patterns
    assert (_ROOT / "src" / "snapmap_midi" / "data" / "sound_palette.json").is_file()


# ---- nothing committed names the machine it was written on ----
#
# A settings sidecar records the ABSOLUTE path of its MIDI and of whichever
# baseline map was picked. One reached a commit, so the repository carried a
# developer's home directory and every test run produced a diff. The tests that
# open a fixture song now drive a copy outside the tree, and the two guards
# below are what keep it that way -- a review will not catch this twice.

#: Directories whose contents are not the repository's own committed text.
_NOT_OURS = {".git", ".venv", "venv", "build", "dist", "__pycache__"}

#: A path INTO a home directory, which names both a person and their machine.
#: `%USERPROFILE%` and `~` are deliberately absent: those are the portable
#: spellings, and the README is right to tell somebody to use one.
_MACHINE_LOCAL = ("\\Users\\", "/Users/", "\\home\\", "/home/")


def _committed_text_files():
    """Every tracked-looking text file, skipping caches and agent scratch."""
    for path in _ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".json", ".md", ".toml"}:
            continue
        # This file has to spell the offending patterns out to look for them.
        if path == pathlib.Path(__file__).resolve():
            continue
        parts = set(path.relative_to(_ROOT).parts)
        if parts & _NOT_OURS or any(p.startswith(".") for p in parts - {path.name}):
            continue
        yield path


def test_no_committed_file_names_a_home_directory():
    """A home directory in a committed file is somebody's name and somebody's
    machine, and it is useless to everyone else who clones this."""
    offenders = []
    for path in _committed_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in _MACHINE_LOCAL:
            if needle in text:
                offenders.append("%s contains %r" % (path.relative_to(_ROOT), needle))
    assert offenders == [], offenders


def test_the_fixture_directory_holds_no_generated_sidecar():
    """`tests/fixtures/` is input. A sidecar in it means some test opened a
    fixture song in place rather than a copy, and the next run will write that
    machine's paths into the working tree again."""
    strays = sorted(p.name for p in (_ROOT / "tests" / "fixtures").glob("*.snapmap.json"))
    assert strays == [], strays
