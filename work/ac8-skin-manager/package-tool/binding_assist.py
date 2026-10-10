"""Read-only material profiles captured by the in-game manager."""
from pathlib import Path
import json
import re
import time
import uuid
import os
import tempfile

PROFILE_LIMIT = 262144
AIRCRAFT = re.compile(r'PP\d{4}_[a-z0-9]+')
MOD = Path('Game/Binaries/Win64/ue4ss/Mods/AC8SkinManager')


class BindingError(ValueError):
    pass


def validate_profile(value, aircraft=None):
    if not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('kind') != 'ac8-material-bindings':
        raise BindingError('无效的材质绑定记录。 / Invalid material binding profile.')
    plane = value.get('aircraft_id')
    if not isinstance(plane, str) or not AIRCRAFT.fullmatch(plane) or aircraft and plane != aircraft:
        raise BindingError('绑定记录与当前机型不匹配。 / The profile does not match this aircraft.')
    if value.get('game_sha256') != '51510e2a520565dbe81fb0d569e95cd4393077acaaa859371489b80b8128829f':
        raise BindingError('绑定记录的游戏版本不兼容。 / Unsupported game build in binding profile.')
    if value.get('native') is not True:
        raise BindingError('需要原生材质记录，请切到 STD 后重新读取。 / Select STD and capture native materials again.')
    materials = value.get('materials')
    if not isinstance(materials, list) or not 1 <= len(materials) <= 128:
        raise BindingError('绑定记录中没有有效的材质列表。 / No valid material list in profile.')
    seen, total, cleaned = set(), 0, []
    for row in materials:
        if not isinstance(row, dict) or type(row.get('slot')) is not int or not 0 <= row['slot'] <= 127 or row['slot'] in seen:
            raise BindingError('绑定记录的材质槽无效或重复。 / Invalid or duplicate material slot.')
        seen.add(row['slot'])
        if not isinstance(row.get('material'), str) or len(row['material']) > 1024:
            raise BindingError('材质名称无效。 / Invalid material name.')
        parameters = row.get('parameters')
        if not isinstance(parameters, list) or len(parameters) > 64:
            raise BindingError('贴图参数列表无效。 / Invalid texture parameter list.')
        names, params = set(), []
        for item in parameters:
            if not isinstance(item, dict):
                raise BindingError('贴图参数记录无效。 / Invalid texture parameter record.')
            name, texture = item.get('parameter'), item.get('texture')
            if not isinstance(name, str) or not 1 <= len(name) <= 120 or name in names or not isinstance(texture, str) or len(texture) > 1024:
                raise BindingError('贴图参数记录无效。 / Invalid texture parameter record.')
            path = texture.split(' ', 1)[-1]
            if not path.startswith('/Game/') or '/AC8SkinManager/' in path or '..' in path or '\\' in path:
                raise BindingError('需要原生游戏贴图路径。 / A native game texture path is required.')
            names.add(name); params.append({'parameter': name, 'texture': path})
        total += len(params)
        cleaned.append({'slot': row['slot'], 'material': row['material'], 'parameters': params})
    if not 1 <= total <= 2048:
        raise BindingError('未读取到贴图参数，请重新采集。 / No texture parameters were captured. Capture again.')
    return {**value, 'materials': sorted(cleaned, key=lambda row: row['slot'])}


def read_profile(path, aircraft=None):
    with Path(path).open('rb') as stream:
        raw = stream.read(PROFILE_LIMIT + 1)
    if len(raw) > PROFILE_LIMIT:
        raise BindingError('绑定记录过大。 / Binding profile is too large.')
    try:
        return validate_profile(json.loads(raw.decode('utf-8-sig')), aircraft)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise BindingError('无效的材质绑定记录。 / Invalid material binding profile.') from exc


def export_profile(profile, target):
    raw = json.dumps(validate_profile(profile), ensure_ascii=False, indent=2).encode('utf-8')
    if len(raw) > PROFILE_LIMIT:
        raise BindingError('绑定记录过大。 / Binding profile is too large.')
    target = Path(target)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.ac8-binding-', delete=False) as out:
            temporary = Path(out.name)
            out.write(raw); out.flush(); os.fsync(out.fileno())
        if temporary.read_bytes() != raw:
            raise BindingError('保存校验失败，请重试。')
        temporary.replace(target)
        return {'cancelled': False, 'path': str(target)}
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def choices(profile):
    grouped = {}
    for row in profile['materials']:
        for item in row['parameters']:
            key = (item['parameter'], item['texture'])
            group = grouped.setdefault(key, {'parameter': key[0], 'texture': key[1], 'slots': [], 'materials': []})
            group['slots'].append(row['slot']); group['materials'].append(row['material'])
    return sorted(grouped.values(), key=lambda row: (row['slots'][0], row['parameter'], row['texture']))


def suggestions(assets, options):
    result = []
    for row in assets:
        path = row['asset'].split('.')[0]
        exact = [c for c in options if c['texture'].split('.')[0] == path]
        # Matching only a basename can silently confuse liveries or aircraft.
        match = exact[0] if len(exact) == 1 else None
        result.append({'asset': row['asset'], 'slots': match['slots'] if match else [],
                       'parameter': match['parameter'] if match else '', 'matched': bool(match)})
    return result


class BindingStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def file(self, aircraft):
        if not isinstance(aircraft, str) or not AIRCRAFT.fullmatch(aircraft):
            raise BindingError('机型编号无效。 / Invalid aircraft ID.')
        return self.directory / (aircraft + '.json')

    def save(self, profile):
        profile = validate_profile(profile)
        raw = json.dumps(profile, ensure_ascii=False, indent=2).encode('utf-8')
        if len(raw) > PROFILE_LIMIT:
            raise BindingError('绑定记录过大。 / Binding profile is too large.')
        target = self.file(profile['aircraft_id'])
        temporary = target.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_bytes(raw); temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return profile

    def load(self, aircraft, game=None):
        saved = self.file(aircraft)
        if game:
            captured = Path(game) / MOD / 'BindingProfiles' / (aircraft + '.json')
            # An imported record remains selected until a newer game capture
            # arrives; refreshing must not silently replace it with an old file.
            if captured.is_file() and (not saved.is_file() or captured.stat().st_mtime_ns > saved.stat().st_mtime_ns):
                try:
                    return self.save(read_profile(captured, aircraft))
                except (BindingError, ValueError, OSError):
                    if not saved.is_file():
                        raise
        return read_profile(saved, aircraft) if saved.is_file() else None

    def capture(self, game, aircraft, timeout=18):
        self.file(aircraft)
        mod = Path(game) / MOD
        if not (mod / 'Scripts/binding_capture.lua').is_file():
            raise BindingError('请先安装带材质读取功能的新版游戏管理器。 / Install the updated in-game manager with binding capture first.')
        from compatibility import preflight
        preflight(game)
        from packaging_core import game_running
        if not game_running():
            raise BindingError('请离线启动 AC8，在选机页选择对应飞机和 STD 后读取。 / Start AC8 offline, select the matching aircraft and STD, then capture.')
        token = uuid.uuid4().hex
        request, reply = mod / 'binding-request.json', mod / 'binding-response.json'
        # Exclusive creation prevents two tool windows replacing each other's request.
        try:
            with request.open('x', encoding='utf-8') as stream:
                json.dump({'schema_version': 1, 'token': token, 'aircraft_id': aircraft}, stream)
        except FileExistsError as exc:
            raise BindingError('还有材质读取请求，请等待游戏处理；可在游戏按 F7 保存记录后刷新。 / Another capture is pending. Wait, or press F7 in-game and refresh saved records.') from exc
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                if reply.is_file():
                    try:
                        if reply.stat().st_size > PROFILE_LIMIT:
                            raise BindingError('绑定记录过大。 / Binding profile is too large.')
                        result = json.loads(reply.read_text(encoding='utf-8-sig'))
                        if isinstance(result, dict) and result.get('token') == token:
                            if not result.get('ok'):
                                raise BindingError(str(result.get('error', 'Capture failed.')))
                            return self.save(validate_profile(result.get('profile'), aircraft))
                    except (json.JSONDecodeError, UnicodeError, PermissionError):
                        pass  # The game may still be replacing its response.
                time.sleep(.2)
            raise BindingError('读取超时；请确认新版 MOD 已启用并停留在对应选机页，或按 F7 后刷新。 / Capture timed out. Check the updated MOD and aircraft selection page, or press F7 then refresh.')
        finally:
            try:
                if request.is_file() and json.loads(request.read_text(encoding='utf-8-sig')).get('token') == token:
                    request.unlink()
            except (OSError, ValueError):
                pass
