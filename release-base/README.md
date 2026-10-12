# Release assembly base

This archive is a checked binary base for `python tools/assemble_release.py`. It is not the current player download. The assembler applies the recorded ZIP changes without recompressing third-party binaries, checks the exact resulting SHA256, and verifies every archive entry against `docs/release-files.json` and the current distribution/runtime source. GitHub Actions publishes the resulting complete ZIP to Releases.

当前完整安装包请从 Releases 下载。此目录仅存放打包基准；在仓库根目录运行 `python tools/assemble_release.py` 可重建与本地完整包字节一致的 ZIP。
