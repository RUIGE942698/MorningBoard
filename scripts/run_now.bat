@echo off
rem Manual launch of MorningBoard (dev / on-demand)
rem Prefers the official Python in LOCALAPPDATA, falls back to PATH pythonw.
cd /d "%~dp0"
set "PYW=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" "%~dp0..\morning_show.py"
    exit /b 0
)
where pythonw >nul 2>nul && (start "" pythonw "%~dp0..\morning_show.py") || (start "" python "%~dp0..\morning_show.py")
