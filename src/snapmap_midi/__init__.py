"""snapmap-midi — compile a standard MIDI file into a playable in-game music map.

The compiler pairs note-on and note-off events, maps each note's instrument
program to a sound family and its pitch to the nearest sound in the palette,
then schedules the result as timed events on a timeline entity. Notes whose
samples decay on their own play as one-shots; notes that hold at full volume
play on dedicated speaker voices so they can actually be stopped when the note
ends.

Layout:
    rawmap/     the map authoring core -- codec, value builders, documents
    palette     the sound palette index and pitch resolution
    gm          instrument-program and percussion mapping tables
    midi        MIDI parsing and note pairing
    voices      voice allocation and polyphony thinning
    events      event-call construction
    timeline    the reusable timeline authoring API
    compile     orchestration: notes to a finished map
    audition    build a map that plays candidate sounds in sequence
    paths       resolve game-derived inputs the product may not bundle
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
