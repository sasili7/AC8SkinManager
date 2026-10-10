"""Shared installation/import preflight; never calls into an unverified engine."""
from pathlib import Path
import hashlib
import json
import os
import re
import struct
import tempfile


class CompatibilityError(ValueError):
    pass


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def inspect_pe(path):
    try:
        with Path(path).open('rb') as source:
            if source.read(2) != b'MZ':
                raise ValueError('DOS header')
            source.seek(0x3c)
            offset = struct.unpack('<I', source.read(4))[0]
            if not 64 <= offset <= 1048576:
                raise ValueError('PE offset')
            source.seek(offset)
            header = source.read(88)
            if header[:4] != b'PE\0\0' or struct.unpack_from('<H', header, 4)[0] != 0x8664:
                raise ValueError('Windows x64 required')
            return {'timestamp': struct.unpack_from('<I', header, 8)[0],
                    'image_size': struct.unpack_from('<I', header, 80)[0]}
    except (OSError, ValueError, struct.error) as exc:
        raise CompatibilityError('无效的 Windows x64 文件 / Invalid Windows x64 binary: ' + str(path)) from exc


def check_game(game, expected):
    game = Path(game).resolve()
    exe = game / 'Game/Binaries/Win64/AceCombat8.exe'
    inspect_pe(exe)
    if digest(exe) != expected['engine_sha256'].lower():
        raise CompatibilityError('游戏版本不兼容，请使用针对当前游戏版本的管理器 / Unsupported game build.')
    return game


def enabled(mods, name):
    explicit = []
    txt = mods / 'mods.txt'
    if txt.is_file():
        for line in txt.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\s*' + re.escape(name) + r'\s*:\s*([01])\s*(?:;.*)?$', line, re.I)
            if match:
                explicit.append(match[1] == '1')
    config = mods / 'mods.json'
    if config.is_file():
        try:
            rows = json.loads(config.read_text(encoding='utf-8-sig'))
            if not isinstance(rows, list):
                raise ValueError('expected mod list')
            for row in rows:
                if isinstance(row, dict) and str(row.get('mod_name', '')).lower() == name.lower():
                    explicit.append(row.get('mod_enabled') is True)
        except (ValueError, OSError) as exc:
            raise CompatibilityError('mods.json 无效，请先修复 UE4SS 配置 / Invalid mods.json.') from exc
    return bool(explicit and all(explicit)) or not explicit and (mods / name / 'enabled.txt').is_file()


def preflight(game):
    game = Path(game).resolve()
    if not str(game).isascii():
        raise CompatibilityError('此脚本运行时请使用纯 ASCII 游戏目录 / This Lua runtime requires an ASCII game path.')
    mods = game / 'Game/Binaries/Win64/ue4ss/Mods'
    mod, loader = mods / 'AC8SkinManager', mods / 'AC8OverrideLoader'
    try:
        build = json.loads((mod / 'Native/build-checks.json').read_text(encoding='utf-8'))
        check_game(game, build)
        if digest(mod / 'Native/registrar.dll') != build['dll_sha256'].lower():
            raise CompatibilityError('资源登记组件校验失败 / Registrar checksum mismatch.')
        runtime = mods.parent / 'UE4SS.dll'
        inspect_pe(runtime)
        if os.name == 'nt':
            search = [game / 'Game/Binaries/Win64', mods.parent, Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32']
            for dll in ('MSVCP140.dll', 'MSVCP140_ATOMIC_WAIT.dll', 'MSVCP140_CODECVT_IDS.dll', 'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll'):
                located = next((folder / dll for folder in search if (folder / dll).is_file()), None)
                if located is None:
                    raise CompatibilityError('缺少 Visual C++ x64 运行库 / Missing Visual C++ x64 runtime: ' + dll)
                inspect_pe(located)
        expected = json.loads((mod / 'compatibility.json').read_text(encoding='utf-8'))
        if digest(loader / 'dlls/main.dll') != expected['override_loader_sha256'].lower():
            raise CompatibilityError('通用加载器版本不兼容 / Unsupported override loader.')
        if digest(runtime) not in expected['ue4ss_sha256']:
            raise CompatibilityError('UE4SS 版本与此包不匹配 / Unsupported UE4SS build.')
        for name in ('AC8SkinManager', 'AC8OverrideLoader'):
            if not enabled(mods, name):
                raise CompatibilityError(name + ' 尚未启用 / is not enabled.')
        if enabled(mods, 'IoStoreLoaderMod'):
            raise CompatibilityError('请先停用旧 IoStoreLoaderMod / Disable the legacy IoStoreLoaderMod first.')
        if len(str(mod)) > 180:
            raise CompatibilityError('游戏目录过长，请缩短安装路径 / Game path is too long.')
        for path in (mod, loader):
            with tempfile.TemporaryFile(dir=path) as stream:
                stream.write(b'AC8SkinManager preflight')
    except CompatibilityError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CompatibilityError('加载环境不完整或目录不可写 / Incomplete installation or directory is not writable: ' + str(exc)) from exc
    return expected
