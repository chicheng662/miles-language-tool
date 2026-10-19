"""Pair original translations while retaining the English audio's time tags."""
from dataclasses import dataclass
import html
import re

OPEN = '[[MMZH]]'
CLOSE = '[[/MMZH]]'
TIMING = re.compile(r'<ts=(?:&quot;|\")([^<>]*?)(?:&quot;|\")>', re.IGNORECASE)
NAME = re.compile(r'<name=(?:&quot;|\")[^<>]*?(?:&quot;|\")>', re.IGNORECASE)


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    tag: str
    text: str


def parse_segments(value: str) -> tuple[str, list[Segment]]:
    matches = list(TIMING.finditer(value))
    if not matches:
        return value, []
    result = []
    for index, match in enumerate(matches):
        start, end = map(float, html.unescape(match.group(1)).split(';'))
        if start < 0 or end < start:
            raise ValueError('Invalid subtitle time range')
        stop = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        result.append(Segment(start, end, match.group(0), value[match.end():stop]))
    return value[:matches[0].start()], result


def clean_translation(value: str) -> str:
    return re.sub(r'<blank>', '', NAME.sub('', value), flags=re.IGNORECASE).strip()


def pair_line(english: str, chinese: str) -> str | None:
    if any(marker in text for marker in (OPEN, CLOSE) for text in (english, chinese)):
        raise ValueError('Subtitle already contains bilingual markers')
    prefix, en = parse_segments(english)
    if not en:
        return None
    _, zh = parse_segments(chinese)
    if not zh:
        translation = clean_translation(chinese)
        zh = [Segment(en[0].start, en[-1].end, '', translation)] if translation else []
    if not zh or not any(clean_translation(s.text) for s in zh):
        return english
    paired = [[] for _ in en]
    if len(en) == len(zh):
        for index, segment in enumerate(zh):
            paired[index].append(clean_translation(segment.text))
    else:
        # Keep all overlapping Chinese chunks as context, including a chunk
        # straddling an English boundary. Assigning it exclusively to one
        # English chunk can leave the other with an unrelated translation.
        en_duration = max(en[-1].end - en[0].start, 0.001)
        zh_duration = max(zh[-1].end - zh[0].start, 0.001)

        def overlap(a: Segment, b: Segment) -> float:
            a0, a1 = (a.start - en[0].start) / en_duration, (a.end - en[0].start) / en_duration
            b0, b1 = (b.start - zh[0].start) / zh_duration, (b.end - zh[0].start) / zh_duration
            return max(0.0, min(a1, b1) - max(a0, b0))

        def distance(a: Segment, b: Segment) -> float:
            return abs(((a.start + a.end) / 2 - en[0].start) / en_duration - ((b.start + b.end) / 2 - zh[0].start) / zh_duration)

        indices = [[j for j, segment in enumerate(zh) if overlap(english_segment, segment) > 0] for english_segment in en]
        for j, segment in enumerate(zh):
            if not any(j in group for group in indices):
                closest = min(range(len(en)), key=lambda i: distance(en[i], segment))
                indices[closest].append(j)
        for i, group in enumerate(indices):
            if not group:
                group.append(min(range(len(zh)), key=lambda j: distance(en[i], zh[j])))
            paired[i] = [clean_translation(zh[j].text) for j in sorted(group)]
    return prefix + ''.join(segment.tag + segment.text + (OPEN + ' '.join(paired[index]) + CLOSE if any(paired[index]) else '') for index, segment in enumerate(en))


TOP_OPEN = '[[MMTOP]]'
TOP_CLOSE = '[[/MMTOP]]'


def aligned_texts(english: str, translation: str) -> list[str]:
    """Reuse the proven context alignment without changing the audio timeline."""
    result = pair_line(english, translation)
    if result is None:
        return []
    values = []
    for segment in parse_segments(result)[1]:
        start = segment.text.find(OPEN)
        end = segment.text.find(CLOSE, start + len(OPEN))
        values.append(segment.text[start + len(OPEN):end] if start >= 0 and end >= 0 else '')
    return values


def pair_layers(english: str, bottom: str | None, top: str | None) -> tuple[str | None, dict]:
    """None disables a layer; empty translations use the documented fallback."""
    for text in (english, bottom or '', top or ''):
        if TOP_OPEN in text or TOP_CLOSE in text:
            raise ValueError('Subtitle already contains dual-layer markers')
    prefix, segments = parse_segments(english)
    coverage = {'bottom_fallback': False, 'top_missing': False}
    if not segments:
        return None, coverage
    original_bottom = bottom == english
    bottom_parts = ([segment.text for segment in segments] if original_bottom else aligned_texts(english, bottom)) if bottom is not None else [''] * len(segments)
    top_parts = aligned_texts(english, top) if top is not None else [''] * len(segments)
    result = []
    for index, segment in enumerate(segments):
        lower = bottom_parts[index]
        if bottom is not None and not lower and not original_bottom:
            lower = clean_translation(segment.text)
            coverage['bottom_fallback'] = True
        upper = top_parts[index]
        if top is not None and not upper:
            coverage['top_missing'] = True
        # Speaker IDs belong to the English audio, including any placed after a ts.
        names = '' if original_bottom else ''.join(NAME.findall(segment.text))
        result.append(segment.tag + names + lower + TOP_OPEN + upper + TOP_CLOSE)
    return prefix + ''.join(result), coverage


def encode_wire(english: str, paired: str, table: list) -> str:
    """Only short IDs pass through the engine; full strings live in local GFX."""
    prefix, original = parse_segments(english)
    segments = parse_segments(paired)[1]
    if len(original) != len(segments):
        raise ValueError('配对分段与英语时间轴不一致。')
    wire = []
    for en, segment in zip(original, segments):
        start = segment.text.index(TOP_OPEN)
        end = segment.text.index(TOP_CLOSE, start + len(TOP_OPEN))
        lower = NAME.sub('', segment.text[:start])
        upper = segment.text[start + len(TOP_OPEN):end]
        if any(c in lower + upper for c in ('\x1e', '\x1f')):
            raise ValueError('台词含保留分隔符。')
        index = len(table)
        table.append((lower, upper))
        names = ''.join(NAME.findall(en.text))
        wire.append(en.tag + names + '[[MMID:' + str(index) + ']]')
    return prefix + ''.join(wire)
