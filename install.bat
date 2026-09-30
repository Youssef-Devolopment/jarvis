@echo off
REM JARVIS installer — creates venv + installs all requirement groups
cd /d "%~dp0"
where py >nul 2>nul || where python >nul 2>nul
if errorlevel 1 (
  echo [!] Install Python 3.10+ from https://www.python.org/downloads/ first.
  exit /b 1
)
if not exist .venv (
  echo [*] Creating virtualenv...
  py -3.10 -m venv .venv 2>nul || python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [*] Installing requirements (this takes a few minutes)...
python -m pip install --upgrade pip
pip install -r requirements.txt
echo [*] Installing Playwright Chromium (for browser skills)...
python -m playwright install chromium
echo.
echo [ok] Done. Next steps:
echo   1. copy .env.example .env  (then edit API keys)
echo   2. start.bat  (console)  or  desktop.bat  (tray mode)
