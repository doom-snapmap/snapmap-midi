"""What the window is looking at: one song, one document, and one compile of them.

Every control in the window is a patch to a settings document, and every number
beside those controls comes from compiling that document. Both live here, in one
object, so they cannot disagree: the rulers, the status line and the exported
bytes are three readings of the same state at the same moment rather than three
readings taken while somebody was still typing.

The state is behind a lock because pywebview answers each Javascript call on its
own thread. Two dropdowns changed in quick succession are two threads inside
`apply`, and an unguarded read-modify-write loses one of the changes with
nothing anywhere to show that it happened -- the control snaps back a beat later
and looks like a rendering glitch.

The palette's note index is built once, here, and handed to every compile.
Dropdowns fire immediately rather than on a debounce, so a re-parse per change
is a re-parse per click.

Nothing in here writes to the window and nothing imports pywebview. The bridge
above it turns these answers into `{"ok": ...}` payloads and catches what they
raise; keeping that split is what lets every rule in this file be tested with no
browser engine present.
"""

from __future__ import annotations

import copy
import math
from fractions import Fraction
from pathlib import Path
from threading import RLock

from snapmap_midi import paths
from snapmap_midi import settings as settings_module
from snapmap_midi.compile import (
    compile_to_rawmap,
    installed_event_duration_ms,
    installed_event_is_looping,
)
from snapmap_midi.music import analysis
from snapmap_midi.music.midi import parse_notes
from snapmap_midi.music.voices import (
    allocate_voices,
    prepare_voice_layers,
    thin_polyphony,
)
from snapmap_midi.sound import palette

#: The axis every ruler row is drawn against: MIDI's own range, which is also
#: the widest any family reaches. Fixed rather than derived from the file,
#: because rows are only comparable while they share one axis -- an axis taken
#: from the notes present would move when a channel was muted, and the same part
#: would sit somewhere else on the strip for a reason that has nothing to do
#: with it.
_AXIS = (0, 127)

#: How much of a bar past the last bar line is read as padding rather than as
#: music. Editors routinely write End-of-Track a handful of ticks past the final
#: bar, and a bare ceiling turns one stray tick into a whole empty measure on the
#: ruler -- 2,000 ms of dead timeline bought with 1/1920th of a bar. A 32nd note
#: is the smallest division the roll draws, so content shorter than that is not
#: content. A genuinely incomplete final measure is far larger than this and
#: still earns its bar.
_GRID_PADDING_BARS = Fraction(1, 32)


def _timing_manifest(mid_path) -> dict:
    """Return the source MIDI clock as absolute tick/time change points.

    The piano roll is read-only, but its ruler still has to speak in bars and
    note values rather than inventing evenly spaced seconds.  A compact tempo
    map lets the browser place those musical divisions accurately even when a
    file changes tempo, without asking it to parse MIDI itself.

    MIDI defines 120 BPM and 4/4 when a file omits the corresponding metadata.
    Markers at the same tick replace one another so a normal tick-zero tempo or
    signature does not leave a redundant default entry in the payload.
    """
    import mido

    mid = mido.MidiFile(str(mid_path), clip=True)
    ticks_per_beat = int(mid.ticks_per_beat)
    tick = 0
    elapsed_s = 0.0
    tempo = 500_000
    tempos = [{"tick": 0, "time_ms": 0.0, "tempo": tempo}]
    signatures = [{"tick": 0, "time_ms": 0.0, "numerator": 4, "denominator": 4}]

    def record(markers, marker):
        if markers[-1]["tick"] == marker["tick"]:
            markers[-1] = marker
        else:
            markers.append(marker)

    for message in mido.merge_tracks(mid.tracks):
        delta = int(message.time)
        elapsed_s += mido.tick2second(delta, ticks_per_beat, tempo)
        tick += delta
        time_ms = round(elapsed_s * 1000, 6)
        if message.type == "set_tempo":
            tempo = int(message.tempo)
            record(tempos, {"tick": tick, "time_ms": time_ms, "tempo": tempo})
        elif message.type == "time_signature":
            record(
                signatures,
                {
                    "tick": tick,
                    "time_ms": time_ms,
                    "numerator": int(message.numerator),
                    "denominator": int(message.denominator),
                },
            )

    source_duration_ticks = tick
    signature = signatures[-1]
    ticks_per_bar = Fraction(
        ticks_per_beat * 4 * int(signature["numerator"]),
        int(signature["denominator"]),
    )
    ticks_since_signature = max(0, source_duration_ticks - int(signature["tick"]))
    raw_bars = Fraction(ticks_since_signature, 1) / ticks_per_bar
    completed_bars = math.ceil(raw_bars - _GRID_PADDING_BARS) if raw_bars else 0
    # Absorbing the padding must never absorb the music with it: any content at
    # all occupies at least the measure it started in.
    if ticks_since_signature and completed_bars < 1:
        completed_bars = 1
    grid_duration_ticks = max(
        source_duration_ticks,
        int(math.ceil(Fraction(int(signature["tick"]), 1) + completed_bars * ticks_per_bar)),
    )

    def time_at_tick(target_tick):
        marker = tempos[0]
        for candidate in tempos[1:]:
            if int(candidate["tick"]) > target_tick:
                break
            marker = candidate
        return round(
            float(marker["time_ms"])
            + (target_tick - int(marker["tick"])) * int(marker["tempo"]) / 1000 / ticks_per_beat,
            6,
        )

    return {
        "ticks_per_beat": ticks_per_beat,
        # Keep the file boundary and the workstation boundary separate. Some
        # DAWs write End-of-Track at the final note even when their clip still
        # has an empty remainder. The source value remains available for exact
        # MIDI accounting; the padded value gives the read-only piano roll a
        # complete final measure without inventing another note or stop event.
        "duration_ticks": source_duration_ticks,
        "source_duration_ms": time_at_tick(source_duration_ticks),
        "grid_duration_ticks": grid_duration_ticks,
        "grid_duration_ms": time_at_tick(grid_duration_ticks),
        "tempo_changes": tempos,
        "time_signatures": signatures,
    }


def _advice(destination: Path) -> str:
    """How to reach a map that has just been written to `destination`.

    The three cases are genuinely different and used to be two. Writing to the
    working directory because there is no loader folder is NOT "it landed where
    the loader reads", and saying so is the same quiet wrong answer the retired
    `--out` flag produced -- a file that looks finished and is not.
    """
    if paths.destination_is_loadable(destination):
        return "load it with `sh_rawmaps_on` in the console, then open any map"
    if paths.loader_dir() is None:
        return (
            "no loader folder on this platform -- copy it to the game machine's "
            "%%LOCALAPPDATA%%\\%s\\%s to play it" % (paths.LOADER_DIR_NAME, paths.RAWMAP_NAME)
        )
    return "the loader only reads %s; move it there to play it" % paths.rawmap_destination()


class Session:
    """One open song, the document that says what to do with it, and the numbers.

    Constructed with a song, a settings document, both, or neither -- the window
    opens on whatever the command line was given, including nothing at all.

    Opening a song at construction is not the same act as opening one later,
    and the difference is deliberate. `load` is the Open button: there is an
    earlier song whose instruments must not follow the user into the next file.
    The constructor has no earlier song, so it keeps everything the settings
    document brought with it -- otherwise `snapmap-midi ui song.mid --settings
    s.json`, which is one instruction, would throw away half of itself.
    """

    def __init__(self, midi=None, settings_path=None):
        """Open on a song, a settings document, or nothing.

        A song named here must be readable and raises if it is not: the caller
        just said which file, and a window that opened blank after being handed
        a path would be reporting nothing about the one thing it was told.

        A song REMEMBERED by a settings document is different. That path was
        recorded in an earlier session and the file may since have been renamed,
        moved, or handed to somebody else. The document is an afternoon's tuning
        and the path is one line of it, so a song that cannot be read leaves the
        document intact and the analysis empty. The guard is deliberately broad:
        what matters is that the settings survive, and a file can fail to be a
        MIDI file in as many ways as a file can be wrong.
        """
        self._lock = RLock()
        self._note_index = palette.build_note_index()
        self._analysis = None
        if settings_path is None:
            self._doc = settings_module.defaults()
        else:
            self._doc = settings_module.load(settings_path)
        if midi is not None:
            self._doc = settings_module.merge(self._doc, {"midi": str(midi)})
        if self._doc["midi"]:
            try:
                self._analysis = self._analyze()
            except Exception:
                if midi is not None:
                    raise

    # ---- the song ----

    def _analyze(self):
        """Read the current song under the current drums mode.

        Both come from the document, so the analysis the window draws and the
        compile the window exports are always answering the same question about
        the same file.
        """
        return analysis.analyze(self._doc["midi"], drums=self._doc["drums"])

    def load(self, midi_path) -> dict:
        """Open a song, forgetting the last one's instruments and keeping the setup.

        `channels` and `drum_keys` are cleared. They are answers about a
        particular arrangement, and channel numbers collide where parts do not:
        the marimba somebody chose for channel 3 would follow them into the next
        file and silently retimbre a part they have never looked at.

        `tuning`, `button` and `out_dir` stay. Those are about the user's setup
        rather than the song, and clearing them would make every new file a
        fresh argument with the same machine.

        The file is read before anything is stored, so a path that turns out not
        to be there leaves the session showing the song it already had rather
        than a half-opened one it never read.
        """
        with self._lock:
            midi_path = str(midi_path)
            candidate = dict(self._doc)
            candidate["midi"] = midi_path
            candidate["channels"] = {}
            candidate["notes"] = {}
            candidate["drum_keys"] = {}
            candidate = settings_module.validate(candidate)

            fresh = analysis.analyze(midi_path, drums=candidate["drums"])
            self._doc = candidate
            self._analysis = fresh
            return analysis.as_dict(fresh)

    def analysis_dict(self) -> dict | None:
        """The open song as JSON, or None when there is no song open.

        None rather than an empty analysis: "no file yet" and "a file with
        nothing in it" are different states and the window says different things
        about them.
        """
        with self._lock:
            return None if self._analysis is None else analysis.as_dict(self._analysis)

    def channel_info(self, channel):
        """The analyzed part, named either by its key or by a bare channel.

        A part key -- "1:0" -- names exactly one part. A bare channel number is
        still accepted because it is what every existing caller sends and what a
        user means on the ordinary file where a channel holds one part; it
        resolves to the first part on that channel, which on such a file is the
        only one.
        """

        if self._analysis is None:
            raise ValueError("no song is open -- open a MIDI file first")

        info = None
        if isinstance(channel, str) and ":" in channel:
            info = next((c for c in self._analysis.channels if c.key == channel), None)
            if info is None:
                raise ValueError("no part %s in this song" % channel)
        else:
            if isinstance(channel, bool):
                raise ValueError("a MIDI channel from 0 to 15 is required")
            try:
                number = int(channel)
                valid = float(channel) == number and 0 <= number <= 15
            except (TypeError, ValueError):
                valid = False
            if not valid:
                raise ValueError("a MIDI channel from 0 to 15 is required")
            info = next((c for c in self._analysis.channels if c.channel == number), None)
            if info is None:
                raise ValueError("channel %d has no notes to anchor" % number)

        if info.lowest is None or info.highest is None:
            raise ValueError("%s has no notes to anchor" % info.key)
        return info

    # ---- the document ----

    def settings(self) -> dict:
        """The whole document, as a copy.

        A copy because the bridge hands this straight to Javascript and because
        it is the state every other method reads. A caller that edited the
        session's own dict would change what the next compile does without
        passing through `validate`, and sharing one mutable document across
        threads defeats the lock that guards it.
        """
        with self._lock:
            return copy.deepcopy(self._doc)

    def apply(self, patch) -> dict:
        """Merge a patch into the document, and re-read the file if it has to.

        Validation runs before anything is stored, so a refused patch leaves the
        session exactly as it was. That matters more here than in a file: the
        window shows one state and has no undo, so a half-applied patch is a
        window describing settings nobody chose.

        The file is read again when the drums mode changes, because that switch
        decides whether channel 9 is a kit. Without it the row goes on offering a
        family dropdown for a channel the compiler has started routing through
        `DRUM_MAP`, and the window describes an instrument nothing plays. The
        song path is watched for the same reason, though the window changes that
        through `load`.
        """
        with self._lock:
            merged = settings_module.merge(self._doc, patch)
            reread = (merged["drums"], merged["midi"]) != (
                self._doc["drums"],
                self._doc["midi"],
            )
            previous = self._doc
            self._doc = merged
            if reread and self._analysis is not None:
                try:
                    self._analysis = self._analyze()
                except Exception:
                    self._doc = previous
                    raise
            return copy.deepcopy(merged)

    # ---- compiling ----

    def _baseline_bytes(self) -> bytes | None:
        """The saved map to add the song to, or None to author a blank one.

        An explicitly chosen baseline wins over a configured one, which is the
        same order the command line uses. Neither is the ordinary case.
        """
        chosen = self._doc["baseline"]
        path = Path(chosen) if chosen else paths.baseline_map()
        return path.read_bytes() if path else None

    def compile(self):
        """Compile the document as it stands: finished bytes and a statistics summary.

        Held under the lock for its whole duration rather than compiled from a
        snapshot. A compile that read the family list before a change and the
        mute set after it would produce a map matching neither, and the report
        printed beside it would describe a third thing. Serialising is the
        cheaper mistake: the window's Javascript already stamps each call it
        makes and drops answers that arrive out of order.
        """
        with self._lock:
            if not self._doc["midi"]:
                raise ValueError("no song is open -- open a MIDI file first")
            return compile_to_rawmap(
                self._doc["midi"],
                self._baseline_bytes(),
                note_index=self._note_index,
                **settings_module.to_compile_kwargs(self._doc),
            )

    def stats(self) -> dict:
        """A dry run: what a compile of this document produces, plus the warnings.

        Really compiles. An estimate that disagreed with the export would be
        discovered in game, and closing that loop is the entire reason this
        window exists.
        """
        with self._lock:
            _, stats = self.compile()
            return self._report(stats)

    def preview_manifest(self) -> dict:
        """The converted notes the workstation transport will actually play.

        This repeats the note preparation portion of ``compile_to_rawmap`` but
        does not author a map. It applies the same channel choices, duration
        caps, polyphony thinning and per-layer voice stealing so the preview is
        a reading of the current conversion rather than a General MIDI render.
        """
        with self._lock:
            if not self._doc["midi"]:
                raise ValueError("no song is open -- open a MIDI file first")
            levers = settings_module.to_compile_kwargs(self._doc)
            notes, _ = parse_notes(
                self._doc["midi"],
                drums=levers["drums"],
                decaying_families=levers["decaying_families"],
                channel_families=levers["channel_families"],
                channel_sounds=levers["channel_sounds"],
                note_index=self._note_index,
                channel_mutes=levers["channel_mutes"],
                channel_solos=levers["channel_solos"],
                drum_key_overrides=levers["drum_key_overrides"],
                event_is_looping=installed_event_is_looping,
                channel_pitch_profiles=levers["channel_pitch_profiles"],
                note_overrides=levers["note_overrides"],
                master_volume_db=levers["master_volume_db"],
                include_silent=True,
            )
            audible_notes = [note for note in notes if note.audible]
            decaying = [note for note in audible_notes if not note.sustained]
            sustained = [note for note in audible_notes if note.sustained]
            shared_decaying, _expressive_decaying, layers = prepare_voice_layers(
                decaying,
                sustained,
                cap_sustain_ms=levers["cap_sustain_ms"],
                bass_pitch=levers["bass_pitch"],
                bass_cap_ms=levers["bass_cap_ms"],
                family_caps=levers["family_caps"],
                duration_lookup=installed_event_duration_ms,
            )
            prepared = list(shared_decaying)
            for channel in sorted(layers):
                layer = layers[channel]
                if levers["max_poly"]:
                    layer = thin_polyphony(layer, levers["max_poly"])
                allocate_voices(layer, levers["max_speakers"])

                # Starting a note on a stolen speaker cuts off the note that
                # owned it. Reflect that effective end for both sustains and
                # expressive one-shots so browser preview matches the map.
                by_voice: dict = {}
                for note in layer:
                    by_voice.setdefault(note.voice, []).append(note)
                for voice_notes in by_voice.values():
                    voice_notes.sort(key=lambda note: note.start)
                    for index, note in enumerate(voice_notes[:-1]):
                        following = voice_notes[index + 1]
                        effective_end = (
                            note.end if note.sustained else getattr(note, "voice_end", note.end)
                        )
                        if following.start <= effective_end:
                            note.preview_cut = True
                        if following.start < effective_end:
                            note.preview_end = following.start
                prepared.extend(layer)

            prepared_ids = {id(note) for note in prepared}

            def _event_payload(note, *, converted):
                return {
                    "id": note.id,
                    "start": note.start,
                    # `end` is when the note stops being heard, after caps and
                    # speaker stealing -- the preview transport schedules from
                    # it. `midi_end` is what the file wrote, which is what the
                    # roll draws, so moving a tuning lever changes the shading
                    # on a block rather than the block.
                    "end": max(
                        note.start,
                        getattr(note, "preview_end", note.end),
                    ),
                    "midi_end": max(note.start, getattr(note, "midi_end", note.end)),
                    "sound": note.shader,
                    "channel": note.chan,
                    # The part this note belongs to, matching `ChannelInfo.key`.
                    # Without it the roll sees only a channel, so three parts
                    # written to channel 0 are one undifferentiated mass and
                    # nothing can select, dim, or mute one of them.
                    "part": "%d:%d" % (getattr(note, "track", 0), note.chan),
                    "track": getattr(note, "track", 0),
                    "source_pitch": note.source_pitch,
                    "pitch": note.source_pitch,
                    "velocity": note.velocity,
                    "family": note.fam,
                    "sustained": note.sustained,
                    "cut": bool(getattr(note, "preview_cut", False)),
                    "audible": bool(note.audible),
                    "muted": bool(note.muted),
                    "solo_excluded": bool(note.solo_excluded),
                    "converted": bool(converted),
                    "pitch_follow": note.pitch_follow,
                    "root_pitch": note.profile_root_pitch,
                    "applied_root_pitch": note.root_pitch,
                    "root_confidence": note.root_confidence,
                    "root_source": note.root_source,
                    "pitch_offset": note.pitch_offset,
                    "automatic_pitch": note.automatic_pitch,
                    "requested_pitch": note.requested_pitch,
                    "pitch_modifier": note.pitch_modifier,
                    "pitch_limited": note.pitch_limited,
                    "playback_rate": note.playback_rate,
                    "velocity_db": note.velocity_db,
                    "volume_trim_db": note.volume_trim_db,
                    "note_volume_db": note.note_volume_db,
                    "master_volume_db": note.master_volume_db,
                    "requested_volume_db": note.requested_volume_db,
                    "volume_db": note.volume_db,
                    "volume_limited": note.volume_limited,
                    "voice_end": getattr(note, "voice_end", None),
                }

            def _event_order(note):
                return (note.start, note.chan, note.source_pitch, note.id)

            events = [
                _event_payload(note, converted=True) for note in sorted(prepared, key=_event_order)
            ]
            display_events = [
                _event_payload(note, converted=id(note) in prepared_ids)
                for note in sorted(notes, key=_event_order)
            ]
            timing = _timing_manifest(self._doc["midi"])
            duration_ms = int(round(timing["grid_duration_ms"]))
            # Both boundaries, so the surface never shrinks under a tuning lever:
            # `midi_end` is what the roll draws, `end` is what playback reaches.
            if display_events:
                duration_ms = max(duration_ms, max(e["midi_end"] for e in display_events))
            if events:
                duration_ms = max(duration_ms, max(event["end"] for event in events))
            return {
                "duration_ms": duration_ms,
                "source_duration_ms": int(round(timing["source_duration_ms"])),
                "events": events,
                "sounds": sorted({event["sound"] for event in events}),
                "display_events": display_events,
                "release_s": levers["release_s"],
                "hard_stop": levers["hard_stop"],
                "timing": timing,
            }

    def _report(self, stats) -> dict:
        report = dict(stats)
        report["warnings"] = self._warnings(stats)
        return report

    def export(self) -> dict:
        """Write the map, and say where it went and what was already there.

        `replaced` is read BEFORE the write, which is the only moment it can be
        read at all. `rawmap.json` is a single global slot -- one filename in one
        folder, because that is the only thing the loader reads -- and a button
        invites repeated use in a way a typed command did not. Overwriting
        somebody's other map without saying so is the failure this answers.
        """
        with self._lock:
            raw, stats = self.compile()
            destination = paths.rawmap_destination(self._doc["out_dir"])
            replaced = destination.exists()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            return {
                "destination": str(destination),
                "advice": _advice(destination),
                "replaced": replaced,
                "stats": self._report(stats),
            }

    # ---- the rulers ----

    def _family_for(self, channel):
        """The family a channel will actually be compiled with.

        The chosen one if there is one, the automatic one otherwise -- and the
        automatic one is what makes this worth a method. A ruler or a warning
        that only spoke about families somebody had picked would say nothing at
        all about a file nobody had touched yet, which is every file at the
        moment it opens.
        """
        entry = self._entry_for(channel)
        if entry and entry.get("sound") is not None:
            return None
        chosen = entry.get("family")
        return chosen or channel.auto_family

    def rulers(self) -> dict:
        """Where to draw every channel's notes and its instrument's reach.

        `{channel-as-string: segments}`, and the segments are None for the
        percussion channel, whose lowest and highest are key numbers rather than
        pitches. String keys because this crosses into Javascript, where JSON
        has no integer ones and a reader looking up channel 0 would find nothing
        and draw an empty row without ever raising.
        """
        with self._lock:
            if self._analysis is None:
                return {}
            rulers = {}
            for channel in self._analysis.channels:
                family = self._family_for(channel)
                sample_span = (
                    None if family is None else palette.family_range(family, self._note_index)
                )
                span = (
                    None
                    if sample_span is None
                    else (max(_AXIS[0], sample_span[0] - 24), min(_AXIS[1], sample_span[1] + 24))
                )
                rulers[channel.key] = analysis.ruler_segments(channel, span, _AXIS)
            return rulers

    # ---- warnings ----

    def _parts(self) -> list:
        return list(self._analysis.channels) if self._analysis is not None else []

    def _entry_for(self, info) -> dict:
        """The settings entry governing one part: its own, else its channel's.

        The same precedence the parser applies, restated here because the
        warnings have to describe the arrangement the compile actually
        produces. A bare channel entry is the wildcard covering every part on
        that channel; a part key names one and beats it.
        """
        channels = self._doc["channels"]
        entry = channels.get(info.key)
        if entry is None:
            entry = channels.get(str(info.channel))
        return entry or {}

    def _muted(self) -> set:
        """The keys of parts a mute silences. Keys, not channel numbers: two
        parts can share a channel and only one of them be muted."""
        return {p.key for p in self._parts() if self._entry_for(p).get("muted")}

    def _soloed(self) -> set:
        return {p.key for p in self._parts() if self._entry_for(p).get("soloed")}

    def _inaudible(self) -> set:
        muted = self._muted()
        soloed = self._soloed()
        if not soloed:
            return muted
        return muted | ({p.key for p in self._parts()} - soloed)

    def _who(self, channel: int) -> str:
        """A channel named the way every sentence here names it.

        Both halves earn their place: the number is what the window's row is
        labelled with, so it is how the reader finds the row, and the General
        MIDI program name is what the composer asked for, so it is how they
        recognise the part.
        """
        for info in self._analysis.channels if self._analysis is not None else ():
            if info.channel == channel:
                return "Channel %d (%s)" % (channel, info.program_name)
        return "Channel %d" % channel

    def _layer_voices(self) -> dict:
        """How many voices each channel's sustained layer needs, by channel.

        Rebuilt here because `compile_to_rawmap` reports the worst layer's count
        and not which layer it was. Widening its return to carry that would
        change a surface every other caller depends on, for one sentence in one
        window that only ever needs it when something is already wrong.

        It is a rebuild rather than an estimate: the same parse, the same caps,
        the same thinning and the same allocation, through the same functions
        the compile calls. Two things keep it honest. It runs only while the
        warning is already firing, so the second read of the file is paid on the
        arrangement that has a problem instead of on every dropdown. And the
        answer is checked against the compile's own `peak_voices` before a word
        of it is used, so a compiler that starts thinning differently makes this
        say nothing rather than say something false.
        """
        levers = settings_module.to_compile_kwargs(self._doc)
        notes, _ = parse_notes(
            self._doc["midi"],
            drums=levers["drums"],
            decaying_families=levers["decaying_families"],
            channel_families=levers["channel_families"],
            channel_sounds=levers["channel_sounds"],
            note_index=self._note_index,
            channel_mutes=levers["channel_mutes"],
            channel_solos=levers["channel_solos"],
            drum_key_overrides=levers["drum_key_overrides"],
            event_is_looping=installed_event_is_looping,
            channel_pitch_profiles=levers["channel_pitch_profiles"],
            note_overrides=levers["note_overrides"],
            master_volume_db=levers["master_volume_db"],
        )
        decaying = [note for note in notes if not note.sustained]
        sustained = [note for note in notes if note.sustained]
        _, _, layers = prepare_voice_layers(
            decaying,
            sustained,
            cap_sustain_ms=levers["cap_sustain_ms"],
            bass_pitch=levers["bass_pitch"],
            bass_cap_ms=levers["bass_cap_ms"],
            family_caps=levers["family_caps"],
            duration_lookup=installed_event_duration_ms,
        )
        counts = {}
        for channel, layer in layers.items():
            if levers["max_poly"]:
                layer = thin_polyphony(layer, levers["max_poly"])
            counts[channel] = allocate_voices(layer, levers["max_speakers"])
        return counts

    def _busiest_channel(self, stats):
        """The channel that used every speaker it was allowed, or None if unsure.

        The rebuilt counts are a hypothesis; `peak_voices` is the fact, because
        it comes from the compile the sentence is actually about. When the two
        disagree the name is dropped and the warning says "the busiest channel"
        as it did before there was any way to know. A named channel that was
        never thinned sends somebody off to rewrite a part that was fine, which
        is a worse answer than the vague one.

        Ties resolve to the lower channel number rather than to whichever layer
        the dictionary happened to be built in.
        """
        counts = self._layer_voices()
        if not counts:
            return None
        channel = max(counts, key=lambda number: (counts[number], -number))
        return channel if counts[channel] == stats["peak_voices"] else None

    def _unmapped_drum_keys(self) -> list:
        """Percussion keys the file plays that nothing has a sound for.

        `DRUM_MAP` drops the exotic keys rather than guessing at them, so this is
        the ordinary way a file loses notes. Keys the user has already given a
        sound are excluded, or the warning would go on naming a row that has
        been dealt with.
        """
        given = {int(key) for key in self._doc["drum_keys"]}
        keys = set()
        inaudible = self._inaudible()
        for channel in self._analysis.channels:
            if channel.key in inaudible:
                continue
            keys.update(
                key
                for key, shader in channel.drum_keys.items()
                if shader is None and key not in given
            )
        return sorted(keys)

    @staticmethod
    def _note_name(note: int) -> str:
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        note = int(note)
        return "%s%d" % (names[note % 12], note // 12 - 1)

    def _pitch_limit_warnings(self, stats) -> list[str]:
        details = stats.get("pitch_limit_channels") or []
        if not details:
            return [
                "%d notes need more than SnapMap's -24 to +24 semitone range. "
                "Their pitch is clamped at the nearest engine limit." % stats["pitch_limited"]
            ]
        warnings = []
        for detail in details:
            low = self._note_name(detail["source_low"])
            high = self._note_name(detail["source_high"])
            notes = low if low == high else "%s-%s" % (low, high)
            requested = (
                str(detail["requested_low"])
                if detail["requested_low"] == detail["requested_high"]
                else "%+d to %+d" % (detail["requested_low"], detail["requested_high"])
            )
            warnings.append(
                "%s: %d note%s (%s) request%s %s semitones, outside SnapMap's -24 to +24 "
                "semitone range, so playback and export clamp at the nearest limit. Change the "
                "channel pitch reference or the affected note offsets."
                % (
                    self._who(detail["channel"]),
                    detail["count"],
                    "" if detail["count"] == 1 else "s",
                    notes,
                    "s" if detail["count"] == 1 else "",
                    requested,
                )
            )
        return warnings

    def _warnings(self, stats) -> list:
        """Plain-language problems, each with the number that decides whether to
        care and the lever that changes it.

        The thresholds are `docs/limits.md`'s, not invented here. Neutral
        decaying notes hold no dedicated speaker, while expressive one-shots
        reserve one for their measured or fallback tail and are included in the
        same per-channel peak as sustains. Total event count still says nothing
        about simultaneous pressure: a long sequence can be cheap and one dense
        chord expensive. The quantities below describe duration and peak voice
        use instead.

        Ordered by what each costs a listener. Silence first, then notes that do
        not play, then notes that play at the wrong pitch, then the smearing the
        emitter limit produces, then passages the compiler thinned on purpose.
        """
        channels = self._analysis.channels if self._analysis is not None else []
        muted = self._muted()
        inaudible = self._inaudible()
        warnings = []

        if channels and all(channel.key in muted for channel in channels):
            warnings.append("Nothing will play: all %d channels are muted." % len(channels))
        elif channels and all(channel.key in inaudible for channel in channels):
            warnings.append(
                "Nothing will play: mute and solo settings exclude all %d channels." % len(channels)
            )
        elif not stats["notes"]:
            warnings.append("Nothing will play: no note in this file has a sound in the palette.")
        if stats["dropped"]:
            keys = self._unmapped_drum_keys() if channels else []
            text = "%d notes have no sound and will not play." % stats["dropped"]
            if keys:
                # Named only when there are keys to name. Percussion is very
                # nearly the only way a note reaches this count -- every family
                # the picker offers has a sound for some pitch -- but claiming
                # unmapped percussion keys where there are none would send the
                # reader toward a track that does not need changing.
                text += (
                    " Percussion keys %s are unmapped -- assign that channel an instrument "
                    "set or exact sound, or add per-key drum_keys in the sidecar."
                    % ", ".join(str(key) for key in keys)
                )
            warnings.append(text)

        if stats.get("pitch_limited"):
            warnings.extend(self._pitch_limit_warnings(stats))
        if stats.get("volume_limited"):
            warnings.append(
                "%d notes exceed SnapMap's -60 to +20 dB output range after note and global "
                "volume. Their loudness is clamped." % stats["volume_limited"]
            )

        if stats["long_sustains"]:
            # Counted from the sustained notes before `max_poly` thinning, so
            # with that lever set this is an upper bound rather than a tally.
            # Erring high is the right side for a warning about a risk, and the
            # sentence claims no more than the number can carry.
            warnings.append(
                "%d sustained notes hold longer than a second. Past about a second the engine "
                "may recycle the emitter, and a recycled note rings to the end of its sample "
                "under the next phrase. Cap the sustain, or move the family to the decaying "
                "path." % stats["long_sustains"]
            )

        if stats["peak_voices"] >= stats["max_speakers"]:
            # A layer that needs exactly the cap and a layer that was thinned
            # look identical from here; the warning fires on both, because
            # raising the lever costs nothing and settles which one it was.
            # Which layer it was is rebuilt rather than reported -- see
            # `_busiest_channel` -- and the sentence falls back to the number
            # alone when that rebuild cannot be trusted.
            busiest = self._busiest_channel(stats)
            warnings.append(
                "%s used all %d speakers, so its densest passages were thinned. Raise max "
                "speakers, or cap the polyphony."
                % (
                    "The busiest channel" if busiest is None else self._who(busiest),
                    stats["max_speakers"],
                )
            )
        return warnings
