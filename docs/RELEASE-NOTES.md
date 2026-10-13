# AC8 Skin Manager

飞行性能更新：正常飞行复用玩家机体缓存，保留实时机体与材质检查。新机体通知、对象失效时重新查找，约每 30 秒完整兜底；普通任务 HUD 不再清空玩家缓存，稳定飞行停止定期写入状态文件。保留进入及重开任务后的涂装恢复。

Flight performance update: reuse player discovery during stable flight, retaining live body/material checks. Refresh on player creation or invalidation, with a roughly 30-second full fallback. Ordinary mission HUD widgets no longer invalidate the player cache, and stable flight no longer periodically rewrites the status file. Mission entry/restart livery restoration is preserved.

97 项运行逻辑检查和 23 项安装检查通过。模拟测试用于统计引擎调用次数，实际游戏帧时间及其他实体电脑尚未测试。

97 runtime checks and 23 installation checks passed. Simulations count engine calls; actual game frame times and other physical PCs have not been measured.

**[下载完整包 / Download complete package](https://github.com/sasili7/AC8SkinManager/releases/download/download/AC8SkinManager.zip)**

完整包包含游戏内 MOD、中英文涂装制作/导入/管理 EXE、AC8OverrideLoader、可选 UE4SS、安装脚本和四份中英文教程。全部解压后运行 Setup.cmd；安装前完全退出游戏。EXE 与教程也可在下方 Assets 单独下载。

The complete package includes the in-game MOD, bilingual author/import/library EXE, AC8OverrideLoader, optional UE4SS setup, installation scripts and four Chinese/English guides. Fully extract it and run Setup.cmd after closing the game. The EXE and guides are also available separately under Assets.

仅用于 Windows x64 离线单机战役。Steam 启动选项：

```text
cmd /d /c "set EOS_USE_ANTICHEATCLIENTNULL=1&& %command% -anticheat_settings=AC8SkinManager_Offline.json"
```

Windows x64, offline single-player campaign only. Read the bundled README for requirements and conflict handling. Character liveries, game assets, painting tools and personal saves are not included. SHA256SUMS.txt lists download checksums.
