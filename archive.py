"""Minimal, bounds-checked readers for this game's DAT1/DSAR assets.

Format references: Tkachov/Overstrike (DAT1/TOC.cs, DSAR.cs) and the
Insomniac localization format. This implementation uses no external packages.
"""
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
import struct
import zlib


def lz4_decode(src: bytes) -> bytes:
    out = bytearray()
    pos = 0
    try:
        while pos < len(src):
            token = src[pos]
            pos += 1
            length = token >> 4
            if length == 15:
                while True:
                    part = src[pos]
                    pos += 1
                    length += part
                    if part != 255:
                        break
            if pos + length > len(src):
                raise ValueError('Truncated LZ4 literal')
            out.extend(src[pos:pos + length])
            pos += length
            if pos == len(src):
                break
            distance = src[pos] | src[pos + 1] << 8
            pos += 2
            length = (token & 15) + 4
            if token & 15 == 15:
                while True:
                    part = src[pos]
                    pos += 1
                    length += part
                    if part != 255:
                        break
            if not 0 < distance <= len(out):
                raise ValueError('Invalid LZ4 reference')
            pattern = bytes(out[-distance:])
            out.extend((pattern * ((length + distance - 1) // distance))[:length])
    except IndexError as exc:
        raise ValueError('Truncated LZ4 block') from exc
    return bytes(out)


def asset_hash(path: str) -> int:
    value = 0xC96C5795D7870F42
    path = '/'.join(part for part in path.replace('\\', '/').lower().split('/') if part)
    for char in path.encode('ascii'):
        entry = (value & 255) ^ char
        for _ in range(8):
            entry = (entry >> 1) ^ (0xC96C5795D7870F42 if entry & 1 else 0)
        value = entry ^ (value >> 8)
    return (value >> 2) | 0x8000000000000000


class Dat1:
    def __init__(self, data: bytes):
        if len(data) < 16:
            raise ValueError('Truncated DAT1 header')
        magic, _, size, count = struct.unpack_from('<4I', data)
        if magic != 0x44415431 or size != len(data) or 16 + count * 12 > len(data):
            raise ValueError('Invalid DAT1 header or length')
        self.sections = {}
        first = len(data)
        ranges = []
        for i in range(count):
            tag, offset, size = struct.unpack_from('<III', data, 16 + i * 12)
            if offset < 16 + count * 12 or offset + size > len(data) or tag in self.sections:
                raise ValueError('Invalid DAT1 section bounds or duplicate tag')
            self.sections[tag] = data[offset:offset + size]
            first = min(first, offset)
            if size:
                ranges.append((offset, offset + size))
        ranges.sort()
        if any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):
            raise ValueError('Overlapping DAT1 sections')
        self.prefix = data[:first]

    def build(self, changes: dict[int, bytes]) -> bytes:
        if not changes.keys() <= self.sections.keys():
            raise ValueError('Cannot add unknown DAT1 sections')
        out = bytearray(self.prefix)
        for i, (tag, original) in enumerate(self.sections.items()):
            out.extend(b'\0' * (-len(out) % 16))
            payload = changes.get(tag, original)
            struct.pack_into('<III', out, 16 + i * 12, tag, len(out), len(payload))
            out.extend(payload)
        struct.pack_into('<I', out, 8, len(out))
        return bytes(out)


@dataclass(frozen=True)
class Entry:
    index: int
    asset_id: int
    span: int
    archive: str
    offset: int
    size: int


class GameArchive:
    def __init__(self, game: Path, toc: bytes | None = None):
        self.root = Path(game) / 'asset_archive'
        self.toc = toc if toc is not None else (self.root / 'toc').read_bytes()
        if self.toc[:4] != bytes.fromhex('af12af77'):
            raise ValueError('Unsupported game TOC')
        raw = zlib.decompressobj().decompress(self.toc[8:])
        if len(raw) != struct.unpack_from('<I', self.toc, 4)[0]:
            raise ValueError('Truncated TOC')
        self.dat = Dat1(raw)
        sections = self.dat.sections
        if set(sections) != {0x398ABFF0, 0x506D7B8A, 0x65BCF461, 0x6D921D7B, 0xDCD720B5, 0xEDE8ADA9}:
            raise ValueError('Unsupported TOC format; expected Miles Morales PC I20')
        archives = sections[0x398ABFF0]
        if len(archives) % 72:
            raise ValueError('Invalid archive map')
        self.archives = [archives[i + 8:i + 72].split(b'\0')[0].decode('ascii') for i in range(0, len(archives), 72)]
        spans = list(struct.iter_unpack('<II', sections[0xEDE8ADA9]))
        ids = list(struct.iter_unpack('<Q', sections[0x506D7B8A]))
        sizes = list(struct.iter_unpack('<III', sections[0x65BCF461]))
        offsets = list(struct.iter_unpack('<II', sections[0xDCD720B5]))
        if len(ids) != len(sizes):
            raise ValueError('TOC asset count mismatch')
        self.entries = []
        self.lookup = {}
        for span, (start, count) in enumerate(spans):
            if start + count > len(ids):
                raise ValueError('Invalid asset span')
            for i in range(start, start + count):
                _, size, index = sizes[i]
                archive, offset = offsets[index]
                entry = Entry(i, ids[i][0], span, self.archives[archive], offset, size)
                self.entries.append(entry)
                self.lookup[(span, entry.asset_id)] = entry

    def find(self, path: str | int, span: int = 0) -> Entry:
        return self.lookup[(span, asset_hash(path) if isinstance(path, str) else path)]

    def extract(self, path: str | int, span: int = 0) -> bytes:
        entry = self.find(path, span)
        archive_path = (self.root / entry.archive).resolve()
        if archive_path.parent != self.root.resolve():
            raise ValueError('Unsafe archive path')
        with archive_path.open('rb') as stream:
            header = stream.read(32)
            if header[:4] != b'DSAR':
                stream.seek(entry.offset)
                data = stream.read(entry.size)
            else:
                count, end = struct.unpack_from('<II', header, 8)
                if end != 32 + count * 32:
                    raise ValueError('Invalid DSAR block map')
                headers = stream.read(count * 32)
                if len(headers) != count * 32:
                    raise ValueError('Truncated DSAR block map')
                blocks = list(struct.iter_unpack('<QQIIB7x', headers))
                starts = [block[0] for block in blocks]
                first = max(0, bisect_right(starts, entry.offset) - 1)
                result = []
                for offset, compressed_offset, size, compressed_size, kind in blocks[first:]:
                    if offset >= entry.offset + entry.size:
                        break
                    if kind != 3:
                        raise ValueError(f'Unsupported DSAR compression {kind}')
                    stream.seek(compressed_offset)
                    raw = lz4_decode(stream.read(compressed_size))
                    if len(raw) != size:
                        raise ValueError('DSAR decompressed length mismatch')
                    result.append(raw[max(0, entry.offset - offset):min(size, entry.offset + entry.size - offset)])
                data = b''.join(result)
        if len(data) != entry.size:
            raise ValueError('Truncated asset')
        return data

    def redirect(self, archive_name: str, overrides: list[tuple[Entry, int, int]]) -> bytes:
        name = archive_name.encode('ascii')
        if not name or len(name) > 63 or '/' in archive_name or '\\' in archive_name or archive_name in self.archives:
            raise ValueError('Unsafe or duplicate archive name')
        sections = self.dat.sections
        archives = sections[0x398ABFF0] + sections[0x398ABFF0][:8] + name.ljust(64, b'\0')
        offsets = bytearray(sections[0xDCD720B5])
        sizes = bytearray(sections[0x65BCF461])
        seen = set()
        for entry, offset, size in overrides:
            if entry != self.lookup.get((entry.span, entry.asset_id)) or entry.index in seen:
                raise ValueError('Invalid or duplicate asset override')
            if offset < 0 or size <= 0 or offset + size > 0xFFFFFFFF:
                raise ValueError('Invalid replacement asset bounds')
            seen.add(entry.index)
            index = len(offsets) // 8
            offsets.extend(struct.pack('<II', len(self.archives), offset))
            struct.pack_into('<II', sizes, entry.index * 12 + 4, size, index)
        raw = self.dat.build({0x398ABFF0: archives, 0xDCD720B5: bytes(offsets), 0x65BCF461: bytes(sizes)})
        return self.toc[:4] + struct.pack('<I', len(raw)) + zlib.compress(raw, 9)
