/* snapmap-midi workstation.

   Python resolves the converted arrangement. This page presents that answer as
   tracks, a piano roll and one transport; it never reimplements sound mapping
   or map limits in JavaScript. */
(function () {
  'use strict';

  var THEME_KEY = 'snapmap_midi_theme';
  var TRACKS_WIDTH_KEY = 'snapmap_midi_tracks_width';
  var TRACKS_DEFAULT_WIDTH = 314;
  var TRACKS_MIN_WIDTH = 220;
  var ROLL_MIN_WIDTH = 420;
  var LOOKAHEAD_MS = 1300;
  var SCHEDULE_EVERY_MS = 100;
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
  var SELECTED_CHANNEL = null;
  var TRACK_KEY = '';
  var OPEN_MENU = null;
  var INSPECTOR_OPEN = false;
  var NOTIFICATIONS_OPEN = false;
  var DRAW_FRAME = null;
  var SEEK_DRAG = null;
  var SCRUB_DRAG = null;
  var NOTE_POINTER = null;
  var PANE_SPLIT_DRAG = null;
  var TRACKS_PREFERRED_WIDTH = TRACKS_DEFAULT_WIDTH;
  var CANVAS_RESIZE_QUEUED = false;
  var PLAY_TOKEN = 0;

  var AUDIO = {
    context: null,
    master: null,
    buffers: {},
    key: '',
    loading: null,
    playing: false,
    position: 0,
    anchorPosition: 0,
    anchorTime: 0,
    nextIndex: 0,
    timer: null,
    frame: null,
    sources: []
  };

  function el(id) { return document.getElementById(id); }
  function api() { return window.pywebview && window.pywebview.api; }
  function nextRequest() { REQUEST += 1; return REQUEST; }
  function hasSong() { return !!(STATE.analysis && STATE.settings && STATE.settings.midi); }
  function channels() { return (STATE.analysis && STATE.analysis.channels) || []; }
  function previewEvents() { return (STATE.preview && STATE.preview.events) || []; }
  function tuning() { return (STATE.settings && STATE.settings.tuning) || {}; }
  function warningMessages() { return (STATE.stats && STATE.stats.warnings) || []; }
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
    return NOTE_NAMES[((note % 12) + 12) % 12] + (Math.floor(note / 12) - 1);
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
    ['settings', 'analysis', 'catalog', 'stats', 'preview', 'audio', 'window'].forEach(function (key) {
      if (payload[key] !== undefined && accept(key, sequence)) { STATE[key] = payload[key]; }
    });
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
    queueDraw();
  }

  function initTheme() {
    var saved = storedTheme();
    var dark = saved ? saved === 'dark' : !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    setTheme(dark ? 'dark' : 'light', false);
    el('menuLight').addEventListener('click', function () { setTheme('light', true); closeMenus(); });
    el('menuDark').addEventListener('click', function () { setTheme('dark', true); closeMenus(); });
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
    ['menuReopen', 'menuExport', 'menuPlay', 'menuStart'].forEach(function (id) { el(id).disabled = !song; });
    el('menuPlay').querySelector('span').textContent = AUDIO.playing ? 'Pause' : 'Play';
    el('menuAudio').querySelector('span').textContent = STATE.audio && STATE.audio.ready ? 'Audio Ready' : 'Set Up Audio...';
    el('menuAudio').disabled = !!(STATE.audio && STATE.audio.ready);
  }

  /* --------------------------------------------------------------- tracks */

  function channelEntry(channel) {
    return (STATE.settings && STATE.settings.channels && STATE.settings.channels[String(channel)]) || {};
  }

  function assignmentValue(channel) {
    var entry = channelEntry(channel);
    if (entry.sound) { return 'sound:' + entry.sound; }
    if (entry.family) { return 'family:' + entry.family; }
    return '';
  }

  function option(parent, value, text) {
    var node = document.createElement('option');
    node.value = value;
    node.textContent = text;
    parent.appendChild(node);
  }

  function fillSoundPicker(select, channel) {
    select.textContent = '';
    option(
      select,
      '',
      channel.is_drums
        ? 'Automatic — General MIDI percussion map'
        : 'Automatic — ' + (channel.auto_family || channel.program_name)
    );

    var families = (STATE.catalog && STATE.catalog.families) || [];
    var familyGroup = document.createElement('optgroup');
    familyGroup.label = 'Pitched instrument sets';
    families.forEach(function (family) {
      option(familyGroup, 'family:' + family.name, humanCategory(family.name));
    });
    select.appendChild(familyGroup);

    var groups = (STATE.catalog && STATE.catalog.sound_groups) || [];
    groups.forEach(function (group) {
      var node = document.createElement('optgroup');
      node.label = humanCategory(group.name) + ' — exact sounds';
      group.sounds.forEach(function (sound) {
        option(node, 'sound:' + sound.name, sound.label || sound.name);
      });
      select.appendChild(node);
    });
  }

  function trackShapeKey() {
    var groups = (STATE.catalog && STATE.catalog.sound_groups) || [];
    return channels().map(function (channel) { return channel.channel + ':' + channel.program; }).join('|')
      + '#' + groups.length + ':' + ((STATE.catalog && STATE.catalog.sound_count) || 0);
  }

  function buildTracks() {
    var list = el('trackList');
    list.textContent = '';
    channels().forEach(function (channel) {
      var row = document.createElement('div');
      row.className = 'track-row';
      row.dataset.channel = String(channel.channel);
      row.style.setProperty('--track-color', channelColor(channel.channel));

      var number = document.createElement('div');
      number.className = 'track-channel';
      number.textContent = String(channel.channel + 1);
      number.title = 'MIDI channel ' + (channel.channel + 1);
      row.appendChild(number);

      var name = document.createElement('div');
      name.className = 'track-name';
      name.textContent = channel.program_name + (channel.is_drums ? ' · Percussion' : '');
      name.title = channel.notes + ' notes · ' + noteName(channel.lowest) + '–' + noteName(channel.highest);
      row.appendChild(name);

      var select = document.createElement('select');
      select.className = 'track-sound';
      select.setAttribute('aria-label', 'Sound for MIDI channel ' + (channel.channel + 1));
      fillSoundPicker(select, channel);
      select.addEventListener('change', function () {
        var value = this.value;
        var body = { family: null, sound: null };
        if (value.indexOf('family:') === 0) { body.family = value.slice(7); }
        if (value.indexOf('sound:') === 0) { body.sound = value.slice(6); }
        var patch = { channels: {} };
        patch.channels[String(channel.channel)] = body;
        applyPatch(patch, true);
      });
      row.appendChild(select);

      var mute = document.createElement('label');
      mute.className = 'track-mute';
      var check = document.createElement('input');
      check.type = 'checkbox';
      check.setAttribute('aria-label', 'Mute MIDI channel ' + (channel.channel + 1));
      check.addEventListener('change', function () {
        var patch = { channels: {} };
        patch.channels[String(channel.channel)] = { muted: this.checked };
        applyPatch(patch, true);
      });
      mute.appendChild(check);
      mute.appendChild(document.createTextNode('Mute'));
      row.appendChild(mute);

      row.addEventListener('click', function (event) {
        if (event.target.closest('select, input, label')) { return; }
        SELECTED_CHANNEL = SELECTED_CHANNEL === channel.channel ? null : channel.channel;
        patchTracks();
        queueDraw();
      });
      list.appendChild(row);
    });
  }

  function patchTracks() {
    var rows = el('trackList').querySelectorAll('.track-row');
    for (var index = 0; index < rows.length; index += 1) {
      var row = rows[index];
      var channel = Number(row.dataset.channel);
      var entry = channelEntry(channel);
      row.classList.toggle('selected', SELECTED_CHANNEL === channel);
      row.classList.toggle('muted-track', !!entry.muted);
      row.querySelector('.track-sound').value = assignmentValue(channel);
      row.querySelector('.track-mute input').checked = !!entry.muted;
    }
  }

  function renderTracks() {
    var key = trackShapeKey();
    if (key !== TRACK_KEY) {
      TRACK_KEY = key;
      buildTracks();
    }
    patchTracks();
    el('trackCount').textContent = String(channels().length);
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

  function sizeCanvas(canvas, width, height) {
    var ratio = window.devicePixelRatio || 1;
    var pixelWidth = Math.max(1, Math.round(width * ratio));
    var pixelHeight = Math.max(1, Math.round(height * ratio));
    canvas.style.width = Math.max(1, width) + 'px';
    canvas.style.height = Math.max(1, height) + 'px';
    if (canvas.width !== pixelWidth) { canvas.width = pixelWidth; }
    if (canvas.height !== pixelHeight) { canvas.height = pixelHeight; }
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

    sizeCanvas(el('pianoRoll'), width, height);
    sizeCanvas(el('timeRuler'), width, 31);
    sizeCanvas(el('pitchRuler'), 72, height);

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

  function timeAtTick(tick) {
    var timing = timingManifest();
    var changes = timing.tempo_changes || [];
    var marker = changes.length ? changes[0] : { tick: 0, time_ms: 0, tempo: 500000 };
    for (var index = 1; index < changes.length && Number(changes[index].tick) <= tick; index += 1) {
      marker = changes[index];
    }
    return Number(marker.time_ms) + (tick - Number(marker.tick)) * Number(marker.tempo) / 1000 / Number(timing.ticks_per_beat || 480);
  }

  function tickAtTime(timeMs) {
    var timing = timingManifest();
    var changes = timing.tempo_changes || [];
    var marker = changes.length ? changes[0] : { tick: 0, time_ms: 0, tempo: 500000 };
    for (var index = 1; index < changes.length && Number(changes[index].time_ms) <= timeMs; index += 1) {
      marker = changes[index];
    }
    return Number(marker.tick) + (timeMs - Number(marker.time_ms)) * 1000 * Number(timing.ticks_per_beat || 480) / Number(marker.tempo || 500000);
  }

  function contentXAtTime(timeMs) {
    var duration = Math.max(1, Number(STATE.preview && STATE.preview.duration_ms) || 1);
    return clamp(Number(timeMs) || 0, 0, duration) / duration * ROLL.contentWidth;
  }

  function eachVisibleTick(step, callback) {
    if (!isFinite(step) || step <= 0) { return; }
    var duration = Math.max(1, Number(STATE.preview && STATE.preview.duration_ms) || 1);
    var viewport = el('pianoRollViewport');
    var startMs = viewport.scrollLeft / ROLL.contentWidth * duration;
    var endMs = (viewport.scrollLeft + ROLL.viewportWidth) / ROLL.contentWidth * duration;
    var startTick = Math.max(0, tickAtTime(startMs));
    var endTick = Math.max(startTick, tickAtTime(endMs));
    var stride = Math.max(1, Math.ceil((endTick - startTick) / step / 4000));
    var actualStep = step * stride;
    var first = Math.max(0, Math.floor(startTick / actualStep) * actualStep);
    for (var tick = first; tick <= endTick + actualStep; tick += actualStep) {
      callback(tick, contentXAtTime(timeAtTick(tick)) - viewport.scrollLeft);
    }
  }

  function timingLines() {
    var ticksPerBeat = Number(timingManifest().ticks_per_beat) || 480;
    var gridTicks = ticksPerBeat * 4 / ROLL.gridDenominator;
    var barTicks = ticksPerBeat * 4 / ROLL.meterDenominator * ROLL.meterNumerator;
    var lines = { grid: [], bars: [] };
    var lastGridX = -Infinity;
    var lastBarX = -Infinity;

    eachVisibleTick(gridTicks, function (_tick, x) {
      if (x >= -1 && x <= ROLL.viewportWidth + 1 && x - lastGridX >= 4) {
        lines.grid.push(x);
        lastGridX = x;
      }
    });
    eachVisibleTick(barTicks, function (tick, x) {
      if (x >= -1 && x <= ROLL.viewportWidth + 1 && x - lastBarX >= 18) {
        lines.bars.push({ x: x, number: Math.round(tick / barTicks) + 1 });
        lastBarX = x;
      }
    });
    return lines;
  }

  function prepareContext(canvas) {
    var ratio = window.devicePixelRatio || 1;
    var context = canvas.getContext('2d');
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = 'high';
    if ('fontKerning' in context) { context.fontKerning = 'normal'; }
    if ('textRendering' in context) { context.textRendering = 'geometricPrecision'; }
    return context;
  }

  function drawPitchRuler() {
    var canvas = el('pitchRuler');
    var context = prepareContext(canvas);
    var width = 72;
    var height = ROLL.viewportHeight;
    var scrollTop = el('pianoRollViewport').scrollTop;
    var border = css('--border');
    var border2 = css('--border2');
    var white = css('--keyWhite');
    var whiteText = css('--keyWhiteText');
    var black = css('--keyBlack');
    var blackText = css('--keyBlackText');
    var fontSize = clamp(ROLL.rowHeight - 2, 7, 11);

    context.clearRect(0, 0, width, height);
    context.fillStyle = css('--panel2');
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

  function drawTimeRuler(lines, playheadX) {
    var canvas = el('timeRuler');
    var context = prepareContext(canvas);
    var width = ROLL.viewportWidth;
    var height = 31;
    context.clearRect(0, 0, width, height);
    context.fillStyle = css('--panel2');
    context.fillRect(0, 0, width, height);
    context.strokeStyle = css('--rollGrid');
    lines.grid.forEach(function (x) {
      context.beginPath(); context.moveTo(Math.round(x) + 0.5, 20); context.lineTo(Math.round(x) + 0.5, height); context.stroke();
    });
    context.font = '10px Consolas, monospace';
    context.textAlign = 'left';
    context.textBaseline = 'middle';
    lines.bars.forEach(function (bar) {
      context.strokeStyle = css('--rollBeat');
      context.beginPath(); context.moveTo(Math.round(bar.x) + 0.5, 0); context.lineTo(Math.round(bar.x) + 0.5, height); context.stroke();
      context.fillStyle = css('--muted');
      context.fillText(String(bar.number), Math.max(4, bar.x + 4), 10);
    });
    if (playheadX >= -1 && playheadX <= width + 1) {
      context.strokeStyle = css('--accent');
      context.lineWidth = 2;
      context.beginPath(); context.moveTo(playheadX, 0); context.lineTo(playheadX, height); context.stroke();
      context.fillStyle = css('--accent');
      context.beginPath(); context.moveTo(playheadX - 5, 0); context.lineTo(playheadX + 5, 0); context.lineTo(playheadX, 7); context.closePath(); context.fill();
    }
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

  function drawPianoRoll(positionOverride) {
    if (DRAW_FRAME !== null) {
      cancelAnimationFrame(DRAW_FRAME);
      DRAW_FRAME = null;
    }
    var canvas = el('pianoRoll');
    if (!canvas || canvas.width <= 1 || canvas.height <= 1 || canvas.hidden) { return; }
    var width = ROLL.viewportWidth;
    var height = ROLL.viewportHeight;
    var viewport = el('pianoRollViewport');
    var context = prepareContext(canvas);
    context.clearRect(0, 0, width, height);

    var duration = Math.max(1, (STATE.preview && STATE.preview.duration_ms) || 1);
    var background = css('--field');
    var border = css('--border');
    var border2 = css('--border2');
    var text = css('--text');
    var accent = css('--accent');

    context.fillStyle = background;
    context.fillRect(0, 0, width, height);
    for (var pitch = 0; pitch <= 127; pitch += 1) {
      var y = (127 - pitch) * ROLL.rowHeight - viewport.scrollTop;
      if (y + ROLL.rowHeight < 0 || y > height) { continue; }
      if (BLACK_KEYS[pitch % 12]) {
        context.fillStyle = css('--rollBlack');
        context.fillRect(0, y, width, ROLL.rowHeight);
      }
      context.strokeStyle = pitch % 12 === 0 ? border2 : border;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(0, Math.round(y) + 0.5);
      context.lineTo(width, Math.round(y) + 0.5);
      context.stroke();
    }

    var lines = timingLines();
    context.strokeStyle = css('--rollGrid');
    lines.grid.forEach(function (x) {
      context.beginPath(); context.moveTo(Math.round(x) + 0.5, 0); context.lineTo(Math.round(x) + 0.5, height); context.stroke();
    });
    context.strokeStyle = css('--rollBeat');
    lines.bars.forEach(function (bar) {
      context.beginPath(); context.moveTo(Math.round(bar.x) + 0.5, 0); context.lineTo(Math.round(bar.x) + 0.5, height); context.stroke();
    });

    var position = positionOverride === undefined ? currentPosition() : positionOverride;
    var hoverPoint = !AUDIO.playing && !SEEK_DRAG ? pianoRollPointer(canvas) : null;
    var events = previewEvents();
    for (var index = 0; index < events.length; index += 1) {
      var event = events[index];
      if (event.pitch === null || event.pitch === undefined) { continue; }
      var eventPitch = Number(event.pitch);
      if (eventPitch < 0 || eventPitch > 127) { continue; }
      var eventStart = Number(event.start) || 0;
      var eventEnd = Math.max(eventStart, Number(event.end) || eventStart);
      var startX = contentXAtTime(eventStart) - viewport.scrollLeft;
      var endX = contentXAtTime(Math.max(eventEnd, eventStart + duration / ROLL.contentWidth * 2)) - viewport.scrollLeft;
      var eventY = (127 - eventPitch) * ROLL.rowHeight - viewport.scrollTop + 1;
      var eventHeight = Math.max(2, ROLL.rowHeight - 2);
      if (endX < 0 || startX > width || eventY + eventHeight < 0 || eventY > height) { continue; }
      var eventWidth = Math.max(2, endX - startX);
      var eventRadius = Math.min(4, eventWidth / 2, eventHeight / 2);
      var active = AUDIO.playing && position >= eventStart && position < eventEnd;
      var hovered = !!hoverPoint &&
        hoverPoint.x >= startX && hoverPoint.x <= startX + eventWidth &&
        hoverPoint.y >= eventY && hoverPoint.y <= eventY + eventHeight;
      var glowing = active || hovered;
      var noteAlpha = SELECTED_CHANNEL === null || SELECTED_CHANNEL === event.channel ? 0.88 : 0.25;
      var color = channelColor(event.channel);
      fillNoteBlock(
        context,
        startX,
        eventY,
        eventWidth,
        eventHeight,
        eventRadius,
        color,
        noteAlpha,
        glowing
      );
      if (SELECTED_CHANNEL === event.channel) {
        context.globalAlpha = 1;
        context.strokeStyle = text;
        context.lineWidth = 0.7;
        roundedRectPath(
          context,
          startX + 0.5,
          eventY + 0.5,
          Math.max(1, eventWidth - 1),
          Math.max(1, eventHeight - 1),
          Math.max(0, eventRadius - 0.5)
        );
        context.stroke();
      }
      if (ROLL.rowHeight >= 14 && endX - startX >= 25 && startX >= 0) {
        var label = noteName(eventPitch);
        var labelSize = clamp(Math.floor(eventHeight * 0.58), 9, 12);
        context.fillStyle = noteTextColor(color);
        context.font = '600 ' + labelSize + 'px "Segoe UI", Tahoma, Arial, sans-serif';
        context.textAlign = 'left';
        context.textBaseline = 'middle';
        if (context.measureText(label).width <= eventWidth - 8) {
          context.globalAlpha = glowing || SELECTED_CHANNEL === null || SELECTED_CHANNEL === event.channel ? 1 : 0.55;
          context.fillText(label, Math.round(startX + 4), Math.round(eventY + eventHeight / 2));
        }
      }
    }
    context.globalAlpha = 1;

    var playheadX = contentXAtTime(position) - viewport.scrollLeft;
    if (playheadX >= -1 && playheadX <= width + 1) {
      context.strokeStyle = accent;
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(playheadX, 0);
      context.lineTo(playheadX, height);
      context.stroke();
    }
    drawPitchRuler();
    drawTimeRuler(lines, playheadX);
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
    if (!AUDIO.playing && !SEEK_DRAG) { queueDraw(); }
  }

  function clearNotePointer() {
    NOTE_POINTER = null;
    if (!AUDIO.playing) { queueDraw(); }
  }

  function revealPlayhead(position, following) {
    var viewport = el('pianoRollViewport');
    if (ROLL.contentWidth <= ROLL.viewportWidth) { return; }
    var x = contentXAtTime(position);
    if (following) {
      var anchor = ROLL.viewportWidth * 0.32;
      viewport.scrollLeft = clamp(x - anchor, 0, ROLL.contentWidth - ROLL.viewportWidth);
    } else if (x < viewport.scrollLeft || x > viewport.scrollLeft + ROLL.viewportWidth) {
      viewport.scrollLeft = clamp(x - ROLL.viewportWidth / 2, 0, ROLL.contentWidth - ROLL.viewportWidth);
    }
  }

  function setPosition(position, reveal) {
    var duration = (STATE.preview && STATE.preview.duration_ms) || 0;
    AUDIO.position = clamp(Number(position) || 0, 0, duration);
    if (reveal !== false) { revealPlayhead(AUDIO.position, false); }
    renderPosition(AUDIO.position);
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

  function audioKey() {
    return ((STATE.preview && STATE.preview.sounds) || []).join('\n');
  }

  function invalidateAudio() {
    PLAY_TOKEN += 1;
    stopSources();
    AUDIO.key = '';
    AUDIO.buffers = {};
    AUDIO.loading = null;
  }

  function ensureSongAudio() {
    if (!STATE.audio || !STATE.audio.ready) {
      return Promise.reject(new Error('Set up audio preview before playing the converted song'));
    }
    var key = audioKey();
    if (AUDIO.key === key && !AUDIO.loading) { return Promise.resolve(); }
    if (AUDIO.loading && AUDIO.loading.key === key) { return AUDIO.loading.promise; }
    if (!api()) { return Promise.reject(new Error('The audio bridge is not available')); }
    var context;
    try { context = ensureAudioContext(); } catch (error) { return Promise.reject(error); }
    var sounds = (STATE.preview && STATE.preview.sounds) || [];
    setBusy(true, 'Loading song audio...');
    var promise = api().preview_samples(sounds).then(function (response) {
      if (!response || !response.ok) { throw new Error(response && response.error || 'Song audio could not be loaded'); }
      if (response.missing && response.missing.length) {
        throw new Error(response.missing.length + ' sounds are missing from the local audio cache');
      }
      var names = Object.keys(response.samples || {});
      return Promise.all(names.map(function (name) {
        return decodeDataUri(context, response.samples[name]).then(function (buffer) {
          return [name, buffer];
        });
      }));
    }).then(function (pairs) {
      var buffers = {};
      pairs.forEach(function (pair) { buffers[pair[0]] = pair[1]; });
      AUDIO.buffers = buffers;
      AUDIO.key = key;
    }).finally(function () {
      setBusy(false);
      if (AUDIO.loading && AUDIO.loading.promise === promise) { AUDIO.loading = null; }
    });
    AUDIO.loading = { key: key, promise: promise };
    return promise;
  }

  function stopSources() {
    var sources = AUDIO.sources.slice();
    AUDIO.sources = [];
    sources.forEach(function (source) {
      try { source.stop(); } catch (_error) { /* already ended */ }
    });
    if (AUDIO.timer !== null) { clearInterval(AUDIO.timer); AUDIO.timer = null; }
    if (AUDIO.frame !== null) { cancelAnimationFrame(AUDIO.frame); AUDIO.frame = null; }
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
    gain.gain.value = 0.34;
    source.connect(gain);
    gain.connect(AUDIO.master);
    var offset = Math.max(0, (audiblePosition - event.start) / 1000);
    var stopAfter;

    if (event.sustained) {
      var release = STATE.preview && !STATE.preview.hard_stop && !event.cut
        ? Number(STATE.preview.release_s || 0)
        : 0;
      var sounding = Math.max(0, (event.end - event.start) / 1000);
      var total = sounding + release;
      if (offset >= total) { return; }
      if (buffer.duration > 0.04 && sounding > buffer.duration) {
        source.loop = true;
        source.loopEnd = buffer.duration;
        offset = offset % buffer.duration;
      } else if (offset >= buffer.duration) {
        return;
      }
      stopAfter = Math.max(0.01, total - Math.max(0, (audiblePosition - event.start) / 1000));
      var noteEndAt = when + Math.max(0, (event.end - audiblePosition) / 1000);
      if (release > 0 && noteEndAt >= AUDIO.context.currentTime) {
        gain.gain.setValueAtTime(0.34, noteEndAt);
        gain.gain.exponentialRampToValueAtTime(0.001, noteEndAt + release);
      }
      source.start(when, offset);
      source.stop(when + stopAfter);
    } else {
      if (offset >= buffer.duration) { return; }
      source.start(when, offset);
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
        : event.start + (buffer ? buffer.duration * 1000 : 0);
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
      pausePlayback();
      setPosition(0);
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
    renderPosition(AUDIO.position);
  }

  function togglePlayback() {
    if (AUDIO.playing) { pausePlayback(); } else { startPlayback(); }
  }

  function renderPosition(position) {
    var duration = (STATE.preview && STATE.preview.duration_ms) || 0;
    el('currentTime').textContent = formatTime(position);
    el('totalTime').textContent = formatTime(duration);
    el('scrubber').max = String(duration);
    el('scrubber').value = String(clamp(position, 0, duration));
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
    if (!AUDIO.playing) { queueDraw(); }
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
    previewEvents().forEach(function (event) { if (event.family) { seen[event.family] = true; } });
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
        invalidateAudio();
        render();
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
    invalidateAudio();
    TRACK_KEY = '';
    SELECTED_CHANNEL = null;
    adopt(response, sequence);
    render();
    if (response.sidecar_error) { toast(response.sidecar_error, 'warn'); }
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

  function setupAudio() {
    closeMenus();
    if (!api() || (STATE.audio && STATE.audio.ready)) { return; }
    var sequence = nextRequest();
    setBusy(true, 'Extracting game audio...');
    api().extract_audio().then(function (response) {
      setBusy(false);
      if (response && response.audio) { adopt({ audio: response.audio }, sequence); }
      renderAudio();
      if (!response || !response.ok) { fail(response); return; }
      invalidateAudio();
      toast('Audio preview is ready', 'ok');
    }, function (error) { setBusy(false); fail(error); });
  }

  function applyPatch(body, resumePlayback) {
    if (!api()) { return; }
    var wasPlaying = !!resumePlayback && AUDIO.playing;
    pausePlayback();
    var sequence = nextRequest();
    setBusy(true, 'Updating conversion...');
    api().apply_settings(body).then(function (response) {
      setBusy(false);
      if (!response || !response.ok) { fail(response); render(); return; }
      adopt(response, sequence);
      invalidateAudio();
      AUDIO.position = clamp(AUDIO.position, 0, (STATE.preview && STATE.preview.duration_ms) || 0);
      render();
      if (wasPlaying) { startPlayback(); }
    }, function (error) { setBusy(false); fail(error); render(); });
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
      if (response.error) { toast(response.error, 'warn'); }
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
    el('slotAudio').hidden = !state;
    el('audioBanner').hidden = !song || !state || !!state.ready;
    if (!state) { return; }
    if (state.ready) { el('audioText').textContent = 'ready'; }
    else if (state.error) { el('audioText').textContent = 'unavailable'; }
    else if (!state.install) { el('audioText').textContent = 'game not found'; }
    else { el('audioText').textContent = (state.count || 0) + ' / ' + (state.expected || 0); }
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
    el('bridgeDot').className = 'dot ' + (api() ? 'ok' : 'no');
    el('bridgeText').textContent = api() ? 'ready' : 'browser preview';
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
    if (song) { renderTracks(); }
    renderTransportState();
    renderPosition(currentPosition());
    renderAudio();
    renderWarnings();
    renderStatus();
    renderWindow();
    if (INSPECTOR_OPEN) { syncInspector(); }
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
      if (OPEN_MENU) { closeMenus(); }
      else if (NOTIFICATIONS_OPEN) { closeNotifications(); }
      else if (INSPECTOR_OPEN) { closeInspector(); }
      return;
    }
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
      queueDraw();
    });
    el('timeSignature').addEventListener('change', function () {
      var meter = parseMeter(this.value);
      ROLL.meterNumerator = meter.numerator;
      ROLL.meterDenominator = meter.denominator;
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
    initPaneSplitter();
    initInspector();
    el('notificationsBtn').addEventListener('click', toggleNotifications);
    el('closeNotifications').addEventListener('click', closeNotifications);
    initTransport();
    initChrome();
    el('menuImport').addEventListener('click', importMidi);
    el('menuReopen').addEventListener('click', reopenMidi);
    el('menuExport').addEventListener('click', exportMap);
    el('menuExit').addEventListener('click', function () { closeMenus(); if (api()) { api().win_close(); } });
    el('menuAudio').addEventListener('click', setupAudio);
    el('audioBanner').addEventListener('click', setupAudio);
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
