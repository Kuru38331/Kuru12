@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto pythonfallback
py -3 -m venv .venv
if errorlevel 1 goto failed
goto install
:pythonfallback
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" start.py
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo.
echo Could not start. Install Python 3.10 or newer, check your connection and the error above.
pause
exit /b 1
