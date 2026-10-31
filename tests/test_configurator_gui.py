import tkinter as tk
import unittest
from unittest.mock import patch
from configuration import Profile
from configurator_app import Configurator, LAYOUT_LABELS


class ConfiguratorLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        with patch.object(Configurator, 'initial_game', return_value=''), \
             patch('configurator_app.read_game_resolution', return_value=None):
            self.app = Configurator(self.root)
        self.root.update_idletasks()

    def test_english_first_action_selects_layout_languages_and_sizes(self):
        self.app.set_profile(Profile(output_width=2560, output_height=1600))
        self.app.english_first()
        profile = self.app.read_profile()
        self.assertEqual(profile.layout, 'stacked')
        self.assertEqual((profile.top_language, profile.bottom_language), ('en', 'zh-CN'))
        self.assertEqual((profile.top_size, profile.bottom_size), (36, 24))
        self.assertEqual((profile.output_width, profile.output_height), (2560, 1600))

    def test_preview_keeps_upper_text_above_lower_text(self):
        self.app.set_profile(Profile().english_first())
        upper = self.app.canvas.bbox('preview-top')
        lower = self.app.canvas.bbox('preview-bottom')
        self.assertIsNotNone(upper)
        self.assertIsNotNone(lower)
        self.assertLess(upper[3], lower[1])

    def test_single_layer_preview_and_layout_roundtrip(self):
        self.app.set_profile(Profile(layout='stacked', bottom_language=None))
        self.assertFalse(self.app.canvas.find_withtag('preview-bottom'))
        self.assertTrue(self.app.canvas.find_withtag('preview-top'))
        self.app.vars['layout'].set(LAYOUT_LABELS['split'])
        self.assertEqual(self.app.read_profile().layout, 'split')
