# Review notes for Nexus moderators

Release: AC8 Skin Manager 0.8.1. The original uploaded archive and separate EXE are in `release-files`. `docs/release-files.json` records every archive member's size and SHA256. `release-files/SHA256SUMS.txt` records the downloadable artifacts.

## Compiled components

| File | Source / build |
| --- | --- |
| AC8SkinPackTool.exe | `work/ac8-skin-manager/package-tool`; Python/PyInstaller; see BUILD.md |
| AC8SkinManager/Native/registrar.dll | `work/ac8-skin-manager/native/registrar.c` and `engine_build.h`; Zig C build |
| AC8OverrideLoader/dlls/main.dll | Unmodified upstream AC8OverrideLoader 0.2.0; THIRD-PARTY.md |
| optional UE4SS.dll and dwmapi.dll | Upstream UE4SS build e3ba1016; THIRD-PARTY.md |
| retoc.exe inside the desktop EXE | Upstream converter; exact copy and license under work/ac8-kamome/tools/retoc |

## Behavior relevant to review

- The desktop UI is pywebview/WebView2 with an HTTP service bound to 127.0.0.1. API requests use a generated session token and Host/Origin checks. It is not an Internet-facing service.
- Package operations inspect user-selected archives, invoke retoc locally, validate metadata and copy owned livery files into the selected game directory. The library supports removing/restoring its owned files.
- The native registrar validates the supported engine build and bounded texture-only package headers before adding package records under the engine lock. It is an in-process UE4SS MOD component, not a standalone launcher.
- Binding capture is read-only, on demand and limited to matching aircraft preparation with native textures in offline mode.
- Installation can add missing UE4SS components and generate a separate offline configuration from the player's own EAC settings. Steam launch options must be set by the player. No original EAC settings or game executable are supplied or replaced.
- The archive contains scripts and native DLLs by design. A quarantine notice alone is not evidence that those files are malicious; this repository is provided for independent inspection, not a guarantee that every scanner will accept them.

## Snapshot correspondence

All manager Lua files match the uploaded archive byte for byte. The desktop Python/HTML/JS, spec and shipped UI assets are the v0.8.1 build inputs. `build.py` is a portable build entry added for this repository; it replaces a private development script that required local game and test-artwork paths. Public test staging and missing-fixture handling are adapted for a clean checkout. These adaptations do not change the shipped game/runtime source.

The user guides added to the upload are retained in `distribution`. Game executables, cooked game assets, livery resources, local logs, profiles, saved selections, credentials, backups and painting-tool experiments are excluded from this source snapshot.
