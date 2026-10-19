"""Portable, versioned user preferences; no game data or machine paths."""
from dataclasses import asdict, dataclass, fields
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Language:
    label: str
    span: int
    sample: str


LANGUAGES = {
    'en': Language('英语 / English', 0, 'Hey, are you ready?'),
    'zh-CN': Language('简体中文', 176, '嘿，你准备好了吗？'),
    'zh-TW': Language('繁體中文', 184, '嘿，你準備好了嗎？'),
    'ja': Language('日语 / 日本語', 72, 'ねえ、準備はいい？'),
    'ko': Language('韩语 / 한국어', 80, '준비됐어?'),
    'fr': Language('法语 / Français', 48, 'Tu es prêt ?'),
    'de': Language('德语 / Deutsch', 56, 'Bist du bereit?'),
    'it': Language('意大利语 / Italiano', 64, 'Sei pronto?'),
    'es': Language('西班牙语 / Español', 120, '¿Estás listo?'),
    'es-419': Language('拉美西班牙语', 168, '¿Estás listo?'),
    'pt': Language('葡萄牙语 / Português', 104, 'Estás pronto?'),
    'pt-BR': Language('巴西葡萄牙语', 144, 'Você está pronto?'),
    'ru': Language('俄语 / Русский', 112, 'Ты готов?'),
    'pl': Language('波兰语 / Polski', 96, 'Jesteś gotowy?'),
    'cs': Language('捷克语 / Čeština', 200, 'Jsi připraven?'),
    'hu': Language('匈牙利语 / Magyar', 208, 'Készen állsz?'),
    'el': Language('希腊语 / Ελληνικά', 216, 'Είσαι έτοιμος;'),
    'da': Language('丹麦语 / Dansk', 24, 'Er du klar?'),
    'nl': Language('荷兰语 / Nederlands', 32, 'Ben je klaar?'),
    'fi': Language('芬兰语 / Suomi', 40, 'Oletko valmis?'),
    'no': Language('挪威语 / Norsk', 88, 'Er du klar?'),
    'sv': Language('瑞典语 / Svenska', 128, 'Är du redo?'),
}


@dataclass(frozen=True)
class Profile:
    schema_version: int = 1
    top_language: str | None = 'zh-CN'
    bottom_language: str | None = 'en'
    top_size: float = 28
    bottom_size: float = 36
    top_margin_px: float = 20
    top_outline: bool = True
    bottom_outline: bool = True
    top_background: bool = False
    bottom_background: bool = False
    output_width: int = 1920
    output_height: int = 1080

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError('不支持此配置版本，请更新工具。')
        for key in ('top_language', 'bottom_language'):
            value = getattr(self, key)
            if value is not None and (not isinstance(value, str) or value not in LANGUAGES):
                raise ValueError('未知字幕语言：' + str(value))
        if self.top_language is None and self.bottom_language is None:
            raise ValueError('请至少开启一层字幕。')
        for key in ('top_outline', 'bottom_outline', 'top_background', 'bottom_background'):
            if type(getattr(self, key)) is not bool:
                raise ValueError('描边与背景必须为布尔值。')
        for key in ('output_width', 'output_height'):
            value = getattr(self, key)
            if type(value) is not int or not 480 <= value <= 16384:
                raise ValueError('游戏输出尺寸应为 480–16384 像素的整数。')
        for key, low, high in (('top_size', 16, 56), ('bottom_size', 16, 56),
                               ('top_margin_px', 0, self.output_height * .35)):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'{key} 超出允许范围。')

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or value.keys() - {f.name for f in fields(cls)}:
            raise ValueError('配置含未知字段或格式错误。')
        return cls(**value)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8-sig')))

    def save(self, path):
        from patch import atomic_write
        atomic_write(Path(path), (json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + '\n').encode('utf-8'))

    def ui_scale(self):
        return min(self.output_width / 1920, self.output_height / 1080)

    def top_ui_y(self):
        scale = self.ui_scale()
        letterbox = (self.output_height - 1080 * scale) / 2
        return (self.top_margin_px - letterbox) / scale
