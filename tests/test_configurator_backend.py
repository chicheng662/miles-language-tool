import os
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from configuration import Profile
from patch import sha256
from test_assets import original_game, GAME

try:
    backend = importlib.import_module('configurator_backend')
except ModuleNotFoundError:
    backend = None


class ConfiguratorBackendTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(backend, '缺少配置工具后端')
        return backend

    def test_inspect_recovers_original_from_existing_patch(self):
        original_game()  # Skip cleanly when no user-owned game was supplied.
        info = self.module().inspect_game(GAME)
        self.assertEqual(sha256(info['original_toc']), backend.ORIGINAL_TOC_SHA)
        self.assertTrue(info['state'].is_dir())

    def test_no_game_or_unknown_version_is_rejected(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                mod.inspect_game(Path(folder))

    def test_generic_ui_patch_is_separate_and_configurable(self):
        mod = self.module()
        source_path = Path(os.environ.get('MILES_OVERLAY_AS', str(GAME / 'BilingualSubtitles/build/as-original/scripts/overlay/OverlayManager.as')))
        if not source_path.is_file():
            self.skipTest('Set MILES_OVERLAY_AS to a locally exported original OverlayManager.as')
        source = source_path.read_text(encoding='utf-8-sig')
        changed = mod.patch_configurable_source(source, Profile(output_width=2560, output_height=1600))
        self.assertIn('MMShowTop', changed)
        self.assertIn('[[MMID:', changed)
        self.assertIn('var top:Number = -45;', changed)
        self.assertNotIn('MMShowChinese', changed)

    @patch('configurator_backend.game_running', return_value=False)
    def test_build_keeps_menus_and_english_timing(self, guard):
        mod = self.module()
        # Compile is separately integration-tested with real JPEXS. Supply original
        # UI here to isolate binary localization/TOC generation from the compiler.
        game = original_game()
        with tempfile.TemporaryDirectory() as folder:
            manifest = mod.build_bundle(GAME, Profile(top_language='ja', bottom_language='ko'), Path(folder),
                                        overlay_compiler=lambda raw, profile, work, progress, table: raw)
            self.assertEqual(manifest['dialogue_entries'], 15306)
            self.assertFalse(manifest['runtime_verified'])
            report = json.loads((Path(folder) / 'coverage.json').read_text(encoding='utf-8'))
            self.assertIn('top_missing_keys', report)
            from archive import GameArchive
            from localization import Localization
            toc = GameArchive(GAME, (Path(folder) / 'toc.patched').read_bytes())
            entry = toc.find(mod.LOCALIZATION, 176)
            data = (Path(folder) / 'bilingual_subtitles').read_bytes()[entry.offset:entry.offset + entry.size]
            loc = Localization(data)
            self.assertEqual(loc.values['ABANDON_CONFIRM_HEADER'], '放弃任务')
            key = 'SPIM_CINE_A1_WINTERBREAK_BLACKOUT_006'
            from dialogue import parse_segments
            en = Localization(game.extract(mod.LOCALIZATION, 0)).values[key]
            self.assertEqual([s.tag for s in parse_segments(loc.values[key])[1]], [s.tag for s in parse_segments(en)[1]])
            self.assertNotIn('Pete, are you OK?', loc.values[key])
            import re
            index = int(re.search(r'\[\[MMID:(\d+)\]\]', loc.values[key]).group(1))
            table = json.loads((Path(folder) / 'subtitle-table.json').read_text(encoding='utf-8'))
            self.assertTrue(any('\uac00' <= c <= '\ud7a3' for c in table[index][0]))
            self.assertTrue(any('\u3040' <= c <= '\u30ff' for c in table[index][1]))

    def test_baseline_rejects_modified_language_with_same_toc(self):
        mod = self.module()
        self.assertTrue(hasattr(mod, 'validate_localization'), '缺少语言资源基线校验')
        raw = original_game().extract(mod.LOCALIZATION, 0)
        mod.validate_localization(raw, 'en')
        with self.assertRaises(ValueError):
            mod.validate_localization(raw[:-1] + bytes([raw[-1] ^ 1]), 'en')


if __name__ == '__main__':
    unittest.main()
