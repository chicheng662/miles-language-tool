"""Synthetic fixtures only: never redistribute the game's UI or dialogue."""
import dataclasses
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from configuration import Profile


# Independently authored lifecycle fixture, not extracted game code.
NATIVE = """
var subtitle_elems = window.fixtureOwners;
var subtitle_elems_text = window.fixtureTexts;
engine.on('CacheSubtitleCCElements', function () {
  subtitle_elems.forEach(function (e) { e.elem_shown = false; e.elem_playing = false; });
});
engine.on('ShowSubtitle', function (slot) {
  var e = subtitle_elems[slot];
  e.elem_shown = true; e.style.opacity = '0'; e.style.display = 'block';
  var frames = 3;
  function ready() {
    if (!e.elem_shown) return;
    if (--frames) { window.requestAnimationFrame(ready); return; }
    e.style.opacity = '1'; e.style.top = '900px';
  }
  window.requestAnimationFrame(ready);
});
function HideSubtitle(sub_num, instant)
{
  var e = subtitle_elems[sub_num];
  e.elem_shown = false; e.elem_playing = !instant; e.elem_hiding = !instant;
  if (instant) e.style.display = 'none';
  else window.finishFade = function () { e.elem_playing = false; e.elem_hiding = false; e.style.display = 'none'; };
}
engine.on('HideSubtitle', HideSubtitle);
function UpdateSubtitleCCDimensions(owner, text) {}
function getWindowStageScale() { return window.fixtureScale; }
"""


class OverlayTests(unittest.TestCase):
    def adapter(self):
        try:
            return importlib.import_module('spiderman2_overlay')
        except ModuleNotFoundError:
            self.fail('Native Spider-Man 2 overlay adapter is missing')

    def test_rejects_unknown_or_already_patched_lifecycle(self):
        adapter = self.adapter()
        with self.assertRaises(ValueError):
            adapter.patch_overlay_js('var unrelated = 1;', Profile())
        changed = adapter.patch_overlay_js(NATIVE, Profile())
        with self.assertRaises(ValueError):
            adapter.patch_overlay_js(changed, Profile())

    def test_rejects_malformed_dictionary_instead_of_installing_broken_script(self):
        adapter = self.adapter()
        for table in ([('a',)], [('a', 1)], [('a', 'b', 'c')], ['ab']):
            with self.subTest(table=table), self.assertRaises(ValueError):
                adapter.patch_overlay_js(NATIVE, Profile(), table)

    def test_script_safe_serialization_cannot_close_script_element(self):
        script = self.adapter().patch_overlay_js(NATIVE, Profile(), [('x</script>\u2028', '"\\\n\u2029')])
        self.assertNotIn('</script>', script.lower())
        self.assertNotIn('\u2028', script)
        self.assertNotIn('\u2029', script)

    def test_functional_dom_lifecycle_and_layout(self):
        if not shutil.which('node'):
            self.skipTest('Node is unavailable; Python integration guards still run')
        adapter = self.adapter()
        table = [('Lower one', 'Upper one'), ('Second lower', 'Long upper ' * 35),
                 ('Only lower', ''), ('', 'Only upper'),
                 ('<i>Styled &amp; safe</i><blank><font color="#f00">Tint</font>', '<b>Bold</b><script>bad()</script>')]
        profiles = {
            'stacked': Profile().english_first(),
            'split': Profile(),
            'top_only': dataclasses.replace(Profile().english_first(), bottom_language=None),
            'bottom_only': dataclasses.replace(Profile().english_first(), top_language=None),
            'plain': dataclasses.replace(Profile().english_first(), top_outline=False, bottom_outline=False,
                                         top_background=True, bottom_background=True),
        }
        with tempfile.TemporaryDirectory() as folder:
            payload = Path(folder) / 'scripts.json'
            payload.write_text(json.dumps({name: adapter.patch_overlay_js(NATIVE, p, table)
                                           for name, p in profiles.items()}), encoding='utf-8')
            result = subprocess.run(['node', str(Path(__file__).with_name('spiderman2_dom_fixture.js')), str(payload)],
                                    capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('DOM behavior passed', result.stdout)
