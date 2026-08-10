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
from pathlib import Path
from threading import RLock

from snapmap_midi import paths
from snapmap_midi import settings as settings_module
from snapmap_midi.compile import compile_to_rawmap
from snapmap_midi.music import analysis
from snapmap_midi.sound import palette

#: The axis every ruler row is drawn against: MIDI's own range, which is also
#: the widest any family reaches. Fixed rather than derived from the file,
#: because rows are only comparable while they share one axis -- an axis taken
#: from the notes present would move when a channel was muted, and the same part
#: would sit somewhere else on the strip for a reason that has nothing to do
#: with it.
_AXIS = (0, 127)

#: How many channels may carry their own range sentence before they collapse
#: into one. Sixteen near-identical lines in a status bar is not information,
#: and the per-row ruler already carries the detail.
_RANGE_LINES = 3


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
        entry = self._doc["channels"].get(str(channel.channel))
        chosen = entry.get("family") if entry else None
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
                span = None if family is None else palette.family_range(family, self._note_index)
                rulers[str(channel.channel)] = analysis.ruler_segments(channel, span, _AXIS)
            return rulers

    # ---- warnings ----

    def _muted(self) -> set:
        return {int(c) for c, entry in self._doc["channels"].items() if entry["muted"]}

    def _unmapped_drum_keys(self) -> list:
        """Percussion keys the file plays that nothing has a sound for.

        `DRUM_MAP` drops the exotic keys rather than guessing at them, so this is
        the ordinary way a file loses notes. Keys the user has already given a
        sound are excluded, or the warning would go on naming a row that has
        been dealt with.
        """
        given = {int(key) for key in self._doc["drum_keys"]}
        keys = set()
        for channel in self._analysis.channels:
            keys.update(
                key
                for key, shader in channel.drum_keys.items()
                if shader is None and key not in given
            )
        return sorted(keys)

    def _range_warnings(self, muted) -> list:
        """One sentence per channel whose family cannot reach its notes.

        Muted channels are skipped: reporting that a channel somebody just
        silenced cannot reach its notes is noise about a decision already made.

        Past `_RANGE_LINES` affected channels the sentences collapse into the
        worst one plus a count. Ranked by how many notes are actually displaced
        rather than by proportion, because that is what a listener hears; a
        channel with no overlap at all displaces every note it has and sorts
        itself to the top without needing a special case.
        """
        lines = []
        for channel in self._analysis.channels:
            if channel.is_drums or channel.channel in muted or not channel.pitches:
                continue
            family = self._family_for(channel)
            span = None if family is None else palette.family_range(family, self._note_index)
            if span is None:
                continue
            low, high = span
            if channel.highest < low or channel.lowest > high:
                lines.append(
                    (
                        channel.notes,
                        "Channel %d (%s) shares no note with %s at all. Every note is "
                        "transposed." % (channel.channel, channel.program_name, family),
                    )
                )
                continue
            outside = analysis.notes_outside(channel, span)
            if outside:
                lines.append(
                    (
                        outside,
                        "Channel %d (%s) plays %d-%d. %s only reaches %d-%d, so %d of its %d "
                        "notes move to another octave, or to the nearest pitch the family "
                        "has."
                        % (
                            channel.channel,
                            channel.program_name,
                            channel.lowest,
                            channel.highest,
                            family,
                            low,
                            high,
                            outside,
                            channel.notes,
                        ),
                    )
                )
        if len(lines) <= _RANGE_LINES:
            return [text for _, text in lines]
        # `max` keeps the first of a tie, and these were built in channel order,
        # so two equally bad channels resolve to the lower number rather than to
        # whichever the dict happened to yield.
        worst = max(lines, key=lambda line: line[0])
        return [
            "%s %d other channels have notes their family cannot reach -- each row's ruler "
            "shows where." % (worst[1], len(lines) - 1)
        ]

    def _warnings(self, stats) -> list:
        """Plain-language problems, each with the number that decides whether to
        care and the lever that changes it.

        The thresholds are `docs/limits.md`'s, not invented here. That doc gives
        one practical target -- notes held under about a second cut reliably --
        and states that decaying one-shots are immune because they hold no
        emitter slot, so only the sustained path is exposed. An earlier draft
        warned on total event count, which is dominated by exactly those immune
        one-shots: it fired hardest on a drum-heavy song that cannot reach the
        limit and stayed silent on the three-voice pad that will. The two
        quantities below are the ones that doc actually names.

        Ordered by what each costs a listener. Silence first, then notes that do
        not play, then notes that play at the wrong pitch, then the smearing the
        emitter limit produces, then passages the compiler thinned on purpose.
        """
        channels = self._analysis.channels if self._analysis is not None else []
        muted = self._muted()
        warnings = []

        if channels and all(channel.channel in muted for channel in channels):
            warnings.append("Nothing will play: all %d channels are muted." % len(channels))
        elif not stats["notes"]:
            warnings.append("Nothing will play: no note in this file has a sound in the palette.")

        if stats["dropped"]:
            keys = self._unmapped_drum_keys() if channels else []
            text = "%d notes have no sound and will not play." % stats["dropped"]
            if keys:
                # Named only when there are keys to name. Percussion is very
                # nearly the only way a note reaches this count -- every family
                # the picker offers has a sound for some pitch -- but claiming
                # unmapped drum keys where there are none would send the reader
                # to a tab with nothing on it to fix.
                text += " Drum keys %s are unmapped -- give them sounds on the Drums tab." % (
                    ", ".join(str(key) for key in keys)
                )
            warnings.append(text)

        warnings.extend(self._range_warnings(muted))

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
            # The statistics carry the worst layer's voice count and not which
            # layer it was, so the sentence says "the busiest channel" rather
            # than naming one it cannot know. A layer that needs exactly the cap
            # and a layer that was thinned look identical from here; the warning
            # fires on both, because raising the lever costs nothing and settles
            # which one it was.
            warnings.append(
                "The busiest channel used all %d speakers, so its densest passages were "
                "thinned. Raise max speakers, or cap the polyphony." % stats["max_speakers"]
            )
        return warnings
