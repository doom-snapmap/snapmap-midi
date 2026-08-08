"""The game's sound surface — everything that knows about sounds, not music.

This layer speaks the engine's language: sound names, event calls, and the
timeline entity that schedules them. It knows nothing about MIDI, note pairing
or instrument programs, so a caller that wants to place sounds directly can use
it without a MIDI file anywhere in sight.

    palette     which sounds exist, and which one plays a given pitch
    events      the engine event calls: start, stop, fade
    timeline    schedule events onto a timeline entity and trigger them

It sits on `rawmap` and is sat on by `music`. That direction is enforced by a
test, because the whole point of the split is that either side stays usable
without the other.
"""

from __future__ import annotations
