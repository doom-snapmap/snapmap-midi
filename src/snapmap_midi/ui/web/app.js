/* snapmap-midi workstation.

   Python resolves the converted arrangement. This page presents that answer as
   tracks, a piano roll and one transport; it never reimplements sound mapping
   or map limits in JavaScript. */
(function () {
  'use strict';

  var THEME_KEY = 'snapmap_midi_theme';
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
  var DRAW_QUEUED = false;
  var SEEK_DRAG = null;
  var SCRUB_DRAG = null;
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
  function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }
  function baseName(path) { return String(path || '').replace(/^.*[\\/]/, ''); }
  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function channelColor(channel) { return CHANNEL_COLORS[Number(channel) % CHANNEL_COLORS.length]; }
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

  function canvasGeometry() {
    var events = previewEvents();
    var pitches = events.map(function (event) { return Number(event.pitch); }).filter(function (pitch) { return isFinite(pitch); });
    var low = pitches.length ? Math.max(0, Math.min.apply(null, pitches) - 2) : 36;
    var high = pitches.length ? Math.min(127, Math.max.apply(null, pitches) + 2) : 84;
    if (high - low < 24) {
      var extra = 24 - (high - low);
      low = Math.max(0, low - Math.floor(extra / 2));
      high = Math.min(127, low + 24);
      low = Math.max(0, high - 24);
    }
    return { low: low, high: high, top: 30, keys: 48, right: 8, bottom: 8 };
  }

  function resizeCanvas() {
    var canvas = el('pianoRoll');
    if (!canvas || !canvas.parentNode || canvas.parentNode.hidden) { return; }
    var rect = canvas.getBoundingClientRect();
    var ratio = window.devicePixelRatio || 1;
    var width = Math.max(1, Math.round(rect.width * ratio));
    var height = Math.max(1, Math.round(rect.height * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    drawPianoRoll();
  }

  function currentPosition() {
    if (!AUDIO.playing || !AUDIO.context) { return AUDIO.position; }
    return clamp(
      AUDIO.anchorPosition + (AUDIO.context.currentTime - AUDIO.anchorTime) * 1000,
      0,
      (STATE.preview && STATE.preview.duration_ms) || 0
    );
  }

  function gridStep(duration, width) {
    var candidates = [1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000];
    for (var index = 0; index < candidates.length; index += 1) {
      if (duration / candidates[index] <= Math.max(2, width / 90)) { return candidates[index]; }
    }
    return candidates[candidates.length - 1];
  }

  function drawPianoRoll(positionOverride) {
    DRAW_QUEUED = false;
    var canvas = el('pianoRoll');
    if (!canvas || canvas.width <= 1 || canvas.height <= 1 || canvas.hidden) { return; }
    var ratio = window.devicePixelRatio || 1;
    var width = canvas.width / ratio;
    var height = canvas.height / ratio;
    var context = canvas.getContext('2d');
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);

    var geometry = canvasGeometry();
    var duration = Math.max(1, (STATE.preview && STATE.preview.duration_ms) || 1);
    var plotWidth = Math.max(1, width - geometry.keys - geometry.right);
    var pitchCount = geometry.high - geometry.low + 1;
    var plotHeight = Math.max(1, height - geometry.top - geometry.bottom);
    var pitchHeight = plotHeight / pitchCount;
    var background = css('--field');
    var panel = css('--panel2');
    var border = css('--border');
    var border2 = css('--border2');
    var muted = css('--muted');
    var text = css('--text');
    var accent = css('--accent');

    context.fillStyle = background;
    context.fillRect(0, 0, width, height);
    context.fillStyle = panel;
    context.fillRect(0, 0, width, geometry.top);
    context.fillRect(0, geometry.top, geometry.keys, plotHeight);

    context.font = '10px Consolas, monospace';
    context.textBaseline = 'middle';
    for (var pitch = geometry.low; pitch <= geometry.high; pitch += 1) {
      var row = geometry.high - pitch;
      var y = geometry.top + row * pitchHeight;
      if (BLACK_KEYS[pitch % 12]) {
        context.fillStyle = panel;
        context.fillRect(geometry.keys, y, plotWidth, pitchHeight);
      }
      context.strokeStyle = pitch % 12 === 0 ? border2 : border;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(0, Math.round(y) + 0.5);
      context.lineTo(width, Math.round(y) + 0.5);
      context.stroke();
      if (pitch % 12 === 0 && pitchHeight >= 5) {
        context.fillStyle = muted;
        context.fillText(noteName(pitch), 5, y + pitchHeight / 2);
      }
    }

    var step = gridStep(duration, plotWidth);
    for (var time = 0; time <= duration; time += step) {
      var x = geometry.keys + time / duration * plotWidth;
      context.strokeStyle = time === 0 ? border2 : border;
      context.beginPath();
      context.moveTo(Math.round(x) + 0.5, geometry.top);
      context.lineTo(Math.round(x) + 0.5, height);
      context.stroke();
      context.fillStyle = muted;
      context.fillText(formatTime(time), x + 4, geometry.top / 2);
    }

    var events = previewEvents();
    for (var index = 0; index < events.length; index += 1) {
      var event = events[index];
      if (event.pitch === null || event.pitch === undefined) { continue; }
      var eventPitch = Number(event.pitch);
      if (eventPitch < geometry.low || eventPitch > geometry.high) { continue; }
      var startX = geometry.keys + event.start / duration * plotWidth;
      var endX = geometry.keys + Math.max(event.end, event.start + duration / plotWidth * 2) / duration * plotWidth;
      var eventY = geometry.top + (geometry.high - eventPitch) * pitchHeight + 1;
      var eventHeight = Math.max(2, pitchHeight - 2);
      context.globalAlpha = SELECTED_CHANNEL === null || SELECTED_CHANNEL === event.channel ? 0.88 : 0.25;
      context.fillStyle = channelColor(event.channel);
      context.fillRect(startX, eventY, Math.max(2, endX - startX), eventHeight);
      if (SELECTED_CHANNEL === event.channel) {
        context.strokeStyle = text;
        context.lineWidth = 0.7;
        context.strokeRect(startX + 0.5, eventY + 0.5, Math.max(1, endX - startX - 1), Math.max(1, eventHeight - 1));
      }
    }
    context.globalAlpha = 1;

    var position = positionOverride === undefined ? currentPosition() : positionOverride;
    var playheadX = geometry.keys + clamp(position, 0, duration) / duration * plotWidth;
    context.strokeStyle = accent;
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(playheadX, 0);
    context.lineTo(playheadX, height);
    context.stroke();
    context.fillStyle = accent;
    context.beginPath();
    context.moveTo(playheadX - 5, 0);
    context.lineTo(playheadX + 5, 0);
    context.lineTo(playheadX, 7);
    context.closePath();
    context.fill();
  }

  function queueDraw() {
    if (DRAW_QUEUED) { return; }
    DRAW_QUEUED = true;
    requestAnimationFrame(function () { drawPianoRoll(); });
  }

  function positionFromCanvas(event) {
    var canvas = el('pianoRoll');
    var rect = canvas.getBoundingClientRect();
    var geometry = canvasGeometry();
    var width = Math.max(1, rect.width - geometry.keys - geometry.right);
    var x = clamp(event.clientX - rect.left - geometry.keys, 0, width);
    return x / width * ((STATE.preview && STATE.preview.duration_ms) || 0);
  }

  function setPosition(position) {
    var duration = (STATE.preview && STATE.preview.duration_ms) || 0;
    AUDIO.position = clamp(Number(position) || 0, 0, duration);
    renderPosition(AUDIO.position);
  }

  function beginCanvasSeek(event) {
    if (!hasSong()) { return; }
    event.preventDefault();
    var wasPlaying = AUDIO.playing;
    pausePlayback();
    SEEK_DRAG = { pointer: event.pointerId, resume: wasPlaying };
    el('pianoRoll').setPointerCapture(event.pointerId);
    setPosition(positionFromCanvas(event));
  }

  function moveCanvasSeek(event) {
    if (!SEEK_DRAG || SEEK_DRAG.pointer !== event.pointerId) { return; }
    setPosition(positionFromCanvas(event));
  }

  function endCanvasSeek(event) {
    if (!SEEK_DRAG || SEEK_DRAG.pointer !== event.pointerId) { return; }
    var resume = SEEK_DRAG.resume;
    SEEK_DRAG = null;
    try { el('pianoRoll').releasePointerCapture(event.pointerId); } catch (_error) { /* already released */ }
    if (resume) { startPlayback(); }
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
    drawPianoRoll(position);
  }

  function renderTransportState() {
    var playable = hasSong();
    el('transportPlay').disabled = !playable;
    el('scrubber').disabled = !playable;
    el('playGlyph').innerHTML = AUDIO.playing ? '&#10074;&#10074;' : '&#9654;';
    el('transportPlay').setAttribute('aria-label', AUDIO.playing ? 'Pause' : 'Play');
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
    INSPECTOR_OPEN = true;
    el('conversionInspector').hidden = false;
    syncInspector();
  }

  function closeInspector() {
    INSPECTOR_OPEN = false;
    el('conversionInspector').hidden = true;
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
    el('warnBar').addEventListener('click', openInspector);
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
    el('winMax').title = STATE.window && STATE.window.maximized ? 'Restore' : 'Maximize';
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
    var warnings = (STATE.stats && STATE.stats.warnings) || [];
    var bar = el('warnBar');
    bar.hidden = warnings.length === 0;
    bar.textContent = warnings.length
      ? warnings[0] + (warnings.length > 1 ? '  +' + (warnings.length - 1) + ' more' : '')
      : '';
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
    el('emptyState').hidden = song;
    el('workspace').hidden = !song;
    el('songName').textContent = song ? baseName(STATE.settings.midi) : '';
    el('menuExport').disabled = !song;
    el('exportBtn').disabled = !song;
    if (song) { renderTracks(); }
    renderTransportState();
    renderPosition(currentPosition());
    renderAudio();
    renderWarnings();
    renderStatus();
    renderWindow();
    if (INSPECTOR_OPEN) { syncInspector(); }
    requestAnimationFrame(resizeCanvas);
  }

  /* --------------------------------------------------------------- startup */

  function shortcut(event) {
    var target = event.target;
    var editing = target && target.closest && target.closest('input, select, textarea');
    if (event.key === 'Escape') {
      if (OPEN_MENU) { closeMenus(); }
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
    canvas.addEventListener('pointerup', endCanvasSeek);
    canvas.addEventListener('pointercancel', endCanvasSeek);
  }

  function init() {
    initMenus();
    initTheme();
    initInspector();
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
    window.addEventListener('resize', debounce(resizeCanvas, 40));
    if (window.ResizeObserver) { new ResizeObserver(resizeCanvas).observe(el('pianoRoll')); }
    render();
    if (api()) { setTimeout(boot, 0); }
  }

  window.addEventListener('pywebviewready', boot);
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); }
  else { init(); }
}());
