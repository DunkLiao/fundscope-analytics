@echo off
cd /d "%~dp0"

set "PORT=8000"
set "URL=http://127.0.0.1:%PORT%/"

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
if "%ERRORLEVEL%"=="0" (
    echo Website is already running: %URL%
    start "" "%URL%"
    exit /b 0
)

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) else (
    echo [WARN] venv\Scripts\activate.bat was not found. Using Python from PATH.
)

if not exist "db\funddata.db" (
    echo [WARN] db\funddata.db was not found.
    echo        Run the fund list update batch file before querying NAV data.
)

echo Starting fund NAV website: %URL%
echo Press Ctrl+C in this window to stop the website.

start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process '%URL%'"
python -m uvicorn fundlist.app:app --host 127.0.0.1 --port %PORT%

echo.
echo Website stopped.
pause
