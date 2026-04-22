@echo off
TITLE PAIKS - Local Server Launcher

if exist ".venv\Scripts\python.exe" goto START_LAUNCHER

echo [*] Virtual environment not found. 
echo [*] Creating new Python virtual environment... (This may take a minute)
call python -m venv .venv
if errorlevel 1 goto VENV_ERROR

echo [*] Virtual environment created successfully.

:START_LAUNCHER
echo [*] Starting PAIKS Launcher...
call ".venv\Scripts\python.exe" launcher.py
pause
goto :EOF

:VENV_ERROR
echo [ERROR] Failed to create virtual environment. Ensure Python 3.13+ is installed and in your PATH.
pause
exit /b 1
