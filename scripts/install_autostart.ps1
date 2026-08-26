# -*- coding: utf-8 -*-
# ============================================================
#  每日播报 MorningBoard  一键安装
#  双击 "一键安装.bat" 即可（本脚本会被它用 -ExecutionPolicy Bypass 调用）
#
#  做什么：
#   1. 自动寻找一个可用、且带 tkinter 的 Python
#   2. 注册每晚 20:00 的计划任务 MorningBoard-Generate（联播 19:00 播完后
#      生成缓存并自动弹出，错过自动补跑；且不再开机自动弹窗）
#   3. 创建桌面快捷方式 "每日播报"（只读缓存，随时可点开）
#   4. 校验并给出中文结果
# ============================================================
param([string]$PythonPath = "")

$ErrorActionPreference = "Stop"
# 让中文提示在控制台正确显示（配合 一键安装.bat 里的 chcp 65001）
try {
    $OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
} catch {}
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path      # 本脚本目录(scripts/)
$Root = Split-Path -Parent $Dir                              # 项目根目录( MorningBoard_Share )
$EveningScript = Join-Path $Root "morning_evening.py"
$ShowScript    = Join-Path $Root "morning_show.py"

function Write-Step([string]$msg) { Write-Host ("  " + $msg) }

function Test-Tk([string]$py) {
    if (-not $py -or -not (Test-Path $py)) { return $false }
    try {
        $null = & $py -c "import tkinter; r = tkinter.Tk(); r.destroy()" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Resolve-Python([string]$hint) {
    if ($hint -ne "" -and (Test-Tk $hint)) { return $hint }          # 1) 显式指定
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and (Test-Tk $cmd.Source)) { return $cmd.Source }       # 2) PATH 上的 python
    $cands = @()
    Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $cands += $_.FullName }
    Get-ChildItem "$env:ProgramFiles\Python*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $cands += $_.FullName }
    Get-ChildItem "${env:ProgramFiles(x86)}\Python*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $cands += $_.FullName }
    Get-ChildItem "C:\Python*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $cands += $_.FullName }
    foreach ($c in ($cands | Sort-Object -Descending)) {
        if (Test-Tk $c) { return $c }
    }
    return $null
}

Write-Host ""
Write-Host "============================================="
Write-Host "  每日播报 MorningBoard  一键安装"
Write-Host "============================================="

# ---- 1. 找 Python ----
Write-Host "[1/4] 正在查找可用的 Python (含 tkinter)..."
$Py = Resolve-Python $PythonPath
if (-not (Test-Tk $Py)) {
    Write-Host ""
    Write-Host "   [!!] 没找到可用的 Python（需要能开 Tk 窗口）。"
    Write-Host "       请先到 python.org 下载安装 Python 3.10+："
    Write-Host "         https://www.python.org/downloads/ "
    Write-Host "       安装时勾选默认选项即可（已包含 tkinter）。"
    Write-Host "       装好后重新双击『一键安装.bat』。"
    Write-Host ""
    Write-Host "       正在打开下载页面..."
    try { Start-Process "https://www.python.org/downloads/" } catch {}
    exit 1
}
$PyW = Join-Path (Split-Path -Parent $Py) "pythonw.exe"
if (-not (Test-Path $PyW)) { $PyW = $Py }
Write-Step ("Python : " + $Py)
Write-Step ("python : " + $PyW)

# ---- 2. 注册每晚 20:00 计划任务 ----
Write-Host "[2/4] 注册每晚 20:00 自动任务 MorningBoard-Generate ..."
$xmlGen = @'
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>MorningBoard: every 20:00, collect info after CCTV news (19:00) and pop up the daily briefing</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T20:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT15M</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"@PYW@"</Command>
      <Arguments>"@EVENING@"</Arguments>
    </Exec>
  </Actions>
</Task>
'@
$xmlGen = $xmlGen.Replace("@PYW@", $PyW).Replace("@EVENING@", $EveningScript)
$tmp = Join-Path $Dir "task_MorningBoard-Generate.xml"
try {
    [System.IO.File]::WriteAllText($tmp, $xmlGen, [System.Text.Encoding]::Unicode)
    $out = & schtasks /Create /F /TN "MorningBoard-Generate" /XML $tmp 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("   [!!] 任务计划被拒绝：{0}" -f $out)
        Write-Host "       若在受限环境，请用普通（非沙箱）PowerShell 或用管理员身份重试。"
        exit 1
    }
    Write-Step "任务已注册：MorningBoard-Generate（每天 20:00）。"
} finally {
    Remove-Item $tmp -ErrorAction SilentlyContinue
}

# ---- 3. 清理旧的登录自动弹窗 ----
$oldLauncher = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\MorningBoard.vbs"
if (Test-Path $oldLauncher) {
    Remove-Item $oldLauncher -Force -ErrorAction SilentlyContinue
    Write-Step "已移除旧的“开机自启弹窗”（不再开机弹窗）。"
}

# ---- 4. 创建快捷方式（桌面 + 包文件夹） ----
Write-Host "[3/4] 创建快捷方式『每日播报』..."
$ico = Join-Path $Root "tools\csgo_bg.ico"
$ws = New-Object -ComObject WScript.Shell
$lnkTargets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) "每日播报.lnk"),
    (Join-Path $Root "打开每日播报.lnk")
)
foreach ($lnkPath in $lnkTargets) {
    try {
        $lnk = $ws.CreateShortcut($lnkPath)
        $lnk.TargetPath = $PyW
        $lnk.Arguments = ('"' + $ShowScript + '"')
        $lnk.WorkingDirectory = $Root
        if (Test-Path $ico) { $lnk.IconLocation = ("{0},0" -f $ico) }
        $lnk.Description = "每日播报 MorningBoard"
        $lnk.Save()
        if (Test-Path $lnkPath) { Write-Step ("快捷方式已创建：" + $lnkPath) }
        else { Write-Host "   [!!] 快捷方式可能未创建成功：$lnkPath" }
    } catch {
        Write-Host ("   [!] 创建快捷方式失败（{0}）：{1}" -f $lnkPath, $_.Exception.Message)
    }
}

# ---- 5. 校验并总结 ----
Write-Host "[4/4] 校验..."
& schtasks /Query /TN "MorningBoard-Generate" /FO LIST 2>$null | Select-String -Pattern "TaskName|Next Run|Status|Task To Run" | ForEach-Object { Write-Step $_.Line }

Write-Host ""
Write-Host "  ──────────────────────────────────────"
Write-Host "   ✔ 安装完成！"
Write-Host "    · 每晚 20:00（联播 19:00 播完后）自动收集并弹出今日播报。"
Write-Host "    · 想立刻看：双击桌面『每日播报』（只读缓存，秒开）。"
Write-Host "    · 换自选基金：编辑 config.json 里 funds 列表。"
Write-Host "  ──────────────────────────────────────"
Write-Host ""
exit 0
