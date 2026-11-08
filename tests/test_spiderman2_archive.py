"""Synthetic I29 contracts; optional real-game checks never write game files."""
import os
from pathlib import Path
import struct
import tempfile
import unittest

from archive import Dat1, Entry
from spiderman2_archive import BareLocalization, GameArchiveI29

MAP, IDS, SIZES, SPANS = 0x398ABFF0, 0x506D7B8A, 0x65BCF461, 0xEDE8ADA9
LOC_ID = 0xBE55D94F171BF8DE


def dat1(sections):
    out = bytearray(struct.pack('<4I', 0x44415431, 0xAABBCCDD, 0, len(sections)))
    out.extend(b'\0' * (12 * len(sections)))
    out.extend(b'preserved-prefix')
    for i, (tag, payload) in enumerate(sections.items()):
        out.extend(b'\0' * (-len(out) % 16))
        struct.pack_into('<III', out, 16 + 12*i, tag, len(out), len(payload))
        out.extend(payload)
    struct.pack_into('<I', out, 8, len(out))
    return bytes(out)


def sections():
    return {
        MAP: b'd\\original'.ljust(40, b'\0') + struct.pack('<QQIHI', 123, 456, 789, 12, 345),
        IDS: struct.pack('<3Q', LOC_ID, 22, LOC_ID),
        SIZES: struct.pack('<IIIiIIIiIIIi', 5, 0, 2, 123, 3, 0, 9, -1, 4, 0, 15, 456),
        SPANS: struct.pack('<4I', 0, 2, 2, 1),
        0x654BDED9: b'header-data\xff\x00',
        0x36A6C8CC: b'texture-data\x00\xfe',
        0xC9FB9DDA: b'unknown-metadata',
    }


def toc(parts=None):
    raw = dat1(sections() if parts is None else parts)
    return struct.pack('<II', 0x34E89035, len(raw)) + raw


def literal(data):
    length = len(data)
    out = bytearray([min(length, 15) << 4])
    if length >= 15:
        remaining = length - 15
        out.extend(b'\xff' * (remaining // 255))
        out.append(remaining % 255)
    return bytes(out) + data


def dsar(blocks):
    end = 32 + 32*len(blocks)
    out = bytearray(struct.pack('<4s7I', b'DSAR', 1, len(blocks), end, 0, 0, 0, 0))
    payloads = bytearray()
    for offset, raw, kind in blocks:
        payload = literal(raw)
        out.extend(struct.pack('<QQIIB7x', offset, end + len(payloads), len(raw), len(payload), kind))
        payloads.extend(payload)
    return bytes(out + payloads)


class I29Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'd').mkdir()
        (self.root / 'toc').write_bytes(toc())
        (self.root / 'd/original').write_bytes(b'__hello__bye___!test')

    def test_reads_root_toc_normalizes_archive_paths_and_selects_span(self):
        archive = GameArchiveI29(self.root)
        self.assertEqual(archive.find('localization/localization_all.localization'), Entry(0, LOC_ID, 0, 'd/original', 2, 5))
        self.assertEqual(archive.extract(LOC_ID), b'hello')
        self.assertEqual(archive.extract(LOC_ID, 1), b'!tes')
        with self.assertRaises(KeyError):
            archive.find(22, 1)

    def test_redirect_changes_only_selected_size_record_and_appends_archive(self):
        archive = GameArchiveI29(self.root)
        before = archive.toc
        output = archive.redirect('d/bilingual_subtitles', [(archive.find(LOC_ID), 16, 8)])
        rewritten = GameArchiveI29(self.root, output)
        self.assertEqual(rewritten.find(LOC_ID), Entry(0, LOC_ID, 0, 'd/bilingual_subtitles', 16, 8))
        self.assertEqual(rewritten.find(22), archive.find(22))
        self.assertEqual(rewritten.find(LOC_ID, 1), archive.find(LOC_ID, 1))
        for tag, payload in archive.dat.sections.items():
            if tag not in (MAP, SIZES):
                self.assertEqual(rewritten.dat.sections[tag], payload)
        self.assertEqual(rewritten.dat.sections[MAP][:66], archive.dat.sections[MAP])
        self.assertEqual(rewritten.dat.sections[MAP][66:], b'd\\bilingual_subtitles'.ljust(40, b'\0') + bytes(26))
        self.assertEqual(rewritten.dat.sections[SIZES][:16], struct.pack('<IIIi', 8, 1, 16, 123))
        self.assertEqual(rewritten.dat.sections[SIZES][16:], archive.dat.sections[SIZES][16:])
        self.assertEqual(archive.toc, before)
        self.assertEqual((self.root / 'toc').read_bytes(), before)
        (self.root / 'd/bilingual_subtitles').write_bytes(bytes(16) + b'replaced')
        self.assertEqual(rewritten.extract(LOC_ID), b'replaced')
        self.assertEqual(output[8:16], before[8:16])

    def test_rejects_unsafe_duplicate_and_overlong_archive_names(self):
        archive = GameArchiveI29(self.root)
        for name in ('', '../outside', '/absolute', 'C:/absolute', 'd/../outside', 'd//x', 'd/./x', 'd/x:stream', 'd/x\0y', 'd/CON', 'd/trailing.', 'd/trailing ', 'd/' + 'x'*38, 'd/ORIGINAL', 'd\\original'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                archive.redirect(name, [])
        for name in ('../outside', 'd/../x', '/x', 'd/NUL'):
            parts = sections()
            parts[MAP] = name.encode().ljust(40, b'\0') + bytes(26)
            with self.subTest(name=name), self.assertRaises(ValueError):
                GameArchiveI29(self.root, toc(parts))

    def test_rejects_foreign_duplicate_and_invalid_override_bounds(self):
        archive = GameArchiveI29(self.root)
        entry = archive.find(LOC_ID)
        cases = [ [(entry, 0, 1), (entry, 2, 1)], [(Entry(99, LOC_ID, 0, 'd/original', 2, 5), 0, 1)] ]
        cases += [[(entry, offset, size)] for offset, size in ((-1, 1), (0, 0), (0, -1), (0xFFFFFFFF, 1), (1, 0xFFFFFFFF), (1.5, 2), (True, 2))]
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                archive.redirect('d/replacement', overrides)

    def test_rejects_truncated_headers_sections_indices_and_overlapping_spans(self):
        good = toc()
        invalid = [b'', good[:7], good[:-1], bytes(4) + good[4:], good[:4] + struct.pack('<I', 1) + good[8:]]
        for tag, payload in ((MAP, b'x'), (IDS, b'x'), (SIZES, b'x'), (SPANS, b'x'), (IDS, struct.pack('<Q', LOC_ID)), (SIZES, struct.pack('<IIIi', 5, 12, 2, -1)*3), (SPANS, struct.pack('<4I', 0, 3, 2, 1)), (SPANS, struct.pack('<II', 3, 2))):
            parts = sections()
            parts[tag] = payload
            invalid.append(toc(parts))
        parts = sections()
        del parts[MAP]
        invalid.append(toc(parts))
        for data in invalid:
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                GameArchiveI29(self.root, data)

    def header_archive(self, flags=0xC0000000, header=None, header_offset=16):
        parts = sections()
        header = header if header is not None else struct.pack('<IBBHII', 0x97F26013, 0, 1, 3, flags | 5, 0x100CD93A) + b'xyz'
        parts[0x654BDED9] = b'ORIGINAL-PREFIX!' + header
        parts[SIZES] = struct.pack('<IIIiIIIiIIIi', 5, 0, 2, header_offset, 3, 0, 9, -1, 5, 0, 15, header_offset)
        return GameArchiveI29(self.root, toc(parts))

    def test_replacement_header_updates_low30_size_and_preserves_flags_and_extra(self):
        for flags in (0, 0x40000000, 0x80000000, 0xC0000000):
            archive = self.header_archive(flags)
            original = archive.dat.sections[0x654BDED9][16:]
            changed = archive.replacement_header(archive.find(LOC_ID), 7)
            self.assertEqual(changed[:8], original[:8])
            self.assertEqual(struct.unpack_from('<I', changed, 8)[0], flags | 7)
            self.assertEqual(changed[12:], original[12:])
            self.assertEqual(archive.dat.sections[0x654BDED9][16:], original)
        self.assertIsNone(archive.replacement_header(archive.find(22), 8))
        multi = struct.pack('<IBBHIIII', 0x97F26013, 7, 2, 3, 0x80000005, 0x100CD93A, 99, 12345) + b'xyz'
        archive = self.header_archive(header=multi)
        changed = archive.replacement_header(archive.find(LOC_ID), 7)
        self.assertEqual(changed[12:], multi[12:])
        self.assertEqual(changed[:8], multi[:8])

    def test_replacement_header_rejects_mismatch_unsupported_and_invalid_bounds(self):
        archive = self.header_archive()
        for size in (0, -1, 1 << 30, 1.5, True):
            with self.subTest(size=size), self.assertRaises(ValueError):
                archive.replacement_header(archive.find(LOC_ID), size)
        foreign = Entry(99, LOC_ID, 0, 'd/original', 2, 5)
        with self.assertRaises(ValueError):
            archive.replacement_header(foreign, 7)
        for offset in (-2, 1000):
            bad = self.header_archive(header_offset=offset)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                bad.replacement_header(bad.find(LOC_ID), 7)
        for header in (b'', bytes(7), struct.pack('<IBBH', 0x97F26013, 0, 0, 0), struct.pack('<IBBHII', 0x97F26013, 0, 1, 1, 5, 0), struct.pack('<IBBHII', 0x97F26013, 0, 1, 0, 6, 0)):
            bad = self.header_archive(header=header)
            with self.subTest(header=header), self.assertRaises(ValueError):
                bad.replacement_header(bad.find(LOC_ID), 7)

    def test_redirect_appends_explicit_header_without_mutating_shared_original(self):
        archive = self.header_archive()
        entry = archive.find(LOC_ID)
        original = archive.dat.sections[0x654BDED9]
        header = archive.replacement_header(entry, 7)
        output = archive.redirect('d/replaced', [(entry, 0, 7)], headers={entry.index: header})
        changed = GameArchiveI29(self.root, output)
        self.assertEqual(changed.dat.sections[0x654BDED9], original + header)
        self.assertEqual(archive.dat.sections[0x654BDED9], original)
        sizes = changed.dat.sections[SIZES]
        self.assertEqual(struct.unpack_from('<i', sizes, 12)[0], len(original))
        self.assertEqual(struct.unpack_from('<i', sizes, 44)[0], 16)
        self.assertEqual(sizes[16:], archive.dat.sections[SIZES][16:])
        self.assertEqual(changed.replacement_header(changed.find(LOC_ID), 9)[12:], header[12:])
        ordinary = GameArchiveI29(self.root, archive.redirect('d/ordinary', [(entry, 0, 7)]))
        self.assertEqual(ordinary.dat.sections[0x654BDED9], original)
        self.assertEqual(struct.unpack_from('<i', ordinary.dat.sections[SIZES], 12)[0], 16)

    def test_redirect_rejects_header_for_unmodified_asset_and_malformed_headers(self):
        archive = self.header_archive()
        entry = archive.find(LOC_ID)
        header = archive.replacement_header(entry, 7)
        for headers in ({1: header}, {99: header}, {True: header}, {entry.index: b''}, {entry.index: header[:-1]}, {entry.index: header+b'X'}, {entry.index: None}, {entry.index: bytearray(header)}):
            with self.subTest(headers=headers), self.assertRaises(ValueError):
                archive.redirect('d/replaced', [(entry, 0, 7)], headers=headers)

    def test_extracts_lz4_across_blocks_and_refuses_gdeflate(self):
        path = self.root / 'd/original'
        path.write_bytes(dsar([(0, b'__hel', 3), (5, b'lo__bye___!test', 3)]))
        archive = GameArchiveI29(self.root)
        self.assertEqual(archive.extract(LOC_ID), b'hello')
        path.write_bytes(dsar([(0, b'__hello', 2)]))
        with self.assertRaisesRegex(ValueError, 'compression 2'):
            archive.extract(LOC_ID)

    def test_rejects_raw_and_dsar_truncation_gaps_overlap_and_bad_lengths(self):
        archive = GameArchiveI29(self.root)
        valid = dsar([(0, b'__hello', 3)])
        wrong_length = bytearray(valid)
        struct.pack_into('<I', wrong_length, 32+16, 8)
        bad_map = bytearray(valid)
        struct.pack_into('<I', bad_map, 12, 0)
        bad_offset = bytearray(valid)
        struct.pack_into('<Q', bad_offset, 40, 32)
        invalid = [b'__hel', b'DSAR', valid[:40], valid[:-1], bytes(wrong_length), bytes(bad_map), bytes(bad_offset), dsar([(0, b'__hel', 3), (6, b'lo', 3)]), dsar([(0, b'__hello', 3), (4, b'lo', 3)])]
        for data in invalid:
            (self.root / 'd/original').write_bytes(data)
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                archive.extract(LOC_ID)


class BareLocalizationTests(unittest.TestCase):
    def data(self):
        return dat1({0x4D73CEBD: b'FIRST\0SECOND\0', 0x70A382B8: b'Hello\0World\0', 0xA4EA55B2: struct.pack('<II', 0, 6), 0xF80DEEB4: struct.pack('<II', 0, 6), 0x12345678: b'key-hash-metadata'})

    def test_bare_dat1_edit_retains_keys_and_unknown_sections(self):
        original = self.data()
        loc = BareLocalization(original)
        self.assertEqual(loc.values, {'FIRST': 'Hello', 'SECOND': 'World'})
        output = loc.replace({'FIRST': '娴嬭瘯 / TEST'})
        self.assertEqual(output[:4], b'1TAD')
        changed = BareLocalization(output)
        self.assertEqual(changed.values, {'FIRST': '娴嬭瘯 / TEST', 'SECOND': 'World'})
        for tag, payload in Dat1(original).sections.items():
            if tag not in (0x70A382B8, 0xF80DEEB4):
                self.assertEqual(Dat1(output).sections[tag], payload)
        self.assertEqual(loc.values['FIRST'], 'Hello')

    def test_rejects_wrappers_truncation_unknown_keys_and_nuls(self):
        data = self.data()
        for raw in (b'', data[:-1], bytes.fromhex('abb02b12') + bytes(32) + data):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                BareLocalization(raw)
        loc = BareLocalization(data)
        for changes in ({'UNKNOWN': 'x'}, {'FIRST': 'bad\0text'}):
            with self.assertRaises(ValueError):
                loc.replace(changes)


@unittest.skipUnless(os.environ.get('MILES_MSM2_GAME_DIR'), 'Set MILES_MSM2_GAME_DIR for read-only real-game integration')
class LocalI29Tests(unittest.TestCase):
    def test_read_only_real_localization_and_in_memory_redirect(self):
        root = Path(os.environ['MILES_MSM2_GAME_DIR'])
        import spiderman2_backend
        current_toc = (root / 'toc').read_bytes()
        archive = GameArchiveI29(root, spiderman2_backend.inspect_game(root)['original_toc'])
        loc_path = 'localization/localization_all.localization'
        english = BareLocalization(archive.extract(loc_path, 0))
        chinese = BareLocalization(archive.extract(loc_path, 168))
        self.assertGreater(len(english.values), 50000)
        self.assertEqual(list(english.values), list(chinese.values))
        key = next(iter(english.values))
        replacement = english.replace({key: 'Generated integration sample'})
        self.assertEqual(BareLocalization(replacement).values[key], 'Generated integration sample')
        entry = archive.find(loc_path)
        header = archive.replacement_header(entry, len(replacement))
        self.assertIsNotNone(header)
        overlay = archive.find('ui/loaded/authored/overlay/js/overlay.js')
        self.assertIsNone(archive.replacement_header(overlay, 123))
        rewritten = GameArchiveI29(root, archive.redirect('d/bilingual_subtitles', [(entry, 16, len(replacement))], headers={entry.index: header}))
        old_headers = archive.dat.sections[0x654BDED9]
        self.assertEqual(rewritten.dat.sections[0x654BDED9], old_headers + header)
        self.assertEqual(rewritten.find(loc_path).archive, 'd/bilingual_subtitles')
        self.assertEqual(rewritten.find(loc_path, 168), archive.find(loc_path, 168))
        self.assertEqual(len(rewritten.entries), len(archive.entries))
        for tag, payload in archive.dat.sections.items():
            if tag not in (MAP, SIZES, 0x654BDED9):
                self.assertEqual(rewritten.dat.sections[tag], payload)
        old_sizes = archive.dat.sections[SIZES]
        new_sizes = rewritten.dat.sections[SIZES]
        start = entry.index * 16
        self.assertEqual(old_sizes[:start], new_sizes[:start])
        self.assertEqual(old_sizes[start+16:], new_sizes[start+16:])
        self.assertEqual(struct.unpack_from('<i', new_sizes, start+12)[0], len(old_headers))
        self.assertEqual((root / 'toc').read_bytes(), current_toc)


if __name__ == '__main__':
    unittest.main()
