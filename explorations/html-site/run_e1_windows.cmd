@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ==================================================
echo SRW Web E1 exploration - READ ONLY
echo This tool attaches to the ALREADY RUNNING Windows EXE.
echo It does not start another SRW service or write data.
echo ==================================================
echo.

if not "%~1"=="" (
    set "SRW_DATA_ROOT=%~1"
)

if not defined SRW_DATA_ROOT (
    echo Open the SRW Windows EXE first.
    echo Its default data directory is the "data" folder
    echo next to the EXE application root.
    echo.
    echo You may drag the EXE data folder onto this BAT
    echo instead of typing its path.
    echo.
    set /p "SRW_DATA_ROOT=Full path to running EXE data directory: "
)

if not defined SRW_DATA_ROOT (
    echo ERROR: no data directory supplied.
    pause
    exit /b 2
)

if not exist "%SRW_DATA_ROOT%\app.lock\instance.json" (
    echo.
    echo ERROR: cannot locate "%SRW_DATA_ROOT%\app.lock\instance.json"
    echo Keep the EXE running and select its actual DATA directory.
    echo.
    pause
    exit /b 3
)

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_COMMAND=py -3"
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_COMMAND=python"
    ) else (
        echo ERROR: Python 3 not found on PATH.
        echo Install Python 3, or launch serve_e1.py with your trusted Python interpreter.
        pause
        exit /b 4
    )
)

echo Attaching to EXE, verifying identity and opening browser...
echo To stop the exploration, press Ctrl+C in this window.
echo.
%PYTHON_COMMAND% "%~dp0serve_e1.py" --data-root "%SRW_DATA_ROOT%" --port 8877 --open-browser
set "RESULT=%ERRORLEVEL%"

echo.
if not "%RESULT%"=="0" (
    echo E1 could not attach. Check the message above.
    echo Do not close the EXE to resolve an E1 error.
)
pause
exit /b %RESULT%
