@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" typecraft.py
) else (
    py -3 -c "import sys" >nul 2>nul
    if errorlevel 1 (
        python -c "import sys" >nul 2>nul
        if errorlevel 1 (
            powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0missing-python.ps1"
            echo Install Python with Tcl/Tk: https://www.python.org/downloads/windows/
            pause
            exit /b 1
        ) else (
            python typecraft.py
        )
    ) else (
        py -3 typecraft.py
    )
)
if errorlevel 1 (
    echo.
    echo Typecraft could not start. See the instructions above or README.md.
    pause
)
