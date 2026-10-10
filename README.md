# AC8 Skin Manager / AC8 涂装管理器

Source and review materials for sasili's **v0.8.1** Windows PC release.
Per-aircraft livery selection in the aircraft preparation screen, with a bilingual desktop tool for importing, managing and authoring livery packages.

## Downloads / 下载

- [Complete v0.8.1 package](release-files/AC8SkinManager-v0.8.1-Nexus.zip)
- [Desktop tool v0.8.1](release-files/AC8SkinPackTool-v0.8.1.exe)
- [Build instructions / 构建说明](docs/BUILD.md)
- [Review notes / 审核说明](docs/REVIEW.md)
- [Third-party sources and licenses / 第三方来源](docs/THIRD-PARTY.md)
- [Installation / 安装](distribution/README-English.txt) · [中文](distribution/README-中文.txt)
- [Author API / 作者接入](distribution/SDK/Author-Guide.txt)

**Offline single-player campaign only.** Read the installation instructions before use. The game, its assets and livery artwork are not included. The release bundles optional UE4SS and AC8OverrideLoader components under their respective licenses.

## Layout / 目录

`work/ac8-skin-manager/src`: shipped Lua MOD source.
`work/ac8-skin-manager/native`: source for the version-locked registrar.dll.
`work/ac8-skin-manager/package-tool`: Python, HTML/JS and PyInstaller spec for the desktop EXE.
`distribution`: installation scripts, SDK, licenses, release configuration and user documentation. Executables are supplied in the complete release ZIP.
`work/ac8-kamome/tools/retoc`: exact bundled third-party converter and its license.
`release-files`: original compiled distribution, desktop EXE and checksums.

## License

Original software is MIT licensed. Third-party components retain their own licenses. UI artwork and application icon are supplied by the project author and are not covered by the software MIT license; see [asset notes](work/ac8-skin-manager/package-tool/assets/README.md).
