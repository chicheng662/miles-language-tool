"""Preserve localization keys, hashes and metadata while editing string values."""
import struct
from archive import Dat1, lz4_decode


class Localization:
    def __init__(self, data: bytes):
        self.header = data[:36]
        if len(data) < 36 or data[:4] not in (bytes.fromhex('abb02b12'), bytes.fromhex('b5af20ba')):
            raise ValueError('Unsupported localization wrapper')
        payload = data[36:]
        self.compressed = payload[:4] != b'1TAD'
        if self.compressed:
            payload = lz4_decode(payload)
        self.dat = Dat1(payload)
        sections = self.dat.sections
        keys = sections[0x4D73CEBD]
        texts = sections[0x70A382B8]
        key_offsets = list(struct.iter_unpack('<I', sections[0xA4EA55B2]))
        text_offsets = list(struct.iter_unpack('<I', sections[0xF80DEEB4]))
        if len(key_offsets) != len(text_offsets):
            raise ValueError('Localization string count mismatch')
        self.values = {}
        for (ko,), (to,) in zip(key_offsets, text_offsets):
            key = self._string(keys, ko)
            value = self._string(texts, to)
            if key in self.values:
                raise ValueError('Duplicate localization key')
            self.values[key] = value

    @staticmethod
    def _string(data: bytes, offset: int) -> str:
        if not 0 <= offset < len(data):
            raise ValueError('Invalid localization string offset')
        end = data.find(b'\0', offset)
        if end < 0:
            raise ValueError('Unterminated localization string')
        return data[offset:end].decode('utf-8', errors='strict')

    def replace(self, changes: dict[str, str]) -> bytes:
        if not changes.keys() <= self.values.keys():
            raise ValueError('Unknown localization key')
        texts = bytearray(b'\0')
        offsets = bytearray()
        positions = {'': 0}
        for key, original in self.values.items():
            value = changes.get(key, original)
            if '\0' in value:
                raise ValueError('NUL in localization string')
            if value not in positions:
                positions[value] = len(texts)
                texts.extend(value.encode('utf-8') + b'\0')
            offsets.extend(struct.pack('<I', positions[value]))
        payload = self.dat.build({0x70A382B8: bytes(texts), 0xF80DEEB4: bytes(offsets)})
        header = bytearray(self.header)
        struct.pack_into('<I', header, 4, len(payload))
        if self.compressed:
            length = max(0, len(payload) - 15)
            encoded = bytearray([min(15, len(payload)) << 4])
            if len(payload) >= 15:
                encoded.extend(b'\xff' * (length // 255))
                encoded.append(length % 255)
            encoded.extend(payload)
            return bytes(header) + bytes(encoded)
        return bytes(header) + payload
