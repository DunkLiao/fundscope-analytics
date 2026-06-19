@echo off
setlocal

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo Cannot find venv\Scripts\activate.bat
    pause
    exit /b 1
)

call "venv\Scripts\activate.bat"
python "fundlist\GetFundBackSiteToCsv.py"

pause
