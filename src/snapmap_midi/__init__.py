"""snapmap-midi — compile a standard MIDI file into a playable in-game music map.

The compiler pairs note-on and note-off events, maps each note's instrument
program to a sound family and its pitch to the nearest sound in the palette,
then schedules the result as timed events on a timeline entity. Notes whose
samples decay on their own play as one-shots; notes that hold at full volume
play on dedicated speaker voices so they can actually be stopped when the note
ends.

Layout is by subsystem, stacked lowest first. Each layer may use the ones
below it and never the ones above, which is what keeps any single layer usable
on its own:

    rawmap/     the map authoring core -- codec, values, documents, templates
    sound/      the game's sound surface -- palette, event calls, timelines
    music/      the MIDI domain -- parsing, General MIDI tables, voicing

On top of those sits the product surface:

    compile     orchestration: a MIDI file to a finished map
    settings    one document holding every choice a compile makes
    ui/         the MIDI workstation: assign sounds, preview, tune, export
    cli         the command-line entry point
    paths       optional overrides for the data the product normally ships
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.3.7"
