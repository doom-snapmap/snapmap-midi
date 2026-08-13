/* snapmap-midi workstation.

   Python resolves the converted arrangement. This page presents that answer as
   tracks, a piano roll and one transport; it never reimplements sound mapping
   or map limits in JavaScript. */
(function () {
  'use strict';

  var THEME_KEY = 'snapmap_midi_theme';
  var TRACKS_WIDTH_KEY = 'snapmap_midi_tracks_width';
  var OCTAVE_LABEL_KEY = 'snapmap_midi_middle_c_octave';
  var TRACKS_DEFAULT_WIDTH = 314;
  var TRACKS_MIN_WIDTH = 220;
  var ROLL_MIN_WIDTH = 420;
  var LOOKAHEAD_MS = 1300;
  var SCHEDULE_EVERY_MS = 100;
  var MAX_CANVAS_PIXEL_RATIO = 2;
  var OVERVIEW_CACHE_PIXEL_BUDGET = 16000000;
  var MIDDLE_C_OCTAVE = 4;
  var CHANNEL_COLORS = [
    '#4a9eff', '#e0a52b', '#43b581', '#d75c76',
    '#a57be8', '#43b9c7', '#ed7d31', '#7aa84f',
    '#6689e8', '#d85ca8', '#55a7a1', '#c38b5f',
    '#8f7ee7', '#74a94e', '#d56b52', '#4eafde'
  ];
  var NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  var BLACK_KEYS = { 1: true, 3: true, 6: true, 8: true, 10: true };
  var ROLL = {
    zoom: 100,
    gridDenominator: 8,
    meterNumerator: 4,
    meterDenominator: 4,
    songKey: '',
    pendingInitialScroll: false,
    contentWidth: 1,
    contentHeight: 1,
    rowHeight: 9,
    viewportWidth: 1,
    viewportHeight: 1
  };
  var RENDER = {
    surfaceDirty: true,
    pitchDirty: true,
    timeDirty: true,
    palette: null,
    eventSource: null,
    eventIndex: null,
    tempoSource: null,
    tempoIndex: null,
    lineTimingSource: null,
    timingKey: '',
    timingLines: null,
    overviewCanvas: null,
    overviewValid: false,
    scrollLeft: null,
    scrollTop: null,
    transportTenth: null,
    transportDuration: null,
    scrubberPaintAt: 0
  };

  var STATE = {
    settings: null,
    analysis: null,
    catalog: null,
    stats: null,
    preview: null,
    audio: null,
    window: null
  };
  var REQUEST = 0;
  var APPLIED = {};
  var BUSY = 0;
  var BOOTED = false;
  // The note a rootless sound is treated as already sounding, so Follow MIDI
  // has an interval to measure from. C4 is the sampler convention: the sample
  // plays untouched on middle C and shifts by the interval everywhere else.
  // Nothing measured this -- a door slam is not in any key -- so it is stored
  // as root_source "neutral" and the window says so. Same value and same name
  // as settings.NEUTRAL_PITCH_REFERENCE, which validates it.
  var NEUTRAL_ROOT_MIDI = 60;

  // The focused part, as its "track:channel" key, or null for "show all".
  var SELECTED_PART = null;
  var TRACK_KEY = '';
  var OPEN_MENU = null;
  var INSPECTOR_OPEN = false;
  var NOTIFICATIONS_OPEN = false;
  var CHANNEL_INSPECTOR_OPEN = false;
  var NOTE_INSPECTOR_OPEN = false;
  var SELECTED_NOTE_ID = null;
  var DRAW_FRAME = null;
  var SEEK_DRAG = null;
  var SCRUB_DRAG = null;
  var NOTE_POINTER = null;
  var PANE_SPLIT_DRAG = null;
  var TRACKS_PREFERRED_WIDTH = TRACKS_DEFAULT_WIDTH;
  var CANVAS_RESIZE_QUEUED = false;
  var PLAY_TOKEN = 0;
  var PATCH_QUEUE = Promise.resolve();
  var PATCH_PENDING = 0;
  var PATCH_RESUME = false;

  var SOUND_BROWSER = {
    open: false,
    loading: false,
    request: 0,
    channel: null,
    drumKey: null,
    catalog: null,
    tree: null,
    byName: {},
    expanded: {},
    mode: "events",
    path: "",
    candidate: null,
    page: 0,
    pageSize: 160,
    audition: null,
    auditionToken: 0,
    buffers: {},
    bufferOrder: []
  };

  var AUDIO = {
    context: null,
    master: null,
    buffers: {},
    unavailable: {},
    key: '',
    loading: null,
    playing: false,
    position: 0,
    anchorPosition: 0,
    anchorTime: 0,
    nextIndex: 0,
    timer: null,
    frame: null,
    sources: [],
    generation: 0,
    preparing: false,
    prepareError: null
  };

  function el(id) { return document.getElementById(id); }
  function api() { return window.pywebview && window.pywebview.api; }
  function nextRequest() { REQUEST += 1; return REQUEST; }
  function hasSong() { return !!(STATE.analysis && STATE.settings && STATE.settings.midi); }
  function channels() { return (STATE.analysis && STATE.analysis.channels) || []; }
  function previewEvents() { return (STATE.preview && STATE.preview.events) || []; }
  function previewDisplayEvents() {
    return (STATE.preview && STATE.preview.display_events) || previewEvents();
  }

  function tuning() { return (STATE.settings && STATE.settings.tuning) || {}; }
  function audioUnavailableNames() { return Object.keys(AUDIO.unavailable || {}).sort(); }
  function warningMessages() {
    var warnings = ((STATE.stats && STATE.stats.warnings) || []).slice();
    var unavailable = audioUnavailableNames();
    if (unavailable.length) {
      var sample = unavailable.slice(0, 3).join(', ');
      if (unavailable.length > 3) { sample += ', +' + (unavailable.length - 3) + ' more'; }
      warnings.push(
        unavailable.length + ' selected in-game event' + (unavailable.length === 1 ? '' : 's') +
        ' cannot be rendered as standalone local audio (' + sample +
        '). Song preview skips those events; exported maps still use their exact event strings.'
      );
    }
    return warnings;
  }
  function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }
  function baseName(path) { return String(path || '').replace(/^.*[\\/]/, ''); }
  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function channelColor(channel) { return CHANNEL_COLORS[Number(channel) % CHANNEL_COLORS.length]; }
  function iconElement(name) {
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    var use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    svg.setAttribute('class', 'ui-icon');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    use.setAttribute('href', '#icon-' + name);
    svg.appendChild(use);
    return svg;
  }
  function setIcon(node, name) {
    var use = node && node.querySelector('use');
    if (use) { use.setAttribute('href', '#icon-' + name); }
  }
  function noteName(note) {
    note = Number(note);
    var octave = Math.floor(note / 12) + MIDDLE_C_OCTAVE - 5;
    return NOTE_NAMES[((note % 12) + 12) % 12] + octave;
  }
  function humanCategory(name) {
    return String(name || '')
      .replace(/^([a-z]+\d*)_/, '')
      .replace(/_/g, ' ')
      .replace(/\b\w/g, function (letter) { return letter.toUpperCase(); });
  }
  function formatTime(ms) {
    ms = Math.max(0, Number(ms) || 0);
    var minutes = Math.floor(ms / 60000);
    var seconds = (ms - minutes * 60000) / 1000;
    return minutes + ':' + (seconds < 10 ? '0' : '') + seconds.toFixed(1);
  }
  function debounce(fn, delay) {
    var timer = null;
    return function () {
      var args = arguments;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(null, args); }, delay);
    };
  }

  function toast(message, kind) {
    if (!message) { return; }
    var node = document.createElement('div');
    node.className = 'toast ' + (kind || '');
    node.textContent = String(message);
    el('toastHost').appendChild(node);
    requestAnimationFrame(function () { node.classList.add('show'); });
    setTimeout(function () {
      node.classList.remove('show');
      setTimeout(function () { if (node.parentNode) { node.parentNode.removeChild(node); } }, 320);
    }, 3400);
  }

  function fail(error) {
    toast(error && (error.message || error.error) || String(error || 'Something went wrong'), 'err');
  }

  function stamp(text) { el('stamp').textContent = text || ''; }
  function setBusy(on, text) {
    BUSY += on ? 1 : -1;
    BUSY = Math.max(0, BUSY);
    el('busyText').hidden = BUSY === 0;
    el('busyText').textContent = BUSY ? (text || 'Working...') : 'Working...';
  }

  function accept(key, sequence) {
    if ((APPLIED[key] || 0) > sequence) { return false; }
    APPLIED[key] = sequence;
    return true;
  }

  function adopt(payload, sequence) {
    var previewChanged = false;
    ['settings', 'analysis', 'catalog', 'stats', 'preview', 'audio', 'window',
     'drum_defaults'].forEach(function (key) {
      if (payload[key] !== undefined && accept(key, sequence)) {
        if (key === 'preview' && STATE[key] !== payload[key]) { previewChanged = true; }
        STATE[key] = payload[key];
      }
    });
    if (previewChanged) { invalidatePreviewRenderCache(); }
  }

  /* --------------------------------------------------------------- themes */

  function storedTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (_error) { return null; }
  }

  function setTheme(name, persist) {
    var dark = name === 'dark';
    document.documentElement.classList.toggle('dark', dark);
    el('menuLight').setAttribute('aria-checked', dark ? 'false' : 'true');
    el('menuDark').setAttribute('aria-checked', dark ? 'true' : 'false');
    if (persist) {
      try { localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light'); } catch (_error) { /* local only */ }
    }
    RENDER.palette = null;
    invalidateRollAll();
    queueDraw();
  }

  function initTheme() {
    var saved = storedTheme();
    var dark = saved ? saved === 'dark' : !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    setTheme(dark ? 'dark' : 'light', false);
    el('menuLight').addEventListener('click', function () { setTheme('light', true); closeMenus(); });
    el('menuDark').addEventListener('click', function () { setTheme('dark', true); closeMenus(); });
  }

  /* ---------------------------------------------- pitch-name display convention */

  function storedMiddleCOctave() {
    try { return Number(localStorage.getItem(OCTAVE_LABEL_KEY)); } catch (_error) { return 4; }
  }

  function setMiddleCOctave(octave, persist, refresh) {
    MIDDLE_C_OCTAVE = Number(octave) === 3 ? 3 : 4;
    el('menuMiddleC4').setAttribute('aria-checked', MIDDLE_C_OCTAVE === 4 ? 'true' : 'false');
    el('menuMiddleC3').setAttribute('aria-checked', MIDDLE_C_OCTAVE === 3 ? 'true' : 'false');
    if (persist) {
      try { localStorage.setItem(OCTAVE_LABEL_KEY, String(MIDDLE_C_OCTAVE)); } catch (_error) { /* local only */ }
    }
    invalidateRollAll();
    if (refresh) { render(); }
  }

  function initPitchNameConvention() {
    setMiddleCOctave(storedMiddleCOctave(), false, false);
    el('menuMiddleC4').addEventListener('click', function () {
      setMiddleCOctave(4, true, true);
      closeMenus();
    });
    el('menuMiddleC3').addEventListener('click', function () {
      setMiddleCOctave(3, true, true);
      closeMenus();
    });
  }

  /* ---------------------------------------------------------- desktop menus */

  function closeMenus() {
    var labels = document.querySelectorAll('.menu-label');
    for (var index = 0; index < labels.length; index += 1) {
      labels[index].classList.remove('open');
      labels[index].setAttribute('aria-expanded', 'false');
    }
    var popups = document.querySelectorAll('.menu-popup');
    for (index = 0; index < popups.length; index += 1) { popups[index].hidden = true; }
    OPEN_MENU = null;
  }

  function openMenu(name, focusFirst) {
    closeMenus();
    var label = document.querySelector('.menu-label[data-menu="' + name + '"]');
    var popup = el('menu-' + name);
    if (!label || !popup) { return; }
    label.classList.add('open');
    label.setAttribute('aria-expanded', 'true');
    popup.hidden = false;
    OPEN_MENU = name;
    if (focusFirst) {
      var first = popup.querySelector('button:not(:disabled)');
      if (first) { first.focus(); }
    }
  }

  function initMenus() {
    var labels = document.querySelectorAll('.menu-label');
    for (var index = 0; index < labels.length; index += 1) {
      labels[index].addEventListener('click', function (event) {
        event.stopPropagation();
        var name = this.getAttribute('data-menu');
        if (OPEN_MENU === name) { closeMenus(); } else { openMenu(name, false); }
      });
      labels[index].addEventListener('mouseenter', function () {
        if (OPEN_MENU) { openMenu(this.getAttribute('data-menu'), false); }
      });
      labels[index].addEventListener('keydown', function (event) {
        if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          openMenu(this.getAttribute('data-menu'), true);
        }
      });
    }
    document.addEventListener('pointerdown', function (event) {
      if (OPEN_MENU && !event.target.closest('.menu')) { closeMenus(); }
    });
  }

  function updateMenuState() {
    var song = hasSong();
    var audio = STATE.audio || {};
    ['menuReopen', 'menuExport', 'menuPlay', 'menuStart'].forEach(function (id) { el(id).disabled = !song; });
    el('menuPlay').querySelector('span').textContent = AUDIO.playing ? 'Pause' : 'Play';
    if (audio.source === 'game' || audio.source === 'game+cache') {
      el('menuAudio').querySelector('span').textContent = 'DOOM Audio Ready';
    } else if (audio.source === 'cache') {
      el('menuAudio').querySelector('span').textContent = 'Offline Audio Ready';
    } else {
      el('menuAudio').querySelector('span').textContent = 'Refresh Audio Source';
    }
    el('menuAudio').disabled = false;
  }

  /* --------------------------------------------------------------- tracks */

  // A part's settings: its own entry, else its channel's. The channel-wide
  // entry is the wildcard every document written before parts existed uses,
  // and it still means "every part on this channel" -- the same precedence the
  // parser applies, so the row shows what the compile will do.
  function partEntry(part) {
    var all = (STATE.settings && STATE.settings.channels) || {};
    if (!part) { return {}; }
    return all[part.key] || all[String(part.channel)] || {};
  }

  // Writes always name the part. A write through the wildcard would change
  // every part on the channel, which is the merge this whole feature removes.
  function partPatch(part, values) {
    var patch = { channels: {} };
    patch.channels[part.key] = values;
    return patch;
  }

  function anySoloedChannel() {
    var list = channels();
    for (var index = 0; index < list.length; index += 1) {
      if (partEntry(list[index]).soloed) { return true; }
    }
    return false;
  }

  function partByKey(key) {
    if (key === null || key === undefined) { return null; }
    var list = channels();
    for (var index = 0; index < list.length; index += 1) {
      if (list[index].key === String(key)) { return list[index]; }
    }
    // A bare channel number still resolves, for callers that have only that.
    for (var fallback = 0; fallback < list.length; fallback += 1) {
      if (Number(list[fallback].channel) === Number(key)) { return list[fallback]; }
    }
    return null;
  }

  // Colour identifies a ROW, so it follows the part's position in the list.
  // Colouring by channel number would paint three parts sharing channel 0 the
  // same colour, which is exactly the distinction the row is there to make.
  function partColorForKey(key) {
    var list = channels();
    for (var index = 0; index < list.length; index += 1) {
      if (list[index].key === key) { return channelColor(index); }
    }
    return channelColor(Number(String(key).split(":").pop()) || 0);
  }

  function partColor(part) {
    if (!part) { return channelColor(0); }
    var list = channels();
    for (var index = 0; index < list.length; index += 1) {
      if (list[index].key === part.key) { return channelColor(index); }
    }
    return channelColor(part.channel);
  }

  // Whether any MIDI channel in this song carries more than one part.
  // Decides what the row's number badge can usefully say: neither number
  // identifies a row on its own. On a normal file the channel is unique and
  // the track is not (one track often carries several channels); on a file
  // that writes several tracks to one channel it is the other way round, and
  // on a format 0 file every part shares track 0.
  function partLabel(part) {
    if (!part) { return ""; }
    return part.track_name || part.program_name;
  }

  function humanSoundName(name) {
    return String(name || "")
      .replace(/^play_/i, "")
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, function (letter) { return letter.toUpperCase(); });
  }

  function paletteSoundLabel(name) {
    var groups = (STATE.catalog && STATE.catalog.sound_groups) || [];
    for (var groupIndex = 0; groupIndex < groups.length; groupIndex += 1) {
      var sounds = groups[groupIndex].sounds || [];
      for (var soundIndex = 0; soundIndex < sounds.length; soundIndex += 1) {
        if (sounds[soundIndex].name === name) {
          return sounds[soundIndex].label || humanSoundName(name);
        }
      }
    }
    return humanSoundName(name);
  }

  function browserSoundEvent(name) {
    return SOUND_BROWSER.byName[String(name || "").toLowerCase()] || null;
  }

  function exactSoundLabel(name) {
    var event = browserSoundEvent(name);
    return event && (event.label || humanSoundName(event.name)) || paletteSoundLabel(name);
  }

  function assignmentLabel(channel) {
    var entry = partEntry(channel);
    if (entry.sound) { return exactSoundLabel(entry.sound); }
    if (entry.family) { return humanCategory(entry.family); }
    return channel.is_drums
      ? "Automatic \u2014 General MIDI percussion"
      : "Automatic \u2014 " + humanCategory(channel.auto_family || channel.program_name);
  }

  function assignmentTitle(channel) {
    var entry = partEntry(channel);
    if (entry.sound) { return assignmentLabel(channel) + "\n" + entry.sound; }
    if (entry.family) { return "Pitched family: " + entry.family; }
    return assignmentLabel(channel);
  }

  // ---- Percussion ------------------------------------------------------
  // `drum_keys` is one map for the whole song, keyed by MIDI note, not one map
  // per part. Two kits that both play 36 therefore share a kick, which is what
  // a composer means by "the kick". It also replaces wholesale on patch, and
  // that is the only reason removal is expressible at all: an entry absent from
  // the map is the General MIDI table's answer, and no value could say that,
  // since every value has to name a real sound.

  function drumPool() {
    return (STATE.catalog && STATE.catalog.drum_sounds) || [];
  }

  function drumKeyName(channel, key) {
    var names = (channel && channel.drum_names) || {};
    return names[String(key)] || "Key " + key;
  }

  // Three tables answer for a key, in order. The song's own `drum_keys` wins;
  // then the user's saved table, which is a preference and outlives the song;
  // then the shipped one, which is a taste call nothing writes over. The row
  // has to say WHICH answered, or "save as my default" looks like it did
  // nothing on a key the song was already overriding.

  function drumKeyOverrides() {
    return (STATE.settings && STATE.settings.drum_keys) || {};
  }

  function drumDefaults() {
    return STATE.drum_defaults || {};
  }

  function shippedDrumMap() {
    return (STATE.catalog && STATE.catalog.drum_shipped) || {};
  }

  // What the analysis fell back to: already the user's table where they set
  // one, since the whole compile reads through the same overlay.
  function drumKeyDefault(channel, key) {
    return (channel && channel.drum_keys && channel.drum_keys[String(key)]) || null;
  }

  function drumKeyChoice(channel, key) {
    var song = drumKeyOverrides()[String(key)];
    if (song) { return { sound: song, scope: "song" }; }
    var mine = drumDefaults()[String(key)];
    if (mine) { return { sound: mine, scope: "yours" }; }
    return { sound: drumKeyDefault(channel, key), scope: "builtin" };
  }

  function drumScope() {
    return el("soundScope").value === "default" ? "default" : "song";
  }

  // The row a chosen sound is measured against, which is not the same row in
  // both scopes: editing your own default has to offer the shipped one back,
  // or a saved default could never be undone from here.
  function drumFallback(channel, key) {
    if (drumScope() === "default") {
      var shipped = shippedDrumMap()[String(key)] || null;
      return {
        sound: shipped,
        label: shipped
          ? "Built-in default \u2014 " + exactSoundLabel(shipped)
          : "No built-in sound \u2014 this key stays silent",
        note: shipped
          ? "Clears your saved default for this key"
          : "General MIDI names no sound for this key"
      };
    }
    var choice = drumKeyChoice(channel, key);
    var under = drumDefaults()[String(key)] || drumKeyDefault(channel, key);
    return {
      sound: under,
      label: under
        ? (drumDefaults()[String(key)] ? "Your default \u2014 " : "Built-in default \u2014 ")
          + exactSoundLabel(under)
        : "No sound \u2014 this key stays silent",
      note: choice.scope === "song"
        ? "Drops this song's own choice for this key"
        : "What this key plays with nothing set for this song"
    };
  }

  function defaultDrumLabel(channel, key) {
    return drumFallback(channel, key).label;
  }

  function withKey(table, key, sound) {
    var next = {};
    Object.keys(table).forEach(function (existing) { next[existing] = table[existing]; });
    if (sound) { next[String(key)] = sound; }
    else { delete next[String(key)]; }
    return next;
  }

  function setDrumKeySound(key, sound) {
    applyPatch({ drum_keys: withKey(drumKeyOverrides(), key, sound) }, true);
  }

  function setDrumKeyDefault(key, sound) {
    if (!api()) { return; }
    // The song's own entry goes with it. Saving a default while this song is
    // overriding the same key would store the choice and change nothing you can
    // hear, which is indistinguishable from the save having failed.
    var songNext = drumKeyOverrides()[String(key)] !== undefined
      ? withKey(drumKeyOverrides(), key, null)
      : null;
    var sequence = nextRequest();
    setBusy(true, "Saving your drum default...");
    api().set_drum_defaults(withKey(drumDefaults(), key, sound)).then(function (response) {
      if (!response || !response.ok) { setBusy(false); fail(response); render(); return; }
      adopt(response, sequence);
      if (songNext) {
        setBusy(false);
        applyPatch({ drum_keys: songNext }, true);
        return;
      }
      setBusy(false);
      invalidateAudio(false);
      render();
      toast(sound
        ? "Saved as your default for every song."
        : "Back to the built-in default for every song.");
    }, function (error) { setBusy(false); fail(error); });
  }

  function trackShapeKey() {
    var families = (STATE.catalog && STATE.catalog.families) || [];
    return channels().map(function (channel) {
      return channel.key + ":" + channel.program;
    }).join("|") + "#" + families.length;
  }

  function buildTracks() {
    var list = el("trackList");
    list.textContent = "";
    channels().forEach(function (channel, position) {
      var row = document.createElement("div");
      row.className = "track-row";
      row.dataset.part = channel.key;
      row.style.setProperty("--track-color", partColor(channel));
      row.title = "Click to focus this track and open its settings; click again to show all tracks";

      var number = document.createElement("div");
      number.className = "track-channel";
      // The ROW's number, 1..N -- counted here, not read out of the file. A DAW
      // puts one part on one row and numbers the rows, so this is what a
      // musician means by "track", and it is the only number that is always
      // DISTINCT: a MIDI track index repeats in a type 0 file (one chunk
      // carries every channel, so every part is track 0) and a MIDI channel
      // repeats whenever two tracks share one -- rip and tear's two drum parts
      // are both on channel 10. A column whose job is "this is a different
      // part" cannot be built on either of those.
      //
      // The file's real track index is not lost, just not shouted: it stays in
      // the title for anyone debugging against the source file.
      number.textContent = String(position + 1);
      number.title = "Track " + (position + 1) +
        " \u00b7 MIDI track " + channel.track +
        " \u00b7 MIDI channel " + (channel.channel + 1);
      row.appendChild(number);

      var heading = document.createElement("div");
      heading.className = "track-heading";

      // The channel, on every row rather than only when it is ambiguous. It
      // decides behaviour -- channel 10 is the drum kit -- and the settings
      // panel names it by number, so a reader has to be able to see it without
      // hunting. Labelled, because a bare number in a column reads as a row
      // count. OUTSIDE the name so a long title cannot clip it away.
      var channelChip = document.createElement("span");
      channelChip.className = "track-chip";
      channelChip.textContent = "CH" + (channel.channel + 1);
      channelChip.title = "MIDI channel " + (channel.channel + 1);
      heading.appendChild(channelChip);

      var name = document.createElement("div");
      name.className = "track-name";
      // The track's own name when the file gave it one. A format 0 file has
      // none by definition, and a type 1 conductor's name is the song's, so
      // both fall back to the General MIDI instrument, as before parts existed.
      name.textContent = partLabel(channel) + (channel.is_drums ? " \u00b7 Percussion" : "");
      name.title = channel.notes + " notes \u00b7 " + noteName(channel.lowest) + "\u2013" + noteName(channel.highest) +
        " \u00b7 MIDI channel " + (channel.channel + 1);

      heading.appendChild(name);

      var actions = document.createElement("div");
      actions.className = "track-actions";

      function mixerButton(kind, setting) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "track-toggle track-" + kind + "-toggle";
        button.appendChild(iconElement(kind === "mute" ? "volume-2" : "headphones"));
        button.addEventListener("click", function () {
          var values = {};
          values[setting] = !partEntry(channel)[setting];
          applyPatch(partPatch(channel, values), true);
        });
        return button;
      }

      actions.appendChild(mixerButton("mute", "muted"));
      actions.appendChild(mixerButton("solo", "soloed"));
      heading.appendChild(actions);
      row.appendChild(heading);

      var picker = document.createElement("button");
      picker.type = "button";
      picker.className = "track-sound-picker";
      picker.setAttribute("aria-haspopup", "dialog");
      picker.setAttribute("aria-label", "Choose sound for " + partLabel(channel));
      var pickerCopy = document.createElement("span");
      pickerCopy.className = "track-sound-copy";
      picker.appendChild(pickerCopy);
      picker.appendChild(iconElement("chevron-down"));
      picker.addEventListener("click", function () { openSoundBrowser(channel.key); });
      row.appendChild(picker);

      row.addEventListener("click", function (event) {
        if (event.target.closest("button, input, label")) { return; }
        if (SELECTED_PART === channel.key && CHANNEL_INSPECTOR_OPEN) {
          SELECTED_PART = null;
          closeChannelInspector();
        } else {
          openChannelInspector(channel.key);
        }
        patchTracks();
        invalidateRollSurface();
        queueDraw();
      });
      list.appendChild(row);
    });
  }

  function patchTracks() {
    var rows = el("trackList").querySelectorAll(".track-row");
    var soloActive = anySoloedChannel();
    for (var index = 0; index < rows.length; index += 1) {
      var row = rows[index];
      var partKey = row.dataset.part;
      var channel = partByKey(partKey);
      var entry = partEntry(channel);
      var selected = SELECTED_PART === partKey;
      row.classList.toggle("selected", selected);
      row.setAttribute("aria-selected", selected ? "true" : "false");
      row.setAttribute(
        "aria-expanded",
        selected && CHANNEL_INSPECTOR_OPEN ? "true" : "false"
      );
      row.classList.toggle("muted-track", !!entry.muted);
      row.classList.toggle("soloed-track", !!entry.soloed);
      row.classList.toggle("solo-excluded-track", soloActive && !entry.soloed);
      var picker = row.querySelector(".track-sound-picker");
      if (channel && picker) {
        picker.querySelector(".track-sound-copy").textContent = assignmentLabel(channel);
        picker.title = assignmentTitle(channel);
      }
      var mute = row.querySelector(".track-mute-toggle");
      var solo = row.querySelector(".track-solo-toggle");
      mute.classList.toggle("active", !!entry.muted);
      mute.setAttribute("aria-pressed", entry.muted ? "true" : "false");
      var who = channel ? partLabel(channel) : "this track";
      mute.setAttribute("aria-label", (entry.muted ? "Unmute " : "Mute ") + who);
      mute.title = entry.muted ? "Unmute this track" : "Mute this track";
      setIcon(mute, entry.muted ? "volume-x" : "volume-2");
      solo.classList.toggle("active", !!entry.soloed);
      solo.setAttribute("aria-pressed", entry.soloed ? "true" : "false");
      solo.setAttribute("aria-label", entry.soloed
        ? "Remove " + who + " from the solo mix"
        : "Solo " + who);
      solo.title = entry.soloed
        ? "Remove this track from the solo mix"
        : "Solo this track; other soloed tracks remain audible";
    }
  }

  function renderTracks() {
    var key = trackShapeKey();
    if (key !== TRACK_KEY) {
      TRACK_KEY = key;
      buildTracks();
    }
    patchTracks();
    el("trackCount").textContent = String(channels().length);
  }

  function normalizeSoundPath(path) {
    return String(path || "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  }

  function folderLabel(name) {
    return String(name || "All DOOM sounds")
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, function (letter) { return letter.toUpperCase(); });
  }

  function makeSoundTree(events) {
    var root = { name: "All DOOM sounds", path: "", count: 0, children: {} };
    events.forEach(function (event) {
      var current = root;
      current.count += 1;
      var partial = [];
      normalizeSoundPath(event.path).split("/").filter(Boolean).forEach(function (segment) {
        partial.push(segment);
        if (!current.children[segment]) {
          current.children[segment] = {
            name: segment,
            path: partial.join("/"),
            count: 0,
            children: {}
          };
        }
        current = current.children[segment];
        current.count += 1;
      });
    });
    return root;
  }

  function expandSoundPath(path) {
    var parts = normalizeSoundPath(path).split("/").filter(Boolean);
    var partial = [];
    parts.forEach(function (part) {
      partial.push(part);
      SOUND_BROWSER.expanded[partial.join("/")] = true;
    });
  }

  function prepareSoundCatalog(payload) {
    var events = (payload && payload.events) || [];
    SOUND_BROWSER.byName = {};
    events.forEach(function (event) {
      event.previewable = event.previewable !== false;
      event._path = normalizeSoundPath(event.path);
      event._search = [
        event.name,
        event.label || "",
        event._path,
        event.bus || "",
        event.environment || "",
        event.previewable ? "local preview" : "in game only preview unavailable",
        String(event.id === undefined ? "" : event.id)
      ].join(" ").toLowerCase();
      SOUND_BROWSER.byName[event.name.toLowerCase()] = event;
    });
    events.sort(function (left, right) {
      var pathOrder = left._path.localeCompare(right._path);
      return pathOrder || left.name.localeCompare(right.name);
    });
    SOUND_BROWSER.catalog = payload;
    SOUND_BROWSER.tree = makeSoundTree(events);
    if (SOUND_BROWSER.candidate && SOUND_BROWSER.candidate.kind === "sound") {
      var current = browserSoundEvent(SOUND_BROWSER.candidate.value);
      if (current) {
        SOUND_BROWSER.path = current._path;
        expandSoundPath(current._path);
        SOUND_BROWSER.candidate.label = current.label || humanSoundName(current.name);
      }
    }
  }

  function clearSoundBrowserCatalog() {
    stopSoundAudition();
    SOUND_BROWSER.request += 1;
    SOUND_BROWSER.loading = false;
    SOUND_BROWSER.catalog = null;
    SOUND_BROWSER.tree = null;
    SOUND_BROWSER.byName = {};
    SOUND_BROWSER.expanded = {};
    SOUND_BROWSER.buffers = {};
    SOUND_BROWSER.bufferOrder = [];
  }

  function candidateForChannel(channel) {
    var entry = partEntry(channel);
    if (entry.sound) {
      return { kind: "sound", value: entry.sound, label: exactSoundLabel(entry.sound) };
    }
    if (entry.family) {
      return { kind: "family", value: entry.family, label: humanCategory(entry.family) };
    }
    return {
      kind: "automatic",
      value: "",
      label: channel.is_drums
        ? "Automatic \u2014 General MIDI percussion"
        : "Automatic \u2014 " + humanCategory(channel.auto_family || channel.program_name)
    };
  }

  function candidateMatches(kind, value) {
    var candidate = SOUND_BROWSER.candidate;
    return !!candidate && candidate.kind === kind && String(candidate.value || "") === String(value || "");
  }

  function soundCandidateChanged() {
    var candidate = SOUND_BROWSER.candidate;
    var channel = partByKey(SOUND_BROWSER.part);
    if (!candidate || !channel) { return false; }
    var current = candidateForChannel(channel);
    return candidate.kind !== current.kind ||
      String(candidate.value || "") !== String(current.value || "");
  }

  function updateSoundSelection() {
    var rows = el("soundResultList").querySelectorAll(".sound-result-row");
    for (var index = 0; index < rows.length; index += 1) {
      var selected = candidateMatches(rows[index].dataset.kind, rows[index].dataset.value);
      rows[index].classList.toggle("selected", selected);
      rows[index].setAttribute("aria-selected", selected ? "true" : "false");
    }
    var candidate = SOUND_BROWSER.candidate;
    var summary = el("soundSelection");
    summary.textContent = "";
    if (!candidate) {
      summary.textContent = "Choose an automatic mapping, pitched family, or exact sound.";
      el("soundBrowserUse").disabled = true;
      return;
    }
    var strong = document.createElement("strong");
    strong.textContent = candidate.label;
    summary.appendChild(strong);
    if (candidate.kind === "sound") {
      summary.appendChild(document.createTextNode("  \u00b7  " + candidate.value));
    } else if (candidate.kind === "family") {
      summary.appendChild(document.createTextNode("  \u00b7  Pitched instrument family"));
    } else if (inDrumKeyMode()) {
      summary.appendChild(document.createTextNode("  \u00b7  General MIDI percussion table"));
    } else {
      summary.appendChild(document.createTextNode("  \u00b7  Follows the MIDI channel"));
    }
    if (inDrumKeyMode()) {
      // A drum key's Use is never "unchanged": the same sound can be sent to a
      // different scope, so there is no previous pick to compare against.
      el("soundBrowserUse").disabled = false;
      el("soundBrowserUse").textContent = drumScope() === "default"
        ? "Save as my default"
        : "Use for this song";
    } else {
      el("soundBrowserUse").disabled = !soundCandidateChanged();
      el("soundBrowserUse").textContent = "Use sound";
    }
  }

  function setSoundCandidate(kind, value, label) {
    SOUND_BROWSER.candidate = { kind: kind, value: value || "", label: label };
    updateSoundSelection();
  }

  function soundTreeButton(label, icon, count, selected, depth, onClick, expanded, hasChildren) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "sound-tree-button" + (selected ? " selected" : "");
    button.style.paddingLeft = (8 + depth * 14) + "px";

    var chevron = document.createElement("span");
    chevron.className = "tree-chevron";
    if (hasChildren) { chevron.appendChild(iconElement(expanded ? "chevron-down" : "chevron-right")); }
    button.appendChild(chevron);

    var folder = iconElement(icon);
    folder.classList.add("tree-folder");
    button.appendChild(folder);

    var copy = document.createElement("span");
    copy.className = "tree-label";
    copy.textContent = label;
    button.appendChild(copy);

    if (count !== null && count !== undefined) {
      var tally = document.createElement("span");
      tally.className = "tree-count";
      tally.textContent = String(count);
      button.appendChild(tally);
    }
    button.addEventListener("click", onClick);
    return button;
  }

  function selectSoundMode(mode) {
    SOUND_BROWSER.mode = mode;
    SOUND_BROWSER.page = 0;
    el("soundBrowserSearch").value = "";
    renderSoundBrowser();
  }

  function appendFolderTree(host, node, depth) {
    Object.keys(node.children).sort(function (left, right) {
      return left.localeCompare(right);
    }).forEach(function (key) {
      var child = node.children[key];
      var childKeys = Object.keys(child.children);
      var expanded = !!SOUND_BROWSER.expanded[child.path];
      var selected = SOUND_BROWSER.mode === "events" && SOUND_BROWSER.path === child.path;
      host.appendChild(soundTreeButton(
        folderLabel(child.name),
        expanded ? "folder-open" : "folder",
        child.count,
        selected,
        depth,
        function () {
          SOUND_BROWSER.mode = "events";
          SOUND_BROWSER.page = 0;
          el("soundBrowserSearch").value = "";
          if (selected && childKeys.length) {
            SOUND_BROWSER.expanded[child.path] = !expanded;
          } else {
            SOUND_BROWSER.path = child.path;
            if (childKeys.length) { SOUND_BROWSER.expanded[child.path] = true; }
          }
          renderSoundBrowser();
        },
        expanded,
        childKeys.length > 0
      ));
      if (expanded) { appendFolderTree(host, child, depth + 1); }
    });
  }

  function renderDrumTree() {
    var host = el("soundTree");
    host.textContent = "";
    var choices = drumChoices();
    host.appendChild(soundTreeButton(
      "All percussion sounds", "folder-open", choices.length,
      !SOUND_BROWSER.path, 0,
      function () {
        SOUND_BROWSER.path = "";
        el("soundBrowserSearch").value = "";
        renderSoundBrowser();
      },
      true, choices.length > 0
    ));
    var counts = {};
    var curated = {};
    choices.forEach(function (entry) {
      counts[entry.group] = (counts[entry.group] || 0) + 1;
      if (entry.curated) { curated[entry.group] = true; }
    });
    // Curated groups first, then the catalog folders alphabetically. The one a
    // kit is normally built from should not be somewhere down a list of forty.
    Object.keys(counts).sort(function (left, right) {
      if (!!curated[left] !== !!curated[right]) { return curated[left] ? -1 : 1; }
      return left.localeCompare(right);
    }).forEach(function (group) {
      host.appendChild(soundTreeButton(
        curated[group] ? group : folderLabel(group.split("/").pop()),
        "folder", counts[group],
        SOUND_BROWSER.path === group, 1,
        function () {
          SOUND_BROWSER.path = group;
          el("soundBrowserSearch").value = "";
          renderSoundBrowser();
        },
        false, false
      ));
    });
  }

  function renderSoundTree() {
    if (inDrumKeyMode()) {
      renderDrumTree();
      return;
    }
    var host = el("soundTree");
    host.textContent = "";
    var familyCount = ((STATE.catalog && STATE.catalog.families) || []).length;
    host.appendChild(soundTreeButton(
      "Automatic MIDI mapping", "music-2", null,
      SOUND_BROWSER.mode === "automatic", 0,
      function () { selectSoundMode("automatic"); }, false, false
    ));
    host.appendChild(soundTreeButton(
      "Pitched instruments", "music-2", familyCount,
      SOUND_BROWSER.mode === "families", 0,
      function () { selectSoundMode("families"); }, false, false
    ));
    var divider = document.createElement("div");
    divider.className = "sound-tree-divider";
    host.appendChild(divider);

    if (!SOUND_BROWSER.tree) {
      var loading = document.createElement("div");
      loading.className = "sound-result-empty";
      loading.textContent = SOUND_BROWSER.loading ? "Reading installed soundbanks..." : "Sound catalog unavailable.";
      host.appendChild(loading);
      return;
    }
    var root = SOUND_BROWSER.tree;
    host.appendChild(soundTreeButton(
      root.name, "folder-open", root.count,
      SOUND_BROWSER.mode === "events" && SOUND_BROWSER.path === "", 0,
      function () {
        SOUND_BROWSER.mode = "events";
        SOUND_BROWSER.path = "";
        SOUND_BROWSER.page = 0;
        el("soundBrowserSearch").value = "";
        renderSoundBrowser();
      },
      true,
      Object.keys(root.children).length > 0
    ));
    appendFolderTree(host, root, 1);
  }

  function resultRow(kind, value, title, identifier, metadata, eventRecord) {
    var row = document.createElement("div");
    row.className = "sound-result-row" + (kind === "sound" ? "" : " sound-special-row");
    row.setAttribute("role", "option");
    row.setAttribute("tabindex", "0");
    row.dataset.kind = kind;
    row.dataset.value = value || "";

    var main = document.createElement("div");
    main.className = "sound-result-main";
    var name = document.createElement("div");
    name.className = "sound-result-name";
    name.textContent = title;
    main.appendChild(name);
    if (identifier) {
      var id = document.createElement("div");
      id.className = "sound-result-id mono";
      id.textContent = identifier;
      main.appendChild(id);
    }
    if (metadata && metadata.length) {
      var meta = document.createElement("div");
      meta.className = "sound-result-meta";
      metadata.forEach(function (text) {
        if (!text) { return; }
        var item = document.createElement("span");
        item.textContent = text;
        meta.appendChild(item);
      });
      main.appendChild(meta);
    }
    row.appendChild(main);

    if (eventRecord) {
      var audition = document.createElement("button");
      var previewable = eventRecord.previewable !== false;
      audition.type = "button";
      audition.className = "sound-audition";
      audition.title = previewable
        ? "Audition " + eventRecord.name
        : "This game event has no standalone local preview";
      audition.setAttribute(
        "aria-label",
        previewable ? "Audition " + eventRecord.name : "Local preview unavailable for " + eventRecord.name
      );
      audition.disabled = !previewable;
      audition.appendChild(iconElement("volume-2"));
      if (previewable) {
        audition.addEventListener("click", function (event) {
          event.stopPropagation();
          auditionSound(eventRecord, audition);
        });
      }
      row.appendChild(audition);
    } else {
      row.appendChild(document.createElement("span"));
    }

    function choose() { setSoundCandidate(kind, value, title); }
    row.addEventListener("click", function (event) {
      if (!event.target.closest("button")) { choose(); }
    });
    row.addEventListener("dblclick", function (event) {
      if (event.target.closest("button")) { return; }
      choose();
      useSoundBrowserSelection();
    });
    row.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        choose();
      }
    });
    return row;
  }

  function eventDuration(event) {
    var low = Number(event.duration_min || 0);
    var high = Number(event.duration_max || 0);
    if (!isFinite(high) || high <= 0) { return ""; }
    if (Math.abs(high - low) < 0.01) { return high.toFixed(2) + " s"; }
    return low.toFixed(2) + "\u2013" + high.toFixed(2) + " s";
  }

  function inDrumKeyMode() {
    return SOUND_BROWSER.drumKey !== null && SOUND_BROWSER.drumKey !== undefined;
  }

  function drumFolders() {
    return (STATE.catalog && STATE.catalog.drum_folders) || [];
  }

  // Two rules, and both are needed. The folder is the only place the game says
  // what a sound is FOR -- a half-second event is as likely to be a scope chirp
  // as a drum hit -- and the loop flag is the only thing that says whether
  // firing it as a one-shot leaks an emitter. Unknown counts as looping, the
  // same way an exact channel sound treats it.
  function eventIsDrummable(event) {
    if (!event || event.looping !== false || event.looping_known !== true) { return false; }
    var path = event._path || "";
    var folders = drumFolders();
    for (var index = 0; index < folders.length; index += 1) {
      var folder = folders[index];
      if (path === folder || path.indexOf(folder + "/") === 0) { return true; }
    }
    return false;
  }

  // The curated percussion first, then everything the folders allow. The
  // curated names carry hand-written ear-labels -- `play_noise_tom` is a knock
  // on a door and `play_noise_crash` is a shaker -- so they stay at the top
  // where the common choice is one scroll away.
  function drumChoices() {
    var seen = {};
    var out = [];
    drumPool().forEach(function (entry) {
      seen[entry.name.toLowerCase()] = true;
      out.push({
        name: entry.name,
        label: entry.label || humanSoundName(entry.name),
        group: humanCategory(entry.category),
        curated: true,
        event: browserSoundEvent(entry.name)
      });
    });
    var events = (SOUND_BROWSER.catalog && SOUND_BROWSER.catalog.events) || [];
    events.forEach(function (event) {
      if (seen[event.name.toLowerCase()] || !eventIsDrummable(event)) { return; }
      out.push({
        name: event.name,
        label: event.label || humanSoundName(event.name),
        group: event._path,
        curated: false,
        event: event
      });
    });
    return out;
  }

  function filteredDrumSounds() {
    var query = el("soundBrowserSearch").value.trim().toLowerCase();
    return drumChoices().filter(function (entry) {
      if (query) {
        return (entry.name + " " + entry.label + " " + entry.group)
          .toLowerCase().indexOf(query) >= 0;
      }
      return !SOUND_BROWSER.path || entry.group === SOUND_BROWSER.path;
    });
  }

  function renderDrumKeyResults(list, breadcrumb, count) {
    var channel = partByKey(SOUND_BROWSER.part);
    var key = SOUND_BROWSER.drumKey;
    var sounds = filteredDrumSounds();
    var fallback = drumFallback(channel, key);
    breadcrumb.textContent = drumKeyName(channel, key) +
      " \u00b7 " + noteName(key) + " \u00b7 MIDI " + key;
    count.textContent = sounds.length + (sounds.length === 1 ? " sound" : " sounds");

    // Always first, never filtered away: taking a choice back off a key is not
    // a search result, it is the way out of one already made.
    list.appendChild(resultRow(
      "automatic", "", fallback.label, "",
      [fallback.note],
      browserSoundEvent(fallback.sound)
    ));

    sounds.forEach(function (entry) {
      var event = entry.event;
      // Length first. It is what decides whether a sound works as a hit at
      // all: a three-second sample on a sixteenth-note hat does not leak
      // anything, it just piles up voices and turns to mush.
      var metadata = [event ? eventDuration(event) : "", entry.group];
      if (entry.curated) { metadata.push("Curated percussion"); }
      if (event && !event.previewable) {
        metadata.push("In-game only; local preview unavailable");
      }
      list.appendChild(resultRow(
        "sound", entry.name, entry.label, entry.name, metadata, event
      ));
    });
  }

  function filteredSoundEvents() {
    var events = (SOUND_BROWSER.catalog && SOUND_BROWSER.catalog.events) || [];
    var query = el("soundBrowserSearch").value.trim().toLowerCase();
    if (query) {
      return events.filter(function (event) { return event._search.indexOf(query) >= 0; });
    }
    var path = SOUND_BROWSER.path;
    if (!path) { return events; }
    return events.filter(function (event) {
      return event._path === path || event._path.indexOf(path + "/") === 0;
    });
  }

  function renderSoundResults() {
    var list = el("soundResultList");
    list.textContent = "";
    var breadcrumb = el("soundBreadcrumb");
    var count = el("soundResultCount");
    var pageCount = 1;

    if (inDrumKeyMode()) {
      renderDrumKeyResults(list, breadcrumb, count);
    } else if (SOUND_BROWSER.mode === "automatic") {
      var channel = partByKey(SOUND_BROWSER.part);
      breadcrumb.textContent = "Automatic MIDI mapping";
      count.textContent = "1 choice";
      if (channel) {
        var automatic = candidateForChannel(channel);
        automatic.kind = "automatic";
        automatic.value = "";
        automatic.label = channel.is_drums
          ? "Automatic \u2014 General MIDI percussion"
          : "Automatic \u2014 " + humanCategory(channel.auto_family || channel.program_name);
        list.appendChild(resultRow(
          "automatic", "", automatic.label, "",
          ["Uses MIDI program changes and the curated pitched palette"], null
        ));
      }
    } else if (SOUND_BROWSER.mode === "families") {
      var families = (STATE.catalog && STATE.catalog.families) || [];
      breadcrumb.textContent = "Pitched instruments";
      count.textContent = families.length + (families.length === 1 ? " family" : " families");
      families.forEach(function (family) {
        list.appendChild(resultRow(
          "family",
          family.name,
          humanCategory(family.name),
          family.name,
          [noteName(family.lowest) + "\u2013" + noteName(family.highest), "Pitch follows each MIDI note"],
          null
        ));
      });
    } else {
      var query = el("soundBrowserSearch").value.trim();
      var events = filteredSoundEvents();
      pageCount = Math.max(1, Math.ceil(events.length / SOUND_BROWSER.pageSize));
      SOUND_BROWSER.page = clamp(SOUND_BROWSER.page, 0, pageCount - 1);
      var start = SOUND_BROWSER.page * SOUND_BROWSER.pageSize;
      var page = events.slice(start, start + SOUND_BROWSER.pageSize);
      breadcrumb.textContent = query
        ? "Search all DOOM soundbanks"
        : (SOUND_BROWSER.path ? SOUND_BROWSER.path : "All DOOM sounds");
      count.textContent = events.length.toLocaleString() + (events.length === 1 ? " sound" : " sounds");
      if (!page.length) {
        var empty = document.createElement("div");
        empty.className = "sound-result-empty";
        empty.textContent = SOUND_BROWSER.loading
          ? "Reading installed soundbanks..."
          : "No sounds match this view.";
        list.appendChild(empty);
      }
      page.forEach(function (event) {
        var metadata = [
          event._path || "Unfiled",
          event.bus ? "Bus: " + event.bus : "",
          event.looping_known === false
            ? "Loop behavior unknown"
            : (event.looping ? "Looping" : "One-shot"),
          event.previewable ? "Local preview" : "In-game only; local preview unavailable",
          eventDuration(event),
          "Wwise ID " + event.id
        ];
        list.appendChild(resultRow(
          "sound",
          event.name,
          event.label || humanSoundName(event.name),
          event.name,
          metadata,
          event
        ));
      });
    }

    var paginationVisible = SOUND_BROWSER.mode === "events" && !inDrumKeyMode();
    el("soundPagePrevious").hidden = !paginationVisible;
    el("soundPageNext").hidden = !paginationVisible;
    el("soundPageStatus").hidden = !paginationVisible;
    el("soundPagePrevious").disabled = SOUND_BROWSER.page <= 0;
    el("soundPageNext").disabled = SOUND_BROWSER.page >= pageCount - 1;
    el("soundPageStatus").textContent = "Page " + (SOUND_BROWSER.page + 1) + " of " + pageCount;
    list.scrollTop = 0;
    updateSoundSelection();
  }

  function renderSoundBrowser() {
    if (!SOUND_BROWSER.open) { return; }
    var catalog = SOUND_BROWSER.catalog;
    if (SOUND_BROWSER.loading) {
      el("soundBrowserSource").textContent = "Reading soundbanks...";
    } else if (catalog) {
      var total = Number(catalog.count || 0);
      var previewable = Number(catalog.previewable_count || 0);
      if (catalog.source === "game") {
        el("soundBrowserSource").textContent =
          total.toLocaleString() + " installed events \u00b7 " +
          previewable.toLocaleString() + " local previews";
      } else {
        el("soundBrowserSource").textContent = total.toLocaleString() + " palette fallback";
      }
    } else {
      el("soundBrowserSource").textContent = "Catalog unavailable";
    }
    renderSoundTree();
    renderSoundResults();
  }

  function loadSoundBrowserCatalog() {
    if (SOUND_BROWSER.catalog || SOUND_BROWSER.loading || !api()) { return; }
    SOUND_BROWSER.loading = true;
    var token = ++SOUND_BROWSER.request;
    renderSoundBrowser();
    api().sound_catalog().then(function (response) {
      if (token !== SOUND_BROWSER.request) { return; }
      SOUND_BROWSER.loading = false;
      if (!response || !response.ok) {
        fail(response);
        renderSoundBrowser();
        return;
      }
      prepareSoundCatalog(response);
      renderSoundBrowser();
      patchTracks();
    }, function (error) {
      if (token !== SOUND_BROWSER.request) { return; }
      SOUND_BROWSER.loading = false;
      fail(error);
      renderSoundBrowser();
    });
  }

  function stopSoundAudition() {
    SOUND_BROWSER.auditionToken += 1;
    if (SOUND_BROWSER.audition) {
      try { SOUND_BROWSER.audition.stop(); } catch (_error) { /* already ended */ }
      SOUND_BROWSER.audition = null;
    }
  }

  function rememberAuditionBuffer(name, buffer) {
    if (!SOUND_BROWSER.buffers[name]) { SOUND_BROWSER.bufferOrder.push(name); }
    SOUND_BROWSER.buffers[name] = buffer;
    while (SOUND_BROWSER.bufferOrder.length > 24) {
      delete SOUND_BROWSER.buffers[SOUND_BROWSER.bufferOrder.shift()];
    }
  }

  function playAuditionBuffer(eventRecord, buffer, token) {
    if (token !== SOUND_BROWSER.auditionToken || !SOUND_BROWSER.open) { return; }
    var context = ensureAudioContext();
    return context.resume().then(function () {
      if (token !== SOUND_BROWSER.auditionToken || !SOUND_BROWSER.open) { return; }
      var source = context.createBufferSource();
      var gain = context.createGain();
      source.buffer = buffer;
      gain.gain.value = 0.34;
      source.connect(gain);
      gain.connect(AUDIO.master);
      SOUND_BROWSER.audition = source;
      source.onended = function () {
        if (SOUND_BROWSER.audition === source) { SOUND_BROWSER.audition = null; }
      };
      source.start();
      if (buffer.duration > 8) { source.stop(context.currentTime + 8); }
    });
  }

  function auditionSound(eventRecord, button) {
    stopSoundAudition();
    var token = SOUND_BROWSER.auditionToken;
    var cached = SOUND_BROWSER.buffers[eventRecord.name];
    button.disabled = true;
    var promise;
    if (cached) {
      promise = Promise.resolve(cached);
    } else if (!api()) {
      promise = Promise.reject(new Error("The audio bridge is not available"));
    } else {
      promise = api().preview_sound(eventRecord.name).then(function (response) {
        if (!response || !response.ok) {
          throw new Error(response && response.error || "The sound could not be previewed");
        }
        var context = ensureAudioContext();
        return decodeDataUri(context, response.data_uri).then(function (buffer) {
          rememberAuditionBuffer(eventRecord.name, buffer);
          return buffer;
        });
      });
    }
    promise.then(function (buffer) {
      return playAuditionBuffer(eventRecord, buffer, token);
    }).catch(fail).finally(function () {
      if (button && button.isConnected) { button.disabled = false; }
    });
  }

  function openSoundBrowser(partKey) {
    var channel = partByKey(partKey);
    if (!channel) { return; }
    closeMenus();
    closeInspector();
    closeNotifications();
    closeNoteInspector();
    closeChannelInspector();
    pausePlayback();
    SOUND_BROWSER.open = true;
    SOUND_BROWSER.part = channel.key;
    SOUND_BROWSER.drumKey = null;
    SOUND_BROWSER.candidate = candidateForChannel(channel);
    SOUND_BROWSER.page = 0;
    SOUND_BROWSER.path = "";
    SOUND_BROWSER.mode = SOUND_BROWSER.candidate.kind === "family"
      ? "families"
      : (SOUND_BROWSER.candidate.kind === "automatic" ? "automatic" : "events");
    el("soundBrowserSearch").value = "";
    el("soundBrowserSubtitle").textContent =
      partLabel(channel) + " \u00b7 MIDI channel " + (channel.channel + 1);
    el("soundBrowserOverlay").hidden = false;
    if (SOUND_BROWSER.candidate.kind === "sound") {
      var event = browserSoundEvent(SOUND_BROWSER.candidate.value);
      if (event) {
        SOUND_BROWSER.path = event._path;
        expandSoundPath(event._path);
      }
    }
    renderSoundBrowser();
    loadSoundBrowserCatalog();
    setTimeout(function () { el("soundBrowserSearch").focus(); }, 0);
  }

  function openDrumKeyBrowser(partKey, key) {
    var channel = partByKey(partKey);
    if (!channel) { return; }
    openSoundBrowser(partKey);
    if (!SOUND_BROWSER.open) { return; }
    SOUND_BROWSER.drumKey = key;
    SOUND_BROWSER.mode = "events";
    SOUND_BROWSER.path = "";
    el("soundScopeField").hidden = false;
    el("soundScope").value = "song";
    var current = drumKeyChoice(channel, key);
    SOUND_BROWSER.candidate = current.scope === "builtin"
      ? { kind: "automatic", value: "", label: defaultDrumLabel(channel, key) }
      : { kind: "sound", value: current.sound, label: exactSoundLabel(current.sound) };
    el("soundBrowserSubtitle").textContent =
      drumKeyName(channel, key) + " \u00b7 " + noteName(key) +
      " \u00b7 " + partLabel(channel);
    renderSoundBrowser();
  }

  function closeSoundBrowser() {
    if (!SOUND_BROWSER.open) { return; }
    stopSoundAudition();
    SOUND_BROWSER.open = false;
    SOUND_BROWSER.part = null;
    SOUND_BROWSER.drumKey = null;
    el("soundScopeField").hidden = true;
    el("soundBrowserOverlay").hidden = true;
  }

  function useSoundBrowserSelection() {
    var candidate = SOUND_BROWSER.candidate;
    var partKey = SOUND_BROWSER.part;
    if (!candidate || partKey === null || partKey === undefined) { return; }
    if (inDrumKeyMode()) {
      var drumKey = SOUND_BROWSER.drumKey;
      var chosen = candidate.kind === "sound" ? candidate.value : null;
      var everySong = drumScope() === "default";
      closeSoundBrowser();
      openChannelInspector(partKey);
      if (everySong) { setDrumKeyDefault(drumKey, chosen); }
      else { setDrumKeySound(drumKey, chosen); }
      return;
    }
    if (!soundCandidateChanged()) { return; }
    // The user's OWN Follow-MIDI choice, carried across a sound change. null
    // means they never said, and then the incoming sound's own plan decides.
    var savedPart = partEntry(partByKey(partKey));
    var pitchPreference = Object.prototype.hasOwnProperty.call(
      savedPart,
      "pitch_follow_preference"
    ) ? !!savedPart.pitch_follow_preference : null;
    var body = { family: null, sound: null };
    if (candidate.kind === "family") { body.family = candidate.value; }
    function commit() {
      var patch = { channels: {} };
      patch.channels[partKey] = body;
      closeSoundBrowser();
      openChannelInspector(partKey);
      applyPatch(patch, false);
    }
    if (candidate.kind !== "sound") {
      commit();
      return;
    }

    body.sound = candidate.value;
    body.pitch_follow = false;
    body.root_midi = null;
    var useButton = el("soundBrowserUse");
    useButton.disabled = true;
    el("soundSelection").textContent = "Analyzing musical pitch...";
    setBusy(true, "Resolving sound pitch...");
    api().sound_profile(candidate.value, partKey).then(function (response) {
      setBusy(false);
      if (response && response.ok && response.profile && response.pitch_plan) {
        var plan = response.pitch_plan;
        body.root_midi = plan.root_midi !== null && plan.root_midi !== undefined &&
          isFinite(Number(plan.root_midi)) ? Number(plan.root_midi) : null;
        body.pitch_follow = body.root_midi !== null &&
          (pitchPreference === null ? !!plan.pitch_follow : pitchPreference);
        body.root_confidence = Number(plan.root_confidence || 0);
        body.root_source = plan.root_source || null;
        if (!body.pitch_follow && body.root_midi === null) {
          toast("This sound will play unchanged at its natural pitch.");
        }
      } else {
        toast("Pitch analysis was unavailable; this sound will play at natural pitch", "warn");
      }
      commit();
    }, function () {
      setBusy(false);
      toast("Pitch analysis was unavailable; this sound will play at natural pitch", "warn");
      commit();
    }).finally(function () {
      if (useButton && useButton.isConnected) { useButton.disabled = false; }
    });
  }

  function initSoundBrowser() {
    el("soundBrowserClose").addEventListener("click", closeSoundBrowser);
    el("soundBrowserCancel").addEventListener("click", closeSoundBrowser);
    el("soundBrowserUse").addEventListener("click", useSoundBrowserSelection);
    el("soundBrowserOverlay").addEventListener("pointerdown", function (event) {
      if (event.target === this) { closeSoundBrowser(); }
    });
    el("soundBrowserSearch").addEventListener("input", debounce(function () {
      SOUND_BROWSER.mode = "events";
      SOUND_BROWSER.page = 0;
      renderSoundBrowser();
    }, 70));
    el("soundPagePrevious").addEventListener("click", function () {
      SOUND_BROWSER.page = Math.max(0, SOUND_BROWSER.page - 1);
      renderSoundResults();
    });
    el("soundScope").addEventListener("change", function () {
      // The scope changes what the first row means and what the button says,
      // so both are redrawn rather than left describing the other scope.
      if (inDrumKeyMode()) { renderSoundResults(); }
    });
    el("soundPageNext").addEventListener("click", function () {
      SOUND_BROWSER.page += 1;
      renderSoundResults();
    });
  }

  /* ----------------------------------------------------------- piano roll */

  function audibleContextTime() {
    if (!AUDIO.context) { return 0; }
    var clock = AUDIO.context.currentTime;
    if (typeof AUDIO.context.getOutputTimestamp === 'function' && window.performance) {
      var stamp = AUDIO.context.getOutputTimestamp();
      if (stamp && isFinite(stamp.contextTime) && isFinite(stamp.performanceTime)) {
        clock = stamp.contextTime + Math.max(0, performance.now() - stamp.performanceTime) / 1000;
      }
    } else {
      clock -= Number(AUDIO.context.outputLatency || AUDIO.context.baseLatency || 0);
    }
    return clock;
  }

  function currentPosition() {
    if (!AUDIO.playing || !AUDIO.context) { return AUDIO.position; }
    return clamp(
      AUDIO.anchorPosition + Math.max(0, audibleContextTime() - AUDIO.anchorTime) * 1000,
      0,
      (STATE.preview && STATE.preview.duration_ms) || 0
    );
  }

  function timingManifest() {
    return (STATE.preview && STATE.preview.timing) || {
      ticks_per_beat: 480,
      duration_ticks: 0,
      tempo_changes: [{ tick: 0, time_ms: 0, tempo: 500000 }],
      time_signatures: [{ tick: 0, time_ms: 0, numerator: 4, denominator: 4 }]
    };
  }

  function invalidateRollSurface(keepOverview) {
    RENDER.surfaceDirty = true;
    if (!keepOverview) { RENDER.overviewValid = false; }
  }

  function invalidateRollTimeline() {
    invalidateRollSurface(false);
    RENDER.timeDirty = true;
    RENDER.timingKey = '';
    RENDER.timingLines = null;
  }

  function invalidateRollAll() {
    RENDER.surfaceDirty = true;
    RENDER.pitchDirty = true;
    RENDER.timeDirty = true;
    RENDER.timingKey = '';
    RENDER.timingLines = null;
    RENDER.overviewValid = false;
    RENDER.scrollLeft = null;
    RENDER.scrollTop = null;
  }

  function invalidatePreviewRenderCache() {
    RENDER.eventSource = null;
    RENDER.eventIndex = null;
    RENDER.tempoSource = null;
    RENDER.tempoIndex = null;
    RENDER.lineTimingSource = null;
    RENDER.overviewCanvas = null;
    RENDER.transportTenth = null;
    RENDER.transportDuration = null;
    RENDER.scrubberPaintAt = 0;
    invalidateRollAll();
  }

  function syncRollViewportState() {
    var viewport = el('pianoRollViewport');
    var left = viewport.scrollLeft;
    var top = viewport.scrollTop;
    if (RENDER.scrollLeft !== left) {
      RENDER.scrollLeft = left;
      RENDER.surfaceDirty = true;
      RENDER.timeDirty = true;
      RENDER.timingKey = '';
      RENDER.timingLines = null;
      RENDER.overviewValid = false;
    }
    if (RENDER.scrollTop !== top) {
      RENDER.scrollTop = top;
      RENDER.surfaceDirty = true;
      RENDER.pitchDirty = true;
    }
  }

  function rollPalette() {
    if (!RENDER.palette) {
      RENDER.palette = {
        field: css('--field'),
        panel2: css('--panel2'),
        border: css('--border'),
        border2: css('--border2'),
        text: css('--text'),
        muted: css('--muted'),
        accent: css('--accent'),
        rollBlack: css('--rollBlack'),
        rollGrid: css('--rollGrid'),
        rollBeat: css('--rollBeat'),
        keyWhite: css('--keyWhite'),
        keyWhiteText: css('--keyWhiteText'),
        keyBlack: css('--keyBlack'),
        keyBlackText: css('--keyBlackText')
      };
    }
    return RENDER.palette;
  }

  function eventRenderIndex() {
    var source = previewDisplayEvents();
    if (RENDER.eventSource === source && RENDER.eventIndex) { return RENDER.eventIndex; }
    var buckets = [];
    for (var pitch = 0; pitch <= 127; pitch += 1) {
      buckets.push({ records: [], prefixEnds: [] });
    }
    var records = [];
    for (var sourceIndex = 0; sourceIndex < source.length; sourceIndex += 1) {
      var event = source[sourceIndex];
      if (event.pitch === null || event.pitch === undefined) { continue; }
      var eventPitch = Number(event.pitch);
      if (!isFinite(eventPitch) || eventPitch < 0 || eventPitch > 127) { continue; }
      eventPitch = Math.round(eventPitch);
      var eventStart = Math.max(0, Number(event.start) || 0);
      var record = {
        id: String(event.id || ""),
        source: event,
        pitch: eventPitch,
        start: eventStart,
        // The block is the MIDI note. `playedEnd` is where the conversion
        // actually stops it -- a capped sustain or a stolen speaker -- and is
        // drawn as shading on the tail, never as a shorter block. Falls back to
        // `end` so an older manifest still renders.
        end: Math.max(
          eventStart,
          Number(event.midi_end !== undefined && event.midi_end !== null
            ? event.midi_end
            : event.end) || eventStart
        ),
        playedEnd: Math.max(eventStart, Number(event.end) || eventStart),
        channel: Number(event.channel) || 0,
        // Falls back to the channel so a manifest from an older build,
        // which had no part, still renders instead of collapsing to one row.
        part: String(event.part || (Number(event.channel) || 0)),
        color: partColorForKey(String(event.part || (Number(event.channel) || 0))),
        audible: event.audible !== false,
        muted: !!event.muted,
        soloExcluded: !!event.solo_excluded,
        converted: event.converted !== false,
        label: noteName(eventPitch)
      };
      records.push(record);
      buckets[eventPitch].records.push(record);
    }
    buckets.forEach(function (bucket) {
      bucket.records.sort(function (left, right) {
        return left.start - right.start || left.end - right.end;
      });
      var maximumEnd = -Infinity;
      for (var index = 0; index < bucket.records.length; index += 1) {
        maximumEnd = Math.max(maximumEnd, bucket.records[index].end);
        bucket.prefixEnds.push(maximumEnd);
      }
    });
    RENDER.eventSource = source;
    RENDER.eventIndex = { records: records, buckets: buckets };
    return RENDER.eventIndex;
  }

  function lowerBound(values, target) {
    var low = 0;
    var high = values.length;
    while (low < high) {
      var middle = (low + high) >> 1;
      if (values[middle] < target) { low = middle + 1; } else { high = middle; }
    }
    return low;
  }

  function upperBoundRecords(records, target) {
    var low = 0;
    var high = records.length;
    while (low < high) {
      var middle = (low + high) >> 1;
      if (records[middle].start <= target) { low = middle + 1; } else { high = middle; }
    }
    return low;
  }

  function recordsOverlapping(bucket, startMs, endMs, output) {
    var first = lowerBound(bucket.prefixEnds, startMs);
    var limit = upperBoundRecords(bucket.records, endMs);
    for (var index = first; index < limit; index += 1) {
      var record = bucket.records[index];
      if (record.end >= startMs) { output.push(record); }
    }
  }

  function visibleRenderEvents(scrollLeft, scrollTop, width, height) {
    var duration = Math.max(1, Number(STATE.preview && STATE.preview.duration_ms) || 1);
    var startMs = clamp(scrollLeft, 0, ROLL.contentWidth) / ROLL.contentWidth * duration;
    var endMs = clamp(scrollLeft + width, 0, ROLL.contentWidth) / ROLL.contentWidth * duration;
    var firstRow = clamp(Math.floor(scrollTop / ROLL.rowHeight), 0, 127);
    var lastRow = clamp(Math.floor((scrollTop + height) / ROLL.rowHeight), 0, 127);
    var index = eventRenderIndex();
    var visible = [];
    for (var row = firstRow; row <= lastRow; row += 1) {
      recordsOverlapping(index.buckets[127 - row], startMs, endMs, visible);
    }
    return visible;
  }

  function eventGeometry(record, scrollLeft, scrollTop, duration) {
    var startX = contentXAtTime(record.start) - scrollLeft;
    var minimumEnd = record.start + duration / ROLL.contentWidth * 2;
    var endX = contentXAtTime(Math.max(record.end, minimumEnd)) - scrollLeft;
    var eventY = (127 - record.pitch) * ROLL.rowHeight - scrollTop + 1;
    var eventHeight = Math.max(2, ROLL.rowHeight - 2);
    var eventWidth = Math.max(2, endX - startX);
    // Where the sound actually stops inside the block, when that is earlier
    // than the written note-off. Null when the note plays its full length.
    var cutX = null;
    if (record.playedEnd !== undefined && record.playedEnd < record.end) {
      cutX = clamp(contentXAtTime(record.playedEnd) - scrollLeft, startX, startX + eventWidth);
    }
    return {
      x: startX,
      y: eventY,
      width: eventWidth,
      height: eventHeight,
      radius: Math.min(4, eventWidth / 2, eventHeight / 2),
      cutX: cutX
    };
  }

  function shadeCutTail(context, geometry, palette) {
    if (geometry.cutX === null || geometry.cutX === undefined) { return; }
    var tail = geometry.x + geometry.width - geometry.cutX;
    if (tail <= 0.5) { return; }
    context.save();
    context.globalAlpha = 0.62;
    context.fillStyle = palette.field;
    context.fillRect(geometry.cutX, geometry.y, tail, geometry.height);
    context.globalAlpha = 0.9;
    context.strokeStyle = palette.field;
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(geometry.cutX + 0.5, geometry.y);
    context.lineTo(geometry.cutX + 0.5, geometry.y + geometry.height);
    context.stroke();
    context.restore();
  }

  function parseMeter(value) {
    var parts = String(value || '4/4').split('/');
    return {
      numerator: Math.max(1, Number(parts[0]) || 4),
      denominator: Math.max(1, Number(parts[1]) || 4)
    };
  }

  function syncRollSong() {
    var key = hasSong() ? String(STATE.settings.midi) : '';
    if (key === ROLL.songKey) { return; }
    ROLL.songKey = key;
    ROLL.pendingInitialScroll = !!key;
    invalidateRollAll();
    el('pianoRollViewport').scrollLeft = 0;
    el('pianoRollViewport').scrollTop = 0;
    if (!key) { return; }

    var signatures = timingManifest().time_signatures || [];
    var source = signatures.length ? signatures[0] : { numerator: 4, denominator: 4 };
    var value = String(source.numerator) + '/' + String(source.denominator);
    var select = el('timeSignature');
    if (!select.querySelector('option[value="' + value + '"]')) {
      var option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    }
    select.value = value;
    ROLL.meterNumerator = Number(source.numerator) || 4;
    ROLL.meterDenominator = Number(source.denominator) || 4;
  }

  function canvasPixelRatio() {
    return clamp(Number(window.devicePixelRatio) || 1, 1, MAX_CANVAS_PIXEL_RATIO);
  }

  function sizeCanvas(canvas, width, height) {
    var ratio = canvasPixelRatio();
    var pixelWidth = Math.max(1, Math.round(width * ratio));
    var pixelHeight = Math.max(1, Math.round(height * ratio));
    canvas.style.width = Math.max(1, width) + 'px';
    canvas.style.height = Math.max(1, height) + 'px';
    var changed = canvas.width !== pixelWidth || canvas.height !== pixelHeight;
    if (canvas.width !== pixelWidth) { canvas.width = pixelWidth; }
    if (canvas.height !== pixelHeight) { canvas.height = pixelHeight; }
    return changed;
  }

  function activePitchCenter() {
    var pitches = previewEvents().map(function (event) { return Number(event.pitch); })
      .filter(function (pitch) { return isFinite(pitch) && pitch >= 0 && pitch <= 127; });
    if (!pitches.length) { return 60; }
    return (Math.min.apply(null, pitches) + Math.max.apply(null, pitches)) / 2;
  }

  function playheadZoomAnchor() {
    if (!hasSong()) { return null; }
    var viewport = el('pianoRollViewport');
    var position = currentPosition();
    var viewportX = contentXAtTime(position) - viewport.scrollLeft;
    if (viewportX < 0 || viewportX > viewport.clientWidth) {
      viewportX = viewport.clientWidth / 2;
    }
    return { position: position, viewportX: viewportX };
  }

  function resizeCanvas(zoomAnchor) {
    var viewport = el('pianoRollViewport');
    if (!viewport || el('workspace').hidden || viewport.clientWidth < 1 || viewport.clientHeight < 1) { return; }

    var oldWidth = Math.max(1, ROLL.contentWidth);
    var oldHeight = Math.max(1, ROLL.contentHeight);
    var centerX = (viewport.scrollLeft + viewport.clientWidth / 2) / oldWidth;
    var centerY = (viewport.scrollTop + viewport.clientHeight / 2) / oldHeight;
    var anchoredToPlayhead = zoomAnchor &&
      typeof zoomAnchor.position === 'number' && isFinite(zoomAnchor.position) &&
      typeof zoomAnchor.viewportX === 'number' && isFinite(zoomAnchor.viewportX);
    var timeScale = ROLL.zoom / 100;
    var pitchScale = Math.min(3, 1 + Math.log(timeScale) / Math.LN2 * 0.4);
    var provisionalWidth = Math.max(1, viewport.clientWidth);
    var provisionalHeight = Math.max(1, viewport.clientHeight);
    var baseRowHeight = Math.max(9, provisionalHeight / 128);
    var extent = el('pianoRollExtent');

    extent.style.width = Math.ceil(provisionalWidth * timeScale) + 'px';
    extent.style.height = Math.ceil(128 * baseRowHeight * pitchScale) + 'px';

    var width = Math.max(1, viewport.clientWidth);
    var height = Math.max(1, viewport.clientHeight);
    baseRowHeight = Math.max(9, height / 128);
    ROLL.viewportWidth = width;
    ROLL.viewportHeight = height;
    ROLL.rowHeight = baseRowHeight * pitchScale;
    ROLL.contentWidth = Math.max(width, width * timeScale);
    ROLL.contentHeight = Math.max(height, 128 * ROLL.rowHeight);
    extent.style.width = Math.ceil(ROLL.contentWidth) + 'px';
    extent.style.height = Math.ceil(ROLL.contentHeight) + 'px';

    var geometryChanged = oldWidth !== ROLL.contentWidth || oldHeight !== ROLL.contentHeight;
    geometryChanged = sizeCanvas(el('pianoRoll'), width, height) || geometryChanged;
    geometryChanged = sizeCanvas(el('pianoRollOverlay'), width, height) || geometryChanged;
    geometryChanged = sizeCanvas(el('timeRuler'), width, 31) || geometryChanged;
    geometryChanged = sizeCanvas(el('timeRulerOverlay'), width, 31) || geometryChanged;
    geometryChanged = sizeCanvas(el('pitchRuler'), 72, height) || geometryChanged;
    if (geometryChanged) { invalidateRollAll(); }

    if (ROLL.pendingInitialScroll) {
      var pitch = activePitchCenter();
      viewport.scrollLeft = 0;
      viewport.scrollTop = clamp(
        (127 - pitch + 0.5) * ROLL.rowHeight - height / 2,
        0,
        Math.max(0, ROLL.contentHeight - height)
      );
      ROLL.pendingInitialScroll = false;
    } else {
      viewport.scrollLeft = anchoredToPlayhead
        ? clamp(
          contentXAtTime(zoomAnchor.position) - zoomAnchor.viewportX,
          0,
          Math.max(0, ROLL.contentWidth - width)
        )
        : clamp(centerX * ROLL.contentWidth - width / 2, 0, Math.max(0, ROLL.contentWidth - width));
      viewport.scrollTop = clamp(centerY * ROLL.contentHeight - height / 2, 0, Math.max(0, ROLL.contentHeight - height));
    }
    renderHorizontalScrollLock();
    drawPianoRoll();
  }

  /* --------------------------------------------------------------- layout */

  function storedTracksWidth() {
    try {
      var value = Number(localStorage.getItem(TRACKS_WIDTH_KEY));
      return isFinite(value) && value > 0 ? value : TRACKS_DEFAULT_WIDTH;
    } catch (_error) {
      return TRACKS_DEFAULT_WIDTH;
    }
  }

  function paneSplitBounds() {
    var workspace = el('workspace');
    var splitter = el('paneSplitter');
    var available = workspace.clientWidth - splitter.offsetWidth;
    if (available < 1) { return { min: TRACKS_MIN_WIDTH, max: 720 }; }
    var maximum = Math.max(TRACKS_MIN_WIDTH, available - ROLL_MIN_WIDTH);
    return { min: Math.min(TRACKS_MIN_WIDTH, maximum), max: maximum };
  }

  function queueCanvasResize() {
    if (CANVAS_RESIZE_QUEUED) { return; }
    CANVAS_RESIZE_QUEUED = true;
    requestAnimationFrame(function () {
      CANVAS_RESIZE_QUEUED = false;
      resizeCanvas();
    });
  }

  function applyTracksWidth(value, persist, keepPreference) {
    var workspace = el('workspace');
    var splitter = el('paneSplitter');
    var bounds = paneSplitBounds();
    var width = Math.round(clamp(Number(value) || TRACKS_DEFAULT_WIDTH, bounds.min, bounds.max));
    if (!keepPreference) { TRACKS_PREFERRED_WIDTH = width; }
    workspace.style.setProperty('--tracks-width', width + 'px');
    splitter.setAttribute('aria-valuemin', String(Math.round(bounds.min)));
    splitter.setAttribute('aria-valuemax', String(Math.round(bounds.max)));
    splitter.setAttribute('aria-valuenow', String(width));
    splitter.setAttribute('aria-valuetext', width + ' pixels for channels');
    if (persist) {
      try { localStorage.setItem(TRACKS_WIDTH_KEY, String(TRACKS_PREFERRED_WIDTH)); } catch (_error) { /* local only */ }
    }
    queueCanvasResize();
  }

  function constrainPaneSplit() {
    applyTracksWidth(TRACKS_PREFERRED_WIDTH, false, true);
  }

  function movePaneSplit(event) {
    if (!PANE_SPLIT_DRAG || PANE_SPLIT_DRAG.pointer !== event.pointerId) { return; }
    var workspace = el('workspace');
    var rect = workspace.getBoundingClientRect();
    applyTracksWidth(event.clientX - rect.left - workspace.clientLeft, false, false);
  }

  function endPaneSplit(event) {
    if (!PANE_SPLIT_DRAG || PANE_SPLIT_DRAG.pointer !== event.pointerId) { return; }
    var splitter = el('paneSplitter');
    PANE_SPLIT_DRAG = null;
    splitter.classList.remove('dragging');
    document.body.classList.remove('pane-resizing');
    try { splitter.releasePointerCapture(event.pointerId); } catch (_error) { /* already released */ }
    applyTracksWidth(TRACKS_PREFERRED_WIDTH, true, false);
  }

  function initPaneSplitter() {
    var splitter = el('paneSplitter');
    TRACKS_PREFERRED_WIDTH = storedTracksWidth();
    applyTracksWidth(TRACKS_PREFERRED_WIDTH, false, true);
    splitter.addEventListener('pointerdown', function (event) {
      if (event.button !== 0) { return; }
      event.preventDefault();
      PANE_SPLIT_DRAG = { pointer: event.pointerId };
      splitter.classList.add('dragging');
      document.body.classList.add('pane-resizing');
      splitter.setPointerCapture(event.pointerId);
      movePaneSplit(event);
    });
    splitter.addEventListener('pointermove', movePaneSplit);
    splitter.addEventListener('pointerup', endPaneSplit);
    splitter.addEventListener('pointercancel', endPaneSplit);
    splitter.addEventListener('dblclick', function () {
      TRACKS_PREFERRED_WIDTH = TRACKS_DEFAULT_WIDTH;
      applyTracksWidth(TRACKS_PREFERRED_WIDTH, true, false);
    });
    splitter.addEventListener('keydown', function (event) {
      var bounds = paneSplitBounds();
      var width = el('tracksPane').offsetWidth;
      if (event.key === 'ArrowLeft') { width -= 16; }
      else if (event.key === 'ArrowRight') { width += 16; }
      else if (event.key === 'Home') { width = bounds.min; }
      else if (event.key === 'End') { width = bounds.max; }
      else { return; }
      event.preventDefault();
      applyTracksWidth(width, true, false);
    });
  }

  function tempoRenderIndex() {
    var timing = timingManifest();
    if (RENDER.tempoSource === timing && RENDER.tempoIndex) { return RENDER.tempoIndex; }
    var source = timing.tempo_changes || [];
    var changes = source.map(function (change) {
      return {
        tick: Number(change.tick) || 0,
        time_ms: Number(change.time_ms) || 0,
        tempo: Number(change.tempo) || 500000
      };
    });
    if (!changes.length) { changes.push({ tick: 0, time_ms: 0, tempo: 500000 }); }
    changes.sort(function (left, right) { return left.tick - right.tick; });
    RENDER.tempoSource = timing;
    RENDER.tempoIndex = changes;
    return changes;
  }

  function markerAt(changes, target, key) {
    var low = 0;
    var high = changes.length;
    while (low < high) {
      var middle = (low + high) >> 1;
      if (changes[middle][key] <= target) { low = middle + 1; } else { high = middle; }
    }
    return changes[Math.max(0, low - 1)];
  }

  function timeAtTick(tick) {
    var timing = timingManifest();
    var marker = markerAt(tempoRenderIndex(), tick, 'tick');
    return Number(marker.time_ms) + (tick - Number(marker.tick)) * Number(marker.tempo) / 1000 / Number(timing.ticks_per_beat || 480);
  }

  function tickAtTime(timeMs) {
    var timing = timingManifest();
    var marker = markerAt(tempoRenderIndex(), timeMs, 'time_ms');
    return Number(marker.tick) + (timeMs - Number(marker.time_ms)) * 1000 * Number(timing.ticks_per_beat || 480) / Number(marker.tempo || 500000);
  }

  function contentXAtTime(timeMs) {
    var duration = Math.max(1, Number(STATE.preview && STATE.preview.duration_ms) || 1);
    return clamp(Number(timeMs) || 0, 0, duration) / duration * ROLL.contentWidth;
  }

  function eachVisibleTick(step, minimumPixels, callback) {
    if (!isFinite(step) || step <= 0) { return; }
    var duration = Math.max(1, Number(STATE.preview && STATE.preview.duration_ms) || 1);
    var viewport = el('pianoRollViewport');
    var startMs = viewport.scrollLeft / ROLL.contentWidth * duration;
    var endMs = (viewport.scrollLeft + ROLL.viewportWidth) / ROLL.contentWidth * duration;
    var startTick = Math.max(0, tickAtTime(startMs));
    var endTick = Math.max(startTick, tickAtTime(endMs));
    var maximumSamples = Math.max(2, Math.ceil(ROLL.viewportWidth / Math.max(1, minimumPixels)) + 2);
    var stride = Math.max(1, Math.ceil((endTick - startTick) / step / maximumSamples));
    var actualStep = step * stride;
    var first = Math.max(0, Math.floor(startTick / actualStep) * actualStep);
    for (var tick = first; tick <= endTick + actualStep; tick += actualStep) {
      callback(tick, contentXAtTime(timeAtTick(tick)) - viewport.scrollLeft);
    }
  }

  function timingLines() {
    var timing = timingManifest();
    var viewport = el('pianoRollViewport');
    var key = [
      viewport.scrollLeft,
      ROLL.contentWidth,
      ROLL.viewportWidth,
      ROLL.gridDenominator,
      ROLL.meterNumerator,
      ROLL.meterDenominator
    ].join('|');
    if (RENDER.lineTimingSource === timing && RENDER.timingKey === key && RENDER.timingLines) {
      return RENDER.timingLines;
    }
    var ticksPerBeat = Number(timing.ticks_per_beat) || 480;
    var gridTicks = ticksPerBeat * 4 / ROLL.gridDenominator;
    var barTicks = ticksPerBeat * 4 / ROLL.meterDenominator * ROLL.meterNumerator;
    var lines = { grid: [], bars: [] };
    var lastGridX = -Infinity;
    var lastBarX = -Infinity;

    eachVisibleTick(gridTicks, 4, function (_tick, x) {
      if (x >= -1 && x <= ROLL.viewportWidth + 1 && x - lastGridX >= 4) {
        lines.grid.push(x);
        lastGridX = x;
      }
    });
    eachVisibleTick(barTicks, 18, function (tick, x) {
      if (x >= -1 && x <= ROLL.viewportWidth + 1 && x - lastBarX >= 18) {
        lines.bars.push({ x: x, number: Math.round(tick / barTicks) + 1 });
        lastBarX = x;
      }
    });
    RENDER.lineTimingSource = timing;
    RENDER.timingKey = key;
    RENDER.timingLines = lines;
    return lines;
  }

  // Erase the whole bitmap, not the logical box drawn into.
  //
  // `sizeCanvas` rounds the backing store to Math.round(width * ratio) device
  // pixels while every draw clears `width` LOGICAL pixels under a `ratio`
  // transform. When that rounding goes up, the rightmost fraction of a device
  // pixel is never cleared. The opaque canvases repaint over it and nothing
  // shows; the two overlays have no background, so that column keeps whatever
  // was last stroked into it. The playhead reaches the right edge at the end of
  // the song and strokes accent blue there, which is how a permanent blue line
  // appeared beside the scrollbar and survived every redraw -- only a canvas
  // resize, which reallocates the bitmap, could clear it.
  function clearCanvas(context, canvas) {
    context.save();
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.restore();
  }

  function prepareContext(canvas) {
    var ratio = canvasPixelRatio();
    var context = canvas.getContext('2d');
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = 'high';
    if ('fontKerning' in context) { context.fontKerning = 'normal'; }
    if ('textRendering' in context) { context.textRendering = 'geometricPrecision'; }
    return context;
  }

  function drawPitchRuler(palette) {
    var canvas = el('pitchRuler');
    var context = prepareContext(canvas);
    var width = 72;
    var height = ROLL.viewportHeight;
    var scrollTop = el('pianoRollViewport').scrollTop;
    var border = palette.border;
    var border2 = palette.border2;
    var white = palette.keyWhite;
    var whiteText = palette.keyWhiteText;
    var black = palette.keyBlack;
    var blackText = palette.keyBlackText;
    var fontSize = clamp(ROLL.rowHeight - 2, 7, 11);

    context.clearRect(0, 0, width, height);
    context.fillStyle = palette.panel2;
    context.fillRect(0, 0, width, height);
    context.font = fontSize + 'px Consolas, monospace';
    context.textAlign = 'right';
    context.textBaseline = 'middle';
    for (var pitch = 0; pitch <= 127; pitch += 1) {
      var y = (127 - pitch) * ROLL.rowHeight - scrollTop;
      if (y + ROLL.rowHeight < 0 || y > height) { continue; }
      var isBlack = !!BLACK_KEYS[pitch % 12];
      context.fillStyle = isBlack ? black : white;
      context.fillRect(0, y, width, ROLL.rowHeight);
      context.strokeStyle = pitch % 12 === 0 ? border2 : border;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(0, Math.round(y) + 0.5);
      context.lineTo(width, Math.round(y) + 0.5);
      context.stroke();
      context.fillStyle = isBlack ? blackText : whiteText;
      context.fillText(noteName(pitch), width - 5, y + ROLL.rowHeight / 2);
    }
    context.strokeStyle = border2;
    context.beginPath();
    context.moveTo(width - 0.5, 0);
    context.lineTo(width - 0.5, height);
    context.stroke();
  }

  function drawTimeRuler(lines, palette) {
    var canvas = el('timeRuler');
    var context = prepareContext(canvas);
    var width = ROLL.viewportWidth;
    var height = 31;
    context.clearRect(0, 0, width, height);
    context.fillStyle = palette.panel2;
    context.fillRect(0, 0, width, height);
    context.strokeStyle = palette.rollGrid;
    lines.grid.forEach(function (x) {
      context.beginPath(); context.moveTo(Math.round(x) + 0.5, 20); context.lineTo(Math.round(x) + 0.5, height); context.stroke();
    });
    context.font = '10px Consolas, monospace';
    context.textAlign = 'left';
    context.textBaseline = 'middle';
    lines.bars.forEach(function (bar) {
      context.strokeStyle = palette.rollBeat;
      context.beginPath(); context.moveTo(Math.round(bar.x) + 0.5, 0); context.lineTo(Math.round(bar.x) + 0.5, height); context.stroke();
      context.fillStyle = palette.muted;
      context.fillText(String(bar.number), Math.max(4, bar.x + 4), 10);
    });
  }

  function noteTextColor(hex) {
    var match = /^#([0-9a-f]{6})$/i.exec(String(hex));
    if (!match) { return '#ffffff'; }
    var value = parseInt(match[1], 16);
    var brightness = ((value >> 16) * 299 + ((value >> 8) & 255) * 587 + (value & 255) * 114) / 1000;
    return brightness > 155 ? '#17181b' : '#ffffff';
  }

  function roundedRectPath(context, x, y, width, height, radius) {
    width = Math.max(0, width);
    height = Math.max(0, height);
    radius = Math.max(0, Math.min(radius, width / 2, height / 2));
    context.beginPath();
    if (typeof context.roundRect === 'function') {
      context.roundRect(x, y, width, height, radius);
      return;
    }
    context.moveTo(x + radius, y);
    context.lineTo(x + width - radius, y);
    context.quadraticCurveTo(x + width, y, x + width, y + radius);
    context.lineTo(x + width, y + height - radius);
    context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    context.lineTo(x + radius, y + height);
    context.quadraticCurveTo(x, y + height, x, y + height - radius);
    context.lineTo(x, y + radius);
    context.quadraticCurveTo(x, y, x + radius, y);
    context.closePath();
  }

  function pianoRollPointer(canvas) {
    if (!NOTE_POINTER) { return null; }
    var rect = canvas.getBoundingClientRect();
    var point = {
      x: NOTE_POINTER.clientX - rect.left,
      y: NOTE_POINTER.clientY - rect.top
    };
    if (point.x < 0 || point.y < 0 || point.x > rect.width || point.y > rect.height) {
      return null;
    }
    return point;
  }

  function fillNoteBlock(context, x, y, width, height, radius, color, alpha, glowing) {
    context.save();
    context.globalAlpha = glowing ? 1 : alpha;
    context.fillStyle = color;
    if (glowing) {
      context.shadowColor = color;
      context.shadowBlur = 7;
    }
    roundedRectPath(context, x, y, width, height, radius);
    context.fill();
    if (glowing) {
      context.shadowBlur = 0;
      context.globalAlpha = 0.16;
      context.fillStyle = '#ffffff';
      roundedRectPath(context, x, y, width, height, radius);
      context.fill();
    }
    context.restore();
  }

  function drawRollBackground(context, width, height, scrollTop, lines, palette) {
    context.clearRect(0, 0, width, height);
    context.fillStyle = palette.field;
    context.fillRect(0, 0, width, height);

    context.fillStyle = palette.rollBlack;
    context.beginPath();
    for (var pitch = 0; pitch <= 127; pitch += 1) {
      var y = (127 - pitch) * ROLL.rowHeight - scrollTop;
      if (y + ROLL.rowHeight < 0 || y > height) { continue; }
      if (BLACK_KEYS[pitch % 12]) { context.rect(0, y, width, ROLL.rowHeight); }
    }
    context.fill();

    [
      { color: palette.border, octave: false },
      { color: palette.border2, octave: true }
    ].forEach(function (group) {
      context.strokeStyle = group.color;
      context.lineWidth = 1;
      context.beginPath();
      for (var rowPitch = 0; rowPitch <= 127; rowPitch += 1) {
        if ((rowPitch % 12 === 0) !== group.octave) { continue; }
        var rowY = (127 - rowPitch) * ROLL.rowHeight - scrollTop;
        if (rowY + ROLL.rowHeight < 0 || rowY > height) { continue; }
        context.moveTo(0, Math.round(rowY) + 0.5);
        context.lineTo(width, Math.round(rowY) + 0.5);
      }
      context.stroke();
    });

    context.strokeStyle = palette.rollGrid;
    context.beginPath();
    lines.grid.forEach(function (x) {
      context.moveTo(Math.round(x) + 0.5, 0);
      context.lineTo(Math.round(x) + 0.5, height);
    });
    context.stroke();
    context.strokeStyle = palette.rollBeat;
    context.beginPath();
    lines.bars.forEach(function (bar) {
      context.moveTo(Math.round(bar.x) + 0.5, 0);
      context.lineTo(Math.round(bar.x) + 0.5, height);
    });
    context.stroke();
  }

  function drawNoteLabel(context, record, geometry, alpha, color) {
    if (ROLL.rowHeight < 14 || geometry.width < 25 || geometry.x < 0) { return; }
    var labelSize = clamp(Math.floor(geometry.height * 0.58), 9, 12);
    context.fillStyle = noteTextColor(color || record.color);
    context.font = '600 ' + labelSize + 'px "Segoe UI", Tahoma, Arial, sans-serif';
    context.textAlign = 'left';
    context.textBaseline = 'middle';
    if (context.measureText(record.label).width <= geometry.width - 8) {
      context.globalAlpha = alpha;
      context.fillText(
        record.label,
        Math.round(geometry.x + 4),
        Math.round(geometry.y + geometry.height / 2)
      );
    }
  }


  function noteVisual(record, palette) {
    var focusedOut = SELECTED_PART !== null && SELECTED_PART !== record.part;
    var inactive = record.muted || record.soloExcluded || !record.audible || !record.converted;
    var alpha = inactive ? 0.38 : 0.88;
    var labelAlpha = inactive ? 0.72 : 1;
    if (focusedOut) {
      alpha = Math.min(alpha, 0.2);
      labelAlpha = Math.min(labelAlpha, 0.42);
    }
    return {
      color: inactive ? palette.muted : record.color,
      alpha: alpha,
      labelAlpha: labelAlpha
    };
  }
  function drawStaticNotes(context, records, scrollLeft, scrollTop, width, height, duration, palette) {
    var detailed = ROLL.rowHeight >= 12 && ROLL.zoom > 140;
    var cuts = [];
    if (!detailed) {
      var batches = {};
      records.forEach(function (record) {
        var geometry = eventGeometry(record, scrollLeft, scrollTop, duration);
        if (geometry.x + geometry.width < 0 || geometry.x > width ||
            geometry.y + geometry.height < 0 || geometry.y > height) { return; }
        var visual = noteVisual(record, palette);
        var key = visual.color + '|' + visual.alpha;
        if (!batches[key]) {
          batches[key] = { color: visual.color, alpha: visual.alpha, blocks: [] };
        }
        batches[key].blocks.push(geometry);
        if (geometry.cutX !== null) { cuts.push(geometry); }
      });
      Object.keys(batches).forEach(function (key) {
        var batch = batches[key];
        context.fillStyle = batch.color;
        context.globalAlpha = batch.alpha;
        context.beginPath();
        batch.blocks.forEach(function (geometry) {
          context.rect(geometry.x, geometry.y, geometry.width, geometry.height);
        });
        context.fill();
      });
      context.globalAlpha = 1;
      cuts.forEach(function (geometry) { shadeCutTail(context, geometry, palette); });
      return;
    }

    records.forEach(function (record) {
      var geometry = eventGeometry(record, scrollLeft, scrollTop, duration);
      if (geometry.x + geometry.width < 0 || geometry.x > width ||
          geometry.y + geometry.height < 0 || geometry.y > height) { return; }
      var visual = noteVisual(record, palette);
      fillNoteBlock(
        context,
        geometry.x,
        geometry.y,
        geometry.width,
        geometry.height,
        geometry.radius,
        visual.color,
        visual.alpha,
        false
      );
      shadeCutTail(context, geometry, palette);
      drawNoteLabel(
        context,
        record,
        geometry,
        visual.labelAlpha,
        visual.color
      );
    });
    context.globalAlpha = 1;
  }

  function canCacheOverview() {
    var ratio = canvasPixelRatio();
    var pixels = ROLL.viewportWidth * ROLL.contentHeight * ratio * ratio;
    return ROLL.contentWidth <= ROLL.viewportWidth + 1 &&
      pixels <= OVERVIEW_CACHE_PIXEL_BUDGET;
  }

  function overviewSurface(lines, palette, duration) {
    if (RENDER.overviewValid && RENDER.overviewCanvas) { return RENDER.overviewCanvas; }
    if (!RENDER.overviewCanvas) { RENDER.overviewCanvas = document.createElement('canvas'); }
    var canvas = RENDER.overviewCanvas;
    sizeCanvas(canvas, ROLL.viewportWidth, ROLL.contentHeight);
    var context = prepareContext(canvas);
    drawRollBackground(context, ROLL.viewportWidth, ROLL.contentHeight, 0, lines, palette);
    drawStaticNotes(
      context,
      eventRenderIndex().records,
      0,
      0,
      ROLL.viewportWidth,
      ROLL.contentHeight,
      duration,
      palette
    );
    RENDER.overviewValid = true;
    return canvas;
  }

  function drawStaticRoll(lines, palette) {
    var canvas = el('pianoRoll');
    var context = prepareContext(canvas);
    var viewport = el('pianoRollViewport');
    var width = ROLL.viewportWidth;
    var height = ROLL.viewportHeight;
    var duration = Math.max(1, Number(STATE.preview && STATE.preview.duration_ms) || 1);
    if (canCacheOverview()) {
      var source = overviewSurface(lines, palette, duration);
      var ratio = canvasPixelRatio();
      var sourceY = Math.max(0, Math.round(viewport.scrollTop * ratio));
      var sourceHeight = Math.min(source.height - sourceY, Math.round(height * ratio));
      context.clearRect(0, 0, width, height);
      context.fillStyle = palette.field;
      context.fillRect(0, 0, width, height);
      if (sourceHeight > 0) {
        context.drawImage(
          source,
          0,
          sourceY,
          source.width,
          sourceHeight,
          0,
          0,
          width,
          sourceHeight / ratio
        );
      }
    } else {
      drawRollBackground(context, width, height, viewport.scrollTop, lines, palette);
      drawStaticNotes(
        context,
        visibleRenderEvents(viewport.scrollLeft, viewport.scrollTop, width, height),
        viewport.scrollLeft,
        viewport.scrollTop,
        width,
        height,
        duration,
        palette
      );
    }
    RENDER.surfaceDirty = false;
  }

  function hoveredRenderEvent(canvas) {
    var point = pianoRollPointer(canvas);
    if (!point) { return null; }
    var viewport = el('pianoRollViewport');
    var row = Math.floor((point.y + viewport.scrollTop) / ROLL.rowHeight);
    if (row < 0 || row > 127) { return null; }
    var duration = Math.max(1, Number(STATE.preview && STATE.preview.duration_ms) || 1);
    var time = clamp(point.x + viewport.scrollLeft, 0, ROLL.contentWidth) /
      ROLL.contentWidth * duration;
    var tolerance = duration / ROLL.contentWidth * 2;
    var candidates = [];
    recordsOverlapping(eventRenderIndex().buckets[127 - row], time - tolerance, time + tolerance, candidates);
    for (var index = candidates.length - 1; index >= 0; index -= 1) {
      var candidate = candidates[index];
      if (SELECTED_PART !== null && SELECTED_PART !== candidate.part) { continue; }
      var geometry = eventGeometry(
        candidate, viewport.scrollLeft, viewport.scrollTop, duration);
      if (point.x >= geometry.x && point.x <= geometry.x + geometry.width &&
          point.y >= geometry.y && point.y <= geometry.y + geometry.height) {
        return { record: candidate, geometry: geometry };
      }
    }
    return null;
  }

  function drawRollOverlays(position, palette) {
    var canvas = el('pianoRollOverlay');
    var context = prepareContext(canvas);
    var width = ROLL.viewportWidth;
    var height = ROLL.viewportHeight;
    clearCanvas(context, canvas);

    if (SELECTED_NOTE_ID) {
      var selectedRecords = eventRenderIndex().records;
      for (var selectedIndex = 0; selectedIndex < selectedRecords.length; selectedIndex += 1) {
        var selected = selectedRecords[selectedIndex];
        if (selected.id !== SELECTED_NOTE_ID) { continue; }
        var selectedGeometry = eventGeometry(
          selected,
          el('pianoRollViewport').scrollLeft,
          el('pianoRollViewport').scrollTop,
          Math.max(1, Number(STATE.preview && STATE.preview.duration_ms) || 1)
        );
        context.save();
        context.strokeStyle = palette.accent;
        context.lineWidth = 2;
        roundedRectPath(
          context,
          selectedGeometry.x + 1,
          selectedGeometry.y + 1,
          Math.max(1, selectedGeometry.width - 2),
          Math.max(1, selectedGeometry.height - 2),
          Math.max(0, selectedGeometry.radius - 1)
        );
        context.stroke();
        context.restore();
        break;
      }
    }

    var hovered = hoveredRenderEvent(el('pianoRoll'));
    if (hovered) {
      var geometry = hovered.geometry;
      var visual = noteVisual(hovered.record, palette);
      fillNoteBlock(
        context,
        geometry.x,
        geometry.y,
        geometry.width,
        geometry.height,
        geometry.radius,
        visual.color,
        1,
        true
      );
      shadeCutTail(context, geometry, palette);
      drawNoteLabel(context, hovered.record, geometry, 1, visual.color);
      context.globalAlpha = 1;
    }

    var playheadX = contentXAtTime(position) - el('pianoRollViewport').scrollLeft;
    if (playheadX >= -1 && playheadX <= width + 1) {
      context.strokeStyle = palette.accent;
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(playheadX, 0);
      context.lineTo(playheadX, height);
      context.stroke();
    }

    var rulerCanvas = el('timeRulerOverlay');
    var ruler = prepareContext(rulerCanvas);
    clearCanvas(ruler, rulerCanvas);
    if (playheadX >= -1 && playheadX <= width + 1) {
      ruler.strokeStyle = palette.accent;
      ruler.lineWidth = 2;
      ruler.beginPath();
      ruler.moveTo(playheadX, 0);
      ruler.lineTo(playheadX, 31);
      ruler.stroke();
      ruler.fillStyle = palette.accent;
      ruler.beginPath();
      ruler.moveTo(playheadX - 5, 0);
      ruler.lineTo(playheadX + 5, 0);
      ruler.lineTo(playheadX, 7);
      ruler.closePath();
      ruler.fill();
    }
  }

  function drawPianoRoll(positionOverride) {
    if (DRAW_FRAME !== null) {
      cancelAnimationFrame(DRAW_FRAME);
      DRAW_FRAME = null;
    }
    var canvas = el('pianoRoll');
    if (!canvas || canvas.width <= 1 || canvas.height <= 1 || canvas.hidden ||
        ROLL.viewportWidth <= 1 || ROLL.viewportHeight <= 1) { return; }
    syncRollViewportState();
    var palette = rollPalette();
    var lines = timingLines();
    if (RENDER.surfaceDirty) { drawStaticRoll(lines, palette); }
    if (RENDER.pitchDirty) {
      drawPitchRuler(palette);
      RENDER.pitchDirty = false;
    }
    if (RENDER.timeDirty) {
      drawTimeRuler(lines, palette);
      RENDER.timeDirty = false;
    }
    var position = positionOverride === undefined ? currentPosition() : positionOverride;
    drawRollOverlays(position, palette);
  }

  function queueDraw() {
    if (DRAW_FRAME !== null) { return; }
    DRAW_FRAME = requestAnimationFrame(function () {
      DRAW_FRAME = null;
      drawPianoRoll();
    });
  }

  function positionFromClientX(clientX) {
    var canvas = el('pianoRoll');
    var rect = canvas.getBoundingClientRect();
    var x = clamp(clientX - rect.left + el('pianoRollViewport').scrollLeft, 0, ROLL.contentWidth);
    return x / ROLL.contentWidth * ((STATE.preview && STATE.preview.duration_ms) || 0);
  }

  function positionFromCanvas(event) { return positionFromClientX(event.clientX); }

  function updateNotePointer(event) {
    NOTE_POINTER = { clientX: event.clientX, clientY: event.clientY };
    el("pianoRoll").classList.toggle(
      "note-hover",
      !!hoveredRenderEvent(el("pianoRoll"))
    );
    queueDraw();
  }

  function clearNotePointer() {
    NOTE_POINTER = null;
    el("pianoRoll").classList.remove("note-hover");
    queueDraw();
  }

  function revealPlayhead(position, following) {
    var viewport = el('pianoRollViewport');
    if (ROLL.contentWidth <= ROLL.viewportWidth) { return; }
    var x = contentXAtTime(position);
    if (following) {
      var leadingEdge = viewport.scrollLeft + ROLL.viewportWidth * 0.78;
      var trailingEdge = viewport.scrollLeft + ROLL.viewportWidth * 0.18;
      if (x > leadingEdge || x < trailingEdge) {
        var anchor = ROLL.viewportWidth * 0.32;
        viewport.scrollLeft = clamp(x - anchor, 0, ROLL.contentWidth - ROLL.viewportWidth);
      }
    } else if (x < viewport.scrollLeft || x > viewport.scrollLeft + ROLL.viewportWidth) {
      viewport.scrollLeft = clamp(x - ROLL.viewportWidth / 2, 0, ROLL.contentWidth - ROLL.viewportWidth);
    }
  }

  function setPosition(position, reveal) {
    var duration = (STATE.preview && STATE.preview.duration_ms) || 0;
    AUDIO.position = clamp(Number(position) || 0, 0, duration);
    if (reveal !== false) { revealPlayhead(AUDIO.position, false); }
    renderPosition(AUDIO.position, true);
  }

  function canvasSeekScrollSpeed(clientX) {
    var rect = el('pianoRoll').getBoundingClientRect();
    var edge = Math.min(56, rect.width * 0.14);
    if (clientX < rect.left + edge) {
      return -Math.min(28, Math.max(1, (rect.left + edge - clientX) / edge * 28));
    }
    if (clientX > rect.right - edge) {
      return Math.min(28, Math.max(1, (clientX - (rect.right - edge)) / edge * 28));
    }
    return 0;
  }

  function continueCanvasSeekScroll() {
    if (!SEEK_DRAG) { return; }
    var viewport = el('pianoRollViewport');
    var speed = canvasSeekScrollSpeed(SEEK_DRAG.clientX);
    if (speed) {
      var before = viewport.scrollLeft;
      viewport.scrollLeft = clamp(before + speed, 0, ROLL.contentWidth - ROLL.viewportWidth);
      if (viewport.scrollLeft !== before) {
        setPosition(positionFromClientX(SEEK_DRAG.clientX), false);
      }
    }
    SEEK_DRAG.frame = requestAnimationFrame(continueCanvasSeekScroll);
  }

  function beginCanvasSeek(event) {
    if (!hasSong()) { return; }
    NOTE_POINTER = { clientX: event.clientX, clientY: event.clientY };
    var hit = hoveredRenderEvent(el("pianoRoll"));
    if (hit && hit.record && hit.record.id) {
      event.preventDefault();
      pausePlayback();
      openNoteInspector(hit.record.id);
      return;
    }
    event.preventDefault();
    var wasPlaying = AUDIO.playing;
    pausePlayback();
    SEEK_DRAG = { pointer: event.pointerId, resume: wasPlaying, clientX: event.clientX, frame: null };
    el('pianoRoll').setPointerCapture(event.pointerId);
    setPosition(positionFromCanvas(event), false);
    SEEK_DRAG.frame = requestAnimationFrame(continueCanvasSeekScroll);
  }

  function moveCanvasSeek(event) {
    if (!SEEK_DRAG || SEEK_DRAG.pointer !== event.pointerId) { return; }
    SEEK_DRAG.clientX = event.clientX;
    setPosition(positionFromCanvas(event), false);
  }

  function endCanvasSeek(event) {
    if (!SEEK_DRAG || SEEK_DRAG.pointer !== event.pointerId) { return; }
    var resume = SEEK_DRAG.resume;
    if (SEEK_DRAG.frame !== null) { cancelAnimationFrame(SEEK_DRAG.frame); }
    SEEK_DRAG = null;
    try { el('pianoRoll').releasePointerCapture(event.pointerId); } catch (_error) { /* already released */ }
    if (resume) { startPlayback(); }
    else if (event.type === 'pointercancel') { clearNotePointer(); }
    else { updateNotePointer(event); }
  }

  /* --------------------------------------------------------------- audio */

  function ensureAudioContext() {
    if (AUDIO.context) { return AUDIO.context; }
    var AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) { throw new Error('This WebView cannot create an audio context'); }
    AUDIO.context = new AudioContextClass();
    var compressor = AUDIO.context.createDynamicsCompressor();
    compressor.threshold.value = -10;
    compressor.knee.value = 18;
    compressor.ratio.value = 8;
    compressor.attack.value = 0.004;
    compressor.release.value = 0.18;
    AUDIO.master = AUDIO.context.createGain();
    AUDIO.master.gain.value = 0.72;
    AUDIO.master.connect(compressor);
    compressor.connect(AUDIO.context.destination);
    return AUDIO.context;
  }

  function decodeDataUri(context, uri) {
    return fetch(uri)
      .then(function (response) { return response.arrayBuffer(); })
      .then(function (buffer) { return context.decodeAudioData(buffer); });
  }

  function requiredAudioNames() {
    return (STATE.preview && STATE.preview.sounds) || [];
  }

  function audioKey() {
    return requiredAudioNames().join('\n');
  }

  function retainRequiredBuffers() {
    var keep = {};
    var unavailable = {};
    requiredAudioNames().forEach(function (name) {
      if (AUDIO.buffers[name]) { keep[name] = AUDIO.buffers[name]; }
      if (AUDIO.unavailable[name]) { unavailable[name] = true; }
    });
    AUDIO.buffers = keep;
    AUDIO.unavailable = unavailable;
  }

  function invalidateAudio(clearBuffers) {
    PLAY_TOKEN += 1;
    stopSources();
    AUDIO.key = '';
    AUDIO.prepareError = null;
    if (clearBuffers) {
      AUDIO.generation += 1;
      AUDIO.buffers = {};
      AUDIO.unavailable = {};
      AUDIO.loading = null;
      AUDIO.preparing = false;
    } else {
      retainRequiredBuffers();
    }
  }

  function ensureSongAudio(background) {
    if (!STATE.audio || !STATE.audio.ready) {
      return Promise.reject(new Error(
        'DOOM audio is unavailable. Install DOOM or configure its install directory to preview this song.'
      ));
    }
    if (!api()) { return Promise.reject(new Error('The audio bridge is not available')); }

    var key = audioKey();
    var missing = requiredAudioNames().filter(function (name) {
      return !AUDIO.buffers[name] && !AUDIO.unavailable[name];
    });
    if (!missing.length) {
      AUDIO.key = key;
      AUDIO.prepareError = null;
      return Promise.resolve();
    }

    if (AUDIO.loading) {
      if (AUDIO.loading.key === key) { return AUDIO.loading.promise; }
      return AUDIO.loading.promise.catch(function () {}).then(function () {
        return ensureSongAudio(background);
      });
    }

    var context;
    try { context = ensureAudioContext(); } catch (error) { return Promise.reject(error); }
    var generation = AUDIO.generation;
    AUDIO.preparing = true;
    AUDIO.prepareError = null;
    if (!background) { setBusy(true, 'Preparing song audio...'); }
    renderAudio();

    var promise = api().preview_samples(missing).then(function (response) {
      if (!response || !response.ok) {
        throw new Error(response && response.error || 'Song audio could not be loaded');
      }
      if (generation === AUDIO.generation) {
        (response.missing || []).forEach(function (name) { AUDIO.unavailable[name] = true; });
      }
      var names = Object.keys(response.samples || {});
      return Promise.all(names.map(function (name) {
        return decodeDataUri(context, response.samples[name]).then(function (buffer) {
          return [name, buffer];
        });
      }));
    }).then(function (pairs) {
      if (generation !== AUDIO.generation) { return; }
      var stillRequired = {};
      requiredAudioNames().forEach(function (name) { stillRequired[name] = true; });
      pairs.forEach(function (pair) {
        if (stillRequired[pair[0]]) { AUDIO.buffers[pair[0]] = pair[1]; }
      });
      retainRequiredBuffers();
      var currentMissing = requiredAudioNames().some(function (name) {
        return !AUDIO.buffers[name] && !AUDIO.unavailable[name];
      });
      AUDIO.key = currentMissing ? '' : audioKey();
      AUDIO.prepareError = null;
    }).catch(function (error) {
      if (generation === AUDIO.generation) {
        AUDIO.prepareError = error && error.message || String(error);
      }
      throw error;
    }).finally(function () {
      if (!background) { setBusy(false); }
      if (AUDIO.loading && AUDIO.loading.promise === promise) {
        AUDIO.loading = null;
        AUDIO.preparing = false;
        renderAudio();
        renderWarnings();
      }
    });
    AUDIO.loading = { key: key, promise: promise };
    return promise;
  }

  function prepareSongAudio() {
    if (!hasSong() || !STATE.audio || !STATE.audio.ready) { return; }
    ensureSongAudio(true).catch(function () { renderAudio(); });
  }

  function stopPlaybackClock() {
    if (AUDIO.timer !== null) { clearInterval(AUDIO.timer); AUDIO.timer = null; }
    if (AUDIO.frame !== null) { cancelAnimationFrame(AUDIO.frame); AUDIO.frame = null; }
  }

  function stopSources() {
    var sources = AUDIO.sources.slice();
    AUDIO.sources = [];
    sources.forEach(function (source) {
      try { source.stop(); } catch (_error) { /* already ended */ }
    });
    stopPlaybackClock();
  }

  function forgetSource(source) {
    var index = AUDIO.sources.indexOf(source);
    if (index >= 0) { AUDIO.sources.splice(index, 1); }
  }

  function scheduleEvent(event, audiblePosition, when) {
    var buffer = AUDIO.buffers[event.sound];
    if (!buffer || !AUDIO.context || !AUDIO.master) { return; }
    var source = AUDIO.context.createBufferSource();
    var gain = AUDIO.context.createGain();
    source.buffer = buffer;
    var expressionGain = Math.pow(10, Number(event.volume_db || 0) / 20);
    var baseGain = 0.34 * expressionGain;
    gain.gain.value = baseGain;
    var playbackRate = Number(event.playback_rate || 1);
    source.playbackRate.value = playbackRate;
    source.connect(gain);
    gain.connect(AUDIO.master);
    var wallOffset = Math.max(0, (audiblePosition - event.start) / 1000);
    var offset = wallOffset * playbackRate;
    var naturalDuration = buffer.duration / playbackRate;
    var stopAfter;

    if (event.sustained) {
      var release = STATE.preview && !STATE.preview.hard_stop && !event.cut
        ? Number(STATE.preview.release_s || 0)
        : 0;
      var sounding = Math.max(0, (event.end - event.start) / 1000);
      var total = sounding + release;
      if (wallOffset >= total) { return; }
      if (buffer.duration > 0.04 && sounding > naturalDuration) {
        source.loop = true;
        source.loopEnd = buffer.duration;
        offset = offset % buffer.duration;
      } else if (offset >= buffer.duration) {
        return;
      }
      stopAfter = Math.max(0.01, total - Math.max(0, (audiblePosition - event.start) / 1000));
      var noteEndAt = when + Math.max(0, (event.end - audiblePosition) / 1000);
      if (release > 0 && noteEndAt >= AUDIO.context.currentTime) {
        gain.gain.setValueAtTime(baseGain, noteEndAt);
        gain.gain.exponentialRampToValueAtTime(0.001, noteEndAt + release);
      }
      source.start(when, offset);
      source.stop(when + stopAfter);
    } else {
      if (offset >= buffer.duration) { return; }
      source.start(when, offset);
      if (event.cut) {
        var untilCut = Math.max(0, (event.end - audiblePosition) / 1000);
        if (untilCut <= 0) { source.stop(); return; }
        source.stop(when + Math.max(0.01, untilCut));
      }
    }
    AUDIO.sources.push(source);
    source.onended = function () { forgetSource(source); };
  }

  function firstFutureEvent(position) {
    var events = previewEvents();
    var low = 0;
    var high = events.length;
    while (low < high) {
      var middle = Math.floor((low + high) / 2);
      if (events[middle].start < position) { low = middle + 1; } else { high = middle; }
    }
    return low;
  }

  function scheduleActiveAt(position) {
    var events = previewEvents();
    for (var index = 0; index < AUDIO.nextIndex; index += 1) {
      var event = events[index];
      var buffer = AUDIO.buffers[event.sound];
      var end = event.sustained
        ? event.end + (STATE.preview.hard_stop || event.cut ? 0 : Number(STATE.preview.release_s || 0) * 1000)
        : (event.cut
          ? event.end
          : (event.voice_end || (event.start + (buffer ? buffer.duration * 1000 / Number(event.playback_rate || 1) : 0))));
      if (end > position) { scheduleEvent(event, position, AUDIO.context.currentTime + 0.025); }
    }
  }

  function scheduleAhead() {
    if (!AUDIO.playing || !AUDIO.context) { return; }
    var events = previewEvents();
    var position = currentPosition();
    var horizon = position + LOOKAHEAD_MS;
    while (AUDIO.nextIndex < events.length && events[AUDIO.nextIndex].start <= horizon) {
      var event = events[AUDIO.nextIndex];
      var when = AUDIO.anchorTime + (event.start - AUDIO.anchorPosition) / 1000;
      var audible = event.start;
      if (when < AUDIO.context.currentTime + 0.01) {
        audible += (AUDIO.context.currentTime + 0.01 - when) * 1000;
        when = AUDIO.context.currentTime + 0.01;
      }
      scheduleEvent(event, audible, when);
      AUDIO.nextIndex += 1;
    }
  }

  function animationTick() {
    if (!AUDIO.playing) { return; }
    var position = currentPosition();
    var duration = (STATE.preview && STATE.preview.duration_ms) || 0;
    if (position >= duration) {
      finishPlayback();
      return;
    }
    renderPosition(position);
    AUDIO.frame = requestAnimationFrame(animationTick);
  }

  function startPlayback() {
    if (!hasSong() || AUDIO.playing) { return; }
    var duration = (STATE.preview && STATE.preview.duration_ms) || 0;
    if (AUDIO.position >= duration) { AUDIO.position = 0; }
    var token = ++PLAY_TOKEN;
    ensureSongAudio().then(function () {
      if (token !== PLAY_TOKEN) { return; }
      return AUDIO.context.resume();
    }).then(function () {
      if (token !== PLAY_TOKEN) { return; }
      // A completed song may still have a finite one-shot or release tail.
      // Starting it again deliberately replaces that tail; ordinary natural
      // completion below leaves it alone so preview matches SnapMap playback.
      stopSources();
      AUDIO.playing = true;
      AUDIO.anchorPosition = AUDIO.position;
      AUDIO.anchorTime = AUDIO.context.currentTime;
      AUDIO.nextIndex = firstFutureEvent(AUDIO.position);
      scheduleActiveAt(AUDIO.position);
      scheduleAhead();
      AUDIO.timer = setInterval(scheduleAhead, SCHEDULE_EVERY_MS);
      AUDIO.frame = requestAnimationFrame(animationTick);
      renderTransportState();
    }).catch(function (error) {
      if (token === PLAY_TOKEN) { fail(error); }
    });
  }

  function pausePlayback() {
    PLAY_TOKEN += 1;
    if (AUDIO.playing) { AUDIO.position = currentPosition(); }
    AUDIO.playing = false;
    stopSources();
    renderTransportState();
    renderPosition(AUDIO.position, true);
  }

  function finishPlayback() {
    PLAY_TOKEN += 1;
    AUDIO.playing = false;
    stopPlaybackClock();
    renderTransportState();
    setPosition(0);
  }

  function togglePlayback() {
    if (AUDIO.playing) { pausePlayback(); } else { startPlayback(); }
  }

  function renderPosition(position, immediate) {
    var duration = (STATE.preview && STATE.preview.duration_ms) || 0;
    var bounded = clamp(position, 0, duration);
    var tenth = Math.floor(bounded / 100);
    var now = window.performance ? performance.now() : Date.now();
    if (immediate || RENDER.transportTenth !== tenth) {
      RENDER.transportTenth = tenth;
      el('currentTime').textContent = formatTime(bounded);
    }
    if (RENDER.transportDuration !== duration) {
      RENDER.transportDuration = duration;
      el('totalTime').textContent = formatTime(duration);
      el('scrubber').max = String(duration);
    }
    if (immediate || !AUDIO.playing || now - RENDER.scrubberPaintAt >= 33) {
      RENDER.scrubberPaintAt = now;
      el('scrubber').value = String(bounded);
    }
    if (AUDIO.playing) { revealPlayhead(position, true); }
    drawPianoRoll(position);
  }

  function renderHorizontalScrollLock() {
    var viewport = el('pianoRollViewport');
    var lock = el('horizontalScrollLock');
    var height = Math.max(0, viewport.offsetHeight - viewport.clientHeight);
    var width = Math.max(0, viewport.offsetWidth - viewport.clientWidth);
    var locked = AUDIO.playing && height > 0 && ROLL.contentWidth > ROLL.viewportWidth;
    lock.hidden = !locked;
    if (!locked) { return; }
    lock.style.height = height + 'px';
    lock.style.right = width + 'px';
  }

  function lockedWheelPixels(event, viewport) {
    if (event.deltaMode === 1) { return event.deltaY * Math.max(16, ROLL.rowHeight); }
    if (event.deltaMode === 2) { return event.deltaY * viewport.clientHeight; }
    return event.deltaY;
  }

  function forwardLockedScrollWheel(event) {
    var viewport = el('pianoRollViewport');
    event.preventDefault();
    viewport.scrollTop += lockedWheelPixels(event, viewport);
  }

  function handleRollScroll() {
    queueDraw();
  }

  function renderTransportState() {
    var playable = hasSong();
    el('transportPlay').disabled = !playable;
    el('scrubber').disabled = !playable;
    setIcon(el('playGlyph'), AUDIO.playing ? 'pause' : 'play');
    el('transportPlay').setAttribute('aria-label', AUDIO.playing ? 'Pause' : 'Play');
    renderHorizontalScrollLock();
    updateMenuState();
  }

  /* ------------------------------------------------ conversion inspector */

  function setDependent(id, enabled) {
    var host = el(id);
    host.classList.toggle('disabled', !enabled);
    var controls = host.querySelectorAll('input, select, button');
    for (var index = 0; index < controls.length; index += 1) {
      controls[index].disabled = !enabled;
    }
  }

  function syncPair(rangeId, numberId, value) {
    el(rangeId).value = String(value);
    el(numberId).value = String(value);
  }

  function usedFamilies() {
    var seen = {};
    previewEvents().forEach(function (event) {
      if (event.family && event.family !== "exact") { seen[event.family] = true; }
    });
    return Object.keys(seen).sort();
  }

  function renderFamilyBehavior() {
    var host = el('familyBehavior');
    host.textContent = '';
    var values = tuning();
    var decaying = values.decaying_families || [];
    var caps = values.family_caps || {};
    var families = usedFamilies();
    if (!families.length) {
      var empty = document.createElement('div');
      empty.className = 'list-empty';
      empty.textContent = 'Open a song to see the categories it uses.';
      host.appendChild(empty);
      return;
    }
    families.forEach(function (family) {
      var row = document.createElement('div');
      row.className = 'family-row';
      var name = document.createElement('span');
      name.className = 'family-name';
      name.textContent = humanCategory(family);
      name.title = family;
      row.appendChild(name);
      var label = document.createElement('label');
      var check = document.createElement('input');
      check.type = 'checkbox';
      check.checked = decaying.indexOf(family) >= 0;
      label.appendChild(check);
      label.appendChild(document.createTextNode(' Fire and forget'));
      row.appendChild(label);
      var cap = document.createElement('input');
      cap.type = 'number';
      cap.min = '1';
      cap.step = '10';
      cap.placeholder = 'sustain ms';
      cap.setAttribute('aria-label', 'Sustain cap for ' + humanCategory(family) + ' in milliseconds');
      cap.value = caps[family] || '';
      row.appendChild(cap);
      check.addEventListener('change', function () {
        var next = (tuning().decaying_families || []).slice();
        var where = next.indexOf(family);
        if (this.checked && where < 0) { next.push(family); }
        if (!this.checked && where >= 0) { next.splice(where, 1); }
        next.sort();
        applyPatch({ tuning: { decaying_families: next } }, true);
      });
      cap.addEventListener('change', function () {
        var nextCaps = Object.assign({}, tuning().family_caps || {});
        if (this.value === '') { delete nextCaps[family]; }
        else { nextCaps[family] = Math.max(1, Math.round(Number(this.value))); }
        applyPatch({ tuning: { family_caps: nextCaps } }, true);
      });
      host.appendChild(row);
    });
  }

  function syncInspector() {
    var values = tuning();
    syncPair('maxSpeakersRange', 'maxSpeakersNumber', values.max_speakers || 32);
    var polyOn = values.max_poly !== null && values.max_poly !== undefined;
    el('polyEnabled').checked = polyOn;
    syncPair('maxPolyRange', 'maxPolyNumber', polyOn ? values.max_poly : 16);
    setDependent('polyControls', polyOn);
    el('hardStop').checked = !!values.hard_stop;
    syncPair('releaseRange', 'releaseNumber', Number(values.release_s || 0));
    setDependent('releaseControls', !values.hard_stop);
    var sustainOn = values.cap_sustain_ms !== null && values.cap_sustain_ms !== undefined;
    el('sustainEnabled').checked = sustainOn;
    syncPair('sustainRange', 'sustainNumber', sustainOn ? values.cap_sustain_ms : 1000);
    setDependent('sustainControls', sustainOn);
    var bassOn = values.bass_cap_ms !== null && values.bass_cap_ms !== undefined;
    el('bassEnabled').checked = bassOn;
    syncPair('bassRange', 'bassNumber', bassOn ? values.bass_cap_ms : 750);
    setDependent('bassControls', bassOn);
    setDependent('bassPitchControls', bassOn);
    el('bassPitchNumber').value = String(values.bass_pitch === undefined ? 78 : values.bass_pitch);
    el('bassPitchName').textContent = noteName(values.bass_pitch === undefined ? 78 : values.bass_pitch);
    renderFamilyBehavior();
  }

  function openInspector() {
    closeNotifications();
    closeNoteInspector();
    closeChannelInspector();
    INSPECTOR_OPEN = true;
    el('conversionInspector').hidden = false;
    el('conversionBtn').setAttribute('aria-expanded', 'true');
    syncInspector();
  }

  function closeInspector() {
    INSPECTOR_OPEN = false;
    el('conversionInspector').hidden = true;
    el('conversionBtn').setAttribute('aria-expanded', 'false');
  }

  function openNotifications() {
    closeInspector();
    closeNoteInspector();
    closeChannelInspector();
    NOTIFICATIONS_OPEN = true;
    el('notificationsInspector').hidden = false;
    el('notificationsBtn').setAttribute('aria-expanded', 'true');
    renderWarnings();
  }

  function closeNotifications() {
    NOTIFICATIONS_OPEN = false;
    el('notificationsInspector').hidden = true;
    el('notificationsBtn').setAttribute('aria-expanded', 'false');
  }

  function toggleNotifications() {
    if (NOTIFICATIONS_OPEN) { closeNotifications(); }
    else { openNotifications(); }
  }

  function percussionMode(channel) {
    return partEntry(channel).percussion || "auto";
  }

  function syncChannelPercussion(channel) {
    var mode = percussionMode(channel);
    el("channelPercussion").value = mode;
    var help = el("channelPercussionHelp");
    // Short, and true of the track in front of you. An earlier draft explained
    // the General MIDI channel-10 convention on every row, which is a fact
    // about one channel out of sixteen -- so fifteen rows out of sixteen were
    // reading a sentence that did not describe them.
    if (mode === "kit") {
      help.textContent = "Plays this track as a drum kit \u2014 each MIDI key is "
        + "one drum sound.";
    } else if (mode === "melodic") {
      help.textContent = "Plays this track as an instrument.";
    } else if (channel.is_drums) {
      help.textContent = "Automatic: channel 10, so this plays as a drum kit.";
    } else {
      help.textContent = "Automatic: plays as an instrument. Choose Drum kit if "
        + "this track is really percussion.";
    }
  }

  function drumKeyRow(channel, key) {
    var choice = drumKeyChoice(channel, key);
    var row = document.createElement("button");
    row.type = "button";
    row.className = "drum-key-row"
      + (choice.sound ? "" : " drum-key-silent")
      + (choice.scope === "builtin" ? "" : " drum-key-chosen");
    row.addEventListener("click", function () {
      openDrumKeyBrowser(channel.key, key);
    });

    var head = document.createElement("div");
    head.className = "drum-key-head";

    var pitch = document.createElement("span");
    pitch.className = "drum-key-note mono";
    pitch.textContent = noteName(key);
    head.appendChild(pitch);

    var name = document.createElement("span");
    name.className = "drum-key-name";
    // The General MIDI name, which is what the composer's editor showed them.
    // 47 of the 128 keys have one; the rest are a kit maker's own business, so
    // they get the honest label rather than an invented drum.
    name.textContent = drumKeyName(channel, key);
    head.appendChild(name);

    var count = Number((channel.pitches || {})[String(key)] || 0);
    var hits = document.createElement("span");
    hits.className = "drum-key-hits mono";
    hits.textContent = count + (count === 1 ? " hit" : " hits");
    head.appendChild(hits);
    row.appendChild(head);

    var sound = document.createElement("div");
    sound.className = "drum-key-sound";
    sound.textContent = choice.sound
      ? exactSoundLabel(choice.sound)
      : "No sound \u2014 this key stays silent";
    if (choice.scope !== "builtin") {
      var chip = document.createElement("span");
      chip.className = "drum-key-chip";
      chip.textContent = choice.scope === "song" ? "this song" : "your default";
      sound.appendChild(chip);
    }
    row.appendChild(sound);

    var origin = { song: "Chosen for this song: ", yours: "Your default: " };
    row.title = "MIDI key " + key + "\n" + (choice.sound
      ? (origin[choice.scope] || "Built-in default: ")
        + choice.sound + "\nClick to change it"
      : "No sound is mapped to this key, so nothing plays. Click to choose one.");
    return row;
  }

  function renderDrumKeys(channel) {
    var group = el("drumKeysGroup");
    var host = el("drumKeyList");
    host.textContent = "";
    var keys = Object.keys((channel && channel.drum_keys) || {});
    group.hidden = !channel.is_drums || !keys.length;
    if (group.hidden) { return; }
    keys.sort(function (left, right) { return Number(left) - Number(right); });
    var silent = keys.filter(function (key) {
      return !drumKeyChoice(channel, Number(key)).sound;
    }).length;
    el("drumKeysCount").textContent = keys.length + (keys.length === 1 ? " key" : " keys")
      + (silent ? " \u00b7 " + silent + " silent" : "");
    keys.forEach(function (key) {
      host.appendChild(drumKeyRow(channel, Number(key)));
    });
  }

  function syncChannelInspector() {
    if (!CHANNEL_INSPECTOR_OPEN) { return; }
    var channel = partByKey(SELECTED_PART);
    if (!channel) {
      closeChannelInspector();
      return;
    }
    var entry = partEntry(channel);
    var exact = !!entry.sound;
    var follow = el("channelPitchFollow");
    var root = entry.root_midi;
    var canFollow = root !== null && root !== undefined &&
      entry.root_source !== "detected_octave_pending";
    el("channelInspectorSubtitle").textContent =
      partLabel(channel) + " - MIDI channel " + (channel.channel + 1);
    el("channelSound").textContent = assignmentLabel(channel);
    el("channelSound").title = assignmentTitle(channel);
    el("channelMidiRange").textContent =
      noteName(channel.lowest) + "-" + noteName(channel.highest);
    el("channelNoteCount").textContent = String(channel.notes || 0);
    syncChannelPercussion(channel);
    renderDrumKeys(channel);

    // Available for every exact sound. A detected root makes following
    // musically faithful; without one it still works, against a neutral
    // reference. Refusing it removed the whole point of pitching an
    // unmusical effect across the keyboard.
    follow.disabled = !exact;
    follow.checked = exact ? !!entry.pitch_follow : !channel.is_drums;
    if (!exact) {
      el("channelPitchModeHelp").textContent = channel.is_drums
        ? "Automatic percussion selects a dedicated sound for each MIDI key; channel-wide pitch following does not apply."
        : (entry.family
          ? "This pitched instrument set always follows the imported MIDI notes."
          : "Automatic musical mapping follows MIDI notes through the curated pitched palette.");
      return;
    }

    if (entry.pitch_follow) {
      el("channelPitchModeHelp").textContent = entry.root_source === "neutral"
        ? "This sound follows the imported MIDI notes, treating " +
          noteName(NEUTRAL_ROOT_MIDI) + " as its own pitch. No musical root was "
          + "detected for it, so that reference is assumed rather than measured."
        : "This sound follows the imported MIDI notes.";
      return;
    }
    el("channelPitchModeHelp").textContent = canFollow
      ? "This sound plays unchanged on every note."
      : "This sound plays unchanged. No musical root was detected for it, so "
        + "Follow MIDI note will make it rise and fall against a neutral " +
        noteName(NEUTRAL_ROOT_MIDI) + ".";
  }

  function openChannelInspector(partKey) {
    var channel = partByKey(partKey);
    if (!channel) { return; }
    closeInspector();
    closeNotifications();
    closeNoteInspector();
    SELECTED_PART = channel.key;
    CHANNEL_INSPECTOR_OPEN = true;
    el("channelInspector").hidden = false;
    syncChannelInspector();
    patchTracks();
  }

  function closeChannelInspector() {
    CHANNEL_INSPECTOR_OPEN = false;
    el("channelInspector").hidden = true;
    if (hasSong()) { patchTracks(); }
  }

  function closeChannelInspectorAndClearSelection() {
    SELECTED_PART = null;
    closeChannelInspector();
    invalidateRollSurface();
    queueDraw();
  }

  function updateSelectedChannelPitchFollow(enabled) {
    var channel = partByKey(SELECTED_PART);
    if (!channel) { return; }
    var saved = partEntry(channel);
    // pitch_follow_preference records that the USER asked for this, so a later
    // sound change can honour the choice instead of re-deciding from scratch.
    var body = { pitch_follow: !!enabled, pitch_follow_preference: !!enabled };
    var usable = saved.root_midi !== null && saved.root_midi !== undefined &&
      saved.root_source !== "detected_octave_pending";
    if (enabled && !usable) {
      // Following needs a reference. Supplying the convention is what makes
      // the switch usable on sounds nothing could measure a root for; the
      // settings document requires a root whenever pitch_follow is on.
      body.root_midi = NEUTRAL_ROOT_MIDI;
      body.root_confidence = 0;
      body.root_source = "neutral";
    }
    applyPatch(partPatch(channel, body), true);
  }

  function initChannelInspector() {
    el("closeChannelInspector").addEventListener(
      "click",
      closeChannelInspectorAndClearSelection
    );
    el("channelPercussion").addEventListener("change", function () {
      var channel = partByKey(SELECTED_PART);
      if (!channel) { return; }
      applyPatch(partPatch(channel, { percussion: this.value }), true);
    });
    el("channelPitchFollow").addEventListener("change", function () {
      var saved = partEntry(partByKey(SELECTED_PART));
      if (!saved.sound) {
        syncChannelInspector();
        return;
      }
      updateSelectedChannelPitchFollow(this.checked);
    });
  }

  function noteEventById(noteId) {
    var events = previewDisplayEvents();
    for (var index = 0; index < events.length; index += 1) {
      if (String(events[index].id || "") === String(noteId || "")) { return events[index]; }
    }
    return null;
  }

  function selectedNoteEvent() {
    return noteEventById(SELECTED_NOTE_ID);
  }

  function notePitchOverrideKey(noteId) {
    var note = noteEventById(noteId);
    if (!note) { return null; }
    return note.pitch_follow ? "follow_pitch_semitones" : "pitch_semitones";
  }

  function signed(value) {
    value = Number(value) || 0;
    return (value > 0 ? "+" : "") + String(value);
  }

  function normalizedMasterVolume(value) {
    return clamp(Math.round(Number(value) || 0), -60, 20);
  }

  function paintMasterVolume(value) {
    value = normalizedMasterVolume(value);
    var label = signed(value) + " dB";
    el("masterVolume").value = String(value);
    el("masterVolume").setAttribute("aria-valuetext", label);
    el("masterVolumeValue").textContent = label;
  }

  function syncMasterVolume() {
    paintMasterVolume(tuning().master_volume_db);
  }

  function initMasterVolume() {
    var slider = el("masterVolume");
    var send = debounce(function (value) {
      applyPatch({ tuning: { master_volume_db: value } }, true);
    }, 180);
    slider.addEventListener("input", function () {
      var value = normalizedMasterVolume(this.value);
      paintMasterVolume(value);
      send(value);
    });
  }

  function syncNoteInspector() {
    if (!NOTE_INSPECTOR_OPEN) { return; }
    var note = selectedNoteEvent();
    if (!note) {
      closeNoteInspector();
      return;
    }
    var channel = partByKey(note.part);
    el("noteInspectorSubtitle").textContent =
      (channel ? partLabel(channel) + " - " : "") +
      "MIDI channel " + (Number(note.channel) + 1);
    el("noteSourcePitch").textContent =
      noteName(note.source_pitch) + " (" + note.source_pitch + ")";
    el("noteSound").textContent = String(note.sound || "");
    syncPair("notePitchRange", "notePitchNumber", Number(note.pitch_modifier || 0));
    el("notePitchMode").textContent =
      (note.pitch_follow ? "Follow MIDI" : "Manual") + " / semitones";
    syncPair("noteVolumeRange", "noteVolumeNumber", Number(note.note_volume_db || 0));
    el("noteVolumeReadout").textContent =
      "Global " + signed(note.master_volume_db) +
      " dB; output " + signed(note.volume_db) + " dB.";

    var limits = [];
    if (note.pitch_limited) {
      limits.push(
        "Pitch requested " + signed(note.requested_pitch) +
        " semitones and was clamped to " + signed(note.pitch_modifier) + "."
      );
    }
    if (note.volume_limited) {
      limits.push(
        "Volume requested " + signed(note.requested_volume_db) +
        " dB and was clamped to " + signed(note.volume_db) + " dB."
      );
    }
    el("noteClampNotice").hidden = limits.length === 0;
    el("noteClampNotice").textContent = limits.join(" ");
  }

  function openNoteInspector(noteId) {
    closeInspector();
    closeNotifications();
    closeChannelInspector();
    SELECTED_NOTE_ID = String(noteId || "");
    NOTE_INSPECTOR_OPEN = !!SELECTED_NOTE_ID;
    el("noteInspector").hidden = !NOTE_INSPECTOR_OPEN;
    if (NOTE_INSPECTOR_OPEN) { syncNoteInspector(); }
    queueDraw();
  }

  function closeNoteInspector() {
    NOTE_INSPECTOR_OPEN = false;
    SELECTED_NOTE_ID = null;
    el("noteInspector").hidden = true;
    queueDraw();
  }

  function updateNoteOverride(noteId, key, rawValue) {
    if (!STATE.settings || !noteId || !key) { return; }
    var pitchKey = key === "pitch_semitones" || key === "follow_pitch_semitones";
    var limits = pitchKey ? [-24, 24] : [-60, 20];
    var value = clamp(Math.round(Number(rawValue) || 0), limits[0], limits[1]);
    var notePatch = {};
    var entry = {};
    if (pitchKey) {
      entry[key] = value;
    } else if (key === "volume_db") {
      // Zero is a meaningful absolute note level, not an empty relative trim.
      entry[key] = value;
      entry.volume_trim_db = null;
    } else {
      entry[key] = value === 0 ? null : value;
    }
    notePatch[noteId] = entry;
    applyPatch({ notes: notePatch }, true);
  }

  function initNoteInspector() {
    el("closeNoteInspector").addEventListener("click", closeNoteInspector);
    var sendPitch = debounce(function (value, noteId, key) {
      updateNoteOverride(noteId, key, value);
    }, 180);
    var sendVolume = debounce(function (value, noteId) {
      updateNoteOverride(noteId, "volume_db", value);
    }, 180);
    el("notePitchRange").addEventListener("input", function () {
      el("notePitchNumber").value = this.value;
      sendPitch(this.value, SELECTED_NOTE_ID, notePitchOverrideKey(SELECTED_NOTE_ID));
    });
    el("notePitchNumber").addEventListener("change", function () {
      el("notePitchRange").value = this.value;
      updateNoteOverride(
        SELECTED_NOTE_ID,
        notePitchOverrideKey(SELECTED_NOTE_ID),
        this.value
      );
    });
    el("noteVolumeRange").addEventListener("input", function () {
      el("noteVolumeNumber").value = this.value;
      sendVolume(this.value, SELECTED_NOTE_ID);
    });
    el("noteVolumeNumber").addEventListener("change", function () {
      el("noteVolumeRange").value = this.value;
      updateNoteOverride(SELECTED_NOTE_ID, "volume_db", this.value);
    });
    el("resetNoteExpression").addEventListener("click", function () {
      if (!STATE.settings || !SELECTED_NOTE_ID) { return; }
      var notePatch = {};
      notePatch[SELECTED_NOTE_ID] = null;
      applyPatch({ notes: notePatch }, true);
    });
  }

  function bindPair(rangeId, numberId, key, decimal) {
    var range = el(rangeId);
    var number = el(numberId);
    var send = debounce(function (raw) {
      var value = decimal ? Number(raw) : Math.round(Number(raw));
      var body = {}; body[key] = value;
      applyPatch({ tuning: body }, true);
    }, 180);
    range.addEventListener('input', function () { number.value = this.value; send(this.value); });
    number.addEventListener('change', function () { range.value = this.value; send(this.value); });
  }

  function initInspector() {
    el('conversionBtn').addEventListener('click', openInspector);
    el('menuConversion').addEventListener('click', function () { closeMenus(); openInspector(); });
    el('closeInspector').addEventListener('click', closeInspector);
    bindPair('maxSpeakersRange', 'maxSpeakersNumber', 'max_speakers', false);
    bindPair('maxPolyRange', 'maxPolyNumber', 'max_poly', false);
    bindPair('releaseRange', 'releaseNumber', 'release_s', true);
    bindPair('sustainRange', 'sustainNumber', 'cap_sustain_ms', false);
    bindPair('bassRange', 'bassNumber', 'bass_cap_ms', false);
    el('polyEnabled').addEventListener('change', function () {
      applyPatch({ tuning: { max_poly: this.checked ? Number(el('maxPolyNumber').value || 16) : null } }, true);
    });
    el('hardStop').addEventListener('change', function () { applyPatch({ tuning: { hard_stop: this.checked } }, true); });
    el('sustainEnabled').addEventListener('change', function () {
      applyPatch({ tuning: { cap_sustain_ms: this.checked ? Number(el('sustainNumber').value || 1000) : null } }, true);
    });
    el('bassEnabled').addEventListener('change', function () {
      applyPatch({ tuning: { bass_cap_ms: this.checked ? Number(el('bassNumber').value || 750) : null } }, true);
    });
    el('bassPitchNumber').addEventListener('change', function () {
      applyPatch({ tuning: { bass_pitch: Math.round(Number(this.value)) } }, true);
    });
    el('restoreDefaults').addEventListener('click', function () {
      if (!api()) { return; }
      var resume = AUDIO.playing;
      pausePlayback();
      var sequence = nextRequest();
      setBusy(true, 'Restoring defaults...');
      api().reset_tuning().then(function (response) {
        setBusy(false);
        if (!response || !response.ok) { fail(response); return; }
        adopt(response, sequence);
        invalidateAudio(false);
        render();
        prepareSongAudio();
        toast('Conversion defaults restored', 'ok');
        if (resume) { startPlayback(); }
      }, function (error) { setBusy(false); fail(error); });
    });
  }

  /* ------------------------------------------------------------- bridge IO */

  function afterLoad(response, sequence) {
    setBusy(false);
    if (!response || !response.ok) { fail(response); return; }
    pausePlayback();
    AUDIO.position = 0;
    invalidateAudio(true);
    TRACK_KEY = '';
    SELECTED_PART = null;
    closeChannelInspector();
    closeNoteInspector();
    adopt(response, sequence);
    render();
    prepareSongAudio();
    if (response.sidecar_error) { toast(response.sidecar_error, 'warn'); }
    if (response.pitch_reconciled && response.pitch_reconciled.length) {
      toast('Updated saved automatic pitch settings for this song', 'ok');
    }
    stamp('Opened ' + baseName(STATE.settings && STATE.settings.midi));
  }

  function importMidi() {
    closeMenus();
    if (!api()) { toast('The file picker needs the desktop window', 'warn'); return; }
    var sequence = nextRequest();
    setBusy(true, 'Opening MIDI...');
    api().pick_midi().then(function (response) {
      if (response && response.cancelled) { setBusy(false); return; }
      afterLoad(response, sequence);
    }, function (error) { setBusy(false); fail(error); });
  }

  function reopenMidi() {
    closeMenus();
    if (!api() || !hasSong()) { return; }
    var sequence = nextRequest();
    setBusy(true, 'Reopening MIDI...');
    api().load_midi(STATE.settings.midi).then(function (response) { afterLoad(response, sequence); }, function (error) { setBusy(false); fail(error); });
  }

  function exportMap() {
    closeMenus();
    if (!api() || !hasSong()) { return; }
    var sequence = nextRequest();
    setBusy(true, 'Exporting SnapMap...');
    api().export().then(function (response) {
      setBusy(false);
      if (!response || !response.ok) { fail(response); return; }
      if (response.stats) { adopt({ stats: response.stats }, sequence); }
      renderStatus();
      renderWarnings();
      toast(response.replaced ? 'Map exported and previous map replaced' : 'Map exported', 'ok');
      stamp(baseName(response.destination));
      if (response.sidecar_error) { toast(response.sidecar_error, 'warn'); }
    }, function (error) { setBusy(false); fail(error); });
  }

  function refreshAudio() {
    closeMenus();
    if (!api()) { return; }
    var resume = AUDIO.playing;
    pausePlayback();
    clearSoundBrowserCatalog();
    var sequence = nextRequest();
    setBusy(true, 'Checking DOOM audio...');
    api().audio_status().then(function (response) {
      setBusy(false);
      if (!response || !response.ok) {
        fail(response);
        if (resume) { startPlayback(); }
        return;
      }
      adopt({ audio: response.audio }, sequence);
      invalidateAudio(true);
      renderAudio();
      if (STATE.audio && STATE.audio.ready) {
        prepareSongAudio();
        toast(
          STATE.audio.source === 'cache' ? 'Offline preview cache is ready' : 'DOOM soundbanks are ready',
          'ok'
        );
        if (resume) { startPlayback(); }
      } else {
        toast('DOOM audio was not found; conversion and export are still available', 'warn');
      }
    }, function (error) {
      setBusy(false);
      fail(error);
      if (resume) { startPlayback(); }
    });
  }

  function applyPatch(body, resumePlayback) {
    if (!api()) { return Promise.resolve(); }
    var patch = JSON.parse(JSON.stringify(body || {}));
    if (!resumePlayback) { PATCH_RESUME = false; }
    else if (AUDIO.playing) { PATCH_RESUME = true; }
    pausePlayback();
    PATCH_PENDING += 1;

    function runPatch() {
      var sequence = nextRequest();
      setBusy(true, 'Updating conversion...');
      return api().apply_settings(patch).then(function (response) {
        setBusy(false);
        if (!response || !response.ok) { fail(response); render(); return; }
        adopt(response, sequence);
        invalidateAudio(false);
        AUDIO.position = clamp(
          AUDIO.position,
          0,
          (STATE.preview && STATE.preview.duration_ms) || 0
        );
        render();
        prepareSongAudio();
      }, function (error) {
        setBusy(false);
        fail(error);
        render();
      });
    }

    var operation = PATCH_QUEUE.then(runPatch, runPatch).finally(function () {
      PATCH_PENDING = Math.max(0, PATCH_PENDING - 1);
      if (PATCH_PENDING === 0) {
        var shouldResume = PATCH_RESUME;
        PATCH_RESUME = false;
        if (shouldResume) { startPlayback(); }
      }
    });
    PATCH_QUEUE = operation.catch(function () { /* keep later edits live */ });
    return operation;
  }

  function boot() {
    if (BOOTED || !api()) { return; }
    BOOTED = true;
    var sequence = nextRequest();
    setBusy(true, 'Opening workstation...');
    api().startup().then(function (response) {
      setBusy(false);
      if (!response || !response.ok) { fail(response); render(); return; }
      adopt(response, sequence);
      render();
      prepareSongAudio();
      if (response.error) { toast(response.error, 'warn'); }
      if (response.pitch_reconciled && response.pitch_reconciled.length) {
        toast('Updated saved automatic pitch settings for this song', 'ok');
      }
      setTimeout(refreshWindowState, 0);
    }, function (error) { setBusy(false); fail(error); render(); });
  }

  /* --------------------------------------------------------------- chrome */

  function keyboardClick(node, action) {
    node.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); action(); }
    });
  }

  function useWindowAnswer(response, sequence) {
    if (!response || !response.ok || !accept('window', sequence)) { return; }
    STATE.window = {
      custom: response.custom === undefined ? !!(STATE.window && STATE.window.custom) : !!response.custom,
      maximized: !!response.maximized
    };
    renderWindow();
  }

  function renderWindow() {
    var custom = !!(STATE.window && STATE.window.custom);
    el('winControls').hidden = !custom;
    var grips = document.querySelectorAll('.rz');
    for (var index = 0; index < grips.length; index += 1) { grips[index].hidden = !custom; }
    var maximized = !!(STATE.window && STATE.window.maximized);
    el('winMax').title = maximized ? 'Restore' : 'Maximize';
    setIcon(el('winMax'), maximized ? 'copy' : 'square');
  }

  function refreshWindowState() {
    if (!api()) { return; }
    var sequence = nextRequest();
    api().win_state().then(function (response) { useWindowAnswer(response, sequence); }, function () { /* native frame remains */ });
  }

  function initChrome() {
    function minimize() { if (api()) { api().win_min().then(function () {}, function () {}); } }
    function maximize() {
      if (!api()) { return; }
      var sequence = nextRequest();
      api().win_max().then(function (response) { useWindowAnswer(response, sequence); }, function () {});
    }
    function close() { if (api()) { api().win_close().then(function () {}, function () {}); } }
    el('winMin').addEventListener('click', minimize);
    el('winMax').addEventListener('click', maximize);
    el('winClose').addEventListener('click', close);
    keyboardClick(el('winMin'), minimize);
    keyboardClick(el('winMax'), maximize);
    keyboardClick(el('winClose'), close);

    var menubar = document.querySelector('.menubar');
    function interactive(target) { return target.closest('.app-menus, .win-controls, button, input, select'); }
    menubar.addEventListener('mousedown', function (event) {
      if (event.button !== 0 || interactive(event.target) || !api()) { return; }
      var sequence = nextRequest();
      api().win_drag().then(function (response) { useWindowAnswer(response, sequence); }, function () {});
    });
    menubar.addEventListener('dblclick', function (event) { if (!interactive(event.target)) { maximize(); } });
    [['rz-t', 't'], ['rz-b', 'b'], ['rz-l', 'l'], ['rz-r', 'r'], ['rz-tl', 'tl'], ['rz-tr', 'tr'], ['rz-bl', 'bl'], ['rz-br', 'br']]
      .forEach(function (pair) {
        document.querySelector('.' + pair[0]).addEventListener('mousedown', function (event) {
          if (event.button === 0 && api()) {
            event.preventDefault();
            api().win_resize(pair[1]).then(function () {}, function () {});
          }
        });
      });
  }

  /* --------------------------------------------------------------- render */

  function renderAudio() {
    var state = STATE.audio;
    var song = hasSong();
    el('audioBanner').hidden = !song || !state || !!state.ready;
    updateMenuState();
  }

  function renderWarnings() {
    var warnings = warningMessages();
    var count = warnings.length;
    var button = el('notificationsBtn');
    var badge = el('notificationBadge');
    var list = el('notificationList');
    var label = count + ' warning notification' + (count === 1 ? '' : 's');

    button.classList.toggle('has-notifications', count > 0);
    button.setAttribute('aria-label', count ? label : 'Notifications, no warnings');
    button.title = count ? label : 'Notifications';
    badge.hidden = count === 0;
    badge.textContent = count > 99 ? '99+' : String(count);
    el('notificationsSummary').textContent = count ? label : 'No warnings';

    list.textContent = '';
    if (!count) {
      var empty = document.createElement('div');
      empty.className = 'notification-empty';
      empty.textContent = 'No warnings for the current conversion.';
      list.appendChild(empty);
      return;
    }
    warnings.forEach(function (message) {
      var row = document.createElement('div');
      row.className = 'notification-row';
      row.setAttribute('role', 'listitem');
      var mark = document.createElement('span');
      mark.className = 'notification-mark';
      mark.setAttribute('aria-hidden', 'true');
      mark.appendChild(iconElement('circle-alert'));
      var copy = document.createElement('div');
      copy.className = 'notification-copy';
      copy.textContent = String(message);
      row.appendChild(mark);
      row.appendChild(copy);
      list.appendChild(row);
    });
  }

  function renderStatus() {
    var stats = STATE.stats;
    [['slotNotes', 'statNotes', 'notes'], ['slotVoices', 'statVoices', 'peak_voices'], ['slotSustain', 'statSustain', 'long_sustains']]
      .forEach(function (row) {
        el(row[0]).hidden = !stats;
        if (stats) { el(row[1]).textContent = String(stats[row[2]] || 0); }
      });
    el('slotLength').hidden = !STATE.preview;
    if (STATE.preview) { el('statLength').textContent = ((STATE.preview.duration_ms || 0) / 1000).toFixed(1) + 's'; }
  }

  function render() {
    var song = hasSong();
    syncRollSong();
    el('emptyState').hidden = song;
    el('workspace').hidden = !song;
    el('songName').textContent = song ? baseName(STATE.settings.midi) : '';
    el('menuExport').disabled = !song;
    el('exportBtn').disabled = !song;
    el('gridResolution').disabled = !song;
    el('timeSignature').disabled = !song;
    el('rollZoom').disabled = !song;
    el('masterVolume').disabled = !song;
    syncMasterVolume();
    if (song) { renderTracks(); }
    renderTransportState();
    renderPosition(currentPosition(), true);
    renderAudio();
    renderWarnings();
    renderStatus();
    renderWindow();
    if (INSPECTOR_OPEN) { syncInspector(); }
    if (CHANNEL_INSPECTOR_OPEN) { syncChannelInspector(); }
    if (NOTE_INSPECTOR_OPEN) { syncNoteInspector(); }
    requestAnimationFrame(function () {
      constrainPaneSplit();
      resizeCanvas();
    });
  }

  /* --------------------------------------------------------------- startup */

  function shortcut(event) {
    var target = event.target;
    var editing = target && target.closest && target.closest('input, select, textarea');
    if (event.key === 'Escape') {
      if (SOUND_BROWSER.open) { event.preventDefault(); closeSoundBrowser(); }
      else if (OPEN_MENU) { closeMenus(); }
      else if (NOTIFICATIONS_OPEN) { closeNotifications(); }
      else if (NOTE_INSPECTOR_OPEN) { closeNoteInspector(); }
      else if (CHANNEL_INSPECTOR_OPEN) { closeChannelInspector(); }
      else if (INSPECTOR_OPEN) { closeInspector(); }
      return;
    }
    if (SOUND_BROWSER.open) { return; }
    if (event.ctrlKey && !event.shiftKey && !event.altKey) {
      var key = event.key.toLowerCase();
      if (key === 'i') { event.preventDefault(); importMidi(); }
      else if (key === 'e') { event.preventDefault(); exportMap(); }
      else if (key === 'r') { event.preventDefault(); reopenMidi(); }
      else if (event.key === ',') { event.preventDefault(); openInspector(); }
      return;
    }
    if (!editing && event.code === 'Space') { event.preventDefault(); togglePlayback(); }
    if (!editing && event.key === 'Home') { event.preventDefault(); pausePlayback(); setPosition(0); }
  }

  function initTransport() {
    el('transportPlay').addEventListener('click', togglePlayback);
    el('menuPlay').addEventListener('click', function () { closeMenus(); togglePlayback(); });
    el('menuStart').addEventListener('click', function () { closeMenus(); pausePlayback(); setPosition(0); });
    var scrubber = el('scrubber');
    scrubber.addEventListener('pointerdown', function () {
      SCRUB_DRAG = { resume: AUDIO.playing };
      pausePlayback();
    });
    scrubber.addEventListener('input', function () { setPosition(Number(this.value)); });
    scrubber.addEventListener('pointerup', function () {
      var resume = SCRUB_DRAG && SCRUB_DRAG.resume;
      SCRUB_DRAG = null;
      if (resume) { startPlayback(); }
    });
    scrubber.addEventListener('change', function () {
      if (!SCRUB_DRAG) { pausePlayback(); setPosition(Number(this.value)); }
    });
    var canvas = el('pianoRoll');
    canvas.addEventListener('pointerdown', beginCanvasSeek);
    canvas.addEventListener('pointermove', moveCanvasSeek);
    canvas.addEventListener('pointermove', updateNotePointer);
    canvas.addEventListener('pointerleave', clearNotePointer);
    canvas.addEventListener('pointerup', endCanvasSeek);
    canvas.addEventListener('pointercancel', endCanvasSeek);
    el('pianoRollViewport').addEventListener('scroll', handleRollScroll);
    el('horizontalScrollLock').addEventListener('wheel', forwardLockedScrollWheel, {
      passive: false
    });
    el('gridResolution').addEventListener('change', function () {
      ROLL.gridDenominator = Math.max(1, Number(this.value) || 8);
      invalidateRollTimeline();
      queueDraw();
    });
    el('timeSignature').addEventListener('change', function () {
      var meter = parseMeter(this.value);
      ROLL.meterNumerator = meter.numerator;
      ROLL.meterDenominator = meter.denominator;
      invalidateRollTimeline();
      queueDraw();
    });
    el('rollZoom').addEventListener('input', function () {
      var zoomAnchor = playheadZoomAnchor();
      var stops = clamp(Number(this.value) || 0, 0, 60);
      ROLL.zoom = Math.pow(2, stops / 10) * 100;
      var label = Math.round(ROLL.zoom) + '%';
      el('rollZoomValue').textContent = label;
      this.setAttribute('aria-valuetext', label);
      resizeCanvas(zoomAnchor);
    });
  }

  function init() {
    initMenus();
    initTheme();
    initPitchNameConvention();
    initPaneSplitter();
    initInspector();
    initChannelInspector();
    initNoteInspector();
    initSoundBrowser();
    initMasterVolume();
    el('notificationsBtn').addEventListener('click', toggleNotifications);
    el('closeNotifications').addEventListener('click', closeNotifications);
    initTransport();
    initChrome();
    el('menuImport').addEventListener('click', importMidi);
    el('menuReopen').addEventListener('click', reopenMidi);
    el('menuExport').addEventListener('click', exportMap);
    el('menuExit').addEventListener('click', function () { closeMenus(); if (api()) { api().win_close(); } });
    el('menuAudio').addEventListener('click', refreshAudio);
    el('audioBanner').addEventListener('click', refreshAudio);
    el('emptyOpenBtn').addEventListener('click', importMidi);
    el('exportBtn').addEventListener('click', exportMap);
    document.addEventListener('keydown', shortcut);
    window.addEventListener('resize', debounce(function () {
      constrainPaneSplit();
      resizeCanvas();
    }, 40));
    if (window.ResizeObserver) { new ResizeObserver(resizeCanvas).observe(document.querySelector('.roll-pane')); }
    render();
    if (api()) { setTimeout(boot, 0); }
  }

  window.addEventListener('pywebviewready', boot);
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); }
  else { init(); }
}());
