"""General MIDI mapping tables — program to family, percussion key to sound.

A MIDI file names instruments by program number, not by the sounds this game
actually has. These tables are the translation layer, and they are a taste
call as much as a technical one: several distinct programs collapse onto one
family because the palette has nothing closer.

Families split into two groups that are scheduled completely differently.
DECAYING samples fade on their own and are fired and forgotten. SUSTAINED
samples hold at full volume until something stops them, so they need a
dedicated voice and an explicit note-off. Getting a family into the wrong
group is audible: a sustained note with no note-off rings its whole sample.
"""

from __future__ import annotations

#: Families whose samples hold at full volume and must be stopped explicitly.
SUSTAINED = {
    "ins_violin",
    "ins_horns",
    "ins_trumpet",
    "ins_flute",
    "ins_sine",
    "ins_square",
    "ins_tri",
    "ins_pulse",
    "ins_string",
}

#: MIDI reserves channel 10 (zero-indexed 9) for percussion.
DRUM_CHANNEL = 9


def gm_to_family(program: int) -> str:
    """Map a General MIDI program number to a palette family."""
    p = program
    if p < 8:
        return "ins_piano"
    if p < 16:
        return "ins_marimba"
    if p < 24:
        return "ins_horns"
    if p < 32:
        return "ins_guitar"
    if p < 40:
        return "ins_pulse"
    if p < 56:
        return "ins_violin"
    if p < 64:
        return "ins_trumpet"
    if p < 80:
        return "ins_flute"
    if p < 88:
        return "ins_sine"
    if p < 96:
        return "ins_violin"
    if p < 104:
        return "ins_sine"
    if p < 120:
        return "ins_guitar"
    return "ins_marimba"


#: Percussion key to sound. Covers the common kit; exotic keys are dropped
#: rather than guessed at, and land in the compile statistics as `dropped`.
DRUM_MAP = {
    35: "play_noise_kick_tight",
    36: "play_noise_kick_tight",
    37: "play_sfx_ben_snap_01",
    38: "play_sfx_ben_snare_01",
    40: "play_sfx_ben_snare_01",
    39: "play_noise_clap",
    41: "play_sfx_ben_tom_low_01",
    43: "play_sfx_ben_tom_low_01",
    42: "play_noise_hat",
    44: "play_noise_hat",
    45: "play_sfx_ben_tom_mid_01",
    47: "play_sfx_ben_tom_mid_01",
    46: "play_sfx_ben_hihat_open_01",
    48: "play_sfx_ben_tom_high_01",
    50: "play_sfx_ben_tom_high_01",
    49: "play_noise_crash",
    57: "play_noise_crash",
    51: "play_noise_ride",
    59: "play_noise_ride",
    75: "play_clave1",
    76: "play_wood_block_01",
    77: "play_wood_block_01",
}
