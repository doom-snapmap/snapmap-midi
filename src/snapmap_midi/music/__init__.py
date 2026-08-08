"""The music domain — MIDI in, an arrangement out.

This layer is about notes: pairing them, deciding what each one should sound
like, and deciding how many may sound at once. It reaches down into `sound` to
resolve a pitch to an actual sound name, but nothing here writes a map.

    midi        parse a MIDI file into paired notes
    gm          the General MIDI translation tables
    voices      voice allocation and polyphony thinning
"""

from __future__ import annotations
