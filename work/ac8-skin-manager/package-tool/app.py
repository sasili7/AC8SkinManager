"""AC8 Skin Pack Tool: import, installed livery library and author packaging."""
from pathlib import Path
import argparse
import concurrent.futures
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from packaging_core import Tool, PackageError, MAX_BYTES, detect_games, save_json, game_running
from library import Library
from i18n import localized, messages
from exports import completed_package, export_with_dialog
from runtime_support import desktop_geometry, downloads_folder
from binding_assist import BindingStore, validate_profile, choices


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--browser', action='store_true', help='Use the default browser instead of the desktop window.')
    parser.add_argument('--data', type=Path)
    args = parser.parse_args()
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    data = args.data or Path(os.getenv('LOCALAPPDATA', Path.home())) / 'AC8SkinPackTool'
    data.mkdir(parents=True, exist_ok=True)
    retoc = base / 'Tools/retoc.exe'
    # The source checkout uses the already acquired retoc; the portable build
    # bundles only retoc.exe and its MIT license, never proprietary codec DLLs.
    if not retoc.is_file() and not getattr(sys, 'frozen', False):
        retoc = base.parent.parent / 'ac8-kamome/tools/retoc/retoc.exe'
    tool = Tool(retoc.resolve(), data / 'jobs')
    bindings = BindingStore(data / 'BindingProfiles')
    settings = data / 'settings.json'
    try:
        game = json.loads(settings.read_text(encoding='utf-8')).get('game', '')
    except (OSError, ValueError, AttributeError, TypeError):
        game = ''
    if not isinstance(game, str) or not (Path(game) / 'Game/Binaries/Win64/AceCombat8.exe').is_file():
        game = ''
    detected = detect_games()
    state = {'game': game or (detected[0] if detected else '')}
    jobs, pool, token = {}, concurrent.futures.ThreadPoolExecutor(max_workers=1), secrets.token_urlsafe(32)
    desktop_window = {'value': None}
    operation_lock = threading.RLock()

    def work(job, function):
        job.update(state='working', message='正在处理…', error=None)
        try:
            with operation_lock:
                job['result'] = function(lambda message: job.update(message=message))
            job.update(state='done', message='处理完成')
        except Exception as exc:
            job.update(state='error', error=str(exc), message='处理未完成')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def auth(self):
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                return False
            origin = self.headers.get('Origin')
            if origin and origin != f'http://127.0.0.1:{self.server.server_port}':
                return False
            value = self.headers.get('X-AC8-Token', '')
            if self.path.startswith(('/download/', '/download-binding/')):
                value = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('token', [''])[0]
            return hmac.compare_digest(value, token)

        def respond(self, payload, status=200):
            language = 'en' if self.headers.get('X-AC8-Language') == 'en' else 'zh'
            def translate(value):
                if isinstance(value, list): return [translate(v) for v in value]
                if not isinstance(value, dict): return value
                result = {k: translate(v) for k, v in value.items()}
                for key in ('error', 'message'):
                    if isinstance(value.get(key), str):
                        result[key + '_i18n'] = messages(value[key])
                        result[key] = localized(value[key], language)
                return result
            payload = translate(payload)
            raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers(); self.wfile.write(raw)

        def body(self):
            length = int(self.headers.get('Content-Length', 0))
            if not 0 <= length <= 262144:
                raise PackageError('请求内容过大。')
            return json.loads(self.rfile.read(length) or b'{}')

        def job(self, key):
            if key not in jobs:
                raise PackageError('导入记录已过期，请重新拖入文件。')
            return jobs[key]

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == '/' and self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}':
                raw = (base / 'index.html').read_text(encoding='utf-8').replace('__TOKEN__', token).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
                self.end_headers(); self.wfile.write(raw); return
            if path in ('/assets/mascot.png', '/app.js') and self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}':
                raw = (base / path.lstrip('/')).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'image/png' if path.endswith('.png') else 'text/javascript; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'public, max-age=3600' if path.endswith('.png') else 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers(); self.wfile.write(raw); return
            if not self.auth():
                self.respond({'error': '无效的本机工具会话。'}, 403); return
            try:
                if path == '/api/state':
                    self.respond({**state, 'detected': detected, 'version': '0.8.1-binding-assist', 'platform': 'Windows',
                                  'desktop': not args.no_browser and not args.browser}); return
                if path.startswith('/api/bindings/'):
                    plane = path.rsplit('/', 1)[-1]
                    profile = bindings.load(plane, state['game'])
                    self.respond({'profile': profile, 'choices': choices(profile) if profile else []}); return
                if path.startswith('/download-binding/'):
                    plane = path.rsplit('/', 1)[-1]
                    profile = bindings.load(plane)
                    if profile is None:
                        raise ValueError('没有已保存的绑定记录。 / No saved binding profile.')
                    raw = json.dumps(profile, ensure_ascii=False, indent=2).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Content-Length', str(len(raw)))
                    self.send_header('Content-Disposition', 'attachment; filename="' + plane + '.bindings.json"')
                    self.end_headers(); self.wfile.write(raw); return
                if path == '/api/library':
                    if not operation_lock.acquire(blocking=False):
                        raise PackageError('另一个操作正在进行，请稍后再试。')
                    try:
                        inventory = Library(state['game']).inventory()
                        inventory['game_running'] = game_running()
                        inventory['game'] = state['game']
                    finally:
                        operation_lock.release()
                    self.respond(inventory); return
                if path.startswith('/api/job/'):
                    job = self.job(path.rsplit('/', 1)[-1])
                    self.respond({k: v for k, v in job.items() if k not in ('folder', 'inspection')}); return
                if path.startswith('/download/'):
                    file = completed_package(jobs, path.rsplit('/', 1)[-1], tool.workspace)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/zip')
                    self.send_header('Content-Length', str(file.stat().st_size))
                    self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + urllib.parse.quote(file.name))
                    self.end_headers()
                    with file.open('rb') as src:
                        shutil.copyfileobj(src, self.wfile)
                    return
                self.respond({'error': '页面不存在。'}, 404)
            except Exception as exc:
                self.respond({'error': str(exc)}, 400)

        def do_POST(self):
            if not self.auth():
                self.respond({'error': '无效的本机工具会话。'}, 403); return
            path = urllib.parse.urlsplit(self.path).path
            try:
                if path == '/api/bindings/import':
                    request = self.body()
                    bindings.file(request.get('aircraft_id'))
                    profile = bindings.save(validate_profile(request.get('profile'), request.get('aircraft_id')))
                    self.respond({'profile': profile, 'choices': choices(profile)}); return
                if path == '/api/bindings/capture':
                    request = self.body(); plane = request.get('aircraft_id')
                    bindings.file(plane)
                    key = secrets.token_hex(12); game_snapshot = state['game']
                    job = {'id': key, 'kind': 'bindings', 'state': 'queued', 'message': 'Reading selected aircraft / 正在读取选中机体'}
                    jobs[key] = job
                    def capture(progress):
                        profile = bindings.capture(game_snapshot, plane)
                        return {'profile': profile, 'choices': choices(profile)}
                    pool.submit(work, job, capture)
                    self.respond({'id': key}); return
                if path == '/api/settings':
                    value = self.body().get('game', '').strip().strip('"')
                    if value and not (Path(value) / 'Game/Binaries/Win64/AceCombat8.exe').is_file():
                        raise PackageError('目录不正确：请选择含有 Game 文件夹的 AC8 游戏根目录。')
                    state['game'] = value; save_json(settings, state)
                    self.respond(state); return
                if path == '/api/new':
                    kind = self.body().get('kind')
                    if kind not in ('author', 'player'):
                        raise PackageError('未知操作。')
                    key = secrets.token_hex(12)
                    folder = tool.workspace / key / 'uploads'; folder.mkdir(parents=True)
                    jobs[key] = {'id': key, 'kind': kind, 'folder': str(folder), 'state': 'uploading', 'message': '正在接收文件'}
                    self.respond({'id': key}); return
                if path.startswith('/api/upload/'):
                    key = path.rsplit('/', 1)[-1]; job = self.job(key)
                    if job['state'] != 'uploading':
                        raise PackageError('当前任务不能继续接收文件。')
                    name = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('name', [''])[0]
                    if not re.fullmatch(r'[^<>:"/\\|?*\x00-\x1f]+', name) or name.endswith((' ', '.')):
                        raise PackageError('文件名称不正确。')
                    ext = Path(name).suffix.lower()
                    if ext not in ('.zip', '.utoc', '.ucas', '.pak'):
                        raise PackageError('请选择 ZIP 或 UTOC / UCAS / PAK 文件。')
                    length = int(self.headers.get('Content-Length', 0))
                    folder = Path(job['folder'])
                    if length <= 0 or length + sum(p.stat().st_size for p in folder.iterdir()) > MAX_BYTES:
                        raise PackageError('文件总量不能超过 4 GB。')
                    target = folder / name
                    if any(p.name.casefold() == name.casefold() for p in folder.iterdir()):
                        raise PackageError('文件名重复，请重新选择。')
                    with target.open('xb') as file:
                        remaining = length
                        while remaining:
                            block = self.rfile.read(min(1024 * 1024, remaining))
                            if not block:
                                raise PackageError('上传中断，请重试。')
                            file.write(block); remaining -= len(block)
                    self.respond({'received': length}); return
                if path == '/api/inspect':
                    job = self.job(self.body()['id'])
                    if job['state'] != 'uploading':
                        raise PackageError('任务已经开始。')
                    files = list(Path(job['folder']).iterdir())
                    archives = [p for p in files if p.suffix.lower() == '.zip']
                    if not files or (archives and (len(archives) != 1 or len(files) != 1)):
                        raise PackageError('请选择一个 ZIP，或一组配套资源文件；不能混合导入。')
                    source = archives[0] if len(archives) == 1 else Path(job['folder'])
                    if job['kind'] == 'player' and (len(files) != 1 or len(archives) != 1):
                        raise PackageError('玩家导入请选择一个 .ac8skin.zip 涂装包。')
                    game_snapshot = state['game']
                    def inspect(progress):
                        progress('正在识别机型并校验资源…')
                        if job['kind'] == 'author':
                            result = tool.inspect(source, tool.workspace / job['id'])
                        else:
                            result = tool.inspect_player(source)
                        job['inspection'] = result
                        if job['kind'] == 'player':
                            progress('正在安装到对应机型…')
                            return tool.install(result, game_snapshot)
                        return result
                    job['state'] = 'queued'; pool.submit(work, job, inspect)
                    self.respond({'id': job['id']}); return
                if path == '/api/build':
                    request = self.body(); job = self.job(request['id'])
                    if job['kind'] != 'author' or 'inspection' not in job or job['state'] not in ('done', 'error'):
                        raise PackageError('请先导入并识别现成涂装包。')
                    metadata = request['metadata']
                    metadata['provider_id'] = metadata.get('provider_id') or 'a_' + __import__('hashlib').sha256(metadata.get('author', '').encode()).hexdigest()[:12]
                    metadata['id'] = metadata.get('id') or 's_' + __import__('hashlib').sha256(metadata.get('name', '').encode()).hexdigest()[:12]
                    if not metadata.get('author', '').strip():
                        raise PackageError('请填写作者名称。')
                    job['state'] = 'queued'
                    game_snapshot = state['game']
                    pool.submit(work, job, lambda progress: tool.convert(job['inspection'], metadata, game_snapshot, progress))
                    self.respond({'id': job['id']}); return
                if path in ('/api/library/remove', '/api/library/restore'):
                    request = self.body(); game_snapshot = state['game']
                    library = Library(game_snapshot)
                    if path.endswith('/remove'):
                        identity = request.get('identity')
                        library.targets(identity)  # validate before queuing
                        action = lambda progress: library.remove(identity)
                        message = '正在移除涂装…'
                    else:
                        removal_id = request.get('removal_id')
                        library._record(removal_id)
                        action = lambda progress: library.restore(removal_id)
                        message = '正在恢复涂装…'
                    key = secrets.token_hex(12)
                    job = {'id': key, 'kind': 'library', 'state': 'queued', 'message': message}
                    jobs[key] = job
                    pool.submit(work, job, action)
                    self.respond({'id': key}); return
                if path == '/api/quit':
                    self.respond({'closed': True})
                    def close_tool():
                        window = desktop_window['value']
                        if window is not None:
                            try:
                                window.destroy()
                            except Exception:
                                pass
                        self.server.shutdown()
                    threading.Thread(target=close_tool, daemon=True).start(); return
                self.respond({'error': '接口不存在。'}, 404)
            except Exception as exc:
                self.respond({'error': str(exc)}, 400)

    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError:
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    save_json(data / 'running.json', {'url': url, 'pid': os.getpid()})
    server_thread = None
    try:
        if args.no_browser:
            server.serve_forever()
        elif args.browser:
            webbrowser.open(url)
            server.serve_forever()
        else:
            try:
                import webview
            except ImportError as exc:
                raise RuntimeError('桌面界面组件缺失，请重新解压完整工具。') from exc
            class DesktopApi:
                def save_binding_profile(self, plane):
                    try:
                        if not operation_lock.acquire(blocking=False):
                            raise PackageError('另一个操作正在进行，请稍后再试。')
                        try:
                            if bindings.load(plane) is None:
                                raise ValueError('没有已保存的绑定记录。 / No saved binding profile.')
                            chosen = desktop_window['value'].create_file_dialog(
                                webview.SAVE_DIALOG, directory=downloads_folder(),
                                save_filename=plane + '.bindings.json',
                                file_types=('Binding Profile (*.json)',))
                            if not chosen:
                                return {'cancelled': True}
                            target = Path(chosen if isinstance(chosen, str) else chosen[0])
                            if target.suffix.lower() != '.json':
                                target = target.with_name(target.name + '.json')
                            from binding_assist import export_profile
                            return export_profile(bindings.load(plane), target)
                        finally:
                            operation_lock.release()
                    except Exception as exc:
                        return {'error': str(exc), 'error_i18n': messages(str(exc))}

                def save_author_package(self, key):
                    try:
                        if not operation_lock.acquire(blocking=False):
                            raise PackageError('另一个操作正在进行，请稍后再试。')
                        try:
                            return export_with_dialog(jobs, key, tool.workspace,
                                                      desktop_window['value'], webview.SAVE_DIALOG,
                                                      downloads_folder())
                        finally:
                            operation_lock.release()
                    except Exception as exc:
                        return {'error': str(exc), 'error_i18n': messages(str(exc))}

                def open_skin_folder(self, identity):
                    try:
                        folder = Library(state['game']).folder(identity)
                        os.startfile(str(folder))
                        return {'opened': True}
                    except Exception as exc:
                        return {'error': str(exc), 'error_i18n': messages(str(exc))}

                def choose_game_folder(self):
                    window = desktop_window['value']
                    if window is None:
                        message = '桌面窗口尚未准备完成。'
                        return {'error': message, 'error_i18n': messages(message)}
                    chosen = window.create_file_dialog(
                        webview.FOLDER_DIALOG,
                        directory=state['game'] if Path(state['game']).is_dir() else '',
                    )
                    if not chosen:
                        return {'cancelled': True, **state}
                    value = str(Path(chosen[0]).resolve())
                    if not (Path(value) / 'Game/Binaries/Win64/AceCombat8.exe').is_file():
                        message = '目录不正确：请选择含有 Game 文件夹的 AC8 游戏根目录。'
                        return {'error': message, 'error_i18n': messages(message)}
                    state['game'] = value
                    save_json(settings, state)
                    return {'cancelled': False, **state}
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            size, minimum = desktop_geometry()
            desktop_window['value'] = webview.create_window(
                'AC8 Livery System', url, width=size[0], height=size[1],
                min_size=minimum, background_color='#070a0d', text_select=False,
                js_api=DesktopApi(),
            )
            # Also permit normal attachment links in the embedded browser.
            webview.settings['ALLOW_DOWNLOADS'] = True
            webview.start(gui='edgechromium', debug=False, storage_path=str(data / 'WebView2'))
    finally:
        if args.no_browser or args.browser:
            pass
        elif server_thread is not None and server_thread.is_alive():
            server.shutdown()
        # Finish an active transactional install/conversion safely, but do not
        # start further queued operations after the user closes the window.
        server.server_close(); pool.shutdown(wait=True, cancel_futures=True)
        (data / 'running.json').unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if os.name == 'nt':
            import ctypes
            message = ('程序无法启动 / Unable to start:\n\n' + str(exc)
                       + '\n\n请确认 WebView2 Runtime 与 .NET Framework 4.6.2 或更高版本已安装。'
                       + '\nCheck WebView2 Runtime and .NET Framework 4.6.2 or later.')
            ctypes.windll.user32.MessageBoxW(None, message, 'AC8 Skin Pack Tool', 0x10)
        else:
            raise
