"""Installed livery inventory and reversible, package-owned removal."""
from pathlib import Path
import hashlib
import json
import os
import re
import stat
import time
import uuid
from packaging_core import MOD_REL, LOADER_REL, PackageError, game_running
from validate_skin import validate


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise PackageError('登记文件过大。')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic_bytes(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as out:
            out.write(value); out.flush(); os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))


def guarded(path, root):
    path, root = Path(path).absolute(), Path(root).resolve()
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root):
        raise PackageError('涂装目录被重定向，不能自动管理。')
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink() or (part.exists() and part.stat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise PackageError('涂装目录被重定向，不能自动管理。')
    return path


def identity_parts(identity):
    if not isinstance(identity, str):
        raise PackageError('涂装编号无效。')
    match = re.fullmatch(r'([a-z0-9][a-z0-9_-]{0,63})__(PP\d{4}_[a-z0-9]+)__([a-z0-9][a-z0-9_-]{0,63})', identity)
    if not match:
        raise PackageError('涂装编号无效。')
    return list(match.groups())


class Library:
    def __init__(self, game):
        self.game = Path(game).resolve()
        if not game or not (self.game / 'Game/Binaries/Win64/AceCombat8.exe').is_file():
            raise PackageError('请先选择正确的 AC8 游戏目录。')
        self.mod, self.loader = self.game / MOD_REL, self.game / LOADER_REL
        self.trash = self.mod / 'RemovedPackages'
        guarded(self.mod, self.game); guarded(self.loader, self.game)

    def targets(self, identity):
        provider, plane, local_id = identity_parts(identity)
        short = hashlib.sha256(identity.encode()).hexdigest()[:24]
        return [guarded(self.mod / 'Skins' / provider / plane / local_id, self.game),
                guarded(self.loader / 'payloads' / ('0060_ASM_' + short), self.game),
                guarded(self.mod / 'Native/containers' / ('ASM_' + short + '.bin'), self.game)]

    def _owned(self, identity, targets):
        receipt = read_json(guarded(targets[0] / 'installed-package.json', self.game))
        if not isinstance(receipt, dict) or not isinstance(receipt.get('package'), dict):
            raise PackageError('此涂装缺少有效安装记录，请手动核对。')
        package = receipt.get('package', {})
        if receipt.get('installer') != 'AC8 Skin Pack Tool' or receipt.get('identity') != identity or package.get('identity') != identity or package.get('format') != 'ac8skinpack':
            raise PackageError('此涂装缺少有效安装记录，请手动核对。')
        rows = package.get('files', [])
        if not isinstance(rows, list) or not 4 <= len(rows) <= 8:
            raise PackageError('此涂装缺少有效安装记录，请手动核对。')
        names = set()
        for row in rows:
            name = row.get('path', '') if isinstance(row, dict) else ''
            if name in names or not (name in ('skin.json', 'registration/container.bin', 'preview.png') or re.fullmatch(r'resources/[A-Za-z0-9_-]+\.(pak|utoc|ucas)', name)):
                raise PackageError('此涂装缺少有效安装记录，请手动核对。')
            names.add(name)
        if not {'skin.json', 'registration/container.bin'}.issubset(names):
            raise PackageError('此涂装缺少有效安装记录，请手动核对。')
        allowed = [{'skin.json', 'installed-package.json'} | ({'preview.png'} if 'preview.png' in names else set()),
                   {Path(name).name for name in names if name.startswith('resources/')}]
        size = 0
        for index, folder in enumerate(targets[:2]):
            if folder.exists():
                if not folder.is_dir():
                    raise PackageError('涂装目录结构错误。')
                for file in folder.iterdir():
                    guarded(file, self.game)
                    if not file.is_file() or file.name not in allowed[index]:
                        raise PackageError('涂装目录含有未登记文件，请手动核对。')
                    size += file.stat().st_size
        if targets[2].exists():
            if not targets[2].is_file():
                raise PackageError('涂装目录结构错误。')
            size += targets[2].stat().st_size
        complete = all(t.exists() for t in targets)
        for name in names:
            file = targets[0] / name if name in ('skin.json', 'preview.png') else targets[2] if name == 'registration/container.bin' else targets[1] / Path(name).name
            complete = complete and file.is_file()
        return receipt, size, complete

    def _selections(self):
        path = guarded(self.mod / 'selections.json', self.game)
        if not path.exists():
            path = guarded(self.mod / 'selections.json.bak', self.game)
        if not path.exists():
            return {}
        value = read_json(path)
        if not isinstance(value, dict) or not isinstance(value.get('selections'), dict):
            raise PackageError('涂装选择记录损坏，请先修复 selections.json。')
        return value['selections']

    def installed(self):
        folder = self.mod / 'Skins'
        if not folder.exists():
            return []
        guarded(folder, self.game)
        try:
            selected = self._selections()
        except (OSError, ValueError):
            selected = {}
        result = []
        # Fixed depth, no recursive traversal through junctions or foreign trees.
        for provider in folder.iterdir():
            try:
                guarded(provider, self.game)
                if not provider.is_dir(): continue
                for plane in provider.iterdir():
                    guarded(plane, self.game)
                    if not plane.is_dir(): continue
                    for skin in plane.iterdir():
                        guarded(skin, self.game)
                        if not skin.is_dir(): continue
                        identity = provider.name + '__' + plane.name + '__' + skin.name
                        try:
                            targets = self.targets(identity)
                            if not (skin / 'skin.json').exists() and not (skin / 'installed-package.json').exists(): continue
                            item = {'identity': identity, 'aircraft_id': plane.name, 'name': skin.name, 'author': provider.name,
                                    'button': {}, 'selected': selected.get(plane.name) == identity, 'managed': False,
                                    'complete': False, 'bytes': 0}
                            try:
                                manifest = read_json(guarded(skin / 'skin.json', self.game))
                                if validate(manifest): raise ValueError('invalid manifest')
                                if [manifest['provider_id'], manifest['aircraft_id'], manifest['id']] != identity_parts(identity): raise ValueError('identity mismatch')
                                item.update(name=manifest['name'], author=manifest['author'], button=manifest.get('button', {}))
                            except (OSError, ValueError, TypeError, KeyError):
                                item['damaged'] = True
                            try:
                                _, size, complete = self._owned(identity, targets)
                                item.update(managed=True, bytes=size, complete=complete)
                            except (OSError, ValueError, TypeError, KeyError):
                                pass
                            result.append(item)
                        except (OSError, ValueError):
                            continue
            except (OSError, ValueError):
                continue
        return sorted(result, key=lambda row: (row['aircraft_id'], row['name'].casefold()))

    def removed(self):
        if not self.trash.exists(): return []
        guarded(self.trash, self.game)
        result = []
        for folder in self.trash.iterdir():
            try:
                record = self._record(folder.name)
                if record['state'] not in ('removed', 'removing'): continue
                item = dict(record['item'])
                item.update(removal_id=folder.name, removed_at=record['removed_at'], selected=False,
                            interrupted=record['state'] == 'removing')
                result.append(item)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(result, key=lambda row: row['removed_at'], reverse=True)

    def inventory(self):
        return {'installed': self.installed(), 'removed': self.removed()}

    def folder(self, identity):
        target = self.targets(identity)[0]
        if not target.is_dir(): raise PackageError('涂装已不存在，请刷新列表。')
        return target

    def _record(self, removal_id):
        if not isinstance(removal_id, str) or not re.fullmatch(r'[a-f0-9]{32}', removal_id):
            raise PackageError('恢复记录无效。')
        folder = guarded(self.trash / removal_id, self.game)
        record = read_json(guarded(folder / 'transaction.json', self.game))
        identity_parts(record['identity'])
        if record.get('version') != 1 or record.get('state') not in ('removing', 'removed', 'restoring', 'restored'):
            raise PackageError('恢复记录无效。')
        return record

    def remove(self, identity, *, running=game_running, fault=None):
        if running(): raise PackageError('请完全退出 AC8 后再删除或恢复涂装。')
        targets = self.targets(identity)
        self._owned(identity, targets)
        item = next((row for row in self.installed() if row['identity'] == identity and row['managed']), None)
        if item is None: raise PackageError('此涂装缺少有效安装记录，请手动核对。')
        selections, updated = {}, {}
        for name in ('selections.json', 'selections.json.bak'):
            path = guarded(self.mod / name, self.game)
            if not path.exists(): continue
            selections[name] = path.read_bytes()
            value = read_json(path)
            if not isinstance(value, dict) or not isinstance(value.get('selections'), dict):
                raise PackageError('涂装选择记录损坏，请先修复 selections.json。')
            plane = identity_parts(identity)[1]
            if value['selections'].get(plane) == identity:
                value['selections'][plane] = 'original'; updated[name] = value
        guarded(self.trash, self.game).mkdir(parents=True, exist_ok=True)
        folder = guarded(self.trash / uuid.uuid4().hex, self.game); folder.mkdir()
        record = {'version': 1, 'identity': identity, 'state': 'removing', 'item': item,
                  'removed_at': int(time.time()), 'present': [t.exists() for t in targets]}
        atomic_json(folder / 'transaction.json', record)
        # A copy is for crash recovery only; normal Restore never overwrites
        # choices made after removal or automatically activates the restored pack.
        for name, raw in selections.items(): atomic_bytes(folder / ('before-' + name), raw)
        moved = []
        try:
            for index, target in enumerate(targets):
                if target.exists():
                    os.replace(target, folder / str(index)); moved.append(index)
                if fault: fault(index)
            for name, value in updated.items(): atomic_json(self.mod / name, value)
            if fault: fault(3)
            record['state'] = 'removed'; atomic_json(folder / 'transaction.json', record)
        except Exception:
            for name, raw in selections.items(): atomic_bytes(self.mod / name, raw)
            for index in reversed(moved): os.replace(folder / str(index), targets[index])
            record['state'] = 'restored'; atomic_json(folder / 'transaction.json', record)
            raise
        return {'identity': identity, 'name': item['name'], 'removal_id': folder.name, 'removed': True}

    def restore(self, removal_id, *, running=game_running, fault=None):
        if running(): raise PackageError('请完全退出 AC8 后再删除或恢复涂装。')
        record = self._record(removal_id)
        if record['state'] not in ('removed', 'removing'):
            raise PackageError('此涂装已恢复，请刷新列表。')
        folder = guarded(self.trash / removal_id, self.game)
        targets = self.targets(record['identity'])
        available = [i for i in range(3) if guarded(folder / str(i), self.game).exists()]
        if not available: raise PackageError('恢复文件缺失。')
        if ((record['state'] == 'removed' and any(target.exists() for target in targets))
                or any(targets[i].exists() for i in available)):
            raise PackageError('同编号涂装已存在，不能覆盖恢复。')
        # Validate backed-up paths and file ownership before moving a directory.
        backup_targets = [folder / str(i) for i in range(3)]
        if 0 in available: self._owned(record['identity'], backup_targets)
        moved = []
        old_state = record['state']
        try:
            for i in available:
                targets[i].parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup_targets[i], targets[i]); moved.append(i)
                if fault: fault(i)
            record['state'] = 'restored'; atomic_json(folder / 'transaction.json', record)
        except Exception:
            for i in reversed(moved): os.replace(targets[i], backup_targets[i])
            record['state'] = old_state; atomic_json(folder / 'transaction.json', record)
            raise
        return {'identity': record['identity'], 'name': record['item']['name'], 'restored': True}
