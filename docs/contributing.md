# Contributing to snapmap-midi

This guide takes you from a fresh machine to an open pull request. For what the tool does
see [`capabilities.md`](capabilities.md), for how it works see
[`architecture.md`](architecture.md).

If anything here is wrong, missing, or unclear, fixing it is itself a welcome pull request.

## Contents

1. [Ground rules](#1-ground-rules)
2. [Setup](#2-setup)
3. [Game data](#3-game-data)
4. [Running the suite](#4-running-the-suite)
5. [Style](#5-style)
6. [Opening a pull request](#6-opening-a-pull-request)

## 1. Ground rules

**Clean-room.** Every line here is written from our own work. Do not paste in decompiled
output or copyrighted game content — not into code, not into comments, not into a test
fixture. If you learned something by reading the game's data, describe the finding and write
your own implementation of it.

**No game data, ever.** No `.decl` files. No saved maps. No audio. Sound *names* do ship —
they are identifiers, not content, and the line is drawn in [`game-data.md`](game-data.md).
CI enforces the rest and will fail the pull request.

**One change per pull request.** A rename bundled with a behaviour change makes both harder
to review and makes a byte-gate movement ambiguous.

## 2. Setup

Python 3.12 or newer. Nothing to find or configure — pip fetches the two runtime
dependencies. `mido` reads MIDI files. `pywebview` is the control window and is declared for
Windows only, so on Linux or macOS add the `[ui]` extra to the install line below if you are
working on the window. The suite does not need it: `ui/api.py` and `ui/session.py` import
pywebview nowhere, and `ui/app.py` imports it inside a function, which is what keeps the
whole package importable and testable on a machine that will never open one.

```bash
git clone https://github.com/doom-snapmap/snapmap-midi.git
cd snapmap-midi
py -3.12 -m venv .venv          # Windows
python3.12 -m venv .venv        # Linux / macOS
```

Install into it in editable mode with the dev extras. These call the environment's
interpreter by path, so they work whether or not you have activated it:

```bash
.venv/Scripts/python.exe -m pip install -e ".[dev]"    # Windows
.venv/bin/python -m pip install -e ".[dev]"            # Linux / macOS
```

The `src/` layout means the package is **not** importable from the repository root without
that install. That is deliberate: it makes a green suite prove the installed package works,
not just the checkout.

Check it:

```bash
.venv/Scripts/python.exe -m snapmap_midi --help        # Windows
.venv/bin/python -m snapmap_midi --help                # Linux / macOS
```

If you would rather type `python` and `pytest` bare, activate the environment first — the
[README](../README.md#the-isolated-way-recommended) has the activation line for each shell,
including the PowerShell execution-policy fix. Every command in this guide works either way.

## 3. Game data

You need none. The sound palette ships with the package and maps are authored from nothing,
so a fresh clone compiles real songs and runs the whole suite green.

Four tests compile *against* a saved map, to prove that path still works for people adding
music to a level they already have. They carry the `savedmap` marker and skip when none is
configured. **Seeing them skip is normal and not a failure.**

The suite hides `SNAPMAP_MIDI_PATHS` from every test that has not asked for it, so your own
overrides cannot change the result. That matters: without it, a contributor who had
`palette_decl` configured for their game version ran a different suite than CI did, and nine
tests failed for reasons that had nothing to do with any code change. `savedmap` tests see
the map overrides and still not the palette one — every byte gate is recorded against the
shipped palette, so letting another palette through would compare output to a golden built
from different sounds.

If you want to run them, see [`game-data.md`](game-data.md). One of them also needs
`groove_fixture`, an artifact that is not distributed and will skip permanently even for a
fully configured contributor.

## 4. Running the suite

```bash
python -m pytest
```

Expect `319 passed, 4 skipped` on a clone with nothing configured.

### What the byte gates mean

Three tests compare compiler output byte for byte against a recorded artifact. If one moves,
**read [`limits.md`](limits.md) before doing anything else.**

The short version: bytes moving while the structural assertions still pass is a regression,
not an improvement. The map format preserves key insertion order, so a structurally
identical refactor can change the bytes. Find the reordered structure and restore its
order — do not re-record the fixture.

If output genuinely should change, the commit must touch the compiler, say in words what
semantic change is intended, and show which statistics moved.

### The structural guards

A handful of tests in `tests/test_document.py` assert properties of the repository rather
than of any function: that each subsystem imports only downward, that no shipped module
reaches for a network client, that the protected method names have not been renamed.

They look like bureaucracy and are not. The layering one is what keeps `rawmap/` promotable
to its own library and `sound/` usable without a MIDI compiler; the network one is what
keeps this package a pure bytes-out tool.

The layering test is data-driven over the subsystem list, and it fails if a named package is
missing rather than scanning an empty directory and passing vacuously. Its predecessor
matched modules by bare name and would have gone quiet the moment they moved into packages.

### Working on the control window

Open `src/snapmap_midi/ui/web/index.html` in an ordinary browser. There is no bridge there,
so the window shows its empty state rather than throwing — that is deliberate, because
opening the file directly is how anybody iterating on the markup will look at it.

Everything the window decides is decided in Python, including the pitch ruler's geometry,
which arrives as percentages from `music/analysis.py`. **Do not move a calculation into
`app.js` to save a round trip.** The reason it is on the Python side is that a wrong
percentage there is a test failure and a wrong percentage in the browser is a picture nobody
can check. The same rule bans a sound-family name appearing anywhere in the markup: the
window gets its families from the bridge, which derives them from the palette.

To see it running, `.venv/Scripts/python.exe -m snapmap_midi`. [`ui.md`](ui.md) describes
what should be on screen.

## 5. Style

```bash
ruff check .
ruff format .
```

Both run in CI and both must be clean.

**The lint ruleset is deliberately narrow** — `E`, `F`, `I` only. It was kept that way for
the initial commit so that any movement in a byte gate would have exactly one possible
cause. Broadening it (`UP`, `B`, and friends) is a genuinely useful contribution; do it as
its own pull request, with the byte gates green before and after, and not mixed into a
change that also touches behaviour.

Line length is 100.

## 6. Opening a pull request

Fill in the template. The checklist is short and each item exists because of something that
actually went wrong.

CI runs two gates on every pull request:

- **Guard (secretless)** — no game data, no unexpected binaries, secret scan, and the
  structural guards. Runs with a read-only token and no repository secrets, so it is safe on
  a fork.
- **Test (Windows + Ubuntu)** — lint and the full suite on both platforms.

A maintainer reviews before merge. Changes to `.github/` or `pyproject.toml` require
maintainer review specifically — those are the supply-chain-critical surfaces.

Merges to `main` need both gates green, one approving review, and all conversations
resolved.
