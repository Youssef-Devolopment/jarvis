@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
start "" /B pythonw run.py