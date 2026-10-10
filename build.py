"""Portable source build of the two custom compiled components (Windows x64)."""
from pathlib import Path
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / 'work/ac8-skin-manager'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop', action='store_true')
    parser.add_argument('--native', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt' or sys.maxsize <= 2**32:
        parser.error('Use Windows x64 and Python x64.')
    both = not (args.desktop or args.native)
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    if both or args.native:
        zig = shutil.which('zig')
        if not zig:
            spec = importlib.util.find_spec('ziglang')
            if spec and spec.submodule_search_locations:
                zig = str(Path(next(iter(spec.submodule_search_locations))) / 'zig.exe')
        if not zig or not Path(zig).is_file():
            parser.error('Install ziglang==0.14.1, or put Zig 0.14.1 on PATH.')
        version = subprocess.check_output([zig, 'version'], text=True).strip()
        if version != '0.14.1':
            parser.error(f'Reference compiler is Zig 0.14.1; found {version}.')
        subprocess.run([zig, 'cc', '-target', 'x86_64-windows-gnu', '-shared', '-O2',
                        '-Wall', '-Wextra', '-Werror', str(PROJECT / 'native/registrar.c'),
                        '-o', str(out / 'registrar.dll')], check=True, cwd=ROOT)
    if both or args.desktop:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                        '--distpath', str(out), '--workpath', str(ROOT / 'build/desktop'),
                        str(PROJECT / 'package-tool/AC8SkinPackTool.spec')], check=True, cwd=ROOT)
    print('Build completed:', out)

if __name__ == '__main__':
    main()
