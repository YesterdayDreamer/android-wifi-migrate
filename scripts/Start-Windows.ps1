param([string]$Python, [switch]$SetupOnly)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
Write-Host 'WiFi Migrate'
$environmentPython = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $environmentPython)) {
    if (-not $Python) {
        $candidates = @()
        foreach ($commandName in 'python','python3') {
            $command = Get-Command $commandName -ErrorAction SilentlyContinue
            if ($command -and $command.Source -notmatch '\\WindowsApps\\') { $candidates += $command.Source }
        }
        foreach ($registryRoot in 'HKCU:\Software\Python\PythonCore','HKLM:\Software\Python\PythonCore') {
            Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue | ForEach-Object {
                $installKey = Join-Path $_.PSPath 'InstallPath'
                if (Test-Path -LiteralPath $installKey) {
                    $installPath = (Get-Item -LiteralPath $installKey).GetValue('')
                    if ($installPath) { $candidates += (Join-Path $installPath 'python.exe') }
                }
            }
        }
        foreach ($candidate in $candidates) {
            if (Test-Path -LiteralPath $candidate) {
                & $candidate -c 'import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>$null
                if ($LASTEXITCODE -eq 0) { $Python = $candidate; break }
            }
        }
    }
    if (-not $Python) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Title = '请选择已安装的 Python 3.10 或更新版本的 python.exe'
        $dialog.Filter = 'Python|python.exe'
        if ($dialog.ShowDialog() -ne 'OK') { throw '未选择 Python。请安装 Python 3.10+，或选择现有 Python。' }
        $Python = $dialog.FileName
    }
    & $Python -c 'import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)'
    if ($LASTEXITCODE -ne 0) { throw '需要 Python 3.10 或更新版本。' }
    Write-Host '首次启动：在项目内创建独立环境。随后仅联网下载运行依赖，不上传 WiFi 数据。'
    & $Python -m venv (Join-Path $project '.venv')
    if ($LASTEXITCODE -ne 0) { throw '独立环境创建失败。' }
}
& $environmentPython -c "import importlib.util,sys;sys.exit(0 if all(importlib.util.find_spec(n) is not None for n in ('qrcode','png','Crypto')) else 1)"
if ($LASTEXITCODE -ne 0) {
    & $environmentPython -m pip install --disable-pip-version-check -r (Join-Path $project 'requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        if ($SetupOnly) { throw '依赖下载失败，可按 README 手动安装。' }
        Write-Warning '依赖下载未完成。仍可尝试打开已有配置及导出 CSV/JSON；二维码和加密备份可能不可用。'
    }
}
if ($SetupOnly) { Write-Host '项目环境已准备好。'; exit 0 }
& $environmentPython (Join-Path $project 'launch.py') gui
exit $LASTEXITCODE
