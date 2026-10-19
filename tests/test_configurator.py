import importlib
import json
import unittest

import dialogue

try:
    cfg = importlib.import_module('configuration')
except ModuleNotFoundError:
    cfg = None


class ConfigTests(unittest.TestCase):
    def config(self):
        self.assertIsNotNone(cfg, '缺少可移植配置模型')
        return cfg

    def test_roundtrip_and_defaults(self):
        mod = self.config()
        config = mod.Profile()
        self.assertEqual(mod.Profile.from_dict(json.loads(json.dumps(config.to_dict()))), config)
        self.assertEqual((config.top_language, config.bottom_language), ('zh-CN', 'en'))
        self.assertEqual(config.top_margin_px, 20)

    def test_rejects_invalid_and_future_profiles(self):
        mod = self.config()
        for changes in ({'schema_version': 99}, {'top_language': 'xx'}, {'top_size': float('nan')},
                        {'top_language': None, 'bottom_language': None}, {'output_width': 0},
                        {'top_margin_px': -1}, {'bottom_size': '36'}, {'outline': 'yes'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                mod.Profile.from_dict(dict(mod.Profile().to_dict(), **changes))

    def test_physical_margin_conversion(self):
        mod = self.config()
        self.assertAlmostEqual(mod.Profile(output_width=2560, output_height=1600).top_ui_y(), -45)
        self.assertAlmostEqual(mod.Profile(output_width=1920, output_height=1080).top_ui_y(), 20)
        self.assertAlmostEqual(mod.Profile(output_width=3440, output_height=1440).top_ui_y(), 15)

    def test_all_language_ids_are_unique(self):
        mod = self.config()
        self.assertEqual(len(mod.LANGUAGES), 22)
        self.assertEqual(len({v.span for v in mod.LANGUAGES.values()}), 22)
        self.assertEqual(mod.LANGUAGES['ja'].span, 72)
        self.assertEqual(mod.LANGUAGES['zh-CN'].span, 176)


class DualLayerTests(unittest.TestCase):
    def pair(self, *args):
        self.assertTrue(hasattr(dialogue, 'pair_layers'), '缺少通用双层字幕配对')
        return dialogue.pair_layers(*args)

    def test_bottom_and_top_use_english_tags_and_speaker(self):
        en = '<name="MILE"><ts="0;1">Hi.<ts="1;3">Bye.'
        result, coverage = self.pair(en, '<name="X"><ts="0;1">你好<ts="1;3">再见',
                                    '<name="Y"><ts="0;1">こんにちは<ts="1;3">さようなら')
        prefix, parts = dialogue.parse_segments(result)
        self.assertEqual(prefix, '<name="MILE">')
        self.assertEqual([s.tag for s in parts], ['<ts="0;1">', '<ts="1;3">'])
        self.assertTrue(parts[0].text.startswith('你好'))
        self.assertIn('こんにちは', parts[0].text)
        self.assertNotIn('<name="X">', result)
        self.assertFalse(coverage['bottom_fallback'])

    def test_single_layer_and_missing_translation(self):
        en = '<ts="0;1">Hello.'
        result, coverage = self.pair(en, '', '')
        self.assertTrue(result.startswith(en))
        self.assertTrue(coverage['bottom_fallback'])
        self.assertTrue(coverage['top_missing'])
        result, _ = self.pair(en, None, '<ts="0;1">你好')
        self.assertNotIn('Hello.', result)
        self.assertIn('你好', result)
        result, _ = self.pair(en, en, None)
        self.assertIn('Hello.', result)
        self.assertNotIn('你好', result)

    def test_context_is_preserved_across_unequal_segments(self):
        result, _ = self.pair('<ts="0;1">A<ts="1;2">B', '<ts="0;2">甲乙', '<ts="0;2">한글')
        self.assertEqual(result.count('甲乙'), 2)
        self.assertEqual(result.count('한글'), 2)

    def test_menus_are_not_dialogue(self):
        self.assertIsNone(self.pair('START', '开始', '開始')[0])

    def test_english_bottom_preserves_whitespace_and_original_markup(self):
        en = '<name="MILE"><ts="0;1"> Hello.  <ts="1;2"><blank>'
        result, _ = self.pair(en, en, '<ts="0;2">你好')
        import re
        stripped = re.sub(r'\[\[MMTOP\]\].*?\[\[/MMTOP\]\]', '', result)
        self.assertEqual(stripped, en)

    def test_wire_ids_avoid_native_long_text_truncation(self):
        self.assertTrue(hasattr(dialogue, 'encode_wire'), '缺少短台词编号传输')
        en = '<name="MILE"><ts="0;4">' + 'English sentence. ' * 30
        paired, _ = self.pair(en, en, '完整译文' * 80)
        table = []
        wire = dialogue.encode_wire(en, paired, table)
        self.assertLess(len(dialogue.parse_segments(wire)[1][0].text), 24)
        self.assertEqual(table[0][0], 'English sentence. ' * 30)
        self.assertEqual(table[0][1], '完整译文' * 80)
        self.assertEqual(dialogue.parse_segments(wire)[0], '<name="MILE">')


if __name__ == '__main__':
    unittest.main()
