"""Generate the frozen MIDI input fixture for the compiler golden test.

Run once. The output is committed; the compiler test reads the bytes rather
than rebuilding them, so the golden output cannot drift with the MIDI writer
version.

Note content matches the recipe the compiler test used to build in-process:
a decaying piano note on channel 0, two sustained string notes on channel 1
(one of them in the low register, to exercise the pitch split), and one drum
hit on channel 9.

    python tests/gen_tiny_midi.py
"""

from pathlib import Path

import mido

OUT = Path(__file__).resolve().parent / "fixtures" / "tiny.mid"


def build() -> mido.MidiFile:
    mid = mido.MidiFile()
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.Message("program_change", channel=0, program=0, time=0))  # piano, decaying
    tr.append(mido.Message("program_change", channel=1, program=40, time=0))  # strings, sustained
    tr.append(mido.Message("note_on", channel=0, note=60, velocity=64, time=0))
    tr.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=480))
    tr.append(mido.Message("note_on", channel=1, note=67, velocity=64, time=0))
    tr.append(mido.Message("note_off", channel=1, note=67, velocity=0, time=480))
    tr.append(mido.Message("note_on", channel=1, note=48, velocity=64, time=0))  # low register
    tr.append(mido.Message("note_off", channel=1, note=48, velocity=0, time=240))
    tr.append(mido.Message("note_on", channel=9, note=36, velocity=100, time=0))
    tr.append(mido.Message("note_off", channel=9, note=36, velocity=0, time=120))
    return mid


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    build().save(str(OUT))
    print("wrote {} ({} bytes)".format(OUT, OUT.stat().st_size))
