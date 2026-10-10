"""Translate tool-generated messages, never author metadata or filenames."""
import re

PAIRS = '''
此脚本运行时请使用纯 ASCII 游戏目录 / This Lua runtime requires an ASCII game path.|This Lua runtime requires an ASCII game path.
导出文件缺失或已改变，请重新生成涂装包。|The export file is missing or has changed. Build the package again.
保存校验失败，请重试。|The saved file failed verification. Please try again.
包内包含多个独立涂装，请拆分后再导入。|This package contains multiple independent liveries. Split them before importing.
包内存在不安全的文件路径。|The package contains an unsafe file path.
包内路径不能越出皮肤目录。|Package paths must stay inside the livery directory.
包内包含 Windows 不支持的名称。|The package contains a filename unsupported by Windows.
压缩包文件过多。|The archive contains too many files.
不支持重复路径、符号链接或加密 ZIP。|Duplicate paths, symbolic links and encrypted ZIPs are not supported.
解压后资源总量不能超过 4 GB。|Unpacked resources must not exceed 4 GB.
无法确认游戏是否已退出，请稍后再试。|Unable to check whether AC8 has exited. Try again shortly.
资源注册索引不完整。|The resource registration index is incomplete.
需要无依赖的 UE5.4 贴图容器索引。|A dependency-free UE5.4 texture container index is required.
容器包含依赖、重定向或无效资源编号，当前管理器不能加载。|This container contains dependencies, redirects or invalid resource IDs.
工具缺少 retoc.exe，请重新解压完整工具。|retoc.exe is missing. Extract the complete tool again.
该包使用的 Oodle 压缩编码器不可用。请作者提供无压缩的资源包后再转换。|The required Oodle codec is unavailable. Ask the author for an uncompressed package.
读取或转换资源失败：|Unable to read or convert the resources:
无法识别机型编号。|Unable to detect the aircraft ID.
一个包只能有一款皮肤容器，未找到 UTOC；如果包含多个皮肤，请作者拆分后再导入。|No UTOC found. Each package must contain one livery container; split multiple liveries before importing.
请选择 ZIP，或同时拖入配套的 UTOC / UCAS / PAK 文件。|Select a ZIP or drop the matching UTOC / UCAS / PAK files together.
缺少同名 UCAS 文件，或误选了游戏全局容器。|The matching UCAS is missing, or a global game container was selected.
皮肤需要包含 1–128 个贴图资源。|A livery must contain 1-128 texture assets.
包内包含多个机型，请按机型拆分。|The package contains multiple aircraft. Split it by aircraft first.
请至少给一张贴图填写材质槽。未知机型需要作者填写实际绑定。|Assign material slots to at least one texture. Authors must supply bindings for unknown aircraft.
贴图绑定不属于导入的包，或没有选择任何贴图。|The bindings refer to textures outside the imported package, or no texture is selected.
正在解包现成涂装…|Unpacking the source livery...
作者转换需要本机 AC8。请在右上角填写包含 Game 文件夹的游戏根目录。|Author conversion requires a local AC8 installation. Select the game root containing the Game folder.
正在转换贴图 |Converting texture 
未能完整提取贴图：|Unable to extract the complete texture:
资源路径与包内 header 不匹配。|The asset path does not match the package header.
正在生成独立资源包…|Building independent resources...
打包后资源路径不一致。|Asset paths changed unexpectedly during packaging.
正在核对贴图内容与独立资源路径…|Verifying texture contents and independent asset paths...
转换后的贴图数据与原包不同，已停止输出。|Converted texture data does not match the original. Output was stopped.
完成：原贴图数据保持一致。|Done. Original texture data was preserved.
这不是管理器涂装包。普通 MOD 请作者先用“作者打包”页面转换。|This is not a manager livery package. The author must convert an ordinary mod using the Create page first.
不支持此涂装包格式或版本。|Unsupported livery package format or version.
皮肤登记信息不完整：|Incomplete livery registration:
皮肤编号或资源注册版本不一致。|Livery identity or registration version does not match.
文件清单不完整。|The file manifest is incomplete.
重复文件清单。|The manifest contains duplicate files.
皮肤包中不允许包含脚本、加载器或无关文件。|Livery packages must not contain scripts, loaders or unrelated files.
文件缺失或校验失败：|Missing file or checksum mismatch:
包内包含未登记文件或缺少必要文件。|The package contains unlisted files or is missing required files.
缺少配套资源容器。|The matching resource container is missing.
包中包含多余资源容器。|The package contains extra resource containers.
皮肤包的 PAK 包含额外内容，当前格式只允许纯贴图容器。请作者重新转换。|The PAK contains additional content. Only texture containers are supported; ask the author to rebuild the package.
包内资源与登记贴图不一致。|Container assets do not match the registered textures.
注册索引与资源容器不一致。|The registration index does not match the resource container.
请完全退出 AC8 后再安装；本工具不会自动关闭游戏。|Fully exit AC8 before installing. This tool does not close the game automatically.
未找到 AC8SkinManager。请先安装皮肤管理器，再导入涂装包。|AC8SkinManager was not found. Install the manager before importing liveries.
未找到 AC8OverrideLoader。请先安装管理器要求的通用加载器。|AC8OverrideLoader was not found. Install the required override loader first.
管理器配置格式错误，请修复 config.json。|Invalid manager configuration. Repair config.json first.
当前管理器的资源注册接口不兼容，请更新管理器。|The resource registration interface is incompatible. Update the manager.
管理器安装不完整。|The manager installation is incomplete.
安装前校验失败，请重新拖入涂装包。|Pre-install verification failed. Drop the livery package again.
安装目标路径不安全。|The installation target path is unsafe.
安装目录被重定向到游戏目录以外。|An installation directory redirects outside the game folder.
同编号皮肤已由其它方式安装；为避免覆盖，请先手动核对旧版本。|A livery with this ID was installed by another method. Check the existing version before replacing it.
现有皮肤目录不属于本工具，不能自动覆盖。|This tool does not own the existing livery directory and cannot overwrite it.
已安装资源索引损坏，请移除或重新导入对应包：|An installed resource index is damaged. Remove or reimport its package:
独立资源与已安装涂装冲突：|Resources conflict with an installed livery:
。请更改作者/皮肤编号后重新制作。|. Change the author/livery ID and rebuild the package.
已安装。下次离线启动游戏后，在对应机型的 LIVERY 按钮中选择。|Installed. Restart AC8 offline, select the matching aircraft and choose this livery under LIVERY.
当前版本支持纯贴图包；请删除其它内容后再做转换。|Only texture packages are supported. Remove other content before converting.
不是飞机贴图或未知资源：|Not an aircraft texture, or an unknown asset:
正在处理…|Working...
处理完成|Done
处理未完成|Operation incomplete
请求内容过大。|The request is too large.
导入记录已过期，请重新拖入文件。|This import session has expired. Drop the files again.
无效的本机工具会话。|Invalid local tool session.
页面不存在。|Page not found.
尚未生成涂装包。|No livery package has been built yet.
目录不正确：请选择含有 Game 文件夹的 AC8 游戏根目录。|Select the AC8 game root containing the Game folder.
未知操作。|Unknown operation.
正在接收文件|Receiving files
接口不存在。|Endpoint not found.
当前任务不能继续接收文件。|This task cannot receive more files.
文件名称不正确。|Invalid filename.
请选择 ZIP 或 UTOC / UCAS / PAK 文件。|Select a ZIP or UTOC / UCAS / PAK files.
文件总量不能超过 4 GB。|Total file size must not exceed 4 GB.
文件名重复，请重新选择。|Duplicate filename. Select the files again.
上传中断，请重试。|File transfer interrupted. Try again.
任务已经开始。|The task has already started.
请选择一个 ZIP，或一组配套资源文件；不能混合导入。|Choose one ZIP or one matching set of resource files. Do not mix them.
玩家导入请选择一个 .ac8skin.zip 涂装包。|Select one .ac8skin.zip livery package for player import.
正在识别机型并校验资源…|Detecting aircraft and verifying resources...
正在安装到对应机型…|Installing for the matching aircraft...
请先导入并识别现成涂装包。|Import and inspect an existing livery package first.
请填写作者名称。|Enter the author name.
桌面界面组件缺失，请重新解压完整工具。|Desktop UI components are missing. Extract the complete tool again.
桌面窗口尚未准备完成。|The desktop window is not ready yet.
登记文件过大。|The registration file is too large.
涂装目录被重定向，不能自动管理。|The livery directory is redirected and cannot be managed automatically.
涂装编号无效。|Invalid livery ID.
请先选择正确的 AC8 游戏目录。|Select a valid AC8 game folder first.
此涂装缺少有效安装记录，请手动核对。|This livery has no valid installation receipt. Check it manually.
涂装目录结构错误。|Invalid livery directory structure.
涂装目录含有未登记文件，请手动核对。|This livery directory contains unregistered files. Check it manually.
涂装选择记录损坏，请先修复 selections.json。|Livery selection records are damaged. Repair selections.json first.
涂装已不存在，请刷新列表。|This livery no longer exists. Refresh the list.
恢复记录无效。|Invalid recovery record.
请完全退出 AC8 后再删除或恢复涂装。|Fully exit AC8 before removing or restoring liveries.
此涂装已恢复，请刷新列表。|This livery has already been restored. Refresh the list.
恢复文件缺失。|Recovery files are missing.
同编号涂装已存在，不能覆盖恢复。|A livery with the same ID already exists. Restore will not overwrite it.
正在移除涂装…|Removing livery...
正在恢复涂装…|Restoring livery...
另一个操作正在进行，请稍后再试。|Another operation is in progress. Try again shortly.
请在桌面程序中打开目录。|Open this folder from the desktop app.
需要 UE5 cooked 贴图资源。|UE5 cooked texture assets are required.
资源版本布局不在当前转换器支持范围内。|This asset version layout is not supported by the converter.
不支持未烘焙的编辑器资源。|Uncooked editor assets are not supported.
无效的资源 generation 数量。|Invalid asset generation count.
不支持带有非空 engine version 的 cooked header。|Cooked headers with a non-empty engine version are not supported.
资源 header 布局不匹配；未进行修改。|Asset header layout mismatch. No changes were made.
仅支持单个 Texture2D 导出的贴图资源。|Only texture assets exporting a single Texture2D are supported.
贴图导出名称必须直接来自名称表。|Texture export names must come directly from the name table.
不支持该导出表格式。|Unsupported export table format.
包内包含非 Texture2D 资源。|The package contains non-Texture2D assets.
贴图带有其它游戏资源引用，需作者先拆成独立包。|The texture references other game assets. The author must split it into an independent package.
不支持该导出数据偏移布局。|Unsupported export data offset layout.
仅支持有效的 ASCII cooked 包名称。|A valid ASCII cooked package name is required.
无效字符串。|Invalid string.
导出名称不是预期的名称表引用。|The export name is not the expected name-table reference.
重定位后资源名称回读失败。|Unable to verify the relocated asset name.
贴图 header 不完整。|The texture header is incomplete.
不支持该 bulk resource 版本。|Unsupported bulk resource version.
不支持需要 bulk offset fixup 的贴图。|Textures requiring bulk offset fixups are not supported.
不支持带有 |Not supported with 
 资源。| assets.
游戏版本不兼容，请使用针对当前游戏版本的管理器 / Unsupported game build.|Unsupported game build. Use a manager for this game version.
资源登记组件校验失败 / Registrar checksum mismatch.|Registrar checksum mismatch.
通用加载器版本不兼容 / Unsupported override loader.|Unsupported override loader version.
UE4SS 版本与此包不匹配 / Unsupported UE4SS build.|Unsupported UE4SS build.
请先停用旧 IoStoreLoaderMod / Disable the legacy IoStoreLoaderMod first.|Disable the legacy IoStoreLoaderMod first.
游戏目录过长，请缩短安装路径 / Game path is too long.|The game path is too long. Use a shorter installation path.
无效的 Windows x64 文件 / Invalid Windows x64 binary: |Invalid Windows x64 binary: 
mods.json 无效，请先修复 UE4SS 配置 / Invalid mods.json.|Invalid mods.json. Repair the UE4SS configuration first.
加载环境不完整或目录不可写 / Incomplete installation or directory is not writable: |Incomplete installation or directory is not writable: 
 尚未启用 / is not enabled.| is not enabled.
缺少 Visual C++ x64 运行库 / Missing Visual C++ x64 runtime: |Missing Visual C++ x64 runtime: 
无法识别容器编号。|Cannot identify the container ID.
一次制作一个皮肤容器。未找到 UTOC，或包中包含多个容器，请拆分后再导入。|Create one skin container at a time. No UTOC file was found, or this package contains multiple containers. Split it before importing.
缺少同名 UCAS 文件，或导入的是游戏全局容器。|The matching UCAS file is missing, or the selected file is a global game container.
\n当前版本支持纯贴图包，不会删除其它内容后假装转换成功。|\nOnly texture-only packages are supported. Remove other content before converting.
包含非飞机贴图或未知资源：|Non-aircraft textures or unrecognized assets: 
无效的材质绑定记录。 / Invalid material binding profile.|Invalid material binding profile.
未读取到贴图参数，请重新采集。 / No texture parameters were captured. Capture again.|No texture parameters were captured. Capture again.
机型编号无效。 / Invalid aircraft ID.|Invalid aircraft ID.
材质名称无效。 / Invalid material name.|Invalid material name.
绑定记录与当前机型不匹配。 / The profile does not match this aircraft.|The profile does not match this aircraft.
绑定记录中没有有效的材质列表。 / No valid material list in profile.|No valid material list in profile.
绑定记录的材质槽无效或重复。 / Invalid or duplicate material slot.|Invalid or duplicate material slot.
绑定记录的游戏版本不兼容。 / Unsupported game build in binding profile.|Unsupported game build in binding profile.
绑定记录过大。 / Binding profile is too large.|Binding profile is too large.
请先安装带材质读取功能的新版游戏管理器。 / Install the updated in-game manager with binding capture first.|Install the updated in-game manager with binding capture first.
请离线启动 AC8，在选机页选择对应飞机和 STD 后读取。 / Start AC8 offline, select the matching aircraft and STD, then capture.|Start AC8 offline, select the matching aircraft and STD, then capture.
读取超时；请确认新版 MOD 已启用并停留在对应选机页，或按 F7 后刷新。 / Capture timed out. Check the updated MOD and aircraft selection page, or press F7 then refresh.|Capture timed out. Check the updated MOD and aircraft selection page, or press F7 then refresh.
贴图参数列表无效。 / Invalid texture parameter list.|Invalid texture parameter list.
贴图参数记录无效。 / Invalid texture parameter record.|Invalid texture parameter record.
还有材质读取请求，请等待游戏处理；可在游戏按 F7 保存记录后刷新。 / Another capture is pending. Wait, or press F7 in-game and refresh saved records.|Another capture is pending. Wait, or press F7 in-game and refresh saved records.
需要原生材质记录，请切到 STD 后重新读取。 / Select STD and capture native materials again.|Select STD and capture native materials again.
需要原生游戏贴图路径。 / A native game texture path is required.|A native game texture path is required.
Select the aircraft offline / 请离线进入选机页：|Select the aircraft offline: 
Aircraft mismatch / 游戏选中机型与导入包不一致|The selected aircraft does not match the source package.
Select STD before capture / 请先选择 STD 原生材质再读取|Select STD before capturing native materials.
No texture parameters captured / 未读取到贴图参数|No texture parameters captured.
Aircraft changed / 读取时飞机已切换|The aircraft changed during capture. Try again.
没有已保存的绑定记录。 / No saved binding profile.|No saved binding profile.
Reading selected aircraft / 正在读取选中机体|Reading selected aircraft
'''
TRANSLATIONS = dict(tuple(part.replace('\\n', '\n') for part in line.split('|', 1)) for line in PAIRS.splitlines() if '|' in line)
ORDERED = sorted(TRANSLATIONS, key=len, reverse=True)


def english(message):
    value = str(message)
    for source in ORDERED:
        value = value.replace(source, TRANSLATIONS[source])
    return value


def localized(message, language):
    return english(message) if language == 'en' else str(message)


def messages(message):
    return {'zh': str(message), 'en': english(message)}
