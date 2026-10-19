import os
import struct
import unittest
from pathlib import Path

from archive import Dat1, GameArchive, asset_hash, lz4_decode
from localization import Localization

GAME = Path(os.environ.get("MILES_GAME_DIR", str(Path(__file__).resolve().parents[2])))


def original_game():
    # Tests always inspect the immutable original archives, even while the
    # reversible runtime prototype is installed in the game directory.
    if not (GAME / 'asset_archive/toc').is_file():
        raise unittest.SkipTest('Set MILES_GAME_DIR to run local game integration tests')
    modern = GAME / '.miles-language-tool/toc.original'
    legacy = GAME / 'BilingualSubtitles/backups/install/toc.original'
    backup = modern if modern.is_file() else legacy
    return GameArchive(GAME, backup.read_bytes() if backup.is_file() else None)


class AssetTests(unittest.TestCase):
    def test_lz4_literals_and_overlapping_matches(self):
        self.assertEqual(lz4_decode(b'\x40test'), b'test')
        self.assertEqual(lz4_decode(b'\x32abc\x03\x00\x10!'), b'abcabcabc!')

    def test_lz4_rejects_invalid_reference_and_truncated_literal(self):
        for data in (b'\x00\x00\x00', b'\x40ab', b'\xf0'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                lz4_decode(data)

    def test_known_asset_hash(self):
        self.assertEqual(asset_hash('localization/localization_all.localization'), 0xBE55D94F171BF8DE)
        self.assertEqual(asset_hash('UI\\EXPORT\\Overlay.gfx'), asset_hash('ui/export/overlay.gfx'))

    def test_local_english_and_chinese_dialogue(self):
        game = original_game()
        english = Localization(game.extract('localization/localization_all.localization', 0))
        chinese = Localization(game.extract('localization/localization_all.localization', 176))
        self.assertEqual(english.values['ABANDON_CONFIRM_HEADER'], 'ABANDON MISSION')
        self.assertEqual(chinese.values['ABANDON_CONFIRM_HEADER'], '放弃任务')
        self.assertIn('Pete, are you OK?', english.values['SPIM_CINE_A1_WINTERBREAK_BLACKOUT_006'])
        self.assertIn('彼得，你没事吧？', chinese.values['SPIM_CINE_A1_WINTERBREAK_BLACKOUT_006'])
        self.assertEqual(len(english.values), 35128)
        self.assertEqual(len(chinese.values), 35128)

    def test_localization_edit_preserves_keys_and_other_sections(self):
        game = original_game()
        raw = game.extract('localization/localization_all.localization', 176)
        loc = Localization(raw)
        changed = loc.replace({'ABANDON_CONFIRM_HEADER': '测试 / TEST'})
        result = Localization(changed)
        self.assertEqual(result.values['ABANDON_CONFIRM_HEADER'], '测试 / TEST')
        self.assertEqual(result.values['SPIM_CINE_A1_WINTERBREAK_BLACKOUT_006'], loc.values['SPIM_CINE_A1_WINTERBREAK_BLACKOUT_006'])
        self.assertEqual(list(result.values), list(loc.values))
        for tag, original in loc.dat.sections.items():
            if tag not in (0x70A382B8, 0xF80DEEB4):
                self.assertEqual(result.dat.sections[tag], original)

    def test_toc_override_roundtrip_keeps_original_entries(self):
        game = original_game()
        overlay = game.find('ui/export/Overlay.gfx', 0)
        loc = game.find('localization/localization_all.localization', 176)
        rewritten = game.redirect('bilingual_subtitles', [(overlay, 16, 123), (loc, 144, 456)])
        result = GameArchive(GAME, rewritten)
        self.assertEqual(result.find('ui/export/Overlay.gfx', 0).archive, 'bilingual_subtitles')
        self.assertEqual(result.find('ui/export/Overlay.gfx', 0).offset, 16)
        self.assertEqual(result.find('localization/localization_all.localization', 176).size, 456)
        self.assertEqual(result.find('localization/localization_all.localization', 0), game.find('localization/localization_all.localization', 0))
        self.assertEqual(len(result.entries), len(game.entries))
        self.assertEqual(game.find('ui/export/Overlay.gfx', 0), overlay)

    def test_dat1_rejects_out_of_bounds_section(self):
        bad = struct.pack('<4I3I', 0x44415431, 0, 28, 1, 123, 100, 4)
        with self.assertRaises(ValueError):
            Dat1(bad)


if __name__ == '__main__':
    unittest.main()
