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

    def test_inactive_margin_after_resolution_change_does_not_block_application(self):
        self.app.set_profile(Profile(layout='stacked', output_width=3840, output_height=2160,
                                     bottom_margin_px=700))
        self.app.vars['layout'].set(LAYOUT_LABELS['split'])
        self.app.vars['output_width'].set(1920)
        self.app.vars['output_height'].set(1080)
        self.assertEqual(self.app.read_profile().layout, 'split')
        self.app.english_first()
        self.assertEqual(self.app.read_profile().layout, 'stacked')
        self.assertEqual(self.app.read_profile().bottom_margin_px, 100)

    def test_inactive_split_margin_does_not_block_stacked_layout(self):
        self.app.set_profile(Profile(output_width=3840, output_height=2160, top_margin_px=700))
        self.app.vars['layout'].set(LAYOUT_LABELS['stacked'])
        self.app.vars['output_width'].set(1920)
        self.app.vars['output_height'].set(1080)
        self.assertEqual(self.app.read_profile().layout, 'stacked')

    def test_launch_uses_selected_game_executable(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            game=Path(folder)
            (game/'Spider-Man2.exe').touch()
            (game/'toc').touch()
            (game/'d').mkdir()
            self.app.game_var.set(str(game))
            with patch('configurator_app.inspect_game',return_value={}), \
                 patch('configurator_app.read_game_resolution',return_value=None), \
                 patch('configurator_app.game_running',return_value=False), \
                 patch('configurator_app.subprocess.Popen') as launch:
                self.app.launch()
            self.assertEqual(Path(launch.call_args.args[0][0]).name,'Spider-Man2.exe')

    def test_initial_resolution_uses_supplied_game(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with patch('configurator_app.read_game_resolution', return_value=(2560, 1600)) as read:
            app = Configurator(root, game='C:/Games/SpiderMan2')
        read.assert_called_once_with('C:/Games/SpiderMan2')
        self.assertEqual(app.read_profile().output_height, 1600)

    @patch('configurator_app.atomic_write')
    def test_checked_shows_spiderman2_identity(self,write):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            self.app.applied_profile = Profile()
            self.app.checked({'game':Path(folder),'state':Path(folder)/'state',
                              'status':'not-installed','game_id':'spider-man-2',
                              'game_name':'漫威蜘蛛侠 2','version':'2.810.0.0'})
        self.assertIsNone(self.app.applied_profile)
        self.assertIn('漫威蜘蛛侠 2',self.app.game_status.get())
        self.assertIn('2.810.0.0',self.app.game_status.get())
