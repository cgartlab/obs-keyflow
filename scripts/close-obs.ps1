# 干净关闭 OBS Studio（处理"确认退出"对话框），用于脚本化重启 OBS。
#   .\close-obs.ps1           正常关闭，最多等 20 秒
#   .\close-obs.ps1 -Timeout 40
#   .\close-obs.ps1 -Force    等待超时后强制结束
param(
    [int]$Timeout = 20,
    [switch]$Force
)

$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

$proc = Get-Process obs64 -ErrorAction SilentlyContinue
if (-not $proc) { Write-Output 'OBS 未运行'; exit 0 }

$obsPid = $proc.Id
$proc.CloseMainWindow() | Out-Null
Start-Sleep -Seconds 2

$root = [System.Windows.Automation.AutomationElement]::RootElement
$btnCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button)

$deadline = (Get-Date).AddSeconds($Timeout)
while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process -Id $obsPid -ErrorAction SilentlyContinue)) {
        Write-Output 'OBS 已正常退出'
        exit 0
    }
    $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($w in $wins) {
        try { if ($w.Current.ProcessId -ne $obsPid) { continue } } catch { continue }
        foreach ($b in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)) {
            if ($b.Current.Name -match '^(是|Yes|确定|OK)$') {
                try {
                    $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
                    Write-Output "已确认对话框: $($b.Current.Name)"
                } catch { }
                break
            }
        }
    }
    Start-Sleep -Milliseconds 700
}

if (Get-Process -Id $obsPid -ErrorAction SilentlyContinue) {
    if ($Force) {
        Stop-Process -Id $obsPid -Force
        Write-Output '超时，已强制结束 OBS（下次启动可能提示上次崩溃）'
        exit 2
    }
    Write-Output '超时，OBS 仍在运行；加 -Force 可强制结束'
    exit 1
}
Write-Output 'OBS 已退出'
exit 0
