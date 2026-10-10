param([string]$GamePath, [switch]$InstallUE4SS, [switch]$ConfigureOffline, [switch]$NoUI)
$ErrorActionPreference = 'Stop'
$created = New-Object System.Collections.Generic.List[string]
function Get-Hash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $hasher.Dispose() }
}
function Assert-PlainPath([string]$Path) {
    $cursor = $Path
    while ($cursor) {
        if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Redirected destination / 目标路径存在重定向：$cursor"
        }
        $cursor = Split-Path -Parent $cursor
    }
}
function Copy-Missing([string]$Source, [string]$Target) {
    Assert-PlainPath $Target
    if (Test-Path -LiteralPath $Target) { return }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Target) -Force | Out-Null
    # Exclusive creation prevents overwriting a file created after the check.
    $inputStream = [IO.File]::OpenRead($Source)
    try {
        $outputStream = [IO.File]::Open($Target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
        $created.Add($Target)
        try { $inputStream.CopyTo($outputStream); $outputStream.Flush() } finally { $outputStream.Dispose() }
    } finally { $inputStream.Dispose() }
}
function Test-UE4SSComplete([string]$Win) {
    foreach ($relative in @('dwmapi.dll','ue4ss\UE4SS.dll','ue4ss\UE4SS-settings.ini')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Win $relative) -PathType Leaf)) { return $false }
    }
    return $true
}
try {
    if (-not [Environment]::Is64BitProcess -or [Environment]::OSVersion.Version.Major -lt 10) { throw 'Windows 10/11 x64 required / 需要 Windows 10/11 x64。' }
    if (Get-Process -Name AceCombat8 -ErrorAction SilentlyContinue) { throw 'Close AC8 first / 请先完全退出 AC8。' }
    if (-not $NoUI -and -not $GamePath) {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        [Windows.Forms.Application]::EnableVisualStyles()
        $form = New-Object Windows.Forms.Form
        $form.Text = 'AC8 Skin Manager - Setup / 安装'
        $form.ClientSize = New-Object Drawing.Size(610, 270)
        $form.StartPosition = 'CenterScreen'; $form.FormBorderStyle = 'FixedDialog'; $form.MaximizeBox = $false
        $label = New-Object Windows.Forms.Label
        $label.Text = 'Game folder / 游戏目录'; $label.SetBounds(18,18,550,22)
        $pathBox = New-Object Windows.Forms.TextBox; $pathBox.SetBounds(18,45,460,26)
        $browse = New-Object Windows.Forms.Button; $browse.Text = 'Browse / 选择'; $browse.SetBounds(486,43,105,28)
        $ue = New-Object Windows.Forms.CheckBox; $ue.Text = 'Install missing UE4SS files / 安装缺失的 UE4SS 文件'; $ue.SetBounds(18,90,570,26); $ue.Checked = $true
        $offline = New-Object Windows.Forms.CheckBox; $offline.Text = 'Create offline launch config / 生成离线启动配置'; $offline.SetBounds(18,124,570,26); $offline.Checked = $true
        $note = New-Object Windows.Forms.Label
        $note.Text = 'Compatible existing files and settings are kept. Offline campaign only.' + [Environment]::NewLine + '保留已有兼容文件和设置；仅用于离线单机战役。'
        $note.SetBounds(18,163,570,42)
        $ok = New-Object Windows.Forms.Button; $ok.Text = 'Install / 安装'; $ok.SetBounds(363,223,110,32); $ok.DialogResult = 'OK'
        $cancel = New-Object Windows.Forms.Button; $cancel.Text = 'Cancel / 取消'; $cancel.SetBounds(481,223,110,32); $cancel.DialogResult = 'Cancel'
        $browse.Add_Click({
            $picker = New-Object Windows.Forms.FolderBrowserDialog
            $picker.Description = 'Select the game root containing Game / 选择含 Game 的游戏根目录'
            if ($picker.ShowDialog() -eq 'OK') {
                $pathBox.Text = $picker.SelectedPath
                $ue.Checked = -not (Test-UE4SSComplete (Join-Path $picker.SelectedPath 'Game\Binaries\Win64'))
            }
            $picker.Dispose()
        })
        $form.Controls.AddRange(@($label,$pathBox,$browse,$ue,$offline,$note,$ok,$cancel))
        $form.AcceptButton = $ok; $form.CancelButton = $cancel
        if ($form.ShowDialog() -ne 'OK') { $form.Dispose(); exit 0 }
        $GamePath = $pathBox.Text.Trim().Trim('"'); $InstallUE4SS = $ue.Checked
        $ConfigureOffline = $offline.Checked; $form.Dispose()
    }
    if (-not $GamePath) { throw 'Select a game folder / 请选择游戏目录。' }
    $gameRoot = (Resolve-Path -LiteralPath $GamePath).Path.TrimEnd('\')
    if ($gameRoot -match '[^\x20-\x7e]') { throw 'This Lua runtime requires an ASCII game path / 此脚本运行时请使用纯 ASCII 游戏目录。' }
    $win = Join-Path $gameRoot 'Game\Binaries\Win64'
    $release = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'compatibility.json') -Encoding UTF8 -Raw | ConvertFrom-Json
    if ((Get-Hash (Join-Path $win 'AceCombat8.exe')) -ne $release.engine_sha256) { throw 'Unsupported AC8 build / 游戏版本不兼容。' }
    # The package inventory includes the optional UE4SS files.
    foreach ($row in $release.files) {
        if ((Get-Hash (Join-Path $PSScriptRoot $row.path)) -ne $row.sha256) { throw "Package checksum mismatch / 安装包校验失败：$($row.path)" }
    }
    Assert-PlainPath $win
    $runtime = Join-Path $win 'ue4ss\UE4SS.dll'; $proxy = Join-Path $win 'dwmapi.dll'
    $first = Join-Path $PSScriptRoot 'Prerequisites\UE4SS\Game\Binaries\Win64'
    # An existing runtime alone is not a working injection chain.
    if ((Test-Path -LiteralPath $proxy) -and (Get-Hash $proxy) -ne (Get-Hash (Join-Path $first 'dwmapi.dll'))) { throw 'Existing dwmapi.dll belongs to another loader / 已有 dwmapi.dll 与本包不同，请先处理加载器冲突。' }
    if (-not $InstallUE4SS) {
        if (-not (Test-Path -LiteralPath $runtime -PathType Leaf)) { throw 'Install UE4SS first / 请勾选安装缺失的 UE4SS 文件。' }
        if (-not (Test-UE4SSComplete $win)) { throw 'Incomplete UE4SS installation; select Install missing UE4SS files / UE4SS 不完整，请勾选安装缺失的 UE4SS 文件。' }
    }
    if ($InstallUE4SS) {
        if ((Test-Path -LiteralPath $runtime) -and $release.ue4ss_sha256 -notcontains (Get-Hash $runtime)) { throw 'Existing UE4SS version differs; preserve and migrate it first / 现有 UE4SS 版本不同，请先备份并迁移。' }
        if (-not (Test-Path -LiteralPath $proxy)) {
            foreach ($name in @('winmm.dll','version.dll','dinput8.dll','xinput1_3.dll')) {
                if (Test-Path -LiteralPath (Join-Path $win $name)) { throw "Another proxy loader exists; check it first / 请先核对已有代理加载器：$name" }
            }
        }
    }
    if ($ConfigureOffline) {
        $settings = Join-Path $gameRoot 'EasyAntiCheat\Settings.json'
        $offlineConfig = Get-Content -LiteralPath $settings -Encoding UTF8 -Raw | ConvertFrom-Json
        if (-not $offlineConfig.productid -or -not $offlineConfig.sandboxid -or -not $offlineConfig.deploymentid) { throw 'Incomplete original EAC settings / 原版 EAC 配置不完整。' }
        $offlineConfig | Add-Member -NotePropertyName allow_null_client -NotePropertyValue 'true' -Force
        $offlineConfig | Add-Member -NotePropertyName executable -NotePropertyValue 'Game/Binaries/Win64/AceCombat8.exe' -Force
        $offlineConfig | Add-Member -NotePropertyName hide_bootstrapper -NotePropertyValue 'true' -Force
        $offlineConfig | Add-Member -NotePropertyName hide_gui -NotePropertyValue 'true' -Force
        $offlinePath = Join-Path $gameRoot 'EasyAntiCheat\AC8SkinManager_Offline.json'
        Assert-PlainPath $offlinePath
        if (Test-Path -LiteralPath $offlinePath) {
            $existingOffline = Get-Content -LiteralPath $offlinePath -Encoding UTF8 -Raw | ConvertFrom-Json
            if ($existingOffline.allow_null_client -ne 'true' -or $existingOffline.executable -ne $offlineConfig.executable -or
                $existingOffline.productid -ne $offlineConfig.productid -or $existingOffline.sandboxid -ne $offlineConfig.sandboxid -or
                $existingOffline.deploymentid -ne $offlineConfig.deploymentid) {
                throw 'Existing offline configuration differs; back it up first / 现有离线配置不同，请先备份处理。'
            }
        }
        $appid = Join-Path $win 'steam_appid.txt'
        Assert-PlainPath $appid
        if ((Test-Path -LiteralPath $appid) -and (Get-Content -LiteralPath $appid -Raw).Trim() -ne '2288340') { throw 'Existing steam_appid.txt differs / 已有 steam_appid.txt 内容不同。' }
    }
    if ($InstallUE4SS) {
        foreach ($file in Get-ChildItem -LiteralPath $first -File -Recurse) {
            Copy-Missing $file.FullName (Join-Path $win $file.FullName.Substring($first.Length + 1))
        }
    }
    if ($ConfigureOffline) {
        $scratch = Join-Path ([IO.Path]::GetTempPath()) ('AC8-offline-' + [Guid]::NewGuid().ToString('N') + '.json')
        try {
            [IO.File]::WriteAllText($scratch, (ConvertTo-Json $offlineConfig -Depth 32), (New-Object Text.UTF8Encoding($false)))
            Copy-Missing $scratch $offlinePath
            [IO.File]::WriteAllText($scratch, '2288340', [Text.Encoding]::ASCII)
            Copy-Missing $scratch $appid
        } finally { Remove-Item -LiteralPath $scratch -Force -ErrorAction SilentlyContinue }
    }
    # A child process keeps the core installer's exit from bypassing rollback here.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'Install-Manager.ps1') -GamePath $gameRoot
    if ($LASTEXITCODE -ne 0) { throw 'Manager installation stopped / 管理器安装未完成。' }
    $created.Clear()
    Write-Host 'Installation completed / 安装完成。'
    if ($ConfigureOffline) {
        Write-Host 'Steam launch options / Steam 启动选项（离线单机）：'
        Write-Host 'cmd /d /c "set EOS_USE_ANTICHEATCLIENTNULL=1&& %command% -anticheat_settings=AC8SkinManager_Offline.json"'
    } else { Write-Host 'Keep your existing offline launch settings / 请沿用已有离线启动参数。' }
} catch {
    # Only files exclusively created by this run are removed.
    foreach ($file in $created) { Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue }
    Write-Error $_
    exit 1
}
