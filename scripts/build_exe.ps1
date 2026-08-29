# build_exe.ps1 - Build MorningBoard Windows exe (PyInstaller onefile)
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_exe.ps1
# Requires: a venv with PyInstaller, e.g.
#   "C:\Program Files\Python312\python.exe" -m venv C:\Users\39970\.workbuddy\binaries\python\envs\pyinstaller
#   C:\Users\39970\.workbuddy\binaries\python\envs\pyinstaller\Scripts\pip.exe install pyinstaller
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
$pyi  = "C:\Users\39970\.workbuddy\binaries\python\envs\pyinstaller\Scripts\python.exe"
if (-not (Test-Path $pyi)) { Write-Host "PyInstaller venv not found: $pyi"; exit 1 }

Set-Location $proj
# 打新版本前清掉上一次的中间产物/输出，避免堆出几十 MB（历史教训：堆过 6 个目录共 ~100MB）
foreach ($d in @("build_exe", "build_gen", "dist_exe")) {
    if (Test-Path $d) { Remove-Item -Recurse -Force $d }
}
$common = @("--noconfirm", "--onefile", "--windowed", "--icon", "tools\csgo_bg.ico",
            "--add-data", "knowledge;knowledge", "--add-data", "tools;tools",
            "--add-data", "config.json;.", "--distpath", "dist_exe")
& $pyi -m PyInstaller @common --name MorningBoard    --workpath build_exe  --specpath . morning_show.py
& $pyi -m PyInstaller @common --name MorningBoardGen --workpath build_gen  --specpath . morning_evening.py

Write-Host "Build done. Outputs in dist_exe\"
Write-Host "Copy MorningBoard.exe & MorningBoardGen.exe to ..\MorningBoard_Windows版\ to ship."
