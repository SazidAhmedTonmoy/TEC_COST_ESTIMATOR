@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set "CONEST_PYTHON=python"
) else (
    set "CONEST_PYTHON=py -3"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local Python environment...
    %CONEST_PYTHON% -m venv .venv
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -c "import openpyxl, pdfplumber, PIL" >nul 2>&1
if errorlevel 1 (
    echo Installing the Excel, PDF and image dependencies...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    if errorlevel 1 goto :failed
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
)

echo Starting TEC ConEst...
".venv\Scripts\python.exe" app.py %*
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Setup could not be completed. Review the message above.
pause
exit /b 1
