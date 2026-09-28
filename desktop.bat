@echo off
REM JARVIS Desktop Mode — no console window, opens fresh browser tab
cd /d "%~dp0"
start "" /B .venv\Scripts\pythonw.exe desktop.py --open
exit
