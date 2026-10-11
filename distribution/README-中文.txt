AC8 Skin Manager — 作者 sasili

在选机界面按机型显示独立涂装按钮，保存每架飞机的选择。
本包包含游戏内管理器、AC8OverrideLoader 0.2.0、可选 UE4SS 和安装脚本。
本包附带 AC8SkinPackTool.exe，用于涂装导入、管理和作者打包；不含绘制工具或角色涂装。

要求
Windows 10/11 x64；AC8 1.1.2.0（安装器同时核对实际游戏文件）。
UE4SS 3.0.1 Beta #0 / e3ba1016，可在安装界面勾选安装。
需要 Microsoft Visual C++ v14 x64 运行库；本包不安装该运行库。
游戏目录须使用 ASCII 字符（英文、数字及普通符号，可含空格），避免脚本路径编码问题。
安装器会拒绝过长路径、运行中的游戏、不兼容版本和旧 IoStoreLoaderMod 冲突。

安装
1. 完全退出游戏，将整包解压到独立目录，不要在压缩包内直接运行。
2. 双击 Setup.cmd，选择含 Game 文件夹的游戏根目录。
3. 按需勾选“安装缺失的 UE4SS 文件”和“生成离线启动配置”，然后安装。
   已有兼容 UE4SS 可不勾选；已有有效离线配置可不生成，继续沿用原离线启动参数。
   如果程序提示权限不足，关闭后以管理员身份运行 Setup.cmd。
4. 首次生成离线配置后，Steam → 游戏属性 → 通用 → 启动选项。
   保存原内容，再填入以下完整一行，从 Steam 启动：
cmd /d /c "set EOS_USE_ANTICHEATCLIENTNULL=1&& %command% -anticheat_settings=AC8SkinManager_Offline.json"
   仅用于离线单机战役。不要用于联机。
5. 运行包内 AC8SkinPackTool.exe，导入适配的 .ac8skin.zip，然后重新离线启动游戏。
   空库会休眠，安装管理器本身不会凭空生成角色涂装。

操作
对应机型选机页的 [LIVERY] 中点击涂装，应用成功后高亮；每行四个按钮，超过两行竖向滚动。
STD 撤下管理器材质，并将原生换肤交还游戏；原生具体样式在游戏自己的菜单里选择。
MOD 模式限制原生换肤列表，避免两套系统互相覆盖；武器/特殊导弹页隐藏按钮。
切换机型自动读取该机型的保存选择。新增、删除或更新涂装后请重启游戏。
不要把普通覆盖式 PAK/UTOC 包直接当成管理器涂装；先由作者工具转换为独立资源。

更新与冲突
Setup 保留皮肤、selections.json、config.json、其他作者载荷及现有 UE4SS 设置。
管理器安装前备份到 Game/Binaries/Win64/AC8SkinManager-Backups，安装失败回滚本次管理器文件。
本次补充的 UE4SS/离线文件在安装失败时撤回；已有文件不被这一步覆盖。
已有不同版本 UE4SS、不同 dwmapi.dll 或其他代理加载器时，请先备份并处理冲突。
已有 IoStoreLoaderMod/旧 AC8-PGM 时，先按原作者说明停用或迁移，保留其他 MOD 文件。

卸载与恢复普通启动
退出游戏，备份 Mods/AC8SkinManager 后移走该目录，并从 mods.txt/mods.json 移除或禁用 AC8SkinManager。
AC8OverrideLoader/UE4SS 可能被其他 MOD 使用，不要随意删除。
恢复普通联网启动前，必须停用全部注入组件，并恢复原 Steam 启动选项。
如果 dwmapi.dll 是本包安装且没有其他 MOD 需要它，可移走该文件停用该 UE4SS 入口。
本包生成的 EasyAntiCheat/AC8SkinManager_Offline.json 可在退出游戏后删除。
不要删除或替换游戏原版 EAC 文件；本安装器不会修改原版 Settings.json。

文件与支持
手动安装见 手动安装-Manual-Install.txt；作者接入见 SDK/Author-Guide.txt。
运行记录：Mods/AC8SkinManager/menu-status.json、Native/registrar-status.json、UE4SS 日志。
反馈请附游戏版本、管理器版本和这些记录；上传日志前检查个人路径信息。

作者绑定辅助：运行 AC8SkinPackTool.exe，导入现成涂装后可读取当前原生材质、查看槽位并选择原贴图填写绑定。详见 SDK/Binding-Guide-中文.txt。桌面工具需要 WebView2 Runtime 和 .NET Framework 4.6.2 或更高版本。
