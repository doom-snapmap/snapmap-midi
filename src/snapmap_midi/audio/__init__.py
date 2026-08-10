"""The game's audio, read out of the user's own install.

Everything below is about hearing what a map will sound like before loading it.
Nothing in it is needed to build a map -- the compiler, the palette and the
whole export path work with no game installed at all -- which is why this is a
layer on top rather than a dependency underneath.

    wwise       the soundbank format: a sound name to decoded PCM samples
    locate      finding the install, without asking anybody where it is
    library     the extracted-audio cache, and the one-time extraction

It sits above `sound`, because it needs the palette to know which sounds are
worth extracting, and only the product surfaces -- the window and the explicit
`extract` command -- reach it. `music` neither needs it nor may reach it: a
compile that quietly depended on a game install would put the tool back where
it started, useless until someone went digging.

`wwise` alone imports nothing internal. It is a file-format reader that happens
to live here, and keeping it standalone is what would make promoting it out a
directory move.
"""

from __future__ import annotations
