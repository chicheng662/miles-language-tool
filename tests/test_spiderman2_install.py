import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import patch as installer


class SpiderMan2InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.game = Path(self.temp.name).resolve() / 'game'
        (self.game / 'd').mkdir(parents=True)
        (self.game / 'Spider-Man2.exe').write_bytes(b'fixture')
        (self.game / 'toc').write_bytes(b'ORIGINAL')
        self.bundle = self.game.parent / 'bundle'
        self.bundle.mkdir()
        self.state = self.game / '.miles-language-tool'
        self.manifest = {'format': 1, 'game_id': 'spider-man-2', 'archive': 'bilingual_subtitles',
                         'original_toc_sha256': installer.sha256(b'ORIGINAL'),
                         'patched_toc_sha256': installer.sha256(b'PATCHED'),
                         'archive_sha256': installer.sha256(b'NEW')}
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))
        (self.bundle/'toc.patched').write_bytes(b'PATCHED')
        (self.bundle/'bilingual_subtitles').write_bytes(b'NEW')
        guard = patch('patch.game_running', return_value=False)
        guard.start()
        self.addCleanup(guard.stop)

    def test_install_and_restore_use_root_toc_and_d_archive(self):
        installer.install_bundle(self.game, self.bundle, self.state)
        self.assertEqual((self.game/'toc').read_bytes(), b'PATCHED')
        self.assertEqual((self.game/'d/bilingual_subtitles').read_bytes(), b'NEW')
        self.assertEqual(installer.status(self.game, self.state), 'installed')
        installer.restore(self.game, self.state)
        self.assertEqual((self.game/'toc').read_bytes(), b'ORIGINAL')
        self.assertFalse((self.game/'d/bilingual_subtitles').exists())
        self.assertFalse((self.game/'asset_archive').exists())

    def test_index_failure_cleans_payload_and_keeps_backup(self):
        write = installer.atomic_write
        def fail(path, data):
            if path == self.game/'toc':
                raise OSError('simulated')
            return write(path, data)
        with patch('patch.atomic_write', side_effect=fail), self.assertRaises(OSError):
            installer.install_bundle(self.game, self.bundle, self.state)
        self.assertEqual((self.game/'toc').read_bytes(), b'ORIGINAL')
        self.assertEqual((self.state/'toc.original').read_bytes(), b'ORIGINAL')
        self.assertFalse((self.game/'d/bilingual_subtitles').exists())
        installer.install_bundle(self.game, self.bundle, self.state)
        self.assertEqual(installer.status(self.game, self.state), 'installed')

    def test_wrong_game_manifest_rejected_without_writes(self):
        self.manifest['game_id'] = 'miles'
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError):
            installer.install_bundle(self.game,self.bundle,self.state)
        self.assertFalse((self.state/'toc.original').exists())
