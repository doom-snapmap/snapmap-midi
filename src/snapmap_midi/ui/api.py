"""The Javascript surface: one object whose every method answers.

pywebview hands this object to the window as `window.pywebview.api` and resolves
each call as a promise. An exception raised in here does not arrive in
Javascript as this exception -- it arrives as an opaque Error carrying nothing
worth showing to someone who is looking at a window rather than a console. So
every method catches `Exception` and returns `{"ok": False, "error": ...}`, and
the failure becomes a sentence the window can put in a toast instead of a
rejected promise it can only apologise for.

Nothing here decides how a map is built. `Session` owns that state and every
rule about it; this turns its answers into payloads, resolves local preview
samples through the shared palette, and turns exceptions into sentences.
Keeping that split is what lets the whole bridge be tested with no browser
engine present, and the file dialogs are careful to preserve it: they answer
None before they reach `import webview`, so `tests/test_ui_api.py` runs on a
machine that has never had pywebview installed rather than skipping.

Two things are batched deliberately, and both are about the frame the window
draws rather than about speed. `startup` answers with settings, analysis,
catalog, rulers, statistics, audio readiness and window-frame state together,
because separate promises resolving in separate orders paint partial frames.
And every answer that can change the analysis carries
the analysis with it: the drums switch decides which channel is a kit, and
opening a song changes which drum keys exist at all, so a window left to notice
either for itself is a window showing the last song's keys.

The settings sidecar is written here rather than in `Session`, because it is
part of what the Export BUTTON means and not part of what a compile is. The
command line writes maps and never a settings file; the window's export writes
both, because a window is where the choices are made and closing it used to
lose every one of them.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from pathlib import Path

from snapmap_midi import settings as settings_module
from snapmap_midi.music.gm import gm_drum_name
from snapmap_midi.sound import palette
from snapmap_midi.ui.session import Session

#: What the Open dialog will show. The second entry is not optional politeness:
#: a MIDI file with any other extension is ordinary, and a picker that can only
#: see `.mid` is a picker that cannot open the user's file at all.
_MIDI_TYPES = ("MIDI files (*.mid;*.midi)", "All files (*.*)")

#: A saved map is JSON, and the loader's own is literally `rawmap.json`.
_MAP_TYPES = ("Saved maps (*.json)", "All files (*.*)")


def _fail(exc: Exception) -> dict:
    """A failure as a sentence, because a window has nowhere to put a traceback.

    `str(exc)` rather than the class name: `SettingsError` says nothing, and the
    message it carries names the setting and what is wrong with it. An
    exception whose message is empty falls back to the class name, which is at
    least something to search for -- a toast with no text in it reads as the
    window flickering and nothing having happened.
    """
    return {"ok": False, "error": str(exc) or exc.__class__.__name__}


def _cancelled() -> dict:
    """A dialog that was dismissed, which is not a failure and not an error.

    `ok` is False because nothing was chosen and the window must not treat the
    answer as a new state. There is deliberately no `error`: the window toasts
    that key when it is present, and telling somebody that cancelling failed is
    the sort of message that teaches people to ignore messages.
    """
    return {"ok": False, "cancelled": True}


def _label(sound: str, entry) -> str:
    """One line for a drum row: the sound's name, then what it sounds like.

    `sound_labels()` is nested by category and each label is a record --
    `{heard, role, confirmed}` -- so both the flattening and the sentence have
    to happen somewhere. Handed over as stored, the record reaches a `<select>`
    as `[object Object]` in every row that has one.

    The name comes first because the name is what the settings document holds
    and what someone reading that document searches for. The ear-label comes
    second because the names lie: `play_noise_crash` is a shaker and
    `play_noise_tom` is a knock on a wooden door, so a picker showing only names
    sends people to the tom for a tom.
    """
    if not isinstance(entry, Mapping):
        return sound
    heard = entry.get("heard") or entry.get("role")
    return "%s: %s" % (sound, heard) if heard else sound


class Bridge:
    """Everything `window.pywebview.api` offers, and nothing that can raise.

    Constructed before the window exists, because the window is created WITH
    this object as its Javascript surface -- so `attach` hands the window back
    afterwards, and until it does the file dialogs have nothing to open on.

    A song the constructor cannot read is remembered rather than raised.
    `snapmap-midi ui missing.mid` has to give a usable window that says what
    went wrong: a person who came for a window has no console, and a process
    that exited with a traceback tells them only that nothing happened.
    """

    def __init__(self, midi=None, settings_path=None):
        self._window = None
        self._chrome = None
        self._error = None
        try:
            self._session = Session(midi=midi, settings_path=settings_path)
        except Exception as exc:
            # The FIRST complaint is the one kept. A settings document is read
            # before the song, so a broken document fails this construction and
            # the retry below equally; reporting the retry's failure would
            # describe the same file twice and lose nothing, but reporting a
            # song error over a settings error would name the wrong file.
            self._error = str(exc)
            self._session = self._without(settings_path)

    @staticmethod
    def _without(settings_path) -> Session:
        """A session that opens on as much of the command line as still works.

        A settings document is an afternoon's tuning and the song is one line of
        it, so a song that will not open must not take the document with it.
        When the document is the broken half there is nothing left to keep and
        the window opens empty, which is the state it opens in anyway.
        """
        if settings_path is not None:
            try:
                return Session(settings_path=settings_path)
            except Exception:
                pass
        return Session()

    def attach(self, window) -> None:
        """Hand over the window the file dialogs hang on.

        Separate from construction because neither can be built first: the
        window is created with this object as its `js_api`, so it does not exist
        until after this does. Everything else works without it; only the
        pickers need a window, and they say so rather than raising.
        """
        self._window = window

    # ---- payloads ----

    def _state(self) -> dict:
        """The four things the window redraws itself from.

        `stats` is null rather than absent or zeroed when no song is open. "No
        file yet" and "a file that compiles to nothing" are different states,
        and a zero would make the window describe the second one while the user
        is looking at the first.
        """
        analysis = self._session.analysis_dict()
        return {
            "settings": self._session.settings(),
            "analysis": analysis,
            "rulers": self._session.rulers(),
            "stats": None if analysis is None else self._session.stats(),
            "preview": None if analysis is None else self._session.preview_manifest(),
        }

    def _catalog(self) -> dict:
        """Every choice the window offers, derived from the palette rather than listed.

        The note index is built ONCE here and handed to `family_range` per
        family. `build_note_index` is a full parse of the palette and is
        deliberately not cached -- it returns a mutable defaultdict, for the
        same reason `load_palette` returns a copy -- so asking each family for
        its range without passing the index reparses the palette once per
        family.

        `drum_names` remains in the compatibility payload for sidecar and API
        consumers. The workstation itself keeps percussion in the unified
        channel list and consumes `sound_groups` for its picker.
        """
        index = palette.build_note_index()
        families = []
        for name in palette.pitched_families():
            low, high = palette.family_range(name, index)
            families.append({"name": name, "lowest": low, "highest": high})

        labels = {
            sound: label
            for group in palette.sound_labels().values()
            for sound, label in group.items()
        }
        palette_data = palette.load_palette()
        category_of = {
            sound: category for category, sounds in palette_data.items() for sound in sounds
        }
        drum_sounds = [
            {
                "name": sound,
                "category": category_of.get(sound, ""),
                "label": _label(sound, labels.get(sound)),
            }
            for sound in palette.drum_sound_pool()
        ]

        analysis = self._session.analysis_dict()
        drum_names = {}
        for channel in (analysis or {}).get("channels", ()):
            for key in channel["drum_keys"]:
                drum_names[key] = gm_drum_name(int(key))

        sound_groups = []
        for category, sounds in palette_data.items():
            sound_groups.append(
                {
                    "name": category,
                    "pitched": bool(index.get(category)),
                    "sounds": [
                        {
                            "name": sound,
                            "label": _label(sound, labels.get(sound)),
                        }
                        for sound in sounds
                    ],
                }
            )

        return {
            "families": families,
            "drum_sounds": drum_sounds,
            "drum_names": drum_names,
            "sound_groups": sound_groups,
            "sound_count": sum(len(group["sounds"]) for group in sound_groups),
        }

    def _audio_status(self) -> dict:
        """Preview readiness; audio failure never takes down the editor."""
        try:
            from snapmap_midi.audio import library

            return library.status()
        except Exception as exc:
            return {
                "ready": False,
                "source": None,
                "count": 0,
                "expected": 0,
                "bank_count": 0,
                "cache_count": 0,
                "install": None,
                "cache_dir": "",
                "error": str(exc) or exc.__class__.__name__,
            }

    def _window_state(self) -> dict:
        """Whether the HTML page owns the frame, and its maximize state."""
        from snapmap_midi.ui import chrome as chrome_module

        custom = self._chrome is not None and chrome_module.supported()
        maximized = bool(self._chrome.is_maximized()) if custom else False
        return {"custom": custom, "maximized": maximized}

    # ---- opening ----

    def startup(self) -> dict:
        """Everything the first frame needs, in one call.

        `ok` and `error` can both be set, and that pairing is the point: a song
        the command line named and this could not read leaves a window that
        works, with the Open button live and one sentence saying what went
        wrong. Answering `ok: False` instead would put the window into its
        failure state over a file the user can simply replace.
        """
        try:
            payload = {"ok": True}
            payload.update(self._state())
            payload["catalog"] = self._catalog()
            payload["audio"] = self._audio_status()
            payload["window"] = self._window_state()
            if self._error:
                payload["error"] = self._error
            return payload
        except Exception as exc:
            return _fail(exc)

    def load_midi(self, path) -> dict:
        """Open a song, apply the settings sitting beside it, and answer with both.

        The order is load, then sidecar, and it cannot be the other way around.
        `Session.load` clears `channels` and `drum_keys` on purpose -- channel
        numbers collide where parts do not, so the last song's marimba must not
        follow anybody into this one -- and a sidecar applied first would be
        erased by the very load it was meant to configure.

        The catalog goes back with it because `drum_names` describes the file
        that was open when it was built, and this call is the moment that stops
        being true.
        """
        try:
            self._session.load(path)
            # The song the constructor complained about is gone from the screen,
            # and the window asks for this whole payload again every time the
            # drums switch moves. A complaint that outlived its file would toast
            # a dead path for the rest of the session.
            self._error = None
            sidecar_error = self._restore(path)
            payload = {"ok": True}
            payload.update(self._state())
            payload["catalog"] = self._catalog()
            if sidecar_error is not None:
                payload["sidecar_error"] = sidecar_error
            return payload
        except Exception as exc:
            return _fail(exc)

    def _restore(self, midi) -> str | None:
        """Apply the song's sidecar, or say why it was ignored.

        Ignored rather than fatal. This file is meant to be hand-edited, so a
        broken one is an ordinary event -- and refusing to open the song over it
        would lock out exactly the person trying to fix it. The song is what
        they asked for; the settings are what this could not give them.

        The document's own `midi` is dropped. It was written by an earlier
        session and this file has just been copied, renamed, or handed to
        somebody else, so honouring it would point the session at a song nobody
        asked to open -- and every other key in the document is about how to
        play the song rather than which one it is.
        """
        sidecar = settings_module.sidecar_path(midi)
        if not sidecar.exists():
            return None
        try:
            doc = settings_module.load(sidecar)
            self._session.apply({key: value for key, value in doc.items() if key != "midi"})
        except Exception as exc:
            # `settings.load` names the file in every message it raises, so
            # prefixing one of those would print the path twice in a sentence
            # already long enough. A document that parsed and then failed
            # validation names the SETTING instead, and that message on its own
            # never says which file the setting was in.
            reason = str(exc)
            return reason if str(sidecar) in reason else "%s: %s" % (sidecar, reason)
        return None

    def catalog(self) -> dict:
        """The full grouped palette plus compatibility percussion metadata."""
        try:
            payload = {"ok": True}
            payload.update(self._catalog())
            return payload
        except Exception as exc:
            return _fail(exc)

    # ---- local audio preview ----

    def audio_status(self) -> dict:
        """Recheck installed banks and the offline cache without writing either."""
        try:
            from snapmap_midi.audio import library

            return {"ok": True, "audio": library.status(refresh=True)}
        except Exception as exc:
            return _fail(exc)

    @staticmethod
    def _audio_payload(sound: str) -> dict:
        """One game-bank or offline-cache WAV as a local-page data URI."""
        from snapmap_midi.audio import library

        if sound not in set(library.expected_names()):
            raise ValueError("%r is not a sound in the shipped palette" % sound)
        data = library.read_wav(sound)
        if data is None:
            return {
                "ok": False,
                "error": "%s is unavailable from the installed game and offline cache" % sound,
                "sound": sound,
            }
        encoded = base64.b64encode(data).decode("ascii")
        return {
            "ok": True,
            "sound": sound,
            "data_uri": "data:audio/wav;base64,%s" % encoded,
        }

    def extract_audio(self) -> dict:
        """Build the optional offline cache for compatibility callers."""
        try:
            from snapmap_midi.audio import library

            status = library.extract()
            if not status["ready"]:
                failed = status.get("failed") or []
                return {
                    "ok": False,
                    "error": "%d sound%s could not be decoded"
                    % (len(failed), "" if len(failed) == 1 else "s"),
                    "audio": status,
                }
            return {"ok": True, "audio": status}
        except Exception as exc:
            return _fail(exc)

    def preview_sound(self, sound) -> dict:
        """Return one exact palette sound for compatibility preview callers."""
        try:
            if not isinstance(sound, str) or not sound:
                raise ValueError("a sound name is required")
            return self._audio_payload(sound)
        except Exception as exc:
            return _fail(exc)

    def preview_note(self, family, midi_note) -> dict:
        """Resolve one family and MIDI pitch exactly as the compiler does."""
        try:
            if family not in palette.pitched_families():
                raise ValueError("%r is not a pitched sound family" % family)
            if isinstance(midi_note, bool):
                raise ValueError("a MIDI note from 0 to 127 is required")
            note = int(midi_note)
            if note < 0 or note > 127 or float(midi_note) != note:
                raise ValueError("a MIDI note from 0 to 127 is required")
            sound = palette.decl_for(family, note, palette.build_note_index())
            if sound is None:
                raise ValueError("%s has no sound for MIDI note %d" % (family, note))
            return self._audio_payload(sound)
        except Exception as exc:
            return _fail(exc)

    def preview_manifest(self) -> dict:
        """Resolved events for the global workstation transport."""
        try:
            return {"ok": True, "preview": self._session.preview_manifest()}
        except Exception as exc:
            return _fail(exc)

    def preview_samples(self, names) -> dict:
        """Direct-bank or offline WAVs used by the current conversion only."""
        try:
            if isinstance(names, (str, bytes)) or not isinstance(names, (list, tuple)):
                raise ValueError("preview sample names must be a list")
            requested = []
            seen = set()
            for name in names:
                if not isinstance(name, str) or not name:
                    raise ValueError("every preview sample name must be text")
                if name not in seen:
                    requested.append(name)
                    seen.add(name)
            allowed = set(self._session.preview_manifest()["sounds"])
            outside = [name for name in requested if name not in allowed]
            if outside:
                raise ValueError("%r is not used by the current converted song" % outside[0])

            from snapmap_midi.audio import library

            samples = {}
            missing = []
            for name, data in library.read_wavs(requested).items():
                if data is None:
                    missing.append(name)
                else:
                    samples[name] = "data:audio/wav;base64,%s" % base64.b64encode(data).decode(
                        "ascii"
                    )
            return {"ok": True, "samples": samples, "missing": missing}
        except Exception as exc:
            return _fail(exc)

    # ---- the document ----

    def get_settings(self) -> dict:
        try:
            return {"ok": True, "settings": self._session.settings()}
        except Exception as exc:
            return _fail(exc)

    def apply_settings(self, patch) -> dict:
        """Merge one change in, and answer with everything it can have moved.

        Settings and statistics are obvious. Analysis remains here because
        drums mode can change whether a channel is interpreted as percussion;
        preview is here because every channel choice and conversion lever can
        change the events the global transport schedules.
        """
        try:
            self._session.apply(patch)
            payload = {"ok": True}
            payload.update(self._state())
            return payload
        except Exception as exc:
            return _fail(exc)

    def reset_tuning(self) -> dict:
        """Restore the compiler's conversion defaults without changing tracks."""
        try:
            self._session.apply({"tuning": settings_module.defaults()["tuning"]})
            payload = {"ok": True}
            payload.update(self._state())
            return payload
        except Exception as exc:
            return _fail(exc)

    # ---- compiling ----

    def dry_run(self) -> dict:
        """Compile without writing, and answer with the numbers and the warnings."""
        try:
            return {"ok": True, "stats": self._session.stats()}
        except Exception as exc:
            return _fail(exc)

    def export(self) -> dict:
        """Write the map, and the settings that produced it beside the song.

        Two files and one deliverable. `rawmap.json` is what the loader reads;
        the sidecar is what makes tomorrow's session start where this one
        stopped, and until it was written closing the window lost every choice
        in it.

        A sidecar that cannot be written does NOT fail the export. A read-only
        folder, a name already taken, a song on a share that has gone away --
        none of them are a reason to tell somebody their map failed while it is
        sitting on disk where the report says it is. It is reported instead:
        `sidecar` is the path or null, and the reason rides along when there is
        one, because a convenience that silently stopped working is how a
        feature is discovered to have been broken for a month.
        """
        try:
            result = self._session.export()
            result["ok"] = True
            result.update(self._save_sidecar())
            return result
        except Exception as exc:
            return _fail(exc)

    def _save_sidecar(self) -> dict:
        doc = self._session.settings()
        if not doc["midi"]:
            return {"sidecar": None}
        path = settings_module.sidecar_path(doc["midi"])
        try:
            settings_module.save(doc, path)
        except Exception as exc:
            return {"sidecar": None, "sidecar_error": "%s was not written: %s" % (path, exc)}
        return {"sidecar": str(path)}

    # ---- the file dialogs ----

    def _open_dialog(self, file_types) -> str | None:
        """A chosen file, or None for a cancel and for having no window yet.

        The window check comes BEFORE `import webview`, and that order is what
        makes every test in `tests/test_ui_api.py` run on a machine with no
        pywebview installed. Importing first would turn a bridge with no window
        attached into an ImportError on most of the planet, and the file that
        proves this module answers rather than raises would be a file that
        skips.

        Opening in the current song's folder because that is where the next one
        almost always is -- an Open dialog that starts in the user's home
        directory every time makes them navigate the same four folders again.
        """
        if self._window is None:
            return None
        import webview

        chosen = self._window.create_file_dialog(
            webview.FileDialog.OPEN, directory=self._nearby(), file_types=file_types
        )
        return str(chosen[0]) if chosen else None

    def _folder_dialog(self) -> str | None:
        """A chosen folder, or None. Same guard, same reason."""
        if self._window is None:
            return None
        import webview

        chosen = self._window.create_file_dialog(
            webview.FileDialog.FOLDER, directory=self._nearby()
        )
        return str(chosen[0]) if chosen else None

    def _nearby(self) -> str:
        """The folder the open song is in, or empty for the platform's default."""
        song = self._session.settings()["midi"]
        return str(Path(song).parent) if song else ""

    def pick_midi(self) -> dict:
        """Choose a song, then open it exactly as `load_midi` would."""
        try:
            chosen = self._open_dialog(_MIDI_TYPES)
            if chosen is None:
                return _cancelled()
            return self.load_midi(chosen)
        except Exception as exc:
            return _fail(exc)

    def pick_out_dir(self) -> dict:
        """Choose where the map is written.

        Answers with the settings alone. The output folder changes nothing about
        what is compiled -- only where the bytes land -- so recompiling the song
        to answer this would spend a large file's compile on a value no number
        on screen depends on.
        """
        try:
            chosen = self._folder_dialog()
            if chosen is None:
                return _cancelled()
            self._session.apply({"out_dir": chosen})
            return {"ok": True, "settings": self._session.settings()}
        except Exception as exc:
            return _fail(exc)

    def pick_baseline(self) -> dict:
        """Choose a saved map to add the song to.

        A picker rather than a field to type in: a saved map lives wherever the
        game put it, under a name the game chose, and that is a path people get
        wrong by hand -- silently, because a baseline that cannot be read fails
        later, at export, in a message about the compile.
        """
        try:
            chosen = self._open_dialog(_MAP_TYPES)
            if chosen is None:
                return _cancelled()
            self._session.apply({"baseline": chosen})
            return {"ok": True, "settings": self._session.settings()}
        except Exception as exc:
            return _fail(exc)

    # ---- the window frame ----

    def attach_chrome(self, chrome) -> None:
        """Hand over the thing that moves, sizes and closes the window.

        Stored under a LEADING UNDERSCORE, and the underscore is load-bearing.
        pywebview builds the Javascript surface by walking every public
        non-callable attribute of this object and recursing into each one that
        has a `__module__` -- so a window or a chrome parked on a public name
        sends it down the native form's accessibility tree, `Bounds.Empty.Empty`
        forever, until the stack ends. That happens inside the injection itself,
        which means `pywebviewready` never fires, `evaluate_js` never returns,
        and the window sits there rendering nothing with no error anywhere.
        `_window` is safe by the same rule and for the same reason.

        Optional, like the window: the frame-action methods below answer `ok: False`
        when nothing has been attached, so the whole bridge stays testable with
        no browser engine and no window in existence. There is deliberately no
        `error` on that answer -- the window toasts that key when it is present,
        and the only way to see it is to be running with no window at all.
        """
        self._chrome = chrome

    def win_state(self) -> dict:
        """Whether the page owns the frame, and its current maximize state."""
        try:
            payload = {"ok": True}
            payload.update(self._window_state())
            return payload
        except Exception as exc:
            return _fail(exc)

    def win_drag(self) -> dict:
        """Move the window, and report where the drag left it.

        Answers only when the user lets go: the drag is Windows' own modal move
        loop, not a stream of positions. `maximized` rides along because
        dragging to the top of the screen is one of the ways this window becomes
        maximized, and the button that would say so was never clicked.
        """
        try:
            if self._chrome is None:
                return {"ok": False}
            moved = bool(self._chrome.drag())
            return {"ok": moved, "maximized": bool(self._chrome.is_maximized())}
        except Exception as exc:
            return _fail(exc)

    def win_resize(self, edge) -> dict:
        """Size the window from one of the eight edges.

        `ok: False` for an edge name that is not one of the eight, with no
        `error`: the names come from the markup's own grips, so a bad one is a
        typo in the page rather than anything to tell the user about.
        """
        try:
            if self._chrome is None:
                return {"ok": False}
            return {"ok": bool(self._chrome.resize_from(edge))}
        except Exception as exc:
            return _fail(exc)

    def win_min(self) -> dict:
        """Minimise to the taskbar."""
        try:
            if self._chrome is None:
                return {"ok": False}
            return {"ok": bool(self._chrome.minimize())}
        except Exception as exc:
            return _fail(exc)

    def win_max(self) -> dict:
        """Maximise or restore, and answer with which of the two it now is.

        `ok` stays True for both directions. Answering with the chrome's own
        return value would make restoring the window look like a failed call,
        and the state belongs in its own key anyway -- the button that sent this
        has to change glyph, and nothing else on the page knows which way it
        went.
        """
        try:
            if self._chrome is None:
                return {"ok": False}
            return {"ok": True, "maximized": bool(self._chrome.toggle_maximize())}
        except Exception as exc:
            return _fail(exc)

    def win_close(self) -> dict:
        """Close the window, through pywebview so its own shutdown still runs."""
        try:
            if self._chrome is None:
                return {"ok": False}
            return {"ok": bool(self._chrome.close())}
        except Exception as exc:
            return _fail(exc)
