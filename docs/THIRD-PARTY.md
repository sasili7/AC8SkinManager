# Third-party components

Retain upstream copyright notices and license files when redistributing.

- **AC8OverrideLoader 0.2.0** (MIT), JustMonika24769. [Upstream](https://github.com/JustMonika24769/AC8OverrideLoader), reference source snapshot `71d4f28d2ec232c85da6fb523bbc68ec8020135f`. Also includes IoStoreLoaderMod (MIT) and MinHook (BSD-style); notices under distribution/Licenses. Release DLL SHA256: `225c8d6c3fbf5e8882cb8e334dbd3426cb24a1415b3585073cc4264ae834f851`.
- **UE4SS** (MIT), [upstream source and builds](https://github.com/UE4SS-RE/RE-UE4SS), released runtime build `e3ba1016`, recorded as 3.0.1 Beta #0. Exact optional runtime supplied in the complete ZIP. UE4SS.dll SHA256: `680a026890abb4d0df2211251f8defc1681a584275f1521dcc0fe30af480006f`. Use the original build rather than assuming experimental-latest is identical.
- **retoc** (MIT), Truman Kilen and Archengius, [source](https://github.com/trumank/retoc). Exact executable and notice under work/ac8-kamome/tools/retoc. SHA256: `a145f3557ec60b163ed1b78b2f380232d2753fa30350c8013c98e171db3ae7e7`. No `oo2core` DLL is redistributed.
- **json.lua** (MIT), rxi, [source](https://github.com/rxi/json.lua). Exact source and notice under work/ac8-skin-manager/vendor.
- **pywebview, pythonnet, clr_loader, bottle, cffi, pycparser, PyInstaller**: licenses supplied under distribution/Licenses/DesktopTool. Dependency versions are recorded in requirements-build.txt. PyInstaller's license includes the bootloader distribution exception.
- **Python**: [CPython licensing](https://docs.python.org/3/license.html). A Python x64 runtime is bundled by PyInstaller; source builds use the developer's local Python.
- **Zig 0.14.1**: [official source](https://github.com/ziglang/zig). Build tool only, not bundled as a standalone compiler in the MOD.

Game files and artwork are not re-licensed under the project's MIT license. UI asset notes are in package-tool/assets/README.md.
