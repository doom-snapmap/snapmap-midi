/* snapmap-midi control window.

   Python owns every decision this window shows, including the ruler's geometry.
   Nothing here turns a MIDI note into a position: `rulers` arrives as
   percentages already placed against the 0-127 axis, and this file sets them on
   elements. That is deliberate -- an axis that clips a family, a disjoint range
   drawn as a matter of degree, a drum channel plotted on a pitch axis are all
   failures a Python test can catch and nothing here can.

   Three rules the code below keeps, because breaking them is how a window like
   this goes wrong:

     1. Rows are built once and patched afterwards. Rebuilding the DOM on every
        change replaces the field the user is typing into mid-word and takes the
        caret with it.
     2. The instrument track is updated in place, never recreated -- a CSS
        transition only runs on an element that survives the update.
     3. Every request is stamped and stale answers are dropped. Two overlapping
        applies resolve in arbitrary order, and the older one can return last.

   It also has to survive being opened straight from disk in a browser, which is
   how anyone iterating on the markup will open it: with no `window.pywebview`
   it shows the empty state and throws nothing. */

(function () {
  'use strict';

  var NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  var AXIS_LOW = 0;
  var AXIS_HIGH = 127;          // the axis Python placed its percentages against
  var OCTAVE = 12;
  var TABS = ['channels', 'drums', 'tuning', 'export'];
  var DEBOUNCE_MS = 250;
  var THEME_KEY = 'snapmap_midi_theme';

  var STATE = { settings: null, analysis: null, catalog: null, rulers: null, stats: null };
  var CHAN_ROWS = [];
  var CHAN_KEY = '';
  var DRUM_ROWS = [];
  var DRUM_KEY = '';
  var FAM_ROWS = [];
  var FAM_KEY = '';
  var BUILT = { tuning: false, exporter: false };
  var ACTIVE = 'channels';
  var SEQ = 0;
  var APPLIED = { settings: 0, stats: 0, catalog: 0 };
  var BUSY = 0;
  var BOOTED = false;

  /* ------------------------------------------------------------------ basics */

  function el(id) { return document.getElementById(id); }

  function api() {
    return (window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
  }

  function option(value, text) {
    var o = document.createElement('option');
    o.value = value;
    o.textContent = text;
    return o;
  }

  function noteName(n) {
    if (n === null || n === undefined) { return '--'; }
    var i = ((n % OCTAVE) + OCTAVE) % OCTAVE;
    return NOTE_NAMES[i] + (Math.floor(n / OCTAVE) - 1);
  }

  function baseName(path) {
    var s = String(path || '');
    var cut = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'));
    return cut < 0 ? s : s.slice(cut + 1);
  }

  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }

  function stamp(text) { el('stamp').textContent = text; }

  /* A sliding toast, the same shape snapmap-plus uses. */
  function toast(text, kind) {
    var host = el('toastHost');
    var node = document.createElement('div');
    node.className = 'toast' + (kind ? (' ' + kind) : '');
    node.textContent = text;
    host.appendChild(node);
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { node.classList.add('show'); });
    });
    setTimeout(function () {
      node.classList.remove('show');
      setTimeout(function () { if (node.parentNode) { node.parentNode.removeChild(node); } }, 320);
    }, 2800);
  }

  /* A large file makes an unmarked window look frozen, so anything that crosses
     the bridge holds the busy slot until it answers. Counted, not a flag: two
     calls in flight must not have the first one to finish clear the mark. */
  function setBusy(on) {
    BUSY += on ? 1 : -1;
    if (BUSY < 0) { BUSY = 0; }
    el('busyText').hidden = BUSY === 0;
  }

  function fail(err) {
    toast(String(err && err.message ? err.message : err), 'err');
  }

  /* Text and number fields wait; dropdowns and checkboxes fire immediately,
     because a dropdown has no half-typed state to protect. */
  function debounce(fn) {
    var timer = null;
    return function () {
      var self = this;
      var args = arguments;
      if (timer) { clearTimeout(timer); }
      timer = setTimeout(function () { timer = null; fn.apply(self, args); }, DEBOUNCE_MS);
    };
  }

  /* Never write over a control the user is working in. */
  function held(node) { return document.activeElement === node; }

  function setValue(node, value) { if (!held(node)) { node.value = value; } }

  function setChecked(node, value) { if (!held(node)) { node.checked = !!value; } }

  function numberOrNull(node) {
    var raw = String(node.value).trim();
    if (raw === '') { return null; }
    var n = Number(raw);
    return isNaN(n) ? undefined : n;      // undefined means "unusable, send nothing"
  }

  /* ------------------------------------------------------------------- theme */

  function applyTheme(dark, persist) {
    document.documentElement.classList.toggle('dark', dark);
    el('segLight').classList.toggle('on', !dark);
    el('segDark').classList.toggle('on', dark);
    el('segLight').setAttribute('aria-pressed', String(!dark));
    el('segDark').setAttribute('aria-pressed', String(dark));
    if (!persist) { return; }
    try { window.localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light'); } catch (e) { /* private mode */ }
  }

  function initTheme() {
    var saved = null;
    try { saved = window.localStorage.getItem(THEME_KEY); } catch (e) { saved = null; }
    if (saved === null && window.matchMedia) {
      saved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    applyTheme(saved === 'dark', false);
    el('segLight').addEventListener('click', function () { applyTheme(false, true); });
    el('segDark').addEventListener('click', function () { applyTheme(true, true); });
  }

  /* -------------------------------------------------------------------- tabs */

  function showTab(name) {
    ACTIVE = name;
    var song = hasSong();
    for (var i = 0; i < TABS.length; i++) {
      var which = TABS[i];
      var tab = el('tab-' + which);
      var on = which === name;
      tab.classList.toggle('active', on);
      tab.setAttribute('aria-selected', String(on));
      el('panel-' + which).hidden = !on || !song;
    }
    el('panel-empty').hidden = song;
  }

  function initTabs() {
    for (var i = 0; i < TABS.length; i++) {
      el('tab-' + TABS[i]).addEventListener('click', function () {
        showTab(this.getAttribute('data-tab'));
      });
    }
  }

  /* ------------------------------------------------------------- state reads */

  function hasSong() {
    return !!(STATE.analysis && STATE.analysis.channels && STATE.analysis.channels.length);
  }

  function channels() {
    return (STATE.analysis && STATE.analysis.channels) || [];
  }

  function channelSetting(channel) {
    var all = (STATE.settings && STATE.settings.channels) || {};
    return all[String(channel)] || null;
  }

  function chosenFamily(ch) {
    var entry = channelSetting(ch.channel);
    var name = (entry && entry.family) ? entry.family : ch.auto_family;
    return name || null;
  }

  function familyInfo(name) {
    if (!name || !STATE.catalog) { return null; }
    var families = STATE.catalog.families || [];
    for (var i = 0; i < families.length; i++) {
      if (families[i].name === name) { return families[i]; }
    }
    return null;
  }

  function isMuted(ch) {
    var entry = channelSetting(ch.channel);
    return !!(entry && entry.muted);
  }

  function segmentFor(channel) {
    var all = STATE.rulers || {};
    var seg = all[String(channel)];
    return seg === undefined ? null : seg;
  }

  function drumChannel() {
    var list = channels();
    for (var i = 0; i < list.length; i++) {
      if (list[i].is_drums) { return list[i]; }
    }
    return null;
  }

  function tuning() {
    return (STATE.settings && STATE.settings.tuning) || {};
  }

  /* The sentence a ruler means, in the same words the warning would use, so the
     encoding is never colour alone. It rides on `title` and `aria-label`. */
  function rulerSentence(ch, seg, family) {
    var who = 'Channel ' + ch.channel + ' (' + ch.program_name + ')';
    var plays = who + ' plays ' + noteName(ch.lowest) + '-' + noteName(ch.highest) + '.';
    if (!family) { return plays; }
    var reach = noteName(family.lowest) + '-' + noteName(family.highest);
    if (seg && seg.disjoint) {
      return who + ' shares no note with ' + family.name + ' at all. Every note is transposed.';
    }
    if (seg && seg.outside > 0) {
      return plays + ' ' + family.name + ' only reaches ' + reach + ', so ' + seg.outside
        + ' of its ' + ch.notes + ' notes move to another octave, or to the nearest pitch the family has.';
    }
    return plays + ' ' + family.name + ' reaches ' + reach + ', which covers it.';
  }

  /* ------------------------------------------------------------ bridge calls */

  function next() { return ++SEQ; }

  /* Stamp every request and drop stale answers -- per field, not per call. Two
     overlapping applies resolve in arbitrary order and the older one can return
     last, which is what a stamp fixes. But one counter shared by every call
     buys a second bug: the methods answer with different things, so a dry run
     (stats, no settings) would invalidate an apply still in flight and throw
     away the change the user had just made, putting the control silently back.
     A field only loses to a later answer that actually carries that field. */
  function accept(field, seq) {
    if (seq <= APPLIED[field]) { return false; }
    APPLIED[field] = seq;
    return true;
  }

  function patch(body) {
    if (!api()) { return; }
    var mine = next();
    setBusy(true);
    return api().apply_settings(body).then(function (r) {
      setBusy(false);
      if (!r || !r.ok) {
        /* Re-rendering from the settings we still hold is what puts a refused
           control back to the value the session actually has. */
        if (accept('settings', mine)) {
          toast((r && r.error) || 'that change was refused', 'err');
          render();
        }
        return;
      }
      if (accept('settings', mine)) { STATE.settings = r.settings; STATE.rulers = r.rulers; }
      if (accept('stats', mine)) { STATE.stats = r.stats; }
      stamp('Updated');
      render();
    }, function (e) { setBusy(false); fail(e); });
  }

  function adopt(r, seq) {
    if (accept('settings', seq)) {
      if (r.settings) { STATE.settings = r.settings; }
      if (r.analysis !== undefined) { STATE.analysis = r.analysis; }
      if (r.rulers) { STATE.rulers = r.rulers; }
    }
    if (r.catalog && accept('catalog', seq)) { STATE.catalog = r.catalog; }
    if (r.stats && accept('stats', seq)) { STATE.stats = r.stats; }
  }

  /* `catalog()` names only the drum keys the loaded file uses, so a new file
     needs a fresh one; `load_midi` does not carry it. */
  function refreshCatalog() {
    if (!api()) { return; }
    var mine = next();
    api().catalog().then(function (r) {
      if (r && r.ok && accept('catalog', mine)) { STATE.catalog = r; render(); }
    }, function (e) { fail(e); });
  }

  /* The drums switch changes which channel is a kit and which keys it names,
     and `apply_settings` answers with settings, stats and rulers only. Asking
     for the whole opening payload again is the one call that re-reads the
     analysis without reopening the file and discarding the user's choices. */
  function refreshAll() {
    if (!api()) { return; }
    var mine = next();
    setBusy(true);
    api().startup().then(function (r) {
      setBusy(false);
      if (!r || !r.ok) { toast((r && r.error) || 'the window could not refresh', 'err'); return; }
      adopt(r, mine);
      render();
    }, function (e) { setBusy(false); fail(e); });
  }

  function afterLoad(r, seq) {
    setBusy(false);
    if (!r) { return; }
    if (!r.ok) { toast(r.error || 'that file could not be opened', 'err'); return; }
    adopt(r, seq);
    render();
    refreshCatalog();
    stamp('Opened ' + baseName(STATE.analysis ? STATE.analysis.path : ''));
  }

  function openFile() {
    if (!api()) { toast('the file picker needs the control window', 'warn'); return; }
    var mine = next();
    setBusy(true);
    api().pick_midi().then(function (r) { afterLoad(r, mine); }, function (e) { setBusy(false); fail(e); });
  }

  /* Reads the same file again, for the case where it was edited elsewhere
     between opening it here and looking at it. It goes through `load_midi`
     rather than the picker, so it costs no dialog -- and like any open it
     starts the per-channel choices over, because the channels may not be the
     ones that were there before. */
  function reopen() {
    if (!api() || !STATE.analysis) { return; }
    var mine = next();
    setBusy(true);
    api().load_midi(STATE.analysis.path).then(
      function (r) { afterLoad(r, mine); },
      function (e) { setBusy(false); fail(e); }
    );
  }

  function dryRun() {
    if (!api()) { return; }
    var mine = next();
    setBusy(true);
    api().dry_run().then(function (r) {
      setBusy(false);
      if (!r || !r.ok) { toast((r && r.error) || 'the dry run failed', 'err'); return; }
      if (!accept('stats', mine)) { return; }
      STATE.stats = r.stats;
      render();
      stamp('Checked');
      toast('Map checked', 'ok');
    }, function (e) { setBusy(false); fail(e); });
  }

  function exportMap() {
    if (!api()) { return; }
    var mine = next();
    setBusy(true);
    api().export().then(function (r) {
      setBusy(false);
      if (!r || !r.ok) { toast((r && r.error) || 'the map was not written', 'err'); return; }
      if (r.stats && accept('stats', mine)) { STATE.stats = r.stats; }
      var where = el('xDestination');
      if (where) { where.textContent = r.destination || ''; }
      var advice = el('xAdvice');
      if (advice) { advice.textContent = r.advice || ''; }
      var replaced = el('xReplaced');
      if (replaced) {
        replaced.textContent = r.replaced ? 'This replaced the previous map.' : '';
        replaced.hidden = !r.replaced;
      }
      render();
      stamp('Exported');
      toast('Map exported', 'ok');
    }, function (e) { setBusy(false); fail(e); });
  }

  /* ---------------------------------------------------------------- channels */

  /* Rows are rebuilt only when the file itself changes shape. Every ordinary
     edit patches what is already on screen. */
  function channelKey() {
    var list = channels();
    var parts = [STATE.analysis ? STATE.analysis.path : ''];
    for (var i = 0; i < list.length; i++) {
      parts.push(list[i].channel + ':' + list[i].is_drums + ':' + list[i].notes + ':' + list[i].auto_family);
    }
    return parts.join('|');
  }

  function buildAxis() {
    var strip = document.createElement('div');
    strip.className = 'axis-strip';
    for (var note = AXIS_LOW; note <= AXIS_HIGH; note += OCTAVE) {
      var tick = document.createElement('span');
      tick.className = 'axis-tick';
      tick.style.left = ((note - AXIS_LOW) / (AXIS_HIGH - AXIS_LOW) * 100) + '%';
      tick.textContent = noteName(note);
      strip.appendChild(tick);
    }
    var wrap = document.createElement('div');
    wrap.className = 'axis';
    wrap.appendChild(strip);
    return wrap;
  }

  function fillFamilyOptions(select, autoFamily) {
    select.innerHTML = '';
    /* The way back to the automatic choice. Without it, reopening the file is
       the only way to undo a pick. */
    select.appendChild(option('', 'Automatic (' + (autoFamily || 'none') + ')'));
    var families = (STATE.catalog && STATE.catalog.families) || [];
    for (var i = 0; i < families.length; i++) {
      var f = families[i];
      select.appendChild(option(f.name, f.name + '   ' + noteName(f.lowest) + '-' + noteName(f.highest)));
    }
  }

  function buildChannelRow(ch) {
    var row = document.createElement('div');
    row.className = 'chan-row';
    row.innerHTML =
      '<div class="chan-top">'
      + '<span class="chan-no mono"></span>'
      + '<span class="chan-name"></span>'
      + '<span class="chan-count mono"></span>'
      + '</div>'
      + '<div class="chan-line"></div>'
      + '<div class="chan-note"></div>';

    var top = row.firstChild;
    var ref = {
      node: row,
      channel: ch.channel,
      no: row.querySelector('.chan-no'),
      name: row.querySelector('.chan-name'),
      count: row.querySelector('.chan-count'),
      note: row.querySelector('.chan-note'),
      line: row.querySelector('.chan-line'),
      family: null,
      mute: null,
      ruler: null,
      inst: null,
      cells: [],
      keys: null
    };

    ref.no.textContent = 'Ch ' + ch.channel;
    ref.name.textContent = ch.program_name;
    ref.count.textContent = plural(ch.notes, 'note');

    if (ch.is_drums) {
      var kit = document.createElement('span');
      kit.className = 'chan-kit';
      kit.textContent = 'Drum kit';
      top.appendChild(kit);
    } else {
      ref.family = document.createElement('select');
      ref.family.className = 'chan-family';
      ref.family.setAttribute('aria-label', 'Instrument for channel ' + ch.channel);
      fillFamilyOptions(ref.family, ch.auto_family);
      ref.family.addEventListener('change', function () {
        var body = { channels: {} };
        body.channels[String(ch.channel)] = { family: this.value === '' ? null : this.value };
        patch(body);
      });
      top.appendChild(ref.family);
    }

    var muteWrap = document.createElement('label');
    muteWrap.className = 'chan-mute';
    ref.mute = document.createElement('input');
    ref.mute.type = 'checkbox';
    ref.mute.addEventListener('change', function () {
      var body = { channels: {} };
      body.channels[String(ch.channel)] = { muted: this.checked };
      patch(body);
    });
    muteWrap.appendChild(ref.mute);
    muteWrap.appendChild(document.createTextNode('Mute'));
    top.appendChild(muteWrap);

    if (ch.is_drums) {
      /* No ruler. Its lowest and highest are key numbers, and drawing them on a
         pitch axis would assert something false about what the channel plays. */
      ref.keys = document.createElement('span');
      ref.keys.className = 'mono muted';
      ref.line.appendChild(ref.keys);
    } else {
      ref.ruler = document.createElement('div');
      ref.ruler.className = 'ruler';
      ref.ruler.setAttribute('role', 'img');
      for (var note = AXIS_LOW; note <= AXIS_HIGH; note += OCTAVE) {
        var grid = document.createElement('div');
        grid.className = 'ruler-grid';
        grid.style.left = ((note - AXIS_LOW) / (AXIS_HIGH - AXIS_LOW) * 100) + '%';
        ref.ruler.appendChild(grid);
      }
      /* Created here and updated in place for the life of the row: the
         transition on left/width only runs on an element that survives. */
      ref.inst = document.createElement('div');
      ref.inst.className = 'ruler-inst';
      ref.ruler.appendChild(ref.inst);
      ref.line.appendChild(ref.ruler);
    }
    return ref;
  }

  function buildChannelRows() {
    var host = el('channelList');
    host.innerHTML = '';
    CHAN_ROWS = [];
    var list = channels();
    if (!list.length) {
      var empty = document.createElement('div');
      empty.className = 'list-empty';
      empty.textContent = 'This file has no notes.';
      host.appendChild(empty);
      return;
    }
    for (var i = 0; i < list.length; i++) {
      var ref = buildChannelRow(list[i]);
      CHAN_ROWS.push(ref);
      host.appendChild(ref.node);
    }
    host.appendChild(buildAxis());
  }

  function patchRuler(ref, ch, seg, family) {
    var ruler = ref.ruler;
    if (!ruler) { return; }
    var cells = (seg && seg.cells) || [];
    var width = (seg && seg.cell_width) || 0;

    if (seg && seg.instrument) {
      ref.inst.hidden = false;
      ref.inst.style.left = seg.instrument.left + '%';
      ref.inst.style.width = seg.instrument.width + '%';
    } else {
      ref.inst.hidden = true;
    }
    ref.inst.classList.toggle('disjoint', !!(seg && seg.disjoint));

    while (ref.cells.length < cells.length) {
      var cell = document.createElement('div');
      cell.className = 'ruler-cell';
      ruler.appendChild(cell);
      ref.cells.push(cell);
    }
    while (ref.cells.length > cells.length) {
      var extra = ref.cells.pop();
      if (extra.parentNode) { extra.parentNode.removeChild(extra); }
    }
    for (var i = 0; i < cells.length; i++) {
      var c = cells[i];
      var node = ref.cells[i];
      node.style.left = c.left + '%';
      node.style.width = width + '%';
      node.style.opacity = 0.25 + 0.75 * c.weight;
      var out = !!(family && (c.note < family.lowest || c.note > family.highest));
      node.classList.toggle('out', out);
    }

    var sentence = rulerSentence(ch, seg, family);
    ruler.title = sentence;
    ruler.setAttribute('aria-label', sentence);
  }

  function patchChannelRow(ref, ch) {
    var family = familyInfo(chosenFamily(ch));
    var seg = segmentFor(ch.channel);
    var muted = isMuted(ch);

    ref.node.classList.toggle('off', muted);
    setChecked(ref.mute, muted);
    if (ref.family) {
      var entry = channelSetting(ch.channel);
      setValue(ref.family, (entry && entry.family) ? entry.family : '');
    }

    if (ref.keys) {
      var keys = ch.drum_keys || {};
      var total = 0;
      var unmapped = 0;
      var overrides = (STATE.settings && STATE.settings.drum_keys) || {};
      for (var key in keys) {
        if (!Object.prototype.hasOwnProperty.call(keys, key)) { continue; }
        total += 1;
        if (!overrides[String(key)] && !keys[key]) { unmapped += 1; }
      }
      ref.keys.textContent = plural(total, 'key') + '  ·  ' + unmapped + ' unmapped';
      ref.note.className = 'chan-note' + (unmapped ? ' warn' : '');
      ref.note.textContent = unmapped
        ? 'Give the unmapped keys sounds on the Drums tab, or they play nothing.'
        : '';
      return;
    }

    patchRuler(ref, ch, seg, family);

    if (seg && seg.disjoint) {
      ref.note.className = 'chan-note err';
      ref.note.textContent = rulerSentence(ch, seg, family);
    } else if (seg && seg.outside > 0) {
      ref.note.className = 'chan-note warn';
      ref.note.textContent = rulerSentence(ch, seg, family);
    } else {
      ref.note.className = 'chan-note';
      ref.note.textContent = '';
    }
  }

  function renderChannels() {
    var key = channelKey();
    if (key !== CHAN_KEY) { buildChannelRows(); CHAN_KEY = key; }
    var list = channels();
    el('chanBadge').textContent = list.length;
    for (var i = 0; i < CHAN_ROWS.length && i < list.length; i++) {
      patchChannelRow(CHAN_ROWS[i], list[i]);
    }
  }

  /* ------------------------------------------------------------------- drums */

  function drumKeyList(ch) {
    var keys = (ch && ch.drum_keys) || {};
    var out = [];
    for (var key in keys) {
      if (Object.prototype.hasOwnProperty.call(keys, key)) { out.push(Number(key)); }
    }
    out.sort(function (a, b) { return a - b; });
    return out;
  }

  function drumKeyName(key) {
    var names = (STATE.catalog && STATE.catalog.drum_names) || {};
    return names[String(key)] || ('Key ' + key);
  }

  function fillDrumOptions(select, tableSound) {
    select.innerHTML = '';
    select.appendChild(option('', tableSound ? ('Default (' + tableSound + ')') : 'No sound'));
    var sounds = (STATE.catalog && STATE.catalog.drum_sounds) || [];
    var groups = {};
    var order = [];
    for (var i = 0; i < sounds.length; i++) {
      var cat = sounds[i].category || 'other';
      if (!groups[cat]) { groups[cat] = []; order.push(cat); }
      groups[cat].push(sounds[i]);
    }
    for (var g = 0; g < order.length; g++) {
      var box = document.createElement('optgroup');
      box.label = order[g];
      var members = groups[order[g]];
      for (var m = 0; m < members.length; m++) {
        box.appendChild(option(members[m].name, members[m].label || members[m].name));
      }
      select.appendChild(box);
    }
  }

  /* Sent whole rather than as a single key, because clearing one back to the
     table's own answer has no other spelling in the settings document. */
  function drumKeyPatch(key, value) {
    var current = (STATE.settings && STATE.settings.drum_keys) || {};
    var next = {};
    for (var k in current) {
      if (Object.prototype.hasOwnProperty.call(current, k) && String(k) !== String(key)) {
        next[String(k)] = current[k];
      }
    }
    if (value) { next[String(key)] = value; }
    patch({ drum_keys: next });
  }

  function buildDrumRow(ch, key) {
    var row = document.createElement('div');
    row.className = 'drum-row';
    row.innerHTML =
      '<span class="drum-key mono"></span>'
      + '<span class="drum-name"></span>'
      + '<span class="drum-state"></span>';

    var ref = {
      node: row,
      key: key,
      keyText: row.querySelector('.drum-key'),
      name: row.querySelector('.drum-name'),
      state: row.querySelector('.drum-state'),
      pick: document.createElement('select')
    };
    ref.keyText.textContent = 'Key ' + key;
    ref.name.textContent = drumKeyName(key);
    ref.pick.className = 'drum-pick';
    ref.pick.setAttribute('aria-label', 'Sound for key ' + key);
    fillDrumOptions(ref.pick, (ch.drum_keys || {})[String(key)] || null);
    ref.pick.addEventListener('change', function () { drumKeyPatch(key, this.value); });
    row.insertBefore(ref.pick, ref.state);
    return ref;
  }

  function drumKey() {
    var ch = drumChannel();
    if (!ch) { return 'none'; }
    return ch.channel + '|' + drumKeyList(ch).join(',') + '|'
      + ((STATE.catalog && STATE.catalog.drum_sounds) ? STATE.catalog.drum_sounds.length : 0);
  }

  function buildDrumRows() {
    var host = el('drumList');
    host.innerHTML = '';
    DRUM_ROWS = [];
    var ch = drumChannel();
    if (!ch) {
      var empty = document.createElement('div');
      empty.className = 'list-empty';
      empty.textContent = 'This file has no drum channel. Turn the drum channel on to route channel notes through the kit.';
      host.appendChild(empty);
      return;
    }
    var keys = drumKeyList(ch);
    for (var i = 0; i < keys.length; i++) {
      var ref = buildDrumRow(ch, keys[i]);
      DRUM_ROWS.push(ref);
      host.appendChild(ref.node);
    }
  }

  function renderDrums() {
    var key = drumKey();
    if (key !== DRUM_KEY) { buildDrumRows(); DRUM_KEY = key; }

    var mode = (STATE.settings && STATE.settings.drums) || 'auto';
    setValue(el('drumMode'), mode);
    var ch = drumChannel();
    el('drumModeHint').textContent = ch
      ? ('Channel ' + ch.channel + ' plays the kit.')
      : 'No channel is playing a kit.';

    var overrides = (STATE.settings && STATE.settings.drum_keys) || {};
    var table = (ch && ch.drum_keys) || {};
    var unmapped = 0;
    for (var i = 0; i < DRUM_ROWS.length; i++) {
      var ref = DRUM_ROWS[i];
      var chosen = overrides[String(ref.key)] || '';
      setValue(ref.pick, chosen);
      var effective = chosen || table[String(ref.key)] || null;
      if (!effective) { unmapped += 1; }
      ref.state.className = 'drum-state' + (effective ? '' : ' warn');
      ref.state.textContent = effective ? '' : 'no sound';
    }
    el('drumBadge').textContent = DRUM_ROWS.length + (unmapped ? (' · ' + unmapped) : '');
  }

  /* ------------------------------------------------------------------ tuning */

  function tuningPatch(body) { patch({ tuning: body }); }

  function buildTuning() {
    el('tuningBody').innerHTML =
      '<div class="form-row">'
      + '<label for="tSpeakers">Max speakers</label>'
      + '<input type="number" id="tSpeakers" min="1" max="64" step="1">'
      + '<span class="hint">How many notes may sound at once. The engine recycles slots past this.</span>'
      + '</div>'
      + '<div class="form-row">'
      + '<label for="tRelease">Release (seconds)</label>'
      + '<input type="number" id="tRelease" min="0" max="10" step="0.01">'
      + '<span class="hint">How long a released note takes to fall silent.</span>'
      + '</div>'
      + '<div class="form-row">'
      + '<label for="tHardStop">Hard stop</label>'
      + '<span><input type="checkbox" id="tHardStop"></span>'
      + '<span class="hint">Cut a note dead instead of letting it fade.</span>'
      + '</div>'
      + '<div class="form-row">'
      + '<label for="tMaxPoly">Max polyphony</label>'
      + '<input type="number" id="tMaxPoly" min="1" step="1" placeholder="none">'
      + '<span class="hint">Thin dense chords to this many notes. Leave empty for no limit.</span>'
      + '</div>'
      + '<div class="form-row">'
      + '<label for="tCapSustain">Cap sustain (ms)</label>'
      + '<input type="number" id="tCapSustain" min="0" step="10" placeholder="none">'
      + '<span class="hint">Shorten every held note to this. Leave empty to keep written lengths.</span>'
      + '</div>'
      + '<div class="form-row">'
      + '<label for="tBassPitch">Bass pitch</label>'
      + '<input type="number" id="tBassPitch" min="0" max="127" step="1">'
      + '<span class="hint">Notes below this count as bass, and take the bass cap.</span>'
      + '</div>'
      + '<div class="form-row">'
      + '<label for="tBassCap">Bass cap (ms)</label>'
      + '<input type="number" id="tBassCap" min="0" step="10" placeholder="none">'
      + '<span class="hint">Shorten bass notes to this. Leave empty to keep written lengths.</span>'
      + '</div>'
      + '<div class="section-label">Families in this song</div>'
      + '<p class="muted" id="tFamNote">Move a family to the decaying path to free its speaker slots, or cap how long its notes hold.</p>'
      + '<table class="fam-table"><thead><tr>'
      + '<th>Family</th><th>Decaying</th><th>Cap (ms)</th>'
      + '</tr></thead><tbody id="tFamBody"></tbody></table>';

    bindNumber('tSpeakers', 'max_speakers', false);
    bindNumber('tRelease', 'release_s', false);
    bindNumber('tMaxPoly', 'max_poly', true);
    bindNumber('tCapSustain', 'cap_sustain_ms', true);
    bindNumber('tBassPitch', 'bass_pitch', false);
    bindNumber('tBassCap', 'bass_cap_ms', true);
    el('tHardStop').addEventListener('change', function () {
      tuningPatch({ hard_stop: this.checked });
    });
  }

  function bindNumber(id, keyName, nullable) {
    var node = el(id);
    node.addEventListener('input', debounce(function () {
      var value = numberOrNull(node);
      if (value === undefined) { return; }
      if (value === null && !nullable) { return; }
      var body = {};
      body[keyName] = value;
      tuningPatch(body);
    }));
  }

  /* Only the families this song actually reaches for. A cap on a family no
     channel plays changes nothing, and sixteen inert rows would hide the two
     that matter. */
  function familiesInPlay() {
    var seen = {};
    var out = [];
    var list = channels();
    var i;
    for (i = 0; i < list.length; i++) {
      var name = list[i].is_drums ? null : chosenFamily(list[i]);
      if (name && !seen[name]) { seen[name] = true; out.push(name); }
    }
    var t = tuning();
    var decaying = t.decaying_families || [];
    for (i = 0; i < decaying.length; i++) {
      if (!seen[decaying[i]]) { seen[decaying[i]] = true; out.push(decaying[i]); }
    }
    var caps = t.family_caps || {};
    for (var cap in caps) {
      if (Object.prototype.hasOwnProperty.call(caps, cap) && !seen[cap]) {
        seen[cap] = true;
        out.push(cap);
      }
    }
    out.sort();
    return out;
  }

  function decayingPatch(name, on) {
    var current = (tuning().decaying_families || []).slice();
    var at = current.indexOf(name);
    if (on && at < 0) { current.push(name); }
    if (!on && at >= 0) { current.splice(at, 1); }
    tuningPatch({ decaying_families: current });
  }

  function capPatch(name, value) {
    var current = tuning().family_caps || {};
    var next = {};
    for (var k in current) {
      if (Object.prototype.hasOwnProperty.call(current, k) && k !== name) { next[k] = current[k]; }
    }
    if (value !== null && value !== undefined) { next[name] = value; }
    tuningPatch({ family_caps: next });
  }

  function buildFamilyRows(names) {
    var body = el('tFamBody');
    body.innerHTML = '';
    FAM_ROWS = [];
    for (var i = 0; i < names.length; i++) {
      (function (name) {
        var tr = document.createElement('tr');
        var cellName = document.createElement('td');
        cellName.className = 'mono';
        cellName.textContent = name;

        var cellDecay = document.createElement('td');
        var box = document.createElement('input');
        box.type = 'checkbox';
        box.setAttribute('aria-label', 'Play ' + name + ' on the decaying path');
        box.addEventListener('change', function () { decayingPatch(name, this.checked); });
        cellDecay.appendChild(box);

        var cellCap = document.createElement('td');
        var num = document.createElement('input');
        num.type = 'number';
        num.min = '0';
        num.step = '10';
        num.placeholder = 'none';
        num.setAttribute('aria-label', 'Cap for ' + name + ' in milliseconds');
        num.addEventListener('input', debounce(function () {
          var value = numberOrNull(num);
          if (value === undefined) { return; }
          capPatch(name, value);
        }));
        cellCap.appendChild(num);

        tr.appendChild(cellName);
        tr.appendChild(cellDecay);
        tr.appendChild(cellCap);
        body.appendChild(tr);
        FAM_ROWS.push({ name: name, decay: box, cap: num });
      }(names[i]));
    }
  }

  function renderTuning() {
    if (!BUILT.tuning) { buildTuning(); BUILT.tuning = true; }
    var t = tuning();
    setValue(el('tSpeakers'), t.max_speakers === null || t.max_speakers === undefined ? '' : t.max_speakers);
    setValue(el('tRelease'), t.release_s === null || t.release_s === undefined ? '' : t.release_s);
    setChecked(el('tHardStop'), t.hard_stop);
    setValue(el('tMaxPoly'), t.max_poly === null || t.max_poly === undefined ? '' : t.max_poly);
    setValue(el('tCapSustain'), t.cap_sustain_ms === null || t.cap_sustain_ms === undefined ? '' : t.cap_sustain_ms);
    setValue(el('tBassPitch'), t.bass_pitch === null || t.bass_pitch === undefined ? '' : t.bass_pitch);
    setValue(el('tBassCap'), t.bass_cap_ms === null || t.bass_cap_ms === undefined ? '' : t.bass_cap_ms);

    var names = familiesInPlay();
    var key = names.join(',');
    if (key !== FAM_KEY) { buildFamilyRows(names); FAM_KEY = key; }

    var decaying = t.decaying_families || [];
    var caps = t.family_caps || {};
    for (var i = 0; i < FAM_ROWS.length; i++) {
      var ref = FAM_ROWS[i];
      setChecked(ref.decay, decaying.indexOf(ref.name) >= 0);
      var cap = caps[ref.name];
      setValue(ref.cap, cap === undefined || cap === null ? '' : cap);
    }
  }

  /* ------------------------------------------------------------------ export */

  function buildExport() {
    el('exportBody').innerHTML =
      '<div class="form-row">'
      + '<label for="xButton">Button name</label>'
      + '<span class="wide"><input type="text" id="xButton"></span>'
      + '</div>'
      + '<div class="form-row">'
      + '<label for="xOutDir">Output folder</label>'
      + '<span class="wide"><input type="text" id="xOutDir" readonly>'
      + '<button type="button" class="btn" id="xOutBtn">Browse</button></span>'
      + '</div>'
      + '<div class="form-row">'
      + '<label for="xBaseline">Baseline map</label>'
      + '<span class="wide"><input type="text" id="xBaseline" readonly>'
      + '<button type="button" class="btn" id="xBaseBtn">Browse</button>'
      + '<button type="button" class="btn" id="xBaseClear">Clear</button></span>'
      + '</div>'
      + '<div class="section-label">What this will produce</div>'
      + '<div class="readout">'
      + '<span>Notes <b id="xNotes">0</b></span>'
      + '<span>Dropped <b id="xDropped">0</b></span>'
      + '<span>Decaying <b id="xDecaying">0</b></span>'
      + '<span>Sustained <b id="xSustained">0</b></span>'
      + '<span>Events <b id="xEvents">0</b></span>'
      + '<span>Long sustains <b id="xLong">0</b></span>'
      + '<span>Peak voices <b id="xPeak">0</b></span>'
      + '<span>Length <b id="xLength">0</b></span>'
      + '</div>'
      + '<div class="actions">'
      + '<button type="button" class="btn" id="xDryBtn">Dry run</button>'
      + '<button type="button" class="btn primary" id="xExportBtn">Export map</button>'
      + '</div>'
      + '<p class="muted mono" id="xDestination"></p>'
      + '<p class="muted" id="xReplaced" hidden></p>'
      + '<p class="muted" id="xAdvice"></p>';

    el('xButton').addEventListener('input', debounce(function () {
      patch({ button: el('xButton').value });
    }));
    el('xOutBtn').addEventListener('click', function () {
      if (!api()) { return; }
      var mine = next();
      setBusy(true);
      api().pick_out_dir().then(function (r) {
        setBusy(false);
        if (!r || !r.ok) { if (r && r.error) { toast(r.error, 'err'); } return; }
        adopt(r, mine);
        render();
      }, function (e) { setBusy(false); fail(e); });
    });
    el('xBaseBtn').addEventListener('click', function () {
      if (!api()) { return; }
      var mine = next();
      setBusy(true);
      api().pick_baseline().then(function (r) {
        setBusy(false);
        if (!r || !r.ok) { if (r && r.error) { toast(r.error, 'err'); } return; }
        adopt(r, mine);
        render();
      }, function (e) { setBusy(false); fail(e); });
    });
    el('xBaseClear').addEventListener('click', function () { patch({ baseline: null }); });
    el('xDryBtn').addEventListener('click', dryRun);
    el('xExportBtn').addEventListener('click', exportMap);
  }

  function renderExport() {
    if (!BUILT.exporter) { buildExport(); BUILT.exporter = true; }
    var s = STATE.settings || {};
    setValue(el('xButton'), s.button || '');
    setValue(el('xOutDir'), s.out_dir || '');
    setValue(el('xBaseline'), s.baseline || '');
    el('xBaseClear').disabled = !s.baseline;

    var stats = STATE.stats || {};
    el('xNotes').textContent = stats.notes || 0;
    el('xDropped').textContent = stats.dropped || 0;
    el('xDecaying').textContent = stats.decaying || 0;
    el('xSustained').textContent = stats.sustained || 0;
    el('xEvents').textContent = stats.events || 0;
    el('xLong').textContent = stats.long_sustains || 0;
    el('xPeak').textContent = (stats.peak_voices || 0) + ' / ' + (stats.max_speakers || 0);
    el('xLength').textContent = (stats.duration_s || 0) + 's';
  }

  /* -------------------------------------------------- warnings and statusbar */

  /* Verbatim. Each one already names a cause, a magnitude and the lever that
     changes it; rewording them here would put a second voice in the window. */
  function renderWarnings() {
    var bar = el('warnBar');
    var list = (STATE.stats && STATE.stats.warnings) || [];
    bar.innerHTML = '';
    bar.hidden = !list.length;
    for (var i = 0; i < list.length; i++) {
      var row = document.createElement('div');
      row.className = 'warn-row';
      var sev = document.createElement('span');
      sev.className = 'sev';
      sev.textContent = '!';
      var text = document.createElement('span');
      text.textContent = list[i];
      row.appendChild(sev);
      row.appendChild(text);
      bar.appendChild(row);
    }
  }

  function setBridge(connected, text) {
    var dot = el('bridgeDot');
    dot.className = 'dot' + (connected ? ' ok' : ' no');
    el('bridgeText').textContent = text;
  }

  function renderStatus() {
    el('songName').textContent = STATE.analysis ? baseName(STATE.analysis.path) : '';
    el('reopenBtn').disabled = !(api() && STATE.analysis);
    var stats = STATE.stats;
    var slots = ['slotNotes', 'slotVoices', 'slotSustain', 'slotLength'];
    for (var i = 0; i < slots.length; i++) { el(slots[i]).hidden = !stats; }
    if (!stats) { return; }
    el('statNotes').textContent = stats.notes;
    el('statVoices').textContent = stats.peak_voices + ' / ' + stats.max_speakers;
    el('statSustain').textContent = stats.long_sustains;
    el('statLength').textContent = stats.duration_s + 's';
  }

  function render() {
    showTab(ACTIVE);
    if (hasSong()) {
      renderChannels();
      renderDrums();
      renderTuning();
      renderExport();
    }
    renderStatus();
    renderWarnings();
  }

  /* -------------------------------------------------------------------- boot */

  function boot() {
    if (BOOTED) { return; }
    BOOTED = true;
    if (!api()) { return; }
    setBridge(true, 'ready');
    var mine = next();
    setBusy(true);
    api().startup().then(function (r) {
      setBusy(false);
      if (!r) { return; }
      /* `ok` and `error` can both be set: opening on a bad path still opens a
         usable window, and the message is the only place that says why. */
      if (r.error) { toast(r.error, r.ok ? 'warn' : 'err'); }
      if (!r.ok) { render(); return; }
      adopt(r, mine);
      render();
      if (hasSong()) { stamp('Opened ' + baseName(STATE.analysis.path)); }
    }, function (e) { setBusy(false); fail(e); });
  }

  function init() {
    initTheme();
    initTabs();
    el('openBtn').addEventListener('click', openFile);
    el('emptyOpenBtn').addEventListener('click', openFile);
    el('reopenBtn').addEventListener('click', reopen);
    el('drumMode').addEventListener('change', function () {
      var mode = this.value;
      var done = patch({ drums: mode });
      /* The switch decides which channel is a kit and which keys it names, and
         only the analysis carries that. */
      if (done && done.then) { done.then(refreshAll); } else { refreshAll(); }
    });
    setBridge(false, 'no window attached');
    render();
    if (api()) { boot(); }
  }

  /* pywebview signals its bridge is ready with this event. Opened straight from
     disk in a browser it never fires, `api()` stays null, and the window sits on
     its empty state rather than throwing. */
  window.addEventListener('pywebviewready', boot);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}());
