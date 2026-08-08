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

Python 3.12 or newer. Nothing else — `mido` is the only runtime dependency and pip fetches
it.

```bash
git clone https://github.com/doom-snapmap/snapmap-midi.git
cd snapmap-midi
py -3.12 -m venv .venv          # Windows
python3.12 -m venv .venv        # Linux / macOS
```

Activate it, then install in editable mode with the dev extras:

```bash
.venv/Scripts/python.exe -m pip install -e ".[dev]"    # Windows
.venv/bin/python -m pip install -e ".[dev]"            # Linux / macOS
```

The `src/` layout means the package is **not** importable from the repository root without
that install. That is deliberate: it makes a green suite prove the installed package works,
not just the checkout.

Check it:

```bash
python -m snapmap_midi --help
```

## 3. Game data

You need none. The sound palette ships with the package and maps are authored from nothing,
so a fresh clone compiles real songs and runs the whole suite green.

Four tests compile *against* a saved map, to prove that path still works for people adding
music to a level they already have. They carry the `savedmap` marker and skip when none is
configured. **Seeing them skip is normal and not a failure.**

If you want to run them, see [`game-data.md`](game-data.md). One of them also needs
`groove_fixture`, an artifact that is not distributed and will skip permanently even for a
fully configured contributor.

## 4. Running the suite

```bash
python -m pytest
```

Expect `67 passed, 4 skipped` on a clone with nothing configured.

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
