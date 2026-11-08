"""Independent Spider-Man 2 PC I29 adapter, using documented format facts.

The root TOC wraps an uncompressed DAT1. Unlike I20, each size record
contains its archive index and offset directly. Unknown section payloads,
archive metadata, and per-asset header offsets are retained when redirecting.
No game files are modified by this module.
"""
from pathlib import Path
import re
import struct

from archive import Dat1, Entry, asset_hash, lz4_decode
from localization import Localization


_MAP = 0x398ABFF0
_IDS = 0x506D7B8A
_SIZES = 0x65BCF461
_SPANS = 0xEDE8ADA9
_HEADERS = 0x654BDED9
_MAGIC = 0x34E89035
_RESERVED = {'CON', 'PRN', 'AUX', 'NUL'} | {
    f'{prefix}{number}' for prefix in ('COM', 'LPT') for number in range(1, 10)
}


def _archive_name(name: str) -> str:
    """Canonicalize the Windows separators used by the TOC, rejecting escapes."""
    if not isinstance(name, str):
        raise ValueError('Unsafe archive path')
    name = name.replace('\\', '/')
    parts = name.split('/')
    if not name or any(
        not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*', part)
        or part.endswith('.')
        or part.split('.')[0].upper() in _RESERVED
        for part in parts
    ):
        raise ValueError('Unsafe archive path')
    if len(name.encode('ascii')) > 39:
        raise ValueError('Archive path exceeds I29 filename capacity')
    return name


class GameArchiveI29:
    def __init__(self, game: Path, toc: bytes | None = None):
        self.root = Path(game)
        self.toc = toc if toc is not None else (self.root / 'toc').read_bytes()
        if len(self.toc) < 8:
            raise ValueError('Truncated I29 TOC header')
        magic, length = struct.unpack_from('<II', self.toc)
        if magic != _MAGIC:
            raise ValueError('Unsupported game TOC; expected Spider-Man 2 PC I29')
        if length != len(self.toc) - 8:
            raise ValueError('Invalid I29 TOC length')
        self.dat = Dat1(self.toc[8:])
        sections = self.dat.sections
        if not {_MAP, _IDS, _SIZES, _SPANS} <= sections.keys():
            raise ValueError('Missing I29 TOC section')
        for tag, width in ((_MAP, 66), (_IDS, 8), (_SIZES, 16), (_SPANS, 8)):
            if len(sections[tag]) % width:
                raise ValueError('Invalid I29 section record length')
        self.archives = []
        archive_map = sections[_MAP]
        for offset in range(0, len(archive_map), 66):
            name = archive_map[offset:offset + 40].split(b'\0', 1)[0]
            try:
                self.archives.append(_archive_name(name.decode('ascii')))
            except UnicodeDecodeError as exc:
                raise ValueError('Invalid I29 archive filename') from exc
        if len({name.casefold() for name in self.archives}) != len(self.archives):
            raise ValueError('Duplicate I29 archive path')
        count = len(sections[_IDS]) // 8
        if len(sections[_SIZES]) // 16 != count:
            raise ValueError('TOC asset count mismatch')
        sizes = sections[_SIZES]
        for size, index, offset, header_offset in struct.iter_unpack('<IIIi', sizes):
            if index >= len(self.archives):
                raise ValueError('Invalid I29 archive index')
        self.entries = []
        self.lookup = {}
        occupied = bytearray(count)
        for span, (start, length) in enumerate(struct.iter_unpack('<II', sections[_SPANS])):
            if start + length > count:
                raise ValueError('Invalid asset span')
            for index in range(start, start + length):
                if occupied[index]:
                    raise ValueError('Overlapping asset spans')
                occupied[index] = 1
                asset_id = struct.unpack_from('<Q', sections[_IDS], index * 8)[0]
                size, archive, offset, _ = struct.unpack_from('<IIIi', sizes, index * 16)
                entry = Entry(index, asset_id, span, self.archives[archive], offset, size)
                key = (span, asset_id)
                if key in self.lookup:
                    raise ValueError('Duplicate asset ID within span')
                self.entries.append(entry)
                self.lookup[key] = entry

    def find(self, path: str | int, span: int = 0) -> Entry:
        return self.lookup[(span, asset_hash(path) if isinstance(path, str) else path)]

    def extract(self, path: str | int, span: int = 0) -> bytes:
        entry = self.find(path, span)
        root = self.root.resolve()
        archive_path = (root / _archive_name(entry.archive)).resolve()
        if not archive_path.is_relative_to(root):
            raise ValueError('Unsafe archive path')
        with archive_path.open('rb') as stream:
            stream.seek(0, 2)
            file_size = stream.tell()
            stream.seek(0)
            header = stream.read(32)
            if header[:4] != b'DSAR':
                if entry.offset + entry.size > file_size:
                    raise ValueError('Truncated asset')
                stream.seek(entry.offset)
                data = stream.read(entry.size)
            else:
                if len(header) != 32:
                    raise ValueError('Truncated DSAR header')
                count, end = struct.unpack_from('<II', header, 8)
                if end != 32 + count * 32 or end > file_size:
                    raise ValueError('Invalid or truncated DSAR block map')
                block_headers = stream.read(count * 32)
                if len(block_headers) != count * 32:
                    raise ValueError('Truncated DSAR block map')
                data = bytearray()
                previous_end = 0
                cursor = entry.offset
                limit = entry.offset + entry.size
                for offset, compressed_offset, size, compressed_size, kind in struct.iter_unpack('<QQIIB7x', block_headers):
                    if not size or offset < previous_end:
                        raise ValueError('Overlapping or invalid DSAR blocks')
                    previous_end = offset + size
                    if compressed_offset < end or compressed_offset + compressed_size > file_size:
                        raise ValueError('Invalid or truncated DSAR compressed block')
                    if offset >= limit or offset + size <= entry.offset:
                        continue
                    if offset > cursor:
                        raise ValueError('Gap in DSAR asset blocks')
                    if kind != 3:
                        raise ValueError(f'Unsupported DSAR compression {kind}; only LZ4 (3) is supported')
                    stream.seek(compressed_offset)
                    compressed = stream.read(compressed_size)
                    if len(compressed) != compressed_size:
                        raise ValueError('Truncated DSAR compressed block')
                    raw = lz4_decode(compressed)
                    if len(raw) != size:
                        raise ValueError('DSAR decompressed length mismatch')
                    stop = min(limit, offset + size)
                    data.extend(raw[cursor - offset:stop - offset])
                    cursor = stop
                data = bytes(data)
        if len(data) != entry.size:
            raise ValueError('Truncated asset')
        return data

    @staticmethod
    def _header_length(header: bytes) -> int:
        if not isinstance(header, bytes) or len(header) < 8:
            raise ValueError('Invalid I30 asset header')
        pairs = header[5]
        extra = struct.unpack_from('<H', header, 6)[0]
        length = 8 + pairs * 8 + extra
        if not pairs or length > len(header):
            raise ValueError('Unsupported or truncated I30 asset header')
        return length

    def replacement_header(self, entry: Entry, new_size: int) -> bytes | None:
        """Copy a detached I30 header and change only its low 30-bit size.

        The top two bits and the second pair field are opaque metadata. Their
        meanings are not inferred here; both remain exactly as in the source.
        """
        if not isinstance(entry, Entry) or entry != self.lookup.get((entry.span, entry.asset_id)):
            raise ValueError('Invalid asset for replacement header')
        if type(new_size) is not int or not 0 < new_size < (1 << 30):
            raise ValueError('Replacement size exceeds I30 header capacity')
        offset = struct.unpack_from('<i', self.dat.sections[_SIZES], entry.index * 16 + 12)[0]
        if offset == -1:
            return None
        headers = self.dat.sections.get(_HEADERS, b'')
        if offset < 0 or offset + 8 > len(headers):
            raise ValueError('Invalid I30 asset header offset')
        payload = headers[offset:]
        length = self._header_length(payload)
        original_size = struct.unpack_from('<I', payload, 8)[0]
        if original_size & 0x3FFFFFFF != entry.size:
            raise ValueError('Unsupported I30 asset header size mismatch')
        result = bytearray(payload[:length])
        struct.pack_into('<I', result, 8, (original_size & 0xC0000000) | new_size)
        return bytes(result)

    def redirect(self, archive_name: str, overrides: list[tuple[Entry, int, int]], headers: dict[int, bytes] | None = None) -> bytes:
        archive_name = _archive_name(archive_name)
        if archive_name.casefold() in {name.casefold() for name in self.archives}:
            raise ValueError('Duplicate archive name')
        sizes = bytearray(self.dat.sections[_SIZES])
        seen = set()
        for entry, offset, size in overrides:
            if not isinstance(entry, Entry) or entry != self.lookup.get((entry.span, entry.asset_id)) or entry.index in seen:
                raise ValueError('Invalid or duplicate asset override')
            if type(offset) is not int or type(size) is not int or offset < 0 or size <= 0 or offset + size > 0xFFFFFFFF:
                raise ValueError('Invalid replacement asset bounds')
            seen.add(entry.index)
            # HeaderOffset belongs to the separate header section, not this archive.
            struct.pack_into('<III', sizes, entry.index * 16, size, len(self.archives), offset)
        changes = {}
        if headers is not None:
            if not isinstance(headers, dict):
                raise ValueError('Invalid replacement headers')
            detached = bytearray(self.dat.sections.get(_HEADERS, b''))
            if headers and _HEADERS not in self.dat.sections:
                raise ValueError('Missing detached asset headers section')
            for index, header in headers.items():
                if type(index) is not int or index not in seen:
                    raise ValueError('Header override requires an overridden asset')
                if self._header_length(header) != len(header):
                    raise ValueError('Invalid I30 asset header length')
                if len(detached) + len(header) > 0x7FFFFFFF:
                    raise ValueError('I30 asset header offset exceeds signed capacity')
                # Append even when an old header has the same length: multiple
                # entries may share that old header, which must remain intact.
                struct.pack_into('<i', sizes, index * 16 + 12, len(detached))
                detached.extend(header)
            if headers:
                changes[_HEADERS] = bytes(detached)
        record = archive_name.replace('/', '\\').encode('ascii').ljust(40, b'\0') + bytes(26)
        changes.update({_MAP: self.dat.sections[_MAP] + record, _SIZES: bytes(sizes)})
        raw = self.dat.build(changes)
        return struct.pack('<II', _MAGIC, len(raw)) + raw


class BareLocalization:
    """Expose I29's direct DAT1 using the existing independent string editor."""
    def __init__(self, data: bytes):
        if data[:4] != b'1TAD':
            raise ValueError('Expected bare localization DAT1')
        # This wrapper exists only in memory to reuse string editing. It is never
        # written into an I29 resource, whose payload must remain bare DAT1.
        wrapper = bytes.fromhex('abb02b12') + struct.pack('<I', len(data)) + bytes(28)
        try:
            self._localization = Localization(wrapper + data)
        except (KeyError, struct.error) as exc:
            raise ValueError('Invalid bare localization sections') from exc
        self.dat = self._localization.dat
        self.values = self._localization.values

    def replace(self, changes: dict[str, str]) -> bytes:
        return self._localization.replace(changes)[36:]
