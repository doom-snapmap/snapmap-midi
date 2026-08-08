<!-- Thanks for contributing to snapmap-midi! Keep each PR focused on a single change. -->

## What this changes

<!-- A short description of the change and why it's needed. -->

## Checklist

- [ ] Clean-room: this is my own implementation -- no decompiled or copyrighted game content
      is pasted into the repo.
- [ ] No game data added: no `.decl` files, no saved maps, no audio. Sound *names* do ship --
      they are identifiers, not content. The line is drawn in docs/game-data.md.
- [ ] Suite run locally: `python -m pytest`.
- [ ] Style clean: `ruff check .` and `ruff format --check .`.
- [ ] Docs updated for any behavior change (see docs/contributing.md).

### If a byte gate moved

<!-- Delete this section if none of the three moved. -->

- [ ] The commit touches the compiler, not just the fixture.
- [ ] I have stated the intended semantic change in words, above.
- [ ] I have shown which statistics moved, and by how much.

Bytes moving while the structural assertions still pass is a regression, not an improvement --
the map format preserves key insertion order, so a structurally identical refactor can change
the bytes. See docs/limits.md before re-recording anything.

<!-- CI runs a secretless guard and a two-OS test matrix; a maintainer reviews before merge. -->
