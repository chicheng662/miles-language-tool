"""Per-game identities and language layout; profiles remain portable."""
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from configuration import LANGUAGES


@dataclass(frozen=True)
class GameSpec:
    id: str
    name: str
    executable: str
    toc_relative: str
    assets_relative: str
    version: str
    registry_name: str
    language_spans: object


MILES = GameSpec('miles','迈尔斯·莫拉莱斯','MilesMorales.exe','asset_archive/toc',
                 'asset_archive','4.0630.0.0',"Marvel's Spider-Man Miles Morales",
                 MappingProxyType({code: language.span for code,language in LANGUAGES.items()}))
SPIDER_MAN_2 = GameSpec('spider-man-2','漫威蜘蛛侠 2','Spider-Man2.exe','toc','d','2.810.0.0',
                       "Marvel's Spider-Man 2",MappingProxyType({
    'en':0, 'da':24, 'nl':32, 'fi':40, 'fr':48, 'de':56, 'it':64, 'ja':72, 'ko':80,
    'no':88, 'pl':96, 'pt-BR':104, 'ru':112, 'es':120, 'sv':128, 'pt':136,
    'es-419':160, 'zh-CN':168, 'zh-TW':176, 'cs':192, 'hu':200, 'el':208}))
GAMES = (MILES, SPIDER_MAN_2)


def detect_game(game):
    game = Path(game)
    candidates=[spec for spec in GAMES if (game/spec.executable).is_file()]
    if len(candidates)!=1:
        raise ValueError('请选择一款受支持游戏的独立目录：迈尔斯或蜘蛛侠 2。')
    spec=candidates[0]
    if not (game/spec.toc_relative).is_file() or not (game/spec.assets_relative).is_dir():
        raise ValueError('所选游戏缺少资源索引或资源目录。')
    return spec
