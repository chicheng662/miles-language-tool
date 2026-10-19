import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from patch import install_bundle, restore, status


def digest(data):
    return hashlib.sha256(data).hexdigest()


class InstallationTests(unittest.TestCase):
    def setUp(self):
        # These tests mutate only temporary fixture files. The real process
        # guard is exercised separately without touching the user's game.
        process_guard = patch('patch.game_running', return_value=False)
        process_guard.start()
        self.addCleanup(process_guard.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / 'game'
        self.assets = self.game / 'asset_archive'
        self.assets.mkdir(parents=True)
        (self.assets / 'toc').write_bytes(b'ORIGINAL-TOC')
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        self.state = self.root / 'backup'
        (self.bundle / 'toc.patched').write_bytes(b'PATCHED-TOC')
        (self.bundle / 'bilingual_subtitles').write_bytes(b'NEW-ASSETS')
        self.manifest = {'format': 1, 'mode': 'prototype', 'archive': 'bilingual_subtitles', 'original_toc_sha256': digest(b'ORIGINAL-TOC'), 'patched_toc_sha256': digest(b'PATCHED-TOC'), 'archive_sha256': digest(b'NEW-ASSETS')}
        (self.bundle / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_install_twice_and_restore_preserves_original_backup(self):
        install_bundle(self.game, self.bundle, self.state)
        self.assertEqual((self.assets / 'toc').read_bytes(), b'PATCHED-TOC')
        self.assertEqual((self.assets / 'bilingual_subtitles').read_bytes(), b'NEW-ASSETS')
        self.assertEqual(status(self.game, self.state), 'installed')
        install_bundle(self.game, self.bundle, self.state)
        self.assertEqual((self.state / 'toc.original').read_bytes(), b'ORIGINAL-TOC')
        restore(self.game, self.state)
        self.assertEqual((self.assets / 'toc').read_bytes(), b'ORIGINAL-TOC')
        self.assertFalse((self.assets / 'bilingual_subtitles').exists())
        self.assertEqual(status(self.game, self.state), 'restored')
        restore(self.game, self.state)
        install_bundle(self.game, self.bundle, self.state)
        self.assertEqual((self.state / 'toc.original').read_bytes(), b'ORIGINAL-TOC')

    def test_changed_toc_is_never_overwritten(self):
        (self.assets / 'toc').write_bytes(b'ANOTHER-MOD')
        with self.assertRaises(ValueError):
            install_bundle(self.game, self.bundle, self.state)
        self.assertEqual((self.assets / 'toc').read_bytes(), b'ANOTHER-MOD')
        self.assertFalse(self.state.exists())

    def test_corrupt_payload_has_no_side_effects(self):
        (self.bundle / 'bilingual_subtitles').write_bytes(b'CORRUPT')
        with self.assertRaises(ValueError):
            install_bundle(self.game, self.bundle, self.state)
        self.assertEqual(list(self.assets.iterdir()), [self.assets / 'toc'])
        self.assertFalse(self.state.exists())

    def test_restore_refuses_unrelated_later_mod(self):
        install_bundle(self.game, self.bundle, self.state)
        (self.assets / 'toc').write_bytes(b'LATER-MOD')
        with self.assertRaises(ValueError):
            restore(self.game, self.state)
        self.assertEqual((self.assets / 'toc').read_bytes(), b'LATER-MOD')

    def test_missing_or_corrupt_backup_prevents_restore(self):
        install_bundle(self.game, self.bundle, self.state)
        for bad in (b'BROKEN', None):
            if bad is None:
                (self.state / 'toc.original').unlink()
            else:
                (self.state / 'toc.original').write_bytes(bad)
            with self.assertRaises(ValueError):
                restore(self.game, self.state)
            self.assertEqual((self.assets / 'toc').read_bytes(), b'PATCHED-TOC')

    def test_running_game_blocks_changes(self):
        with patch('patch.game_running', return_value=True):
            with self.assertRaises(RuntimeError):
                install_bundle(self.game, self.bundle, self.state)
        self.assertEqual((self.assets / 'toc').read_bytes(), b'ORIGINAL-TOC')

    def test_upgrade_from_verified_prototype_keeps_original_backup(self):
        install_bundle(self.game, self.bundle, self.state)
        (self.bundle / 'toc.patched').write_bytes(b'FULL-TOC')
        (self.bundle / 'bilingual_subtitles').write_bytes(b'FULL-ASSETS')
        self.manifest.update(mode='full', patched_toc_sha256=digest(b'FULL-TOC'), archive_sha256=digest(b'FULL-ASSETS'))
        (self.bundle / 'manifest.json').write_text(json.dumps(self.manifest))
        install_bundle(self.game, self.bundle, self.state)
        self.assertEqual((self.assets / 'toc').read_bytes(), b'FULL-TOC')
        self.assertEqual((self.assets / 'bilingual_subtitles').read_bytes(), b'FULL-ASSETS')
        self.assertEqual((self.state / 'toc.original').read_bytes(), b'ORIGINAL-TOC')
        restore(self.game, self.state)
        self.assertEqual((self.assets / 'toc').read_bytes(), b'ORIGINAL-TOC')

    def test_equal_toc_different_payload_still_applies_new_style(self):
        install_bundle(self.game, self.bundle, self.state)
        payload = b'ALT-ASSETS'
        self.assertEqual(len(payload), len(b'NEW-ASSETS'))
        (self.bundle / 'bilingual_subtitles').write_bytes(payload)
        self.manifest['archive_sha256'] = digest(payload)
        (self.bundle / 'manifest.json').write_text(json.dumps(self.manifest))
        install_bundle(self.game, self.bundle, self.state)
        self.assertEqual((self.assets / 'bilingual_subtitles').read_bytes(), payload)

    def test_cross_process_game_lock_rejects_concurrent_install(self):
        import patch as installer
        self.assertTrue(hasattr(installer, 'game_lock'), '缺少跨进程安装锁')
        import subprocess
        import sys
        code = "from patch import game_lock; from pathlib import Path; import sys;\nwith game_lock(Path(sys.argv[1])): print('unexpected acquisition')"
        with installer.game_lock(self.game):
            result = subprocess.run([sys.executable, '-B', '-c', code, str(self.game)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b'unexpected acquisition', result.stdout)
        with installer.game_lock(self.game):
            with installer.game_lock(self.game):
                pass  # Same-thread nesting is required for upgrades and restore.

    def test_toc_write_failure_leaves_original_game_and_retry_works(self):
        import patch as installer
        original_write = installer.atomic_write
        def fail_toc(path, data):
            if path == self.assets / 'toc':
                raise OSError('Simulated interruption before index switch')
            return original_write(path, data)
        with patch('patch.atomic_write', side_effect=fail_toc):
            with self.assertRaises(OSError):
                install_bundle(self.game, self.bundle, self.state)
        self.assertEqual((self.assets / 'toc').read_bytes(), b'ORIGINAL-TOC')
        self.assertFalse((self.assets / 'bilingual_subtitles').exists())
        self.assertEqual((self.state / 'toc.original').read_bytes(), b'ORIGINAL-TOC')
        install_bundle(self.game, self.bundle, self.state)
        self.assertEqual(status(self.game, self.state), 'installed')

    def test_hard_interruption_before_toc_can_restore_then_retry(self):
        # Simulate process termination after payload/state writes: no exception
        # handler would run, and the original TOC still boots the original game.
        self.state.mkdir()
        (self.state / 'toc.original').write_bytes(b'ORIGINAL-TOC')
        record = dict(self.manifest, game=str(self.game.resolve()))
        (self.state / 'state.json').write_text(json.dumps(record))
        (self.assets / 'bilingual_subtitles').write_bytes(b'NEW-ASSETS')
        self.assertEqual(status(self.game, self.state), 'restored')
        restore(self.game, self.state)
        self.assertFalse((self.assets / 'bilingual_subtitles').exists())
        install_bundle(self.game, self.bundle, self.state)
        self.assertEqual(status(self.game, self.state), 'installed')


if __name__ == '__main__':
    unittest.main()
