import unittest
from subtitle_layout import stacked_pairs

class StackedLayoutTests(unittest.TestCase):
    def test_english_above_chinese_with_gap_and_bottom_anchor(self):
        upper, lower = stacked_pairs(980, [(48, 28)], 8)[0]
        self.assertEqual(lower + 28, 980)
        self.assertEqual(lower - (upper + 48), 8)

    def test_wrapped_english_grows_upward_and_chinese_stays_at_bottom(self):
        short = stacked_pairs(980, [(48, 28)], 8)[0]
        wrapped = stacked_pairs(980, [(144, 28)], 8)[0]
        self.assertEqual(wrapped[1], short[1])
        self.assertEqual(wrapped[0] + 144 + 8, wrapped[1])
        self.assertLess(wrapped[0], short[0])

    def test_empty_or_disabled_layers_do_not_reserve_gap(self):
        self.assertEqual(stacked_pairs(980, [(0, 28)], 8), [(None, 952)])
        self.assertEqual(stacked_pairs(980, [(48, 0)], 8), [(932, None)])
        self.assertEqual(stacked_pairs(980, [(0, 0), (48, 0)], 8),
                         [(None, None), (932, None)])

    def test_second_speaker_reserves_entire_pair(self):
        first, second = stacked_pairs(980, [(96, 56), (144, 28)], 8, speaker_gap=15)
        self.assertEqual(first[0] - (second[1] + 28), 15)
        self.assertEqual(second[1] - (second[0] + 144), 8)

    def test_invalid_metrics_are_rejected(self):
        for heights in ([(-1, 20)], [(float('nan'), 20)]):
            with self.assertRaises(ValueError):
                stacked_pairs(980, heights, 8)
