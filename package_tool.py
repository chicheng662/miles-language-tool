"""Build the distributable using an explicit allowlist: never package game assets."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ('archive.py', 'localization.py', 'dialogue.py', 'configuration.py',
                'patch.py', 'configurable_overlay.py', 'configurator_backend.py', 'configurator_app.py',
                'language_baselines.json')


def main():
    build = ROOT / 'build/portable-build'
    dist = ROOT / 'dist'
    sys.path.insert(0, str(ROOT / '.tools/packaging'))
    import PyInstaller.__main__
    PyInstaller.__main__.run([
        '--noconfirm', '--clean', '--onedir', '--windowed', '--name', 'MilesLanguageTool',
        '--distpath', str(dist), '--workpath', str(build / 'work'), '--specpath', str(build),
        '--paths', str(ROOT), '--add-data', str(ROOT / 'language_baselines.json') + ';.',
        str(ROOT / 'configurator_app.py'),
    ])
    package = dist / 'MilesLanguageTool'
    for document in ('LICENSE', 'NOTICE', 'THIRD-PARTY-NOTICES.md', 'README.md', 'BUILDING.md'):
        shutil.copy2(ROOT / document, package / document)
    shutil.copytree(ROOT / 'licenses', package / 'licenses', dirs_exist_ok=True)
    runtime = package / 'runtime'
    runtime.mkdir(exist_ok=True)
    shutil.copytree(ROOT / '.tools/ffdec', runtime / 'ffdec', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('*.exe', '*.bat', '*.sh', '*.icns', '*.png', '*.ico'))
    shutil.copytree(ROOT / '.tools/jre', runtime / 'jre', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'runtime/EmbedLearningFont.class', runtime / 'EmbedLearningFont.class')
    shutil.copytree(ROOT / 'fonts', package / 'fonts', dirs_exist_ok=True)
    source = package / 'source'
    source.mkdir(exist_ok=True)
    for name in SOURCE_FILES:
        shutil.copy2(ROOT / name, source / name)
    shutil.copy2(ROOT / 'runtime/EmbedLearningFont.java', source / 'EmbedLearningFont.java')
    for source_name, dest_name in (('工具使用说明.md', '使用说明.md'), ('验证报告.md', '验证报告.md')):
        shutil.copy2(ROOT / source_name, package / dest_name)
    from configuration import Profile
    examples = package / 'profiles'
    examples.mkdir(exist_ok=True)
    Profile().save(examples / '英语在下-简中在上.json')
    Profile(top_language='en', bottom_language='zh-CN').save(examples / '简中在下-英语在上.json')
    Profile(top_language='ja', bottom_language='en').save(examples / '英语在下-日语在上.json')
    # Preserve the curated notice and licensing scope copied above.
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        shutil.copy2(python_license, package / 'PYTHON-LICENSE.txt')
    license_root = package / 'licenses'
    license_root.mkdir(exist_ok=True)
    for directory in (Path(sys.base_prefix) / 'tcl/tcl8.6', Path(sys.base_prefix) / 'tcl/tk8.6'):
        if (directory / 'license.terms').is_file():
            shutil.copy2(directory / 'license.terms', license_root / (directory.name + '-license.terms'))
    forbidden = {'.gfx', '.localization', '.swf', '.dsar'}
    for path in package.rglob('*'):
        if path.is_file() and (path.suffix.lower() in forbidden or path.name in ('toc', 'toc.patched', 'bilingual_subtitles')):
            raise ValueError('Distribution contains a game asset: ' + str(path))
    from patch import sha256
    manifest = {p.relative_to(package).as_posix(): sha256(p.read_bytes())
                for p in package.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.json'}
    (package / 'SHA256SUMS.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    archive = dist / 'MilesLanguageTool-v0.1.0-win64.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as stream:
        for path in package.rglob('*'):
            if path.is_file():
                stream.write(path, path.relative_to(dist))
    (dist / (archive.name + '.sha256')).write_text(sha256(archive.read_bytes()) + '  ' + archive.name + '\n')
    print(json.dumps({'package': str(package), 'zip': str(archive), 'bytes': archive.stat().st_size}))


if __name__ == '__main__':
    main()
