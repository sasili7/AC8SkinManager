AC8 Skin Manager — by sasili

Per-aircraft livery buttons in aircraft selection, with saved independent choices.
Includes the in-game MOD, AC8OverrideLoader 0.2.0, optional UE4SS and setup scripts.
AC8SkinPackTool.exe is included for import, library management and author packaging. No painting tool or livery is included.

Requirements
Windows 10/11 x64; AC8 1.1.2.0. Setup verifies the actual game binary.
UE4SS 3.0.1 Beta #0 / e3ba1016 is included as an optional installation.
Requires Microsoft Visual C++ v14 x64 Runtime; this package does not install it.
Use an ASCII game path, with ordinary letters, numbers and punctuation; spaces are supported.
Overlong paths, a running game, incompatible binaries and legacy loader conflicts are refused.

Installation
1. Fully exit AC8 and extract the entire archive to a separate folder.
2. Run Setup.cmd and choose the game root containing the Game folder.
3. Choose whether to install missing UE4SS files and create the offline launch configuration.
   Keep a compatible existing UE4SS. Keep existing working offline launch settings if preferred.
   If access is denied, close Setup and run Setup.cmd as administrator.
4. After creating the offline configuration, save your existing Steam launch options and enter this complete line:
cmd /d /c "set EOS_USE_ANTICHEATCLIENTNULL=1&& %command% -anticheat_settings=AC8SkinManager_Offline.json"
   Start through Steam. Offline single-player campaign only. Do not use online.
5. Run the included AC8SkinPackTool.exe, import compatible .ac8skin.zip packs, then restart offline.
   An empty library sleeps; installing the manager does not add a character livery.

Use
Click a livery under [LIVERY] for the selected aircraft. The successfully applied selection is highlighted.
Four buttons per row; vertical scrolling after two rows. Each aircraft keeps its own choice.
STD removes the manager's material override and restores the game's native skin controls.
Select native variants in the game's own menu. MOD mode locks that list to avoid competing changes.
Buttons hide on weapon/special-missile pages. Restart after installing, updating or removing a pack.
Ordinary override PAK/UTOC packs require conversion to independent resources before use here.

Updates and conflicts
Existing skins, selections.json, config.json, other payloads and UE4SS settings are preserved.
Manager files are backed up to Game/Binaries/Win64/AC8SkinManager-Backups and restored on install failure.
New prerequisite/offline files added by this run are removed if installation fails; existing files are kept.
An incompatible UE4SS, dwmapi.dll or another proxy loader must be backed up and resolved first.
Disable or migrate legacy IoStoreLoaderMod/AC8-PGM following its author's instructions.

Uninstall and restore normal startup
Exit AC8, back up and move Mods/AC8SkinManager, and remove/disable its entries in mods.txt/mods.json.
AC8OverrideLoader and UE4SS may be shared by other MODs. Do not delete shared components blindly.
Before normal online startup, disable all injection components and restore your original Steam launch options.
If this package installed dwmapi.dll and no other MOD needs it, move that file to disable this UE4SS entry point.
The generated EasyAntiCheat/AC8SkinManager_Offline.json can be removed after exiting AC8.
Do not delete or replace original EAC files. Setup does not alter the original Settings.json.

See the manual installation file and SDK/Author-Guide.txt.
Diagnostic files: Mods/AC8SkinManager/menu-status.json, Native/registrar-status.json and UE4SS logs.
Include game/MOD versions when reporting issues. Check logs for personal paths before sharing.

Author binding assistance: run AC8SkinPackTool.exe, import a source livery and capture native materials to select original textures and fill slots. See SDK/Binding-Guide-English.txt. The desktop tool requires WebView2 Runtime and .NET Framework 4.6.2 or newer.
