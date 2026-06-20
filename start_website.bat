@echo off
cd /d "%~dp0"

set "PORT=8000"
set "URL=http://127.0.0.1:%PORT%/"

echo Checking for existing website service on port %PORT%...
powershell -NoProfile -Command "$processIds = @(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique); if ($processIds.Count -eq 0) { exit 2 }; foreach ($servicePid in $processIds) { Stop-Process -Id $servicePid -Force -ErrorAction Stop }; Start-Sleep -Seconds 1"
if "%ERRORLEVEL%"=="2" (
    echo No existing service was found on port %PORT%.
) else if not "%ERRORLEVEL%"=="0" (
    echo [ERROR] Failed to stop the existing service on port %PORT%.
    pause
    exit /b 1
)

if "%ERRORLEVEL%"=="0" (
    echo Existing service on port %PORT% was stopped.
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }" >nul 2>nul
if not "%ERRORLEVEL%"=="0" (
    echo [ERROR] Port %PORT% is still in use. Please close the old service manually.
    pause
    exit /b 1
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
