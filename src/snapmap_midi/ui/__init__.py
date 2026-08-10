"""The control window: the choices the compiler cannot make on its own.

Which sound family a MIDI channel should become is a taste call. The compiler
guesses it from a General MIDI program number, and that guess is right often
enough to be worth having and wrong often enough that the only way to correct
it used to be compiling, loading the map in game, listening, and editing a
command line. This package is where the guess gets overridden instead, against
the same library the command line compiles with, so a session here and a
command later produce the same map.

Nothing in here is imported by the layers below it, and nothing in here is
imported at module scope by the command line -- the browser engine it needs is
declared for Windows only, and `snapmap-midi compile` has to keep working
everywhere else.
"""

from __future__ import annotations
