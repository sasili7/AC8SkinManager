"""Author conversion and transactional player import, with no shared mod edits."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import time
import uuid
import zipfile
from asset_header import Header
from validate_skin import validate
from compatibility import preflight, CompatibilityError

MAX_BYTES = 4 * 1024**3
MOD_REL = Path('Game/Binaries/Win64/ue4ss/Mods/AC8SkinManager')
LOADER_REL = MOD_REL.parent / 'AC8OverrideLoader'
REGISTRAR_REVISION = '20261008-cached-store'
EMPTY_PAK_SHA256 = '75e7144577253917f6da7312ef5e585b12fb728226a22b0938323751a6b555cd'


class PackageError(ValueError):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value:
        raise PackageError('包内存在不安全的文件路径。')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ('', '.', '..') for p in value.rstrip('/').split('/')):
        raise PackageError('包内路径不能越出皮肤目录。')
    for p in path.parts:
        if p.endswith((' ', '.')) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p):
            raise PackageError('包内包含 Windows 不支持的名称。')
    return path


def extract_zip(source, destination):
    destination = Path(destination)
    seen, total = set(), 0
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > 4096:
            raise PackageError('压缩包文件过多。')
        for entry in entries:
            path = safe_relative(entry.filename)
            key = str(path).casefold()
            if key in seen or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise PackageError('不支持重复路径、符号链接或加密 ZIP。')
            seen.add(key)
            total += entry.file_size
            if total > MAX_BYTES:
                raise PackageError('解压后资源总量不能超过 4 GB。')
        for entry in entries:
            target = destination.joinpath(*PurePosixPath(entry.filename).parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
    return destination


def game_running():
    if os.name != 'nt':
        return False
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq AceCombat8.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, text=True, creationflags=0x08000000)
    if result.returncode:
        raise PackageError('无法确认游戏是否已退出，请稍后再试。')
    return 'acecombat8.exe' in result.stdout.lower()


def detect_games():
    roots = [Path('C:/Program Files (x86)/Steam'), Path('C:/Program Files/Steam')]
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Valve\\Steam') as key:
                roots.insert(0, Path(winreg.QueryValueEx(key, 'SteamPath')[0]))
        except OSError:
            pass
    for root in list(roots):
        vdf = root / 'steamapps/libraryfolders.vdf'
        if vdf.is_file():
            roots += [Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(errors='replace'))]
    found = []
    for root in roots:
        manifest = root / 'steamapps/appmanifest_2288340.acf'
        install = 'ACE COMBAT 8'
        if manifest.is_file():
            match = re.search(r'"installdir"\s+"([^"]+)"', manifest.read_text(errors='replace'))
            if match:
                install = match[1]
        game = root / 'steamapps/common' / install
        if (game / 'Game/Binaries/Win64/AceCombat8.exe').is_file() and str(game) not in found:
            found.append(str(game))
    return found


def inspect_header(raw):
    if len(raw) < 56:
        raise PackageError('资源注册索引不完整。')
    magic, version, container, count = struct.unpack_from('<IIQI', raw)
    if magic != 0x496f436e or version != 3 or not container or not 0 < count <= 4096 or len(raw) != 56 + count * 24:
        raise PackageError('需要无依赖的 UE5.4 贴图容器索引。')
    ids = struct.unpack_from('<' + 'Q' * count, raw, 20)
    at = 20 + count * 8
    if len(set(ids)) != count or 0 in ids or struct.unpack_from('<I', raw, at)[0] != count * 16 or any(raw[at + 4:]):
        raise PackageError('容器包含依赖、重定向或无效资源编号，当前管理器不能加载。')
    return container, set(ids)


class Tool:
    def __init__(self, retoc, workspace):
        self.retoc, self.workspace = Path(retoc), Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def run(self, *args, cwd=None):
        if not self.retoc.is_file():
            raise PackageError('工具缺少 retoc.exe，请重新解压完整工具。')
        result = subprocess.run([str(self.retoc), *map(str, args)], cwd=cwd or self.retoc.parent,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=600,
                                creationflags=0x08000000 if os.name == 'nt' else 0)
        if result.returncode:
            details = (result.stdout + '\n' + result.stderr)[-2500:]
            if 'oodle' in details.lower() or 'oo2core' in details.lower():
                raise PackageError('该包使用的 Oodle 压缩编码器不可用。请作者提供无压缩的资源包后再转换。')
            raise PackageError('读取或转换资源失败：\n' + details)
        return result.stdout

    def manifest(self, toc, scratch):
        scratch.mkdir(parents=True, exist_ok=True)
        self.run('manifest', Path(toc).resolve(), cwd=scratch)
        result = json.loads((scratch / 'pakstore.json').read_text(encoding='utf-8'))
        return [entry['packagestoreentry']['packagename'] for entry in result['oplog']['entries']]

    def container_header(self, toc, scratch):
        info = self.run('info', toc)
        match = re.search(r'container_id: FIoContainerId\(([0-9a-fA-F]+)\)', info)
        if not match:
            raise PackageError('无法识别容器编号。')
        chunk = int(match[1], 16).to_bytes(8, 'little').hex() + '00000006'
        path = scratch / 'container.bin'
        self.run('get', toc, chunk, path)
        raw = path.read_bytes()
        inspect_header(raw)
        return path

    def inspect(self, source, job=None):
        job = Path(job or tempfile.mkdtemp(prefix='author-', dir=self.workspace)).resolve()
        source = Path(source).resolve()
        if source.suffix.lower() == '.zip':
            folder = extract_zip(source, job / 'source')
        elif source.is_dir():
            folder = source
        else:
            raise PackageError('请选择 ZIP，或同时拖入配套的 UTOC / UCAS / PAK 文件。')
        tocs = sorted(p for p in folder.rglob('*') if p.suffix.lower() == '.utoc')
        if len(tocs) != 1:
            raise PackageError('一次制作一个皮肤容器。未找到 UTOC，或包中包含多个容器，请拆分后再导入。')
        toc = tocs[0]
        if toc.stem.lower() == 'global' or not toc.with_suffix('.ucas').is_file():
            raise PackageError('缺少同名 UCAS 文件，或导入的是游戏全局容器。')
        assets = self.manifest(toc, job / 'inspect')
        if not assets or len(assets) > 128:
            raise PackageError('皮肤需要包含 1–128 个贴图资源。')
        planes, isolated_sources = set(), set()
        for asset in assets:
            match = re.fullmatch(r'/Game/Vehicles/Aircraft/PP/(PP\d{4}_[a-z0-9]+)/Textures/[^/]+/[^/]+', asset)
            isolated = re.fullmatch(r'/Game/AC8SkinManager/Skins/([a-z0-9_-]+)/(PP\d{4}_[a-z0-9]+)/([a-z0-9_-]+)/[^/]+', asset)
            if not (match or isolated):
                raise PackageError('包含非飞机贴图或未知资源：' + asset + '\n当前版本支持纯贴图包，不会删除其它内容后假装转换成功。')
            planes.add(match[1] if match else isolated[2])
            if isolated:
                isolated_sources.add((isolated[1], isolated[2], isolated[3]))
        if len(planes) != 1:
            raise PackageError('包内包含多个机型，请按机型拆分。')
        if len(isolated_sources) > 1:
            raise PackageError('包内包含多个独立涂装，请拆分后再导入。')
        plane = next(iter(planes))
        manifests = list(folder.rglob('skin.json'))
        existing = None
        if len(manifests) == 1:
            try:
                candidate = json.loads(manifests[0].read_text(encoding='utf-8-sig'))
                if not validate(candidate) and candidate['aircraft_id'] == plane:
                    existing = candidate
            except (ValueError, OSError):
                pass
        suggestions = []
        for asset in assets:
            slots, parameter = [], 'BaseColor'
            if existing:
                matches = [b for b in existing['bindings'] if b['texture'].split('.')[0] == asset]
                slots = [b['material_index'] for b in matches]
                if matches:
                    parameter = matches[0]['parameter']
            elif plane == 'PP0021_su57' and (asset.endswith('/T_PP0021_su57_001_C')
                  or len(assets) == 1 and asset.endswith('/Texture_001') and bool(isolated_sources)):
                slots = [10, 13]
            suggestions.append({'asset': asset, 'slots': slots, 'parameter': parameter})
        source_identity = None
        if len(isolated_sources) == 1:
            provider_id, _, local_id = next(iter(isolated_sources))
            source_identity = {'provider_id': provider_id, 'id': local_id}
        result = {'job': job.name, 'aircraft_id': plane, 'assets': suggestions, 'toc': str(toc),
                  'existing': existing, 'source_identity': source_identity,
                  'profile': 'Su-57 BaseColor' if any(row['slots'] for row in suggestions) and plane == 'PP0021_su57' else None}
        save_json(job / 'inspection.json', result)
        return result

    def convert(self, inspection, metadata, game, progress=lambda text: None):
        job = self.workspace / inspection['job']
        source_toc = Path(inspection['toc'])
        plane, provider, local_id = inspection['aircraft_id'], metadata.get('provider_id'), metadata.get('id')
        root = f'/Game/AC8SkinManager/Skins/{provider}/{plane}/{local_id}/'
        # Validate all user metadata before running resource tools.
        manifest = {**metadata, 'schema_version': 1, 'aircraft_id': plane, 'status': 'draft', 'bindings': []}
        errors = validate(manifest)
        if errors:
            raise PackageError('\n'.join(errors))
        mappings = metadata.get('mappings', [])
        if not isinstance(mappings, list) or not mappings:
            raise PackageError('请至少给一张贴图填写材质槽。未知机型需要作者填写实际绑定。')
        selected = {row['asset'] for row in mappings if row.get('slots')}
        if not selected or not selected.issubset({row['asset'] for row in inspection['assets']}):
            raise PackageError('贴图绑定不属于导入的包，或没有选择任何贴图。')
        progress('正在解包现成涂装…')
        context = job / ('conversion-' + uuid.uuid4().hex[:8])
        inputs, legacy, output = context / 'input', context / 'legacy', context / 'output'
        inputs.mkdir(parents=True); output.mkdir()
        for ext in ('.utoc', '.ucas', '.pak'):
            file = source_toc.with_suffix(ext)
            if file.is_file():
                shutil.copy2(file, inputs / file.name)
        # Global script object metadata stays on this computer; never put it in
        # a distributed skin or tool. It is required for Zen-to-legacy parsing.
        game = Path(game)
        for name in ('global.utoc', 'global.ucas'):
            file = game / 'Game/Content/Paks' / name
            if not file.is_file():
                raise PackageError('作者转换需要本机 AC8。请在右上角填写包含 Game 文件夹的游戏根目录。')
            shutil.copy2(file, inputs / name)
        self.run('to-legacy', inputs, legacy, '--no-shaders', '--no-script-objects', '--version', 'UE5_4')
        relocated, bindings, checks = context / 'relocated', [], []
        for index, old in enumerate(sorted(selected)):
            progress(f'正在转换贴图 {index + 1}/{len(selected)}…')
            candidates = list(legacy.glob('*/Content/' + old.removeprefix('/Game/') + '.uasset'))
            if len(candidates) != 1:
                raise PackageError('未能完整提取贴图：' + old)
            source = candidates[0]
            header = Header(source.read_bytes())
            if header.package != old:
                raise PackageError('资源路径与包内 header 不匹配。')
            new = root + f'Texture_{index + 1:03d}'
            dest = relocated / 'Live/Content' / (new.removeprefix('/Game/') + '.uasset')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(header.relocate(new))
            for ext in ('.uexp', '.ubulk', '.uptnl'):
                file = source.with_suffix(ext)
                if file.is_file():
                    shutil.copy2(file, dest.with_suffix(ext))
                    checks.append((dest.with_suffix(ext), digest(file)))
            for mapping in mappings:
                if mapping.get('asset') == old:
                    for slot in mapping.get('slots', []):
                        bindings.append({'target': 'body', 'material_index': slot,
                                         'parameter': mapping.get('parameter', ''), 'texture': new + '.' + header.export_name})
        manifest.pop('mappings', None)
        manifest.update(status='ready', bindings=bindings)
        errors = validate(manifest)
        if errors:
            raise PackageError('\n'.join(errors))
        identity = provider + '__' + plane + '__' + local_id
        base = 'ASM_' + hashlib.sha256(identity.encode()).hexdigest()[:24] + '_P'
        toc = output / (base + '.utoc')
        progress('正在生成独立资源包…')
        self.run('to-zen', relocated, toc, '--version', 'UE5_4')
        packages = self.manifest(toc, context / 'manifest-output')
        expected = {binding['texture'].split('.')[0] for binding in bindings}
        if set(packages) != expected:
            raise PackageError('打包后资源路径不一致。')
        registration = self.container_header(toc, context)
        progress('正在核对贴图内容与独立资源路径…')
        verify_input = context / 'verify-input'; verify_input.mkdir()
        for file in output.iterdir():
            shutil.copy2(file, verify_input / file.name)
        for name in ('global.utoc', 'global.ucas'):
            shutil.copy2(inputs / name, verify_input / name)
        roundtrip = context / 'roundtrip'
        self.run('to-legacy', verify_input, roundtrip, '--no-shaders', '--no-script-objects', '--version', 'UE5_4')
        for original, sha in checks:
            back = roundtrip / original.relative_to(relocated)
            if not back.is_file() or digest(back) != sha:
                raise PackageError('转换后的贴图数据与原包不同，已停止输出。')
        files = {'skin.json': json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'),
                 'registration/container.bin': registration.read_bytes()}
        for file in output.iterdir():
            if file.suffix in ('.pak', '.utoc', '.ucas'):
                files['resources/' + file.name] = file
        preview = job / 'preview.png'
        if preview.is_file():
            files['preview.png'] = preview
        package = {'format': 'ac8skinpack', 'version': 1, 'identity': identity, 'engine': 'UE5_4',
                   'registrar_revision': REGISTRAR_REVISION, 'manifest': 'skin.json', 'files': []}
        for name, value in files.items():
            sha = digest(value) if isinstance(value, Path) else hashlib.sha256(value).hexdigest()
            size = value.stat().st_size if isinstance(value, Path) else len(value)
            package['files'].append({'path': name, 'sha256': sha, 'bytes': size})
        export = job / (identity + '.ac8skin.zip')
        with zipfile.ZipFile(export, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            archive.writestr('package.json', json.dumps(package, ensure_ascii=False, indent=2))
            for name, value in files.items():
                if isinstance(value, Path):
                    archive.write(value, name)
                else:
                    archive.writestr(name, value)
        progress('完成：原贴图数据保持一致。')
        return {'path': str(export), 'name': export.name, 'manifest': manifest, 'bytes': export.stat().st_size,
                'payload_verified': True, 'sha256': digest(export)}

    def inspect_player(self, source):
        job = Path(tempfile.mkdtemp(prefix='player-', dir=self.workspace)).resolve()
        folder = extract_zip(source, job / 'package')
        try:
            package = json.loads((folder / 'package.json').read_text(encoding='utf-8'))
            manifest = json.loads((folder / 'skin.json').read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as exc:
            raise PackageError('这不是管理器涂装包。普通 MOD 请作者先用“作者打包”页面转换。') from exc
        if package.get('format') != 'ac8skinpack' or package.get('version') != 1 or package.get('engine') != 'UE5_4':
            raise PackageError('不支持此涂装包格式或版本。')
        errors = validate(manifest)
        if errors or manifest.get('status') != 'ready':
            raise PackageError('皮肤登记信息不完整：' + '\n'.join(errors))
        identity = manifest['provider_id'] + '__' + manifest['aircraft_id'] + '__' + manifest['id']
        if package.get('identity') != identity or package.get('registrar_revision') != REGISTRAR_REVISION:
            raise PackageError('皮肤编号或资源注册版本不一致。')
        rows = package.get('files')
        if not isinstance(rows, list) or not 4 <= len(rows) <= 8:
            raise PackageError('文件清单不完整。')
        listed = set()
        for row in rows:
            name = str(safe_relative(row['path']))
            if name in listed:
                raise PackageError('重复文件清单。')
            listed.add(name)
            permitted = name in ('skin.json', 'registration/container.bin', 'preview.png') or re.fullmatch(r'resources/[A-Za-z0-9_-]+\.(pak|utoc|ucas)', name)
            if not permitted:
                raise PackageError('皮肤包中不允许包含脚本、加载器或无关文件。')
            file = folder / name
            if not file.is_file() or file.stat().st_size != row.get('bytes') or digest(file) != row.get('sha256'):
                raise PackageError('文件缺失或校验失败：' + name)
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
        if actual != listed | {'package.json'} or not {'skin.json', 'registration/container.bin'}.issubset(listed):
            raise PackageError('包内包含未登记文件或缺少必要文件。')
        tocs = list((folder / 'resources').glob('*.utoc'))
        if len(tocs) != 1 or not tocs[0].with_suffix('.ucas').is_file():
            raise PackageError('缺少配套资源容器。')
        allowed_resources = {tocs[0].with_suffix(ext).name for ext in ('.pak', '.utoc', '.ucas')}
        if {p.name for p in (folder / 'resources').iterdir()} - allowed_resources:
            raise PackageError('包中包含多余资源容器。')
        pak = tocs[0].with_suffix('.pak')
        if pak.is_file() and digest(pak) != EMPTY_PAK_SHA256:
            raise PackageError('皮肤包的 PAK 包含额外内容，当前格式只允许纯贴图容器。请作者重新转换。')
        packages = self.manifest(tocs[0], job / 'manifest')
        expected = {b['texture'].split('.')[0] for b in manifest['bindings']}
        if set(packages) != expected:
            raise PackageError('包内资源与登记贴图不一致。')
        actual_header = self.container_header(tocs[0], job)
        if actual_header.read_bytes() != (folder / 'registration/container.bin').read_bytes():
            raise PackageError('注册索引与资源容器不一致。')
        result = {'job': job.name, 'manifest': manifest, 'identity': identity, 'package': package,
                  'source': str(folder), 'bytes': sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())}
        save_json(job / 'player.json', result)
        return result

    def install(self, inspected, game, *, running=game_running, fault=None):
        if running():
            raise PackageError('请完全退出 AC8 后再安装；本工具不会自动关闭游戏。')
        game = Path(game).resolve()
        mod, loader = game / MOD_REL, game / LOADER_REL
        if not (mod / 'Scripts/main.lua').is_file() or not (mod / 'Native/registrar.dll').is_file():
            raise PackageError('未找到 AC8SkinManager。请先安装皮肤管理器，再导入涂装包。')
        if not (loader / 'dlls/main.dll').is_file():
            raise PackageError('未找到 AC8OverrideLoader。请先安装管理器要求的通用加载器。')
        try:
            config_path = mod / 'config.json'
            if not config_path.is_file():
                config_path = mod / 'config.defaults.json'
            config = json.loads(config_path.read_text(encoding='utf-8-sig'))
            if not isinstance(config, dict):
                raise PackageError('管理器配置格式错误，请修复 config.json。')
            script = (mod / 'Scripts/adapter.lua').read_text(encoding='utf-8')
            if not config.get('runtime_switch_enabled') or not config.get('package_registration_enabled') or REGISTRAR_REVISION not in script:
                raise PackageError('当前管理器的资源注册接口不兼容，请更新管理器。')
        except (OSError, ValueError, TypeError) as exc:
            if isinstance(exc, PackageError):
                raise
            raise PackageError('管理器安装不完整。') from exc
        try:
            preflight(game)
        except CompatibilityError as exc:
            raise PackageError(str(exc)) from exc
        source, skin = Path(inspected['source']), inspected['manifest']
        for row in inspected['package']['files']:
            file = source / str(safe_relative(row['path']))
            if not file.is_file() or digest(file) != row['sha256']:
                raise PackageError('安装前校验失败，请重新拖入涂装包。')
        identity = inspected['identity']; short = hashlib.sha256(identity.encode()).hexdigest()[:24]
        skin_target = mod / 'Skins' / skin['provider_id'] / skin['aircraft_id'] / skin['id']
        payload_target = loader / 'payloads' / ('0060_ASM_' + short)
        header_target = mod / 'Native/containers' / ('ASM_' + short + '.bin')
        receipt_name = 'installed-package.json'
        targets = [skin_target, payload_target, header_target]
        for target in targets:
            if not target.is_relative_to(game) or target.is_symlink():
                raise PackageError('安装目标路径不安全。')
            # Resolve detects a redirected parent directory/junction too.
            if not target.resolve().is_relative_to(game):
                raise PackageError('安装目录被重定向到游戏目录以外。')
        owner = {}
        if any(t.exists() for t in targets):
            receipt = skin_target / receipt_name
            try:
                owner = json.loads(receipt.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                raise PackageError('同编号皮肤已由其它方式安装；为避免覆盖，请先手动核对旧版本。')
            if owner.get('installer') != 'AC8 Skin Pack Tool' or owner.get('identity') != identity:
                raise PackageError('现有皮肤目录不属于本工具，不能自动覆盖。')
        container, ids = inspect_header((source / 'registration/container.bin').read_bytes())
        for existing in (mod / 'Native/containers').glob('*.bin'):
            if existing == header_target:
                continue
            try:
                other_container, other_ids = inspect_header(existing.read_bytes())
            except PackageError as exc:
                raise PackageError('已安装资源索引损坏，请移除或重新导入对应包：' + existing.name) from exc
            if container == other_container or ids & other_ids:
                raise PackageError('独立资源与已安装涂装冲突：' + existing.name + '。请更改作者/皮肤编号后重新制作。')
        staging = mod / ('pack-install-' + uuid.uuid4().hex)
        staging.mkdir()
        staged_skin, staged_payload, staged_header = staging / 'skin', staging / 'payload', staging / 'header.bin'
        staged_skin.mkdir(); staged_payload.mkdir()
        shutil.copy2(source / 'skin.json', staged_skin / 'skin.json')
        if (source / 'preview.png').is_file():
            shutil.copy2(source / 'preview.png', staged_skin / 'preview.png')
        save_json(staged_skin / receipt_name, {'installer': 'AC8 Skin Pack Tool', 'identity': identity,
                  'installed_at': owner.get('installed_at', int(time.time())) if owner.get('package') == inspected['package'] else int(time.time()),
                  'package': inspected['package']})
        for file in (source / 'resources').iterdir():
            shutil.copy2(file, staged_payload / file.name)
        shutil.copy2(source / 'registration/container.bin', staged_header)
        backup = mod / 'PackageBackups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + short[:8] + '-' + uuid.uuid4().hex[:6])
        backup.mkdir(parents=True)
        moves, installed = [], []
        try:
            for i, (staged, target) in enumerate(zip([staged_skin, staged_payload, staged_header], targets)):
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    previous = backup / str(i)
                    os.replace(target, previous); moves.append((previous, target))
                if fault:
                    fault(i)
                os.replace(staged, target); installed.append((target, staged))
        except Exception:
            for target, staged in reversed(installed):
                os.replace(target, staged)
            for previous, target in reversed(moves):
                os.replace(previous, target)
            shutil.rmtree(staging)
            raise
        shutil.rmtree(staging)
        save_json(backup / 'transaction.json', {'identity': identity, 'previous': [{'backup': str(a), 'target': str(b)} for a, b in moves]})
        return {'installed': True, 'name': skin['name'], 'aircraft_id': skin['aircraft_id'], 'backup': str(backup),
                'message': '已安装。下次离线启动游戏后，在对应机型的 LIVERY 按钮中选择。'}
