import unittest
from dialogue import pair_line, parse_segments, OPEN, CLOSE


class DialogueTests(unittest.TestCase):
    def test_preserves_english_speaker_and_timing(self):
        en = '<name=&quot;MILE&quot;><ts=&quot;0.069;1.656&quot;>Pete, are you OK?'
        zh = '<name=&quot;MILE&quot;><ts=&quot;0.069;1.469&quot;>彼得，你没事吧？'
        result = pair_line(en, zh)
        self.assertEqual(result, en + OPEN + '彼得，你没事吧？' + CLOSE)

    def test_equal_segment_counts_pair_by_sequence(self):
        result = pair_line('<ts="0;1">Hello.<ts="2;4">Bye.', '<ts="0;1.2">你好。<ts="2.1;3.5">再见。')
        self.assertEqual(result, '<ts="0;1">Hello.' + OPEN + '你好。' + CLOSE + '<ts="2;4">Bye.' + OPEN + '再见。' + CLOSE)

    def test_more_chinese_segments_keep_every_translation(self):
        result = pair_line('<ts="0;4">One long sentence.', '<ts="0;1">甲<ts="1;2">乙<ts="2;4">丙')
        self.assertIn(OPEN + '甲 乙 丙' + CLOSE, result)
        self.assertEqual([s.tag for s in parse_segments(result)[1]], ['<ts="0;4">'])

    def test_more_english_segments_do_not_produce_empty_chinese(self):
        result = pair_line('<ts="0;1">One.<ts="1;2">Two.<ts="2;3">Three.', '<ts="0;3">一二三。')
        self.assertEqual(result.count(OPEN + '一二三。' + CLOSE), 3)

    def test_missing_or_blank_translation_leaves_english_untouched(self):
        for zh in ('', '<BLANK>', '<ts="0;1"><blank>'):
            self.assertEqual(pair_line('<ts="0;1">Hi.', zh), '<ts="0;1">Hi.')

    def test_untimed_menu_is_not_changed(self):
        self.assertIsNone(pair_line('New Game', '新游戏'))

    def test_duplicate_marker_is_rejected(self):
        with self.assertRaises(ValueError):
            pair_line('<ts="0;1">' + OPEN, '<ts="0;1">你好')

    def test_boundary_straddling_translation_is_not_assigned_exclusively_to_later_line(self):
        # Real game entry AARO_WORLD_PROWLCOLLECT_016: the Chinese phrase
        # begins near the end of the corresponding English time interval.
        en = '<ts="0.08;3.917">Client I met here used to take the ferry over from Jersey.<ts="3.917;7.253">Working for him was good money, til he got busted.<ts="7.583;10.148">He is how your dad found out about the Prowler.<ts="10.478;13.753">Not that it was me, but that a thief was making it big in New York,<ts="13.753;16.27">and your dad volunteered for the case.<ts="16.473;18.838">I could feel him closing in.<ts="19.346;25.739">Had to try and guess which would be worse: if I told him, or if he caught me.'
        zh = '<ts="0.08;4.205">和我在这见面的那个客户总会从泽西坐船过来。给他干活赚了不少钱，<ts="4.205;11.127">一直到后来他被抓。你爸爸就是那次发现了徘徊者这个人。他倒没发现徘徊者就是我，<ts="11.127;18.608">不过一想到居然有个小偷在纽约搞出很大动静，你爸爸就主动接下了这个案子。<ts="18.608;20.635">我能感觉到他离我越来越近了。<ts="20.635;25.739">我不得不想象哪一个结果会更可怕，是我主动告诉他，还是等着他抓住我。'
        result = parse_segments(pair_line(en, zh))[1]
        self.assertIn('我能感觉到他离我越来越近了。', result[5].text)
        self.assertNotIn('我不得不想象', result[5].text)
        self.assertEqual([s.tag for s in result], [s.tag for s in parse_segments(en)[1]])


if __name__ == '__main__':
    unittest.main()
