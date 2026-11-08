"""Spider-Man 2 native DOM patch generation, using only the player's resources."""
import json
from pathlib import Path
from spiderman2_archive import GameArchiveI29, BareLocalization
from spiderman2_overlay import patch_overlay_js
from game_registry import SPIDER_MAN_2, detect_game
from dialogue import pair_layers, encode_wire
from patch import sha256, status, checked_backup, game_running, atomic_write

ROOT=Path(__file__).resolve().parent
LOCALIZATION='localization/localization_all.localization'
OVERLAY='ui/loaded/authored/overlay/js/overlay.js'


def baselines():
    return json.loads((ROOT/'spiderman2_baselines.json').read_text(encoding='utf-8'))


def validate_localization(raw,language):
    expected=baselines()['languages'].get(language)
    if not expected or sha256(raw)!=expected:
        raise ValueError('蜘蛛侠 2 语言资源已变更或不兼容：'+language)
    return raw


def inspect_game(game):
    game=Path(game).resolve()
    if detect_game(game)!=SPIDER_MAN_2:
        raise ValueError('请选择蜘蛛侠 2 的游戏目录。')
    state=game/'.miles-language-tool'
    current=(game/'toc').read_bytes()
    state_status=status(game,state)
    if state_status in ('conflict','damaged'):
        raise ValueError('蜘蛛侠 2 资源索引冲突或补丁损坏；不会覆盖未知修改。')
    base=baselines();original=current
    if sha256(current)!=base['toc_sha256']:
        if state_status!='installed':
            raise ValueError('蜘蛛侠 2 仅支持已验证的 2.810.0.0 资源索引。')
        original=checked_backup(state,base['toc_sha256'])
    if sha256(original)!=base['toc_sha256']:
        raise ValueError('蜘蛛侠 2 原始索引不匹配。')
    archive=GameArchiveI29(game,original)
    for path,digest in base['resources'].items():
        if sha256(archive.extract(path))!=digest:
            raise ValueError('蜘蛛侠 2 界面资源已变更：'+path)
    for language in ('en','zh-CN'):
        validate_localization(archive.extract(LOCALIZATION,SPIDER_MAN_2.language_spans[language]),language)
    return {'game':game,'state':state,'status':state_status,'original_toc':original,
            'game_id':SPIDER_MAN_2.id,'game_name':SPIDER_MAN_2.name,
            'version':SPIDER_MAN_2.version,'executable':SPIDER_MAN_2.executable}


def build_bundle(game,profile,output,progress=lambda text:None,sample_keys=None):
    if game_running(game):
        raise RuntimeError('请先退出蜘蛛侠 2，再生成或应用补丁。')
    info=inspect_game(game);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    archive=GameArchiveI29(info['game'],info['original_toc'])
    progress('00-text 读取蜘蛛侠 2 中英文并配对')
    tables={}
    for code in dict.fromkeys(('en','zh-CN',profile.top_language,profile.bottom_language)):
        if code is None:continue
        if code not in SPIDER_MAN_2.language_spans:
            raise ValueError('蜘蛛侠 2 尚未支持所选字幕语言：'+code)
        raw=archive.extract(LOCALIZATION,SPIDER_MAN_2.language_spans[code])
        tables[code]=BareLocalization(validate_localization(raw,code))
    changes={};lines=[]
    selected=set(sample_keys) if sample_keys is not None else None
    coverage={'game_id':SPIDER_MAN_2.id,'top_language':profile.top_language,
              'bottom_language':profile.bottom_language,'total_dialogue_entries':0,
              'top_missing_keys':[],'bottom_fallback_keys':[],
              'alignment':'English millisecond timeline; overlap context pairing',
              'runtime_verified':False,'sample_only':selected is not None}
    for key,text in tables['en'].values.items():
        if selected is not None and key not in selected:continue
        lower=tables[profile.bottom_language].values.get(key,'') if profile.bottom_language else None
        upper=tables[profile.top_language].values.get(key,'') if profile.top_language else None
        paired,record=pair_layers(text,lower,upper)
        if paired is None:continue
        if key not in tables['zh-CN'].values:raise ValueError('简体中文缺少台词标识：'+key)
        changes[key]=encode_wire(text,paired,lines)
        if record['top_missing']:coverage['top_missing_keys'].append(key)
        if record['bottom_fallback']:coverage['bottom_fallback_keys'].append(key)
    if selected is not None and selected!=changes.keys():
        raise ValueError('诊断样本含未知或非对话标识。')
    coverage['total_dialogue_entries']=len(changes)
    progress('01-ui 生成蜘蛛侠 2 原生双层字幕')
    script=patch_overlay_js(archive.extract(OVERLAY).decode('utf-8-sig'),profile,lines).encode('utf-8')
    localization=tables['zh-CN'].replace(changes)
    rebuilt=BareLocalization(localization).values
    if any(rebuilt.get(key)!=value for key,value in tables['zh-CN'].values.items() if key not in changes):
        raise ValueError('非对话文本发生非预期修改。')
    payload=bytearray();overrides=[];headers={}
    for path,span,data in ((OVERLAY,0,script),(LOCALIZATION,168,localization)):
        payload.extend(bytes(-len(payload)%16))
        entry=archive.find(path,span)
        overrides.append((entry,len(payload),len(data)))
        header=archive.replacement_header(entry,len(data))
        if header is not None:headers[entry.index]=header
        payload.extend(data)
    toc=archive.redirect('d/bilingual_subtitles',overrides,headers=headers)
    manifest={'format':1,'game_id':SPIDER_MAN_2.id,'game_name':SPIDER_MAN_2.name,
              'game_version':SPIDER_MAN_2.version,'mode':'configurable-dom',
              'archive':'bilingual_subtitles','original_toc_sha256':sha256(info['original_toc']),
              'patched_toc_sha256':sha256(toc),'archive_sha256':sha256(payload),
              'dialogue_entries':len(changes),'runtime_verified':False,
              'sample_only':selected is not None,'profile':profile.to_dict()}
    progress('02-write 写入并校验本地字幕补丁')
    for name,data in (('toc.patched',toc),('bilingual_subtitles',payload)):
        atomic_write(output/name,data)
    for name,data in (('manifest.json',manifest),('coverage.json',coverage),('subtitle-table.json',lines)):
        atomic_write(output/name,json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8'))
    profile.save(output/'profile.json')
    return manifest
