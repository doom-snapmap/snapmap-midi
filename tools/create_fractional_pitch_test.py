"""Create the small A/B MIDI used to test fractional SnapMap pitch values."""

from __future__ import annotations

import argparse
from pathlib import Path

import mido

TICKS_PER_BEAT = 480
NOTE_LENGTH = 360
TEST_NOTES = (60, 62, 64, 65, 67, 69, 71, 72)


def add_notes(track: mido.MidiTrack, channel: int, first_beat: int) -> None:
    """Write every other beat so the two tracks answer one another."""

    last_tick = 0
    for index, note in enumerate(TEST_NOTES):
        start = (first_beat + index * 2) * TICKS_PER_BEAT
        track.append(
            mido.Message(
                "note_on",
                channel=channel,
                note=note,
                velocity=110,
                time=start - last_tick,
            )
        )
        track.append(
            mido.Message(
                "note_off",
                channel=channel,
                note=note,
                velocity=0,
                time=NOTE_LENGTH,
            )
        )
        last_tick = start + NOTE_LENGTH


def build(path: Path) -> None:
    song = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)

    conductor = mido.MidiTrack()
    conductor.append(mido.MetaMessage("track_name", name="Fractional pitch A/B test"))
    conductor.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120)))
    conductor.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
    conductor.append(mido.MetaMessage("end_of_track", time=0))
    song.tracks.append(conductor)

    whole = mido.MidiTrack()
    whole.append(mido.MetaMessage("track_name", name="A - Whole semitones"))
    whole.append(mido.Message("program_change", channel=0, program=0, time=0))
    add_notes(whole, channel=0, first_beat=0)
    whole.append(mido.MetaMessage("end_of_track", time=0))
    song.tracks.append(whole)

    cents = mido.MidiTrack()
    cents.append(mido.MetaMessage("track_name", name="B - Plus 50 cents"))
    cents.append(mido.Message("program_change", channel=1, program=0, time=0))
    add_notes(cents, channel=1, first_beat=1)
    cents.append(mido.MetaMessage("end_of_track", time=0))
    song.tracks.append(cents)

    path.parent.mkdir(parents=True, exist_ok=True)
    song.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "examples" / "fractional_pitch_ab.mid",
    )
    args = parser.parse_args()
    build(args.output)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
