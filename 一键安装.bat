@echo off
setlocal
chcp 65001 >nul
title MorningBoard Installer
cd /d "%~dp0"

echo.
echo  ============================================
echo    MorningBoard  (Daily Briefing)  Installer
echo  ============================================
echo.
echo  Launching installer, please wait...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_autostart.ps1"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo  [OK] Install finished.
) else (
    echo  [exit code %RC%] Install not completed, see messages above.
)
echo.
echo  Press any key to close...
pause >nul
exit /b %RC%
