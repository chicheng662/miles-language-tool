/* Original native-slot adapter, compiled locally with the user's own strings. */
var MMSpiderMan2 = (function (profile, lines) {
  'use strict';
  var slots = [null, null], scheduled = false, serial = 0;
  var marker = /\[\[MMID:(\d+)\]\]/;

  // Strip only game controls/unsafe tags; preserve native speaker classes and
  // common text emphasis. Never evaluate game strings or copy binding attrs.
  function safeHTML(value) {
    return String(value)
      .replace(/<\s*(script|style|iframe|object)\b[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi, '')
      .replace(/<[^>]*>/g, function (tag) {
        var m = /^<\s*(\/?)\s*([a-z][a-z0-9-]*)\b([^>]*)>/i.exec(tag);
        if (!m) return '';
        var name = m[2].toLowerCase();
        if (!/^(p|span|b|i|u|s|em|strong|br|font)$/.test(name)) return '';
        if (m[1]) return name === 'br' ? '' : '</' + (name === 'font' ? 'span' : name) + '>';
        if (name === 'br') return '<br>';
        var classes = /\bclass\s*=\s*["']([^"']*)["']/i.exec(m[3]);
        var color = /\bcolor\s*=\s*["']?(#[a-f0-9]{3,8})\b/i.exec(m[3]);
        var attrs = '';
        if (classes) {
          var keep = classes[1].split(/\s+/).filter(function (c) {
            return /^(subtitleText|subtitleColor|subtitleSpeakerColor)$/.test(c);
          });
          if (keep.length) attrs = ' class="' + keep.join(' ') + '"';
        }
        if (name === 'font' && color) attrs = ' style="color:' + color[1] + '"';
        return '<' + (name === 'font' ? 'span' : name) + attrs + '>';
      });
  }
  function visibleText(html) { return html.replace(/<[^>]*>/g, '').replace(/&(?:nbsp|#160);/g, ' ').trim(); }
  function scale() {
    var n = getWindowStageScale();
    return isFinite(n) && n > 0 ? n : 1;
  }
  function enqueue() {
    if (!scheduled) { scheduled = true; window.requestAnimationFrame(tick); }
  }
  function clearLayers(s) {
    if (s.upper) s.upper.style.display = 'none';
    if (s.lower) s.lower.style.display = 'none';
    s.visibleUpper = s.visibleLower = null;
  }
  function restore(s) {
    clearLayers(s);
    if (s.masked) {
      s.text.style.visibility = s.visibility;
      s.masked = false;
    }
    s.marked = false;
  }
  function mask(s) {
    if (!s.masked) { s.visibility = s.text.style.visibility || ''; s.masked = true; }
    s.text.style.visibility = 'hidden';
  }
  function getSlot(i) {
    var owner = subtitle_elems[i], text = subtitle_elems_text[i];
    if (!owner || !text) return null;
    if (!slots[i] || slots[i].owner !== owner || slots[i].text !== text) {
      if (slots[i]) restore(slots[i]);
      slots[i] = {owner: owner, text: text, order: 0, wait: 0, marked: false};
    }
    return slots[i];
  }
  function makeLayer(s, which) {
    var elem = document.createElement('div');
    elem.className = 'mm2-layer mm2-' + which;
    elem.style.position = 'absolute'; elem.style.left = '0px'; elem.style.top = '0px';
    elem.style.width = '100px'; elem.style.margin = '0'; elem.style.padding = '0';
    elem.style.transform = 'none'; elem.style.transformOrigin = '0 0';
    elem.style.pointerEvents = 'none'; elem.style.whiteSpace = 'normal';
    elem.style.wordWrap = 'break-word'; elem.style.overflowWrap = 'break-word';
    elem.style.textAlign = 'center'; elem.style.lineHeight = '1.3';
    elem.style.color = 'var(--subtitleTextColor)';
    elem.style.visibility = 'visible';
    s.owner.appendChild(elem);
    return elem;
  }
  function nativeFontFamily(s) {
    // Font selection may live on the generated native paragraph class that
    // safeHTML removes to avoid inheriting its layout. Read the resolved font
    // from the untouched binding on each update, including language changes.
    var nativeText = s.text.querySelector('.subtitleText') || s.text.querySelector('p') || s.text;
    var family = '';
    if (typeof window.getComputedStyle === 'function') {
      try {
        family = window.getComputedStyle(nativeText).fontFamily;
        if (!family && nativeText !== s.text) family = window.getComputedStyle(s.text).fontFamily;
      } catch (error) { /* Some embedded engines expose only inline styles. */ }
    }
    return family || nativeText.style.fontFamily || s.text.style.fontFamily || s.fontFamily || 'sans-serif';
  }
  function layer(s, which, template, value, enabled, size, outline, background) {
    var html = safeHTML(value);
    if (!enabled || !visibleText(html)) {
      if (s[which]) s[which].style.display = 'none';
      return null;
    }
    var elem = s[which] || (s[which] = makeLayer(s, which));
    // Substitute before sanitizing so the engine's speaker prefix and wrapping
    // survive, without ever assigning to the engine-bound native text node.
    var composed = safeHTML(template.replace(marker, function () { return String(value); }));
    if (elem.innerHTML !== composed) elem.innerHTML = composed;
    elem.style.display = 'block';
    var rect = elem.getBoundingClientRect();
    var factor = elem.offsetWidth > 0 ? rect.width / elem.offsetWidth : 1;
    if (!(factor > 0)) factor = 1;
    elem.mmFactor = factor;
    elem.style.width = Math.max(1, Math.min(window.innerWidth - 40, 1370 * scale())) / factor + 'px';
    elem.style.fontFamily = s.fontFamily;
    elem.style.fontSize = size * scale() / factor + 'px';
    elem.style.textShadow = outline ? '1px 1px 2px #000, -1px -1px 2px #000' : 'none';
    elem.style.backgroundColor = background ? 'rgba(0,0,0,0.65)' : 'transparent';
    // Native paragraph classes contain their own font size/background/shadow.
    // Override dimensions only, retaining their speaker/text colors.
    var descendants = elem.querySelectorAll('*');
    for (var j = 0; j < descendants.length; j++) {
      var st = descendants[j].style;
      // Cohtml resolves an explicit family on inserted child text reliably;
      // font-family:inherit renders with its default font (missing CJK glyphs).
      st.fontFamily = s.fontFamily; st.fontSize = 'inherit'; st.lineHeight = 'inherit'; st.textShadow = 'inherit';
      st.position = 'static'; st.width = 'auto'; st.height = 'auto';
      st.margin = '0'; st.padding = '0'; st.backgroundColor = 'transparent';
      st.transform = 'none';
    }
    return elem;
  }
  function place(elem, y) {
    var rect = elem.getBoundingClientRect(), k = elem.mmFactor;
    elem.style.top = ((parseFloat(elem.style.top) || 0) + (y - rect.top) / k) + 'px';
    elem.style.left = ((parseFloat(elem.style.left) || 0) + ((window.innerWidth - rect.width) / 2 - rect.left) / k) + 'px';
  }
  function height(elem) { return elem ? elem.getBoundingClientRect().height : 0; }
  function active(s) { return s && (s.owner.elem_shown || s.owner.elem_playing); }
  function read(s) {
    var template = s.text.innerHTML, match = marker.exec(template);
    if (!match) { restore(s); return; }
    mask(s); s.marked = true;
    var id = Number(match[1]), pair = lines[id];
    if (s.wait > 0 || !pair) { clearLayers(s); return; }
    s.fontFamily = nativeFontFamily(s);
    s.visibleUpper = layer(s, 'upper', template, pair[1], profile.top_language !== null,
      profile.top_size, profile.top_outline, profile.top_background);
    s.visibleLower = layer(s, 'lower', template, pair[0], profile.bottom_language !== null,
      profile.bottom_size, profile.bottom_outline, profile.bottom_background);
  }
  function layout() {
    var shown = slots.filter(active).sort(function (a, b) { return b.order - a.order; });
    if (!shown.some(function (s) { return s.marked; })) {
      shown.forEach(function (s) {
        if (s.nativePlaced && s.owner.style.top === s.nativePlaced) s.owner.style.top = s.nativeTop;
        s.nativePlaced = null;
      });
      return;
    }
    var cursor = window.innerHeight - profile.bottom_margin_px;
    var topCursor = profile.top_margin_px;
    var speakerGap = 12 * scale();
    shown.forEach(function (s) {
      if (!s.marked) {
        // Reserve native-only lines too when mixed with a translated slot.
        var rect = s.text.getBoundingClientRect();
        if (s.owner.style.top !== s.nativePlaced) s.nativeTop = s.owner.style.top;
        var ownerRect = s.owner.getBoundingClientRect();
        var factor = s.owner.offsetWidth > 0 ? ownerRect.width / s.owner.offsetWidth : 1;
        if (!(factor > 0)) factor = 1;
        s.owner.style.top = ((parseFloat(s.owner.style.top) || 0) + (cursor - rect.bottom) / factor) + 'px';
        s.nativePlaced = s.owner.style.top;
        cursor -= rect.height + speakerGap;
        return;
      }
      var upper = s.visibleUpper, lower = s.visibleLower;
      if (s.wait > 0 || !upper && !lower) return;
      var uh = height(upper), lh = height(lower);
      if (lower) { cursor -= lh; place(lower, cursor); }
      if (profile.layout === 'split') {
        if (upper) { place(upper, topCursor); topCursor += uh + speakerGap; }
      } else if (upper) {
        if (lower) cursor -= profile.line_gap_px;
        cursor -= uh; place(upper, cursor);
      }
      // Native metrics inform the other slot's own collision calculations.
      s.owner.elem_height = (lh + (profile.layout === 'stacked' ? uh + (lh && uh ? profile.line_gap_px : 0) : 0)) / scale();
      if (lower || profile.layout === 'stacked' && upper) cursor -= speakerGap;
    });
  }
  function tick() {
    scheduled = false;
    var any = false;
    for (var i = 0; i < 2; i++) {
      var s = getSlot(i);
      if (!s) continue;
      if (active(s)) {
        any = true;
        if (s.wait > 0) s.wait--;
        read(s);
      } else { restore(s); s.visibleUpper = s.visibleLower = null; }
    }
    layout();
    if (any) enqueue();
  }
  function show(i) {
    var s = getSlot(i);
    if (!s) return;
    clearLayers(s); s.visibleUpper = s.visibleLower = null;
    s.wait = 4; s.order = ++serial;
    // Mask immediately; never flash an MMID during the native intro delay.
    if (marker.test(s.text.innerHTML)) mask(s);
    enqueue();
  }
  function cache() {
    slots.forEach(function (s) {
      if (!s) return;
      restore(s);
      ['upper', 'lower'].forEach(function (which) {
        if (s[which] && s[which].parentNode) s[which].parentNode.removeChild(s[which]);
      });
    });
    slots = [null, null];
  }
  engine.on('CacheSubtitleCCElements', cache);
  engine.on('ShowSubtitle', show);
  window.addEventListener('resize', enqueue);
  return {hide: function () { enqueue(); }};
})(__MM2_PROFILE__, __MM2_LINES__);
