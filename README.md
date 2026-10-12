# AC8 Skin Manager · AC8 涂装管理器

为《皇牌空战 8》PC 版提供按机型分类的涂装管理。在选机界面点击 **LIVERY** 下的按钮即可选择 MOD 涂装，每架飞机独立保存选择。附带中英文桌面工具，供玩家导入、管理涂装，也供作者将已完成的贴图资源制作成兼容涂装包。

## 下载

任务涂装恢复更新：进入任务后自动给玩家机体恢复所选 MOD 涂装，资源未就绪时继续重试。安装后请完全退出并重新启动游戏。

**[下载完整安装包](https://github.com/sasili7/AC8SkinManager/releases/latest/download/AC8SkinManager.zip)** · **[打开下载页面](https://github.com/sasili7/AC8SkinManager/releases/latest)**

完整包内含游戏内 MOD、AC8SkinPackTool.exe、AC8OverrideLoader、可选安装的 UE4SS、安装脚本及四份中英文教程。桌面工具已经包含在完整包中，无需重复下载。

| 文件 | 用途 |
| --- | --- |
| [AC8SkinManager.zip](https://github.com/sasili7/AC8SkinManager/releases/latest/download/AC8SkinManager.zip) | 玩家首次安装使用的完整包 |
| [AC8SkinPackTool.exe](https://github.com/sasili7/AC8SkinManager/releases/latest/download/AC8SkinPackTool.exe) | 单独下载涂装制作、导入和管理工具 |
| [使用教程](distribution/使用教程.docx) · [English User Guide](distribution/English_User_Guide.docx) | 玩家安装与使用 |
| [作者教程（中文）](distribution/Skin%20Author%20Guide(中文).docx) · [Skin Author Guide](distribution/Skin_Author_Guide_EN.docx) | 作者制作兼容涂装包 |

## 安装与使用

1. 完全退出游戏，将完整 ZIP 解压到独立文件夹。
2. 运行 **Setup.cmd**，选择含 `Game` 文件夹的游戏根目录，按需勾选安装缺失的 UE4SS 文件及生成离线启动配置。
3. 在 Steam → 游戏属性 → 通用 → 启动选项中，先保存原内容，再填入下方完整的一行，从 Steam 启动游戏。
4. 运行包内 **AC8SkinPackTool.exe**，选择游戏目录，导入作者提供的兼容 `.ac8skin.zip` 涂装包。完成后重启游戏，在对应机型的选机页面选择涂装。

```text
cmd /d /c "set EOS_USE_ANTICHEATCLIENTNULL=1&& %command% -anticheat_settings=AC8SkinManager_Offline.json"
```

**仅用于 Windows x64 离线单机战役，不支持联机。** 恢复联机前，按包内 README 停用注入组件并恢复原启动选项。

- 不附带角色涂装、游戏资源或绘制工具；空涂装库不会显示 MOD 涂装按钮。
- `STD` 解除管理器材质覆盖，原版涂装通过游戏自己的菜单选择；MOD 涂装模式限制原生换肤，避免相互覆盖。
- 按钮每行四个，超过两行可竖向滚动；切换机型读取各自选择，进入武器选择页后隐藏。
- 普通覆盖式 PAK / UTOC / UCAS 文件须先由作者工具转换并正确绑定，不能直接当作兼容涂装包。
- 已有 UE4SS、其他代理加载器或旧 IoStoreLoaderMod / AC8-PGM 的玩家，请先阅读包内冲突说明。游戏目录使用英文、数字及普通符号，可含空格。
- 运行桌面工具需要 WebView2 和 .NET Framework；游戏组件需要 VC++ x64 运行库。安装器会检查游戏和组件兼容性。

## English

Mission restoration update: the saved MOD livery is reapplied to the mission player aircraft, with bounded retries while resources load. Fully exit and restart after updating.

AC8 Skin Manager adds per-aircraft MOD livery selection to the aircraft selection screen in ACE COMBAT 8 on PC. Each aircraft keeps its own selection. The bilingual desktop tool imports and manages compatible livery packages and helps creators package completed texture assets.

**[Download the complete package](https://github.com/sasili7/AC8SkinManager/releases/latest/download/AC8SkinManager.zip)** · [All downloads](https://github.com/sasili7/AC8SkinManager/releases/latest)

The complete ZIP includes the in-game MOD, desktop tool, AC8OverrideLoader, optional UE4SS setup, installation scripts and all four Chinese/English guides.

1. Fully exit the game and extract the entire ZIP to a separate folder.
2. Run **Setup.cmd**, select the game root containing `Game`, and choose the missing UE4SS and offline configuration options as needed.
3. Save your existing Steam launch options, then enter the complete command shown above and launch through Steam.
4. Run the included **AC8SkinPackTool.exe**, select the game directory and import a compatible `.ac8skin.zip` package. Restart the game and select its livery under **LIVERY** for the matching aircraft.

**Windows x64, offline single-player campaign only. Multiplayer is not supported.** Disable injection components and restore normal launch options before returning online. No character livery, painting tool or game assets are included. An empty library does not show MOD livery buttons. Use `STD` to restore native material control, then select native liveries in the game's own menu. Read the bundled README for dependencies, loader conflicts and removal instructions.

## Authors and source · 作者与源码

- [作者接入说明](distribution/SDK/Author-Guide.txt) · [贴图绑定说明](distribution/SDK/Binding-Guide-中文.txt)
- [Build instructions / 构建说明](docs/BUILD.md)
- [Compiled components / 编译组件说明](docs/REVIEW.md)
- [Third-party sources and licenses / 第三方来源与许可](docs/THIRD-PARTY.md)
- [File checksums / 文件校验值](release-files/SHA256SUMS.txt)
- [Report an issue / 反馈问题](https://github.com/sasili7/AC8SkinManager/issues)

Original software is MIT licensed. Third-party components retain their own licenses. UI artwork and the application icon are not covered by the software MIT license; see [asset notes](work/ac8-skin-manager/package-tool/assets/README.md).

作者 / Author: **sasili**
