# Remove MorningBoard.
#  - deletes the scheduled task (evening briefing)
#  - deletes the old logon launcher if still present
$null = & schtasks /Delete /TN "MorningBoard-Generate" /F 2>&1
Write-Host "[OK] Removed task MorningBoard-Generate."
$Launcher = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\MorningBoard.vbs"
if (Test-Path $Launcher) {
    Remove-Item $Launcher -Force
    Write-Host "[OK] Removed old startup launcher."
} else {
    Write-Host "[--] No old startup launcher found."
}
Write-Host "[OK] Done. The desktop shortcut can still open the briefing manually."
