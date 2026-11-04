# 把 obs-keyflow 加入当前用户的开机启动（写入「启动」文件夹快捷方式）。
#   .\install-autostart.ps1           安装
#   .\install-autostart.ps1 -Remove   移除
param([switch]$Remove)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$vbs = Join-Path $PSScriptRoot 'start.vbs'
$startup = [Environment]::GetFolderPath('Startup')
$lnk = Join-Path $startup 'obs-keyflow.lnk'

if ($Remove) {
    if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Output "已移除开机启动: $lnk" }
    else { Write-Output '未安装开机启动' }
    exit 0
}

if (-not (Get-Command python -ErrorAction SilentlyContinue) -and
    -not (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs\Python'))) {
    Write-Warning '未检测到 Python，安装后开机启动才能生效（https://www.python.org/downloads/）'
}

$sh = New-Object -ComObject WScript.Shell
$sc = $sh.CreateShortcut($lnk)
$sc.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$sc.Arguments = '"' + $vbs + '"'
$sc.WorkingDirectory = $repo
$sc.Description = 'obs-keyflow 按键显示服务'
$sc.WindowStyle = 7           # 最小化，避免闪窗
$sc.Save()

Write-Output "已安装开机启动: $lnk"
Write-Output "服务脚本: $vbs"
