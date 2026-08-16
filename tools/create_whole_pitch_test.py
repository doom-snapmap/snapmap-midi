"""Create a minimal integer-semitone test for SnapMap ``fadePitch``."""

from __future__ import annotations

import argparse
from pathlib import Path

import mido


TICKS_PER_BEAT = 480
NOTE_LENGTH = 360
TEST_NOTES = (60, 62, 64, 65, 67, 69, 71, 72)


def build(path: Path) -> None:
    song = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)

    conductor = mido.MidiTrack()
    conductor.append(mido.MetaMessage("track_name", name="Whole-semitone pitch test"))
    conductor.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(60)))
    conductor.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
    conductor.append(mido.MetaMessage("end_of_track", time=0))
    song.tracks.append(conductor)

    notes = mido.MidiTrack()
    notes.append(mido.MetaMessage("track_name", name="Whole semitones C4-C5"))
    notes.append(mido.Message("program_change", channel=0, program=0, time=0))
    for index, note in enumerate(TEST_NOTES):
        notes.append(
            mido.Message(
                "note_on",
                channel=0,
                note=note,
                velocity=127,
                time=0 if index == 0 else TICKS_PER_BEAT - NOTE_LENGTH,
            )
        )
        notes.append(
            mido.Message(
                "note_off",
                channel=0,
                note=note,
                velocity=0,
                time=NOTE_LENGTH,
            )
        )
    notes.append(mido.MetaMessage("end_of_track", time=0))
    song.tracks.append(notes)

    path.parent.mkdir(parents=True, exist_ok=True)
    song.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "examples"
        / "whole_semitone_pitch.mid",
    )
    args = parser.parse_args()
    build(args.output)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
