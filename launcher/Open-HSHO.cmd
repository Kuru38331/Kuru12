@echo off
cd /d "%~dp0"
if exist "%~dp0Kuru12.exe" (
 start "" "%~dp0Kuru12.exe"
 exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Launcher.ps1"
if errorlevel 1 pause
