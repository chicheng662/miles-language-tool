/* Original small DOM/animation fixture. It contains no extracted game code. */
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const scripts = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const number = value => parseFloat(value) || 0;
const plain = html => html.replace(/<[^>]*>/g, '').replace(/&amp;/g, '&');

class Element {
  constructor(tag, scale) {
    this.tagName = tag.toUpperCase(); this.style = {}; this.children = [];
    this.innerHTML = ''; this.scale = scale; this.className = '';
    this.generatedChild = {style: {}};
  }
  appendChild(node) { node.parentNode = this; this.children.push(node); return node; }
  removeChild(node) { this.children.splice(this.children.indexOf(node), 1); node.parentNode = null; }
  get textContent() { return plain(this.innerHTML); }
  get offsetWidth() { return number(this.style.width) || 500; }
  get offsetHeight() {
    const font = number(this.style.fontSize) || 32;
    return Math.max(1, Math.ceil(plain(this.innerHTML).length * font * .55 / this.offsetWidth)) * font * 1.3;
  }
  getBoundingClientRect() {
    const parent = this.parentNode ? this.parentNode.getBoundingClientRect() : {left: 0, top: 0};
    const k = this.scale;
    const width = this.offsetWidth * k, height = this.offsetHeight * k;
    const left = parent.left + number(this.style.left) * k;
    const top = parent.top + number(this.style.top) * k;
    return {left, top, right: left + width, bottom: top + height, width, height};
  }
  querySelectorAll() { return this.innerHTML ? [this.generatedChild] : []; }
  querySelector(selector) { return selector === '.subtitleText' || selector === 'p' ? this.nativeParagraph || null : null; }
}

function setup(name, scale = 1, physicalScale = 1) {
  const handlers = {}, queue = [];
  const owners = [new Element('div', physicalScale), new Element('div', physicalScale)];
  const texts = owners.map(o => o.appendChild(new Element('div', physicalScale)));
  texts.forEach(t => {
    t.innerHTML = '<p class="subtitleText">Native plain</p>';
    t.computedFont = 'FixtureContainer, sans-serif';
    t.nativeParagraph = new Element('p', physicalScale);
    t.nativeParagraph.computedFont = 'FixtureDialogue, sans-serif';
  });
  const window = {fixtureOwners: owners, fixtureTexts: texts, fixtureScale: scale,
    innerWidth: 1920 * scale, innerHeight: 1080 * scale,
    requestAnimationFrame: f => queue.push(f), addEventListener() {},
    getComputedStyle: elem => ({fontFamily: elem.computedFont || ''})};
  const context = {window, console, document: {createElement: tag => new Element(tag, physicalScale)},
    engine: {on(name, f) { (handlers[name] ||= []).push(f); }}};
  vm.runInNewContext(scripts[name], context);
  const emit = (name, ...args) => (handlers[name] || []).forEach(f => f(...args));
  const frames = count => { for (let i = 0; i < count; ++i) queue.splice(0).forEach(f => f()); };
  const bind = (slot, id) => { texts[slot].innerHTML = '<p class="subtitleText"><span class="subtitleSpeakerColor">Speaker: </span><span class="subtitleColor">[[MMID:' + id + ']]</span></p>'; };
  const layers = slot => owners[slot].children.filter(e => /mm2-layer/.test(e.className) && e.style.display !== 'none');
  emit('CacheSubtitleCCElements');
  return {owners, texts, window, emit, frames, bind, layers, queue, context};
}
const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < .02, `${actual} != ${expected}`);
function layer(test, slot, which) {
  return test.layers(slot).find(e => e.className.includes('mm2-' + which));
}

// The discarded native layout class also selects the dialogue font. Copy only
// its resolved family from the untouched native paragraph, following changes.
{
  const t = setup('stacked'); t.bind(0, 0);
  t.texts[0].innerHTML = t.texts[0].innerHTML.replace('subtitleText', 'subtitleText fixture-native-layout');
  const original = t.texts[0].innerHTML;
  t.emit('ShowSubtitle', 0); t.frames(8);
  for (const elem of t.layers(0)) {
    assert.equal(elem.style.fontFamily, 'FixtureDialogue, sans-serif');
    // Cohtml treats font-family:inherit on inserted markup as a family name;
    // the real game displays tofu even though the parent font is correct.
    assert.equal(elem.generatedChild.style.fontFamily, elem.style.fontFamily);
    assert.ok(!elem.innerHTML.includes('fixture-native-layout'));
  }
  t.texts[0].nativeParagraph.computedFont = 'FixtureLanguageSwitch, serif';
  t.frames(2);
  assert.equal(layer(t, 0, 'upper').style.fontFamily, 'FixtureLanguageSwitch, serif');
  assert.equal(layer(t, 0, 'lower').style.fontFamily, 'FixtureLanguageSwitch, serif');
  assert.equal(t.texts[0].innerHTML, original);
  t.texts[0].nativeParagraph = null; t.frames(2);
  assert.equal(layer(t, 0, 'lower').style.fontFamily, 'FixtureContainer, sans-serif');
}
for (const missingStyle of ['absent', 'throws']) {
  const t = setup('stacked');
  if (missingStyle === 'absent') delete t.window.getComputedStyle;
  else t.window.getComputedStyle = () => { throw new Error('Embedded API unavailable'); };
  t.bind(0, 0); t.emit('ShowSubtitle', 0); t.frames(8);
  assert.equal(t.layers(0).length, 2);
  assert.equal(layer(t, 0, 'lower').style.fontFamily, 'sans-serif');
  t.texts[0].style.fontFamily = 'FixtureInlineFallback, serif'; t.frames(2);
  assert.equal(layer(t, 0, 'lower').style.fontFamily, 'FixtureInlineFallback, serif');
}

// Native unmarked binding remains byte-for-byte and style-for-style untouched.
{
  const t = setup('stacked'); const before = t.texts[0].innerHTML;
  t.emit('ShowSubtitle', 0); t.frames(8);
  assert.equal(t.texts[0].innerHTML, before); assert.equal(t.texts[0].style.visibility, undefined);
  assert.equal(t.layers(0).length, 0);
  t.emit('HideSubtitle', 0, true); t.frames(3); assert.equal(t.queue.length, 0);
}
for (const [scale, physicalScale] of [[1, 1], [2, 1], [2, 2], [.75, 1.5]]) {
  const t = setup('stacked', scale, physicalScale);
  t.bind(0, 0); const before = t.texts[0].innerHTML;
  t.emit('ShowSubtitle', 0); t.frames(8);
  assert.equal(t.texts[0].innerHTML, before, 'engine binding must not be overwritten');
  assert.equal(t.texts[0].style.visibility, 'hidden');
  let upper = layer(t, 0, 'upper'), lower = layer(t, 0, 'lower');
  assert.ok(upper.innerHTML.includes('Upper one') && lower.innerHTML.includes('Lower one'));
  assert.ok(upper.innerHTML.includes('subtitleSpeakerColor'));
  close(lower.getBoundingClientRect().bottom, 1080 * scale - 100);
  close(lower.getBoundingClientRect().top - upper.getBoundingClientRect().bottom, 8);
  close(number(upper.style.fontSize) * physicalScale, 36 * scale);
  close(number(lower.style.fontSize) * physicalScale, 24 * scale);
  t.bind(1, 1); t.emit('ShowSubtitle', 1); t.frames(8);
  const newest = layer(t, 1, 'upper').getBoundingClientRect();
  const old = layer(t, 0, 'lower').getBoundingClientRect();
  assert.ok(old.bottom <= newest.top - 12 * scale + .02, 'both complete pairs occupy space');
  assert.ok(newest.height > upper.getBoundingClientRect().height, 'wrapping expands the measured pair');
  t.emit('HideSubtitle', 1, false); t.frames(2);
  assert.ok(t.layers(1).length, 'fade keeps child layers visible');
  t.window.finishFade(); t.frames(3);
  close(layer(t, 0, 'lower').getBoundingClientRect().bottom, 1080 * scale - 100);
  t.emit('HideSubtitle', 0, true); t.frames(3); assert.equal(t.queue.length, 0);
}
// Binding can arrive after ShowSubtitle, and replace a marker while shown.
{
  const t = setup('stacked'); t.bind(0, 0); t.emit('ShowSubtitle', 0); t.frames(8);
  t.emit('ShowSubtitle', 0); assert.equal(t.layers(0).length, 0, 'old pair must not flash on reuse');
  t.frames(1); t.bind(0, 2); t.frames(8);
  assert.equal(t.layers(0).length, 1); assert.ok(layer(t, 0, 'lower').innerHTML.includes('Only lower'));
  t.bind(0, 3); t.frames(2); assert.equal(t.layers(0).length, 1);
  close(layer(t, 0, 'upper').getBoundingClientRect().bottom, 980);
  t.texts[0].innerHTML = '<p>Unmarked next</p>'; t.frames(2);
  assert.equal(t.texts[0].style.visibility, ''); assert.equal(t.layers(0).length, 0);
  t.bind(0, 999); t.frames(2); assert.equal(t.layers(0).length, 0);
  assert.equal(t.texts[0].style.visibility, 'hidden', 'invalid IDs never leak the wire marker');
  t.bind(1, 0); t.emit('ShowSubtitle', 1); t.frames(8);
  close(layer(t, 1, 'lower').getBoundingClientRect().bottom, 980);
}
// A native-only speaker sharing occupancy is moved by its measured transform,
// then receives its original native position when translation leaves.
for (const [scale, physicalScale] of [[2, 1], [1, 2]]) {
  const t = setup('stacked', scale, physicalScale);
  t.bind(0, 0); t.emit('ShowSubtitle', 0); t.frames(8);
  t.emit('ShowSubtitle', 1); t.frames(8);
  close(t.texts[1].getBoundingClientRect().bottom, 1080 * scale - 100);
  assert.ok(layer(t, 0, 'lower').getBoundingClientRect().bottom <= t.texts[1].getBoundingClientRect().top - 12 * scale + .02);
  t.emit('HideSubtitle', 0, true); t.frames(3);
  assert.equal(t.owners[1].style.top, '900px');
}
{
  const t = setup('split'); t.bind(0, 0); t.emit('ShowSubtitle', 0); t.frames(8);
  close(layer(t, 0, 'upper').getBoundingClientRect().top, 20);
  close(layer(t, 0, 'lower').getBoundingClientRect().bottom, 980);
  t.bind(1, 1); t.emit('ShowSubtitle', 1); t.frames(8);
  const uppers = [layer(t, 0, 'upper'), layer(t, 1, 'upper')].map(e => e.getBoundingClientRect()).sort((a,b) => a.top-b.top);
  assert.ok(uppers[1].top >= uppers[0].bottom + 12);
}
for (const [profile, expected] of [['top_only', 'upper'], ['bottom_only', 'lower']]) {
  const t = setup(profile); t.bind(0, 0); t.emit('ShowSubtitle', 0); t.frames(8);
  assert.equal(t.layers(0).length, 1); close(layer(t, 0, expected).getBoundingClientRect().bottom, 980);
}
{
  const t = setup('plain'); t.bind(0, 4); t.emit('ShowSubtitle', 0); t.frames(8);
  const lower = layer(t, 0, 'lower'), upper = layer(t, 0, 'upper');
  assert.ok(lower.innerHTML.includes('<i>Styled &amp; safe</i>'));
  assert.ok(lower.innerHTML.includes('<span style="color:#f00">Tint</span>'));
  assert.ok(upper.innerHTML.includes('<b>Bold</b>')); assert.ok(!upper.innerHTML.includes('<script'));
  assert.ok(!lower.innerHTML.includes('<blank'));
  assert.equal(lower.style.textShadow, 'none'); assert.ok(lower.style.backgroundColor.includes('rgba'));
  t.emit('CacheSubtitleCCElements'); t.frames(2);
  assert.equal(t.layers(0).length, 0); assert.equal(t.texts[0].style.visibility, '');
}
console.log('DOM behavior passed');
