@echo off
REM ResumeTailor Desktop launcher (Windows)
REM Launches the native desktop GUI (pywebview window + system tray).
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Create it first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

.venv\Scripts\python desktop.py
