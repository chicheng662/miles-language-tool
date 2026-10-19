"""Hash-checked, reversible installation of a locally generated patch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from contextlib import contextmanager


_locks = {}
_lock_guard = threading.Lock()
_held_locks = threading.local()


@contextmanager
def game_lock(game: Path):
    """One transaction per installation, including across GUI/CLI processes."""
    identity = sha256(str(Path(game).resolve()).casefold().encode('utf-8'))
    with _lock_guard:
        lock = _locks.setdefault(identity, threading.RLock())
    if not lock.acquire(blocking=False):
        raise RuntimeError('另一个操作正在处理此游戏，请等待完成。')
    held = getattr(_held_locks, 'identities', set())
    if identity in held:
        try:
            yield
        finally:
            lock.release()
        return
    handle = None
    acquired = False
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
            kernel.CreateMutexW.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            kernel.WaitForSingleObject.restype = wintypes.DWORD
            kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            handle = kernel.CreateMutexW(None, False, 'Local\\MilesLanguageTool-' + identity)
            if not handle:
                raise OSError(ctypes.get_last_error(), '无法创建游戏资源锁。')
            acquired = kernel.WaitForSingleObject(handle, 0) in (0, 0x80)
        else:
            import fcntl
            handle = (Path(tempfile.gettempdir()) / ('miles-language-' + identity + '.lock')).open('a+b')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                pass
        if not acquired:
            raise RuntimeError('另一个工具窗口正在处理此游戏，请等待完成。')
        _held_locks.identities = held | {identity}
        yield
    finally:
        _held_locks.identities = held
        if handle is not None:
            if os.name == 'nt':
                if acquired:
                    kernel.ReleaseMutex(handle)
                kernel.CloseHandle(handle)
            else:
                handle.close()
        lock.release()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def game_running() -> bool:
    if os.name != 'nt':
        return False
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq MilesMorales.exe', '/FO', 'CSV', '/NH'], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return b'milesmorales.exe' in result.stdout.lower()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            name = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if name is not None:
            name.unlink(missing_ok=True)


def read_state(state: Path, game: Path) -> dict:
    data = json.loads((state / 'state.json').read_text(encoding='utf-8'))
    if data['game'] != str(game.resolve()) or data['archive'] != 'bilingual_subtitles':
        raise ValueError('Backup belongs to another game folder')
    return data


def checked_backup(state: Path, expected: str) -> bytes:
    path = state / 'toc.original'
    if not path.is_file() or sha256(path.read_bytes()) != expected:
        raise ValueError('Original TOC backup is missing or corrupt; refusing to overwrite game files')
    return path.read_bytes()


def status(game: Path, state: Path) -> str:
    if not (state / 'state.json').is_file():
        return 'not-installed'
    data = read_state(state, game)
    checked_backup(state, data['original_toc_sha256'])
    current = sha256((game / 'asset_archive/toc').read_bytes())
    if current == data['original_toc_sha256']:
        return 'restored'
    if current != data['patched_toc_sha256']:
        return 'conflict'
    archive = game / 'asset_archive' / data['archive']
    if not archive.is_file() or sha256(archive.read_bytes()) != data['archive_sha256']:
        return 'damaged'
    return 'installed'


def install_bundle(game: Path, bundle: Path, state: Path) -> None:
    with game_lock(game):
        _install_bundle(game, bundle, state)


def _install_bundle(game: Path, bundle: Path, state: Path) -> None:
    if game_running():
        raise RuntimeError('Close MilesMorales.exe before installing or restoring the patch')
    game, bundle, state = Path(game).resolve(), Path(bundle).resolve(), Path(state).resolve()
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or manifest.get('archive') != 'bilingual_subtitles':
        raise ValueError('Unsupported patch manifest')
    patched = (bundle / 'toc.patched').read_bytes()
    payload = (bundle / 'bilingual_subtitles').read_bytes()
    if sha256(patched) != manifest['patched_toc_sha256'] or sha256(payload) != manifest['archive_sha256']:
        raise ValueError('Patch payload checksum mismatch')
    assets = game / 'asset_archive'
    current = (assets / 'toc').read_bytes()
    archive = assets / manifest['archive']
    if (state / 'state.json').exists():
        old = read_state(state, game)
        checked_backup(state, old['original_toc_sha256'])
        if (sha256(current) == manifest['patched_toc_sha256']
                and old['archive_sha256'] == manifest['archive_sha256'] and status(game, state) == 'installed'):
            return
        if sha256(current) == old['patched_toc_sha256'] and old['original_toc_sha256'] == manifest['original_toc_sha256'] and status(game, state) == 'installed':
            # Upgrade only a verified installation made by this installer.
            # First return to the backed-up original; if new installation
            # fails, the game remains at a recoverable original baseline.
            restore(game, state)
            current = (assets / 'toc').read_bytes()
        if sha256(current) != old['original_toc_sha256']:
            raise ValueError('Game TOC changed since installation; restore or resolve the conflict first')
    if sha256(current) != manifest['original_toc_sha256']:
        raise ValueError('Game TOC does not match this patch build; refusing to overwrite other modifications')
    if archive.exists():
        raise ValueError('Replacement archive already exists; refusing to overwrite it')
    original = state / 'toc.original'
    if original.exists():
        checked_backup(state, manifest['original_toc_sha256'])
    else:
        atomic_write(original, current)
    checked_backup(state, manifest['original_toc_sha256'])
    record = dict(manifest, game=str(game))
    atomic_write(state / 'state.json', json.dumps(record, indent=2).encode('utf-8'))
    try:
        atomic_write(archive, payload)
        if sha256(archive.read_bytes()) != manifest['archive_sha256']:
            raise ValueError('Installed archive failed verification')
        atomic_write(assets / 'toc', patched)
    except BaseException:
        if sha256((assets / 'toc').read_bytes()) == manifest['original_toc_sha256'] and archive.exists() and sha256(archive.read_bytes()) == manifest['archive_sha256']:
            archive.unlink()
        raise
    if status(game, state) != 'installed':
        raise ValueError('Post-install verification failed')


def restore(game: Path, state: Path) -> None:
    with game_lock(game):
        _restore(game, state)


def _restore(game: Path, state: Path) -> None:
    if game_running():
        raise RuntimeError('Close MilesMorales.exe before installing or restoring the patch')
    game, state = Path(game).resolve(), Path(state).resolve()
    data = read_state(state, game)
    original = checked_backup(state, data['original_toc_sha256'])
    assets = game / 'asset_archive'
    current = sha256((assets / 'toc').read_bytes())
    if current not in (data['original_toc_sha256'], data['patched_toc_sha256']):
        raise ValueError('Game TOC contains unrelated later changes; automatic restore would overwrite them')
    archive = assets / data['archive']
    if archive.exists() and sha256(archive.read_bytes()) != data['archive_sha256']:
        raise ValueError('Replacement archive changed; refusing to delete an unknown file')
    atomic_write(assets / 'toc', original)
    if archive.exists():
        archive.unlink()
    if sha256((assets / 'toc').read_bytes()) != data['original_toc_sha256']:
        raise ValueError('TOC restore verification failed')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'restore', 'status'])
    parser.add_argument('--game', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent / 'build/full')
    parser.add_argument('--state', type=Path, default=Path(__file__).resolve().parent / 'backups/install')
    args = parser.parse_args()
    if args.action == 'install':
        install_bundle(args.game, args.bundle, args.state)
    elif args.action == 'restore':
        restore(args.game, args.state)
    current_status = status(args.game, args.state)
    print(current_status)
    if current_status == 'installed':
        record = read_state(args.state, args.game)
        print('Mode:', record.get('mode'), '| Dialogue entries:', record.get('dialogue_entries', 'unknown'))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print('ERROR:', exc)
        raise SystemExit(1)
