# AC8 Skin Manager

更新：修复选机界面正常、进入任务后 MOD 涂装丢失的加载流程；支持任务机体重新识别、资源延迟重试及恢复日志。88 项运行逻辑检查和 23 项安装检查通过，实际任务画面仍需实机确认。

Update: restore saved MOD liveries on mission aircraft, retry transient streaming failures and record restoration diagnostics. 88 runtime checks and 23 installation checks passed; in-game rendering still requires verification.

**[下载完整包 / Download complete package](https://github.com/sasili7/AC8SkinManager/releases/download/download/AC8SkinManager.zip)**

游戏内按机型独立选择 MOD 涂装，附带中英文涂装制作、导入与管理工具。完整包包含可选 UE4SS、AC8OverrideLoader、安装脚本和四份中英文教程。解压完整包后运行 Setup.cmd；启动参数及详细流程见首页和包内 README。

四份教程同时附在下方 Assets 中，可单独下载：Chinese_User_Guide 为中文使用教程，Skin_Author_Guide_ZH 为中文作者教程；完整包内保留中文原名。桌面 EXE 已包含在完整包里，无需重复下载。不附带角色涂装或绘制工具。

仅用于 Windows x64 离线单机战役，不支持联机。Steam 启动选项：

```text
cmd /d /c "set EOS_USE_ANTICHEATCLIENTNULL=1&& %command% -anticheat_settings=AC8SkinManager_Offline.json"
```

Per-aircraft livery selection with a bilingual desktop tool for authoring, importing and managing compatible livery packages. The complete ZIP includes the MOD, desktop EXE, loader components, setup scripts and all four Chinese/English guides. Fully extract it and run Setup.cmd. The EXE and guides are also available separately below.

Windows x64, offline single-player campaign only. No multiplayer, character livery, painting tool or game assets. Read the README before installation. SHA256SUMS.txt contains the asset checksums.
