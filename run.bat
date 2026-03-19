@echo off
TITLE PAIKS - Local Server Launcher

:: Using simple goto for maximum compatibility
if not exist ".venv\Scripts\python.exe" goto ENV_ERROR

echo Starting PAIKS Launcher...
".venv\Scripts\python.exe" launcher.py
goto :EOF

:ENV_ERROR
echo [ERROR] Virtual environment (.venv) not found.
pause
exit /b 1
