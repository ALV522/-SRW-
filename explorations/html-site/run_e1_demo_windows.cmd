@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title SRW Web E1 - Synthetic Source Demo

echo.
echo ============================================================
echo       SRW HTML E1 - REAL CORE, SYNTHETIC DATA
echo ============================================================
echo This demo does NOT use the Windows EXE.
echo It runs a real C11 backend with a TEMPORARY database.
echo No existing SRW data, resume or provider key is opened.
echo Press Ctrl+C to stop. Temporary data will be deleted.
echo.

for %%I in ("%~dp0..\..") do set "SRW_REPO_ROOT=%%~fI"
if not exist "%SRW_REPO_ROOT%\requirements-ci.txt" (
    echo ERROR: full exploration branch source checkout is required.
    pause
    exit /b 2
)
if not exist "%SRW_REPO_ROOT%\browser_acceptance\serve.py" (
    echo ERROR: missing browser_acceptance/serve.py.
    pause
    exit /b 2
)

where py >nul 2>&1
if errorlevel 1 (
    echo ERROR: Windows Python launcher not found.
    echo Install Python 3.12 with the py launcher first.
    pause
    exit /b 3
)
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.12 is required for the pinned E1 source demo.
    echo This script will not change or install your system Python.
    pause
    exit /b 3
)

set "E1_VENV=%~dp0.e1-demo-venv"
set "E1_PYTHON=%E1_VENV%\Scripts\python.exe"
set "E1_READY=%E1_VENV%\deps-20261019.ready"

if not exist "%E1_PYTHON%" (
    echo Creating isolated E1 virtual environment...
    py -3.12 -m venv "%E1_VENV%"
    if errorlevel 1 goto :failed
)

if not exist "%E1_READY%" (
    echo Installing pinned C11 source dependencies into E1-only venv...
    "%E1_PYTHON%" -m pip install --disable-pip-version-check -r "%SRW_REPO_ROOT%\requirements-ci.txt"
    if errorlevel 1 goto :failed
    echo ready>"%E1_READY%"
)

echo.
echo Starting real SRW C11 synthetic backend + GET-only E1 web...
echo A browser should open automatically. No user records are used.
echo.
"%E1_PYTHON%" "%~dp0run_e1_demo.py" --open-browser
set "E1_EXIT=%ERRORLEVEL%"
echo.
if not "%E1_EXIT%"=="0" (
    echo E1 demo did not pass its start-up checks.
    echo See the error above; no real SRW database was used.
)
echo The synthetic server has stopped.
pause
exit /b %E1_EXIT%

:failed
echo ERROR: unable to prepare isolated E1 Python environment.
echo The official EXE installation was not modified.
pause
exit /b 4
