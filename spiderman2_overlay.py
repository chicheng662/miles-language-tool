"""Compile our independent DOM adapter into the player's own Overlay.js.

No game source, dialogue, or third-party mod implementation is bundled here.
The engine-bound text remains intact; our child layers share the native slots'
visibility and animation lifecycle.
"""
import json
from pathlib import Path
import re

from configuration import Profile


def patch_overlay_js(source: str, profile: Profile, table=()) -> str:
    """Return locally generated JS for the reviewed two-slot native lifecycle."""
    if not isinstance(source, str) or 'MMSpiderMan2' in source:
        raise ValueError('必须从原始 Spider-Man 2 字幕界面生成。')
    patterns = (
        r"engine\.on\(\s*['\"]CacheSubtitleCCElements['\"]\s*,",
        r"engine\.on\(\s*['\"]ShowSubtitle['\"]\s*,",
        r"engine\.on\(\s*['\"]HideSubtitle['\"]\s*,\s*HideSubtitle\s*\)",
        r'\bvar\s+subtitle_elems\s*=',
        r'\bvar\s+subtitle_elems_text\s*=',
    )
    if any(len(re.findall(pattern, source)) != 1 for pattern in patterns):
        raise ValueError('不支持的 Spider-Man 2 原生字幕结构。')
    hide = r'(function\s+HideSubtitle\s*\(\s*sub_num\s*,\s*instant\s*\)\s*\{)'
    if len(re.findall(hide, source)) != 1:
        raise ValueError('不支持的 Spider-Man 2 字幕隐藏函数。')
    rows = []
    for row in table:
        if not isinstance(row, (tuple, list)) or len(row) != 2 or any(not isinstance(s, str) for s in row):
            raise ValueError('字幕字典必须为两层文本的序列。')
        rows.append(list(row))

    def js(value):
        # Safe both in external JS and in an HTML script element. ensure_ascii
        # also escapes U+2028/U+2029 for older embedded JS engines.
        return json.dumps(value, ensure_ascii=True, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

    runtime = (Path(__file__).parent / 'runtime' / 'spiderman2_subtitles.js').read_text(encoding='utf-8')
    runtime = runtime.replace('__MM2_PROFILE__', js(profile.to_dict())).replace('__MM2_LINES__', js(rows))
    changed = re.sub(hide, lambda m: m.group(1) + '\n  MMSpiderMan2.hide(sub_num, instant);', source)
    return changed + '\n;\n' + runtime
