# Security Policy

We take reports seriously and appreciate responsible disclosure.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Instead use GitHub's private
vulnerability reporting: open the repository's **Security** tab and choose **Report a
vulnerability**. That starts a private channel with the maintainer so the issue can be fixed
before it is disclosed.

Please include:

- what the problem is and where in the code it lives,
- how to reproduce it (a minimal example if you can), and
- the impact you believe it has.

We will acknowledge your report, keep you posted on the fix, and credit you when it ships
(unless you prefer to remain anonymous).

## What the threat model actually is

Worth stating plainly, because it is narrower than for a tool that loads into a game process.

**snapmap-midi ships no code into any game.** It is a command-line program and a Python
library. It reads a MIDI file you give it, plus two data files you point it at, and writes a
map file. It opens no network connection — a test enforces that no shipped module even
imports an HTTP client or names a loopback address.

So the realistic risks are:

- **A malicious MIDI input.** Parsing is delegated to `mido`; a crafted file that causes
  unbounded memory use or a crash in the parser is a real report and we want to hear it.
- **A compromised dependency.** `mido` is the only runtime dependency. Dependabot watches
  both it and the GitHub Actions.
- **A compromised release path.** Covered below.

Out of scope: anything that requires the attacker to already control the files you feed the
tool, or the machine it runs on.

## Supported versions

Security fixes are made against the latest release; older releases are not back-patched.

## How releases are protected

- Pull requests run in a secretless sandbox: fork PRs get a read-only token and no repository
  secrets.
- Any change to a supply-chain-critical path — the CI workflows, the dependency declaration —
  requires maintainer review before it can merge.
- Every merge to the default branch requires a passing guard and test gate.
- Third-party GitHub Actions are pinned to full commit SHAs, not tags.
- CI fails the build if any game data or an unexpected binary is committed.

Thank you for helping keep snapmap-midi and its users safe.
