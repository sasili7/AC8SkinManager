# Build / 构建

Build on Windows x64 with Python 3.13 x64. WebView2 Runtime and .NET Framework 4.6.2+ are required to run the desktop application. The reference EXE was produced with Python 3.13.9, PyInstaller 6.22.3 and pywebview 5.4; the registrar uses Zig 0.14.1.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build.py
```

Outputs: `dist/AC8SkinPackTool.exe` and `dist/registrar.dll`.
Build one component with `build.py --desktop` or `build.py --native`.
The registrar build uses the committed `native/engine_build.h` compatibility fingerprints. It does not need or redistribute the game executable. The fingerprints are valid only for the recorded game build; do not regenerate them for an arbitrary build or disable their checks.

The PyInstaller spec uses the same source layout and assets as the released EXE. `retoc.exe` is the exact converter included inside that EXE, with its SHA256 in THIRD-PARTY.md. No proprietary Oodle codec DLL is bundled. Build timestamps, local paths and Python distributions can change resulting binary hashes; these commands describe a source build, not a promise of byte-identical output.

## Assemble an installable package

Run `python tools/assemble_release.py` from the repository root first. This reconstructs `release-files/AC8SkinManager.zip` from the checked binary base and recorded ZIP changes, verifies the exact published SHA256 and all source/inventory entries, without rebuilding or changing any executable. GitHub Actions runs the same command before publishing.

Extract the resulting `release-files/AC8SkinManager.zip` to a new directory. Replace only `AC8SkinPackTool.exe` and `Game/Binaries/Win64/ue4ss/Mods/AC8SkinManager/Native/registrar.dll` with your build outputs. Keep the dependency DLLs, scripts, settings and licenses. Regenerate the root compatibility.json file inventory with:

```powershell
.\.venv\Scripts\python.exe tools\refresh_inventory.py 'D:\Build\AC8SkinManager'
```

Do not install the `distribution` source template directly: binary prerequisites are intentionally supplied in the complete ZIP. Do not upload a modified archive under the original SHA256 or claim it is the published binary package.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s work\ac8-skin-manager\package-tool -p 'test_*.py' -v
.\.venv\Scripts\python.exe -m pip install lupa==2.6
.\.venv\Scripts\python.exe work\ac8-skin-manager\test_framework.py
.\.venv\Scripts\python.exe work\ac8-skin-manager\test_stability.py
.\.venv\Scripts\python.exe work\ac8-skin-manager\test_binding_capture.py
.\.venv\Scripts\python.exe work\ac8-skin-manager\test_mission_restore.py
.\.venv\Scripts\python.exe work\ac8-skin-manager\test_flight_performance.py
```

Texture-fixture integration tests are skipped when the optional author's local `.ac8skin.zip` fixture is absent. This source snapshot does not distribute its artwork. Installer tests additionally require a local matching game installation and a complete release directory selected with `AC8_TEST_RELEASE`. Mock/unit tests do not validate actual game rendering or performance.

## 中文

在 Windows x64 安装 Python 3.13 x64，按上面的命令创建虚拟环境、安装构建依赖并运行 build.py。输出是桌面 EXE 和管理器 registrar.dll。运行 EXE 需要 WebView2 与 .NET Framework 4.6.2 或更高版本。

先在仓库根目录运行 `python tools/assemble_release.py`，重建并校验 release-files 中的当前完整 ZIP；distribution 是去掉二进制的源码模板，不能直接安装。替换自己编译的两个文件后，重新生成兼容性清单。第三方 DLL 来源与许可见 THIRD-PARTY.md。测试不附带游戏或人物涂装资源，缺少该测试素材时会跳过对应集成测试。
