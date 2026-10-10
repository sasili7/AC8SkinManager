# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
project = Path(SPECPATH)
retoc = project.parent.parent / 'ac8-kamome/tools/retoc'

a = Analysis(
    [str(project / 'app.py')],
    pathex=[str(project)],
    binaries=[],
    datas=[(str(project / 'index.html'), '.'), (str(project / 'app.js'), '.'), (str(project / 'assets/mascot.png'), 'assets'), (str(retoc / 'retoc.exe'), 'Tools'), (str(retoc / 'LICENSE'), 'Tools')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AC8SkinPackTool',
    icon=str(project / 'assets/app-icon.jpg'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
