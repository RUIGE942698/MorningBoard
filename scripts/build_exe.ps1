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
$common = @("--noconfirm", "--clean", "--onefile", "--windowed", "--icon", "tools\csgo_bg.ico",
            "--add-data", "knowledge;knowledge", "--add-data", "tools;tools",
            "--add-data", "config.json;.", "--distpath", "dist_exe")
& $pyi -m PyInstaller @common --name MorningBoard    --workpath build_exe  --specpath . morning_show.py
& $pyi -m PyInstaller @common --name MorningBoardGen --workpath build_gen  --specpath . morning_evening.py

Write-Host "Build done. Outputs in dist_exe\"
