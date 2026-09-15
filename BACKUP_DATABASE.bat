@echo off
setlocal
cd /d "%~dp0"
if not exist "data\conest_catalog.db" (
    echo Database not found.
    pause
    exit /b 1
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\backup_database.py
) else (
    py -3 tools\backup_database.py
)
if errorlevel 1 echo Backup failed. Keep your original database and review the message above.
pause
