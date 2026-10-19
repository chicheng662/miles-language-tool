"""GUI-independent local generation, inspection, coverage and installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from archive import GameArchive
from configuration import LANGUAGES, Profile
from configurable_overlay import patch_configurable_source, uses_learning_font
from dialogue import pair_layers, parse_segments, encode_wire
from localization import Localization
from patch import sha256, status, checked_backup, install_bundle, restore, game_running, atomic_write, game_lock

ROOT = Path(__file__).resolve().parent
ORIGINAL_TOC_SHA = 'd2129393b1f8fc433232ce9f7e83de1884a9951b10e34cd68770a8d03b4965c9'
ORIGINAL_OVERLAY_SHA = 'd37ca08839b4576d2c66d53501be9a688b9da8a00d58191d4da44e190fe23636'
LOCALIZATION = 'localization/localization_all.localization'
OVERLAY = 'ui/export/Overlay.gfx'


def validate_localization(raw, language):
    baselines = json.loads((ROOT / 'language_baselines.json').read_text(encoding='utf-8'))
    if language not in baselines or sha256(raw) != baselines[language]:
        raise ValueError('语言资源已变更或版本不兼容：' + language + '。不会覆盖未知修改。')
    return raw


def app_data():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MilesLanguageTool'


def work_directory(game):
    return app_data() / 'work' / hashlib.sha256(str(Path(game).resolve()).casefold().encode()).hexdigest()[:16]


def state_directory(game):
    game = Path(game).resolve()
    # Prefer an existing legacy backup; never take an already patched index as
    # an original. New users keep recoverable state beside their game.
    legacy = game / 'BilingualSubtitles/backups/install'
    modern = game / '.miles-language-tool'
    if (legacy / 'state.json').is_file() and not (modern / 'state.json').is_file():
        return legacy
    return modern


def inspect_game(game):
    game = Path(game).resolve()
    if not (game / 'MilesMorales.exe').is_file() or not (game / 'asset_archive/toc').is_file():
        raise ValueError('请选择包含 MilesMorales.exe 和 asset_archive 的游戏目录。')
    state = state_directory(game)
    current = (game / 'asset_archive/toc').read_bytes()
    state_status = status(game, state)
    if state_status in ('conflict', 'damaged'):
        raise ValueError('检测到索引冲突或补丁损坏，请先处理其他模组变更；工具不会覆盖。')
    original = current
    if sha256(current) != ORIGINAL_TOC_SHA:
        if state_status != 'installed':
            raise ValueError('资源版本不匹配。首版仅支持已验证的 4.0630.0.0 原始索引。')
        original = checked_backup(state, ORIGINAL_TOC_SHA)
    if sha256(original) != ORIGINAL_TOC_SHA:
        raise ValueError('原始索引与受支持版本不匹配。')
    archive = GameArchive(game, original)
    if sha256(archive.extract(OVERLAY)) != ORIGINAL_OVERLAY_SHA:
        raise ValueError('原始字幕界面已变更，无法安全生成。')
    for language in ('en', 'zh-CN'):
        validate_localization(archive.extract(LOCALIZATION, LANGUAGES[language].span), language)
    return {'game': game, 'state': state, 'status': state_status, 'original_toc': original,
            'version': '4.0630.0.0'}


def java_command(*args):
    base = Path(sys.executable).parent / 'runtime' if getattr(sys, 'frozen', False) else ROOT / '.tools'
    jars = list(base.glob('ffdec/ffdec.jar'))
    javas = list(base.glob('jre/*/bin/java.exe')) + list(base.glob('jre/bin/java.exe'))
    if not jars or not javas:
        raise ValueError('缺少随包运行时，请完整解压工具，不要只复制 exe。')
    return [str(javas[0]), '-Djava.awt.headless=true', '-jar', str(jars[0]), '-onerror', 'abort', *map(str, args)]


def compile_overlay(original, profile, work, progress, table=()):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    original_path = work / 'Overlay.original.gfx'
    atomic_write(original_path, original)
    def run(label, *args):
        progress(label)
        with (work / (label.split(' ')[0] + '.log')).open('w', encoding='utf-8') as log:
            subprocess.run(java_command(*args), stdout=log, stderr=subprocess.STDOUT, check=True,
                           timeout=240, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    source_path = work / 'as-original/scripts/overlay/OverlayManager.as'
    run('01-export 导出原生字幕组件', '-export', 'script', work / 'as-original', original_path)
    source = patch_configurable_source(source_path.read_text(encoding='utf-8-sig'), profile, table)
    modified = work / 'as-modified/overlay/OverlayManager.as'
    atomic_write(modified, source.encode('utf-8'))
    output = work / 'Overlay.configurable.gfx'
    output.unlink(missing_ok=True)
    run('02-compile 编译字幕样式', '-importScript', original_path, output, work / 'as-modified')
    run('03-check 校验编译结果', '-export', 'script', work / 'as-check', output)
    checked = (work / 'as-check/scripts/overlay/OverlayManager.as').read_text(encoding='utf-8-sig')
    if 'function MMShowTop' not in checked or 'this.MMShowTop(param1,mmTop)' not in checked:
        raise ValueError('字幕组件编译验证失败。')
    if any(uses_learning_font(code) for code in (profile.top_language, profile.bottom_language)):
        progress('04-font 本地嵌入多语言字体')
        resource_root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else ROOT
        font_root = resource_root / 'fonts'
        helper_root = resource_root / 'runtime'
        ffdec_root = resource_root / 'runtime/ffdec' if getattr(sys, 'frozen', False) else ROOT / '.tools/ffdec'
        chars = ''.join(sorted(set(''.join(lower + upper for lower, upper in table))))
        characters = work / 'font-characters.txt'
        characters.write_text(chars, encoding='utf-8')
        embedded = work / 'Overlay.with-font.gfx'
        classpath = os.pathsep.join([str(helper_root), str(ffdec_root / 'ffdec.jar'), str(ffdec_root / 'lib/*')])
        with (work / '04-font.log').open('w', encoding='utf-8') as log:
            subprocess.run([java_command()[0], '-Djava.awt.headless=true', '-cp', classpath, 'EmbedLearningFont',
                            str(output), str(embedded), str(font_root / 'NotoSansKR.ttf'),
                            str(font_root / 'NotoSans.ttf'), str(font_root / 'NotoSansSC.ttf'), str(characters)],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=240,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        output = embedded
    return output.read_bytes()


def build_bundle(game, profile, output, progress=lambda text: None, overlay_compiler=compile_overlay):
    if game_running():
        raise RuntimeError('请先退出游戏，再生成或应用补丁。')
    info = inspect_game(game)
    game = info['game']
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive = GameArchive(game, info['original_toc'])
    progress('00-text 读取语言资源并配对')
    english = Localization(validate_localization(archive.extract(LOCALIZATION, 0), 'en'))
    base = Localization(validate_localization(archive.extract(LOCALIZATION, 176), 'zh-CN'))
    tables = {'en': english.values, 'zh-CN': base.values}
    for language in (profile.top_language, profile.bottom_language):
        if language is not None and language not in tables:
            tables[language] = Localization(validate_localization(archive.extract(LOCALIZATION, LANGUAGES[language].span), language)).values
    changes = {}
    table = []
    coverage = {'total_dialogue_entries': 0, 'bottom_fallback_keys': [], 'top_missing_keys': [],
                'top_language': profile.top_language, 'bottom_language': profile.bottom_language,
                'alignment': 'English timing; sequence when counts match, normalized overlapping context otherwise',
                'runtime_verified': False}
    for key, text in english.values.items():
        bottom = tables[profile.bottom_language].get(key, '') if profile.bottom_language else None
        top = tables[profile.top_language].get(key, '') if profile.top_language else None
        paired, record = pair_layers(text, bottom, top)
        if paired is None:
            continue
        if key not in base.values:
            raise ValueError('简体中文索引缺少台词标识：' + key)
        changes[key] = encode_wire(text, paired, table)
        coverage['total_dialogue_entries'] += 1
        if record['bottom_fallback']:
            coverage['bottom_fallback_keys'].append(key)
        if record['top_missing']:
            coverage['top_missing_keys'].append(key)
    overlay = overlay_compiler(archive.extract(OVERLAY), profile, output / 'compiler', progress, table)
    loc = base.replace(changes)
    rebuilt = Localization(loc)
    if any(rebuilt.values[k] != v for k, v in base.values.items() if k not in changes):
        raise ValueError('非对话文本发生非预期变更。')
    payload, overrides = bytearray(), []
    for path, span, data in ((OVERLAY, 0, overlay), (LOCALIZATION, 176, loc)):
        payload.extend(b'\0' * (-len(payload) % 16))
        overrides.append((archive.find(path, span), len(payload), len(data)))
        payload.extend(data)
    toc = archive.redirect('bilingual_subtitles', overrides)
    manifest = {'format': 1, 'mode': 'configurable', 'game_version': info['version'],
                'archive': 'bilingual_subtitles', 'original_toc_sha256': sha256(archive.toc),
                'patched_toc_sha256': sha256(toc), 'archive_sha256': sha256(payload),
                'original_overlay_sha256': ORIGINAL_OVERLAY_SHA, 'patched_overlay_sha256': sha256(overlay),
                'dialogue_entries': len(changes), 'runtime_verified': False, 'profile': profile.to_dict()}
    progress('05-write 写入并校验本地补丁')
    for name, data in (('toc.patched', toc), ('bilingual_subtitles', payload)):
        atomic_write(output / name, data)
    for name, data in (('manifest.json', manifest), ('coverage.json', coverage), ('subtitle-table.json', table)):
        atomic_write(output / name, json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))
    profile.save(output / 'profile.json')
    return manifest


def apply_profile(game, profile, progress=lambda text: None):
    with game_lock(game):
        return _apply_profile(game, profile, progress)


def _apply_profile(game, profile, progress):
    game = Path(game).resolve()
    info = inspect_game(game)
    output = work_directory(game) / 'bundle'
    manifest = build_bundle(game, profile, output, progress)
    # Reinspect after compilation: another process/mod might have changed state.
    info = inspect_game(game)
    progress('06-install 安装并校验补丁')
    install_bundle(game, output, info['state'])
    profile.save(info['state'] / 'profile.json')
    return manifest


def restore_game(game):
    with game_lock(game):
        return _restore_game(game)


def _restore_game(game):
    game = Path(game).resolve()
    info = inspect_game(game)
    if info['status'] in ('installed', 'restored'):
        restore(game, info['state'])


def audit_languages(game, output):
    info = inspect_game(game)
    archive = GameArchive(info['game'], info['original_toc'])
    en = Localization(validate_localization(archive.extract(LOCALIZATION, 0), 'en')).values
    timed = {k: v for k, v in en.items() if parse_segments(v)[1]}
    report = {'game_version': info['version'], 'dialogue_entries': len(timed), 'languages': {}}
    for code, language in LANGUAGES.items():
        values = Localization(validate_localization(archive.extract(LOCALIZATION, language.span), code)).values
        missing, different, chars = [], 0, set()
        for key, text in timed.items():
            paired, coverage = pair_layers(text, text, values.get(key, ''))
            if coverage['top_missing']:
                missing.append(key)
            if len(parse_segments(values.get(key, ''))[1]) != len(parse_segments(text)[1]):
                different += 1
            if [s.tag for s in parse_segments(paired)[1]] != [s.tag for s in parse_segments(text)[1]]:
                raise ValueError('时间标签变更：' + code + '/' + key)
            chars.update(c for c in values.get(key, '') if ord(c) > 127)
        report['languages'][code] = {'span': language.span, 'strings': len(values),
                                     'missing_or_partial_dialogue_keys': missing,
                                     'different_segment_count_entries': different,
                                     'non_ascii_characters': len(chars),
                                     'text_audit': 'passed', 'runtime_font_and_sync': 'pending'}
    atomic_write(Path(output), json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'build', 'apply', 'restore', 'audit'])
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    profile = Profile.load(args.profile) if args.profile else Profile()
    if args.action == 'inspect':
        print(json.dumps({k: v for k, v in inspect_game(args.game).items() if k != 'original_toc'}, default=str))
    elif args.action == 'restore':
        restore_game(args.game)
    elif args.action == 'audit':
        audit_languages(args.game, args.output or work_directory(args.game) / 'languages-audit.json')
    elif args.action == 'apply':
        apply_profile(args.game, profile, print)
    else:
        build_bundle(args.game, profile, args.output or work_directory(args.game) / 'bundle', print)


if __name__ == '__main__':
    main()
