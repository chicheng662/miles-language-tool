from pathlib import Path
import tempfile
import unittest
from game_registry import MILES, SPIDER_MAN_2, detect_game

class GameRegistryTests(unittest.TestCase):
    def test_language_spans_are_game_specific(self):
        self.assertEqual(MILES.language_spans['zh-CN'],176)
        self.assertEqual(SPIDER_MAN_2.language_spans['zh-CN'],168)
        self.assertEqual(SPIDER_MAN_2.language_spans['zh-TW'],176)
        self.assertEqual(SPIDER_MAN_2.language_spans['pt-BR'],104)
        self.assertEqual(len(SPIDER_MAN_2.language_spans),22)

    def test_game_is_identified_by_executable_and_index(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'Spider-Man2.exe').touch()
            (root/'toc').touch()
            (root/'d').mkdir()
            self.assertEqual(detect_game(root),SPIDER_MAN_2)
            (root/'MilesMorales.exe').touch()
            with self.assertRaises(ValueError):detect_game(root)

    def test_unknown_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):detect_game(Path(folder))
