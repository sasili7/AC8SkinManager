param([string]$GamePath)
$ErrorActionPreference = 'Stop'
function Get-SHA256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { return ([System.BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $hasher.Dispose() }
}
function Assert-X64([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $reader = New-Object System.IO.BinaryReader($stream)
    try {
        if ($reader.ReadUInt16() -ne 0x5A4D) { throw 'Invalid DLL' }
        $stream.Position = 0x3c; $offset = $reader.ReadUInt32()
        if ($offset -lt 64 -or $offset -gt ($stream.Length - 6)) { throw 'Invalid DLL' }
        $stream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) { throw 'Windows x64 DLL required' }
    } catch { throw "Invalid x64 runtime / x64 运行库无效：$Path" }
    finally { $reader.Dispose(); $stream.Dispose() }
}
function Assert-NotRedirected([string]$Path) {
    $item = $Path
    while ($item) {
        if ((Test-Path -LiteralPath $item) -and ((Get-Item -LiteralPath $item -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "Redirected install path / 安装路径存在重定向：$item"
        }
        $item = Split-Path -Parent $item
    }
}
try {
    if (Get-Process -Name AceCombat8 -ErrorAction SilentlyContinue) { throw 'Please fully close AC8 / 请完全退出游戏。' }
    if (-not $GamePath) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object System.Windows.Forms.FolderBrowserDialog
        $picker.Description = 'Select ACE COMBAT 8 root / 选择含有 Game 文件夹的游戏根目录'
        if ($picker.ShowDialog() -ne 'OK') { exit 0 }
        $GamePath = $picker.SelectedPath
        $picker.Dispose()
    }
    $gameRoot = (Resolve-Path -LiteralPath $GamePath).Path.TrimEnd('\')
    if ($gameRoot -match '[^\x20-\x7e]') { throw 'Use an ASCII game path for this Lua runtime / 此脚本运行时请使用不含中文等非 ASCII 字符的游戏目录。' }
    $exePath = Join-Path $gameRoot 'Game\Binaries\Win64\AceCombat8.exe'
    $release = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'compatibility.json') -Encoding UTF8 -Raw | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { throw 'Wrong game directory / 游戏目录不正确。' }
    if ((Get-SHA256 $exePath) -ne $release.engine_sha256) {
        throw 'Unsupported AC8 game build / 此管理器不支持当前游戏版本。'
    }
    $runtime = Join-Path $gameRoot 'Game\Binaries\Win64\ue4ss\UE4SS.dll'
    if (-not (Test-Path -LiteralPath $runtime -PathType Leaf)) { throw 'Install UE4SS first; see README / 请先按 README 安装 UE4SS。' }
    if ($release.ue4ss_sha256 -notcontains (Get-SHA256 $runtime)) {
        throw 'Unsupported UE4SS build; see README / UE4SS 版本不匹配，请查看 README。'
    }
    $proxy = Join-Path $gameRoot 'Game\Binaries\Win64\dwmapi.dll'
    $settings = Join-Path $gameRoot 'Game\Binaries\Win64\ue4ss\UE4SS-settings.ini'
    if (-not (Test-Path -LiteralPath $proxy -PathType Leaf) -or -not (Test-Path -LiteralPath $settings -PathType Leaf)) {
        throw 'Incomplete UE4SS installation; run Setup.cmd and select Install missing UE4SS files / UE4SS 不完整，请通过 Setup.cmd 补齐缺失文件。'
    }
    $bundledProxy = Join-Path $PSScriptRoot 'Prerequisites\UE4SS\Game\Binaries\Win64\dwmapi.dll'
    if ((Get-SHA256 $proxy) -ne (Get-SHA256 $bundledProxy)) { throw 'Existing dwmapi.dll belongs to another loader / 已有 dwmapi.dll 与本包不兼容。' }
    $modsRoot = Join-Path $gameRoot 'Game\Binaries\Win64\ue4ss\Mods'
    foreach ($dll in @('MSVCP140.dll','MSVCP140_ATOMIC_WAIT.dll','MSVCP140_CODECVT_IDS.dll','VCRUNTIME140.dll','VCRUNTIME140_1.dll')) {
        $locations = @((Join-Path $gameRoot ('Game\Binaries\Win64\' + $dll)),
            (Join-Path $gameRoot ('Game\Binaries\Win64\ue4ss\' + $dll)),
            (Join-Path $env:WINDIR ('System32\' + $dll)))
        $located = $locations | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if (-not $located) {
            throw "Install Visual C++ x64 runtime / 请安装 Visual C++ x64 运行库：$dll"
        }
        Assert-X64 $located
    }
    if ($modsRoot.Length -gt 165) { throw 'Please use a shorter game directory / 请缩短游戏目录路径。' }
    $listPath = Join-Path $modsRoot 'mods.txt'
    $jsonPath = Join-Path $modsRoot 'mods.json'
    $lines = if (Test-Path -LiteralPath $listPath) { @(Get-Content -LiteralPath $listPath -Encoding UTF8) } else { @() }
    $jsonMods = if (Test-Path -LiteralPath $jsonPath) {
        $raw = Get-Content -LiteralPath $jsonPath -Encoding UTF8 -Raw
        if (-not $raw.TrimStart().StartsWith('[')) { throw 'Invalid mods.json / mods.json 格式错误。' }
        @($raw | ConvertFrom-Json)
    } else { @() }
    foreach ($row in $jsonMods) {
        if (-not $row.mod_name -or $row.mod_enabled -isnot [bool]) { throw 'Invalid mods.json / mods.json 格式错误。' }
    }
    $legacyStates = @(
        foreach ($line in $lines) {
            if ($line -match '^\s*IoStoreLoaderMod\s*:\s*([01])\s*(?:;.*)?$') { $Matches[1] -eq '1' }
        }
        foreach ($row in $jsonMods) { if ($row.mod_name -eq 'IoStoreLoaderMod') { $row.mod_enabled } }
    )
    $legacyEnabled = if ($legacyStates.Count) { -not ($legacyStates -contains $false) } else { Test-Path -LiteralPath (Join-Path $modsRoot 'IoStoreLoaderMod\enabled.txt') }
    if ($legacyEnabled) { throw 'Disable the legacy IoStoreLoaderMod first / 请先停用旧 IoStoreLoaderMod。' }
    # Validate package files before modifying any installed file.
    foreach ($row in $release.files) {
        $file = Join-Path $PSScriptRoot $row.path
        if ((Get-SHA256 $file) -ne $row.sha256) { throw "Package checksum mismatch: $($row.path)" }
    }
    # Validate all destinations before backup or writes, including config files.
    Assert-NotRedirected $modsRoot
    foreach ($name in @('AC8SkinManager','AC8OverrideLoader','mods.txt','mods.json')) {
        $existing = Join-Path $modsRoot $name
        Assert-NotRedirected $existing
        if (Test-Path -LiteralPath $existing -PathType Container) {
            foreach ($item in Get-ChildItem -LiteralPath $existing -Recurse -Force) {
                if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Redirected install path / 安装路径存在重定向。' }
            }
        }
    }
    $backupRoot = Join-Path $gameRoot ('Game\Binaries\Win64\AC8SkinManager-Backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    Assert-NotRedirected $backupRoot
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    foreach ($name in @('AC8SkinManager', 'AC8OverrideLoader', 'mods.txt', 'mods.json')) {
        $source = Join-Path $modsRoot $name
        if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $backupRoot $name) -Recurse }
    }
    $written = New-Object System.Collections.Generic.List[string]
    try {
        $payloadRoot = Join-Path $PSScriptRoot 'Game\Binaries\Win64\ue4ss\Mods'
        foreach ($name in @('AC8SkinManager', 'AC8OverrideLoader')) {
            $sourceRoot = Join-Path $payloadRoot $name
            foreach ($file in Get-ChildItem -LiteralPath $sourceRoot -File -Recurse) {
                $relative = $file.FullName.Substring($sourceRoot.Length + 1)
                $target = Join-Path (Join-Path $modsRoot $name) $relative
                $resolved = [System.IO.Path]::GetFullPath($target)
                if (-not $resolved.StartsWith($modsRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe install target' }
                # Reject redirected directories; never write through another mod's junction.
                $ancestor = Split-Path -Parent $target
                while ($ancestor.Length -ge $modsRoot.Length) {
                    if ((Test-Path -LiteralPath $ancestor) -and ((Get-Item -LiteralPath $ancestor).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { throw 'Redirected install directory / 安装目录存在重定向。' }
                    $ancestor = Split-Path -Parent $ancestor
                }
                New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
                $written.Add($target)
                Copy-Item -LiteralPath $file.FullName -Destination $target -Force
            }
        }
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        $lines = @($lines | Where-Object { $_ -notmatch '^\s*(AC8SkinManager|AC8OverrideLoader)\s*:' })
        $lines += 'AC8OverrideLoader : 1'; $lines += 'AC8SkinManager : 1'
        $written.Add($listPath); [System.IO.File]::WriteAllLines($listPath, [string[]]$lines, $utf8)
        if (Test-Path -LiteralPath $jsonPath) {
            $kept = @($jsonMods | Where-Object { $_.mod_name -notin @('AC8SkinManager','AC8OverrideLoader') })
            $kept += [pscustomobject]@{mod_name='AC8OverrideLoader'; mod_enabled=$true}
            $kept += [pscustomobject]@{mod_name='AC8SkinManager'; mod_enabled=$true}
            $written.Add($jsonPath); [System.IO.File]::WriteAllText($jsonPath, (ConvertTo-Json -InputObject @($kept) -Depth 32), $utf8)
        }
        foreach ($relative in @('AC8SkinManager\Skins', 'AC8SkinManager\BindingProfiles', 'AC8SkinManager\Native\containers', 'AC8OverrideLoader\payloads')) {
            New-Item -ItemType Directory -Path (Join-Path $modsRoot $relative) -Force | Out-Null
        }
    } catch {
        foreach ($target in $written) {
            $relative = $target.Substring($modsRoot.Length + 1)
            $backup = Join-Path $backupRoot $relative
            if (Test-Path -LiteralPath $backup -PathType Leaf) { Copy-Item -LiteralPath $backup -Destination $target -Force }
            elseif (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target }
        }
        throw
    }
    Write-Host "Installed / 安装完成。Backup / 备份：$backupRoot"
} catch {
    Write-Error $_
    exit 1
}
