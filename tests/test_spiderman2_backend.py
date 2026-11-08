import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from configuration import Profile
import spiderman2_backend as backend
from spiderman2_archive import GameArchiveI29, BareLocalization

class SpiderMan2BackendTests(unittest.TestCase):
    def game(self):
        path=os.environ.get('MILES_MSM2_GAME_DIR')
        if not path:self.skipTest('Set MILES_MSM2_GAME_DIR for local game integration')
        return Path(path)

    def test_unknown_directory_refused_without_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ValueError):backend.inspect_game(root)
            self.assertFalse((root/'.miles-language-tool').exists())

    def test_supported_game_inspection_and_modified_resource_rejection(self):
        game=self.game()
        info=backend.inspect_game(game)
        self.assertEqual(info['game_id'],'spider-man-2')
        raw=GameArchiveI29(game,info['original_toc']).extract(backend.LOCALIZATION,168)
        backend.validate_localization(raw,'zh-CN')
        with self.assertRaises(ValueError):backend.validate_localization(raw[:-1]+bytes([raw[-1]^1]),'zh-CN')

    @patch('spiderman2_backend.game_running',return_value=False)
    def test_sample_bundle_keeps_menus_and_timing_and_uses_i29(self,guard):
        game=self.game();original=GameArchiveI29(game,backend.inspect_game(game)['original_toc'])
        en=BareLocalization(original.extract(backend.LOCALIZATION,0)).values
        cn=BareLocalization(original.extract(backend.LOCALIZATION,168)).values
        keys=[k for k,v in en.items() if '<ts=' in v][:2]
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            manifest=backend.build_bundle(game,Profile().english_first(),output,sample_keys=keys)
            self.assertEqual(manifest['dialogue_entries'],2)
            archive=GameArchiveI29(game,(output/'toc.patched').read_bytes())
            entry=archive.find(backend.LOCALIZATION,168)
            import struct
            offset=struct.unpack_from('<i',archive.dat.sections[0x65BCF461],entry.index*16+12)[0]
            header_size=struct.unpack_from('<I',archive.dat.sections[0x654BDED9],offset+8)[0]
            self.assertEqual(header_size & 0x3fffffff,entry.size)
            payload=(output/'bilingual_subtitles').read_bytes()
            modified=BareLocalization(payload[entry.offset:entry.offset+entry.size]).values
            self.assertTrue(all(v==modified[k] for k,v in cn.items() if k not in keys))
            from dialogue import parse_segments
            for k in keys:
                self.assertEqual([x.tag for x in parse_segments(modified[k])[1]],
                                 [x.tag for x in parse_segments(en[k])[1]])
            script=archive.find(backend.OVERLAY,0)
            generated=payload[script.offset:script.offset+script.size].decode('utf-8')
            self.assertIn('MMSpiderMan2',generated)
            self.assertEqual(script.archive,'d/bilingual_subtitles')
