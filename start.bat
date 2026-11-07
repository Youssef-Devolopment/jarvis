@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo [*] JARVIS console server - logs appear below.
echo [*] Close this window to stop JARVIS.
python run.py
