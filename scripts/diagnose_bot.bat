@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

cd /d "%~dp0.."

set "LOG_DIR=%CD%\data\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set "LOG_FILE=%LOG_DIR%\run_bot.log"

echo ============================================================
echo  Mail Bot diagnosis
echo ============================================================
echo Project: %CD%
echo Log file: %LOG_FILE%
echo.

call :find_python
if errorlevel 1 goto :fail

echo [OK] Python command: %PY_CMD%
%PY_CMD% --version
if errorlevel 1 (
    echo [ERROR] Python version check failed. Exit code: !ERRORLEVEL!
    goto :fail
)

if not exist "%CD%\.env" (
    echo [ERROR] .env file was not found.
    echo         Copy .env.example.txt to .env and fill in the values.
    goto :fail
)
echo [OK] .env file found.

echo.
echo [STEP] Checking required Python packages...
%PY_CMD% -c "import requests, urllib3, dotenv; print('[OK] required packages are installed')"
if errorlevel 1 (
    echo.
    echo [ERROR] Required Python packages are missing or broken. Exit code: !ERRORLEVEL!
    echo         Run this command from the project folder:
    echo         %PY_CMD% -m pip install -r requirements.txt
    goto :fail
)

echo.
echo [STEP] Checking Python syntax...
%PY_CMD% -m py_compile "%CD%\src\mail_bot.pyw"
if errorlevel 1 (
    echo.
    echo [ERROR] Python syntax check failed. Exit code: !ERRORLEVEL!
    goto :fail
)
echo [OK] Syntax check passed.

echo.
echo [STEP] Running one-time connection check...
%PY_CMD% "%CD%\src\mail_bot.pyw" --check-once
if errorlevel 1 (
    echo.
    echo [ERROR] One-time connection check failed. Exit code: !ERRORLEVEL!
    echo         See the messages above or open the log file:
    echo         %LOG_FILE%
    goto :fail
)
echo [OK] One-time connection check passed.

echo.
echo ============================================================
echo  Diagnosis passed
echo ============================================================
echo The bot can be started in the background with scripts\run_bot.bat.
pause
exit /b 0

:find_python
set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3"
    exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=python"
    exit /b 0
)

echo [ERROR] Python was not found.
echo         Install Python 3 and enable "Add python.exe to PATH".
exit /b 1

:fail
set "BOT_EXIT=%ERRORLEVEL%"
if "%BOT_EXIT%"=="0" set "BOT_EXIT=1"

echo.
echo ============================================================
echo  Diagnosis failed. Exit code: %BOT_EXIT%
echo ============================================================
echo Keep this window open and send the messages above to the maintainer.
pause
exit /b %BOT_EXIT%
