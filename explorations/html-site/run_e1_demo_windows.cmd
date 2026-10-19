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

rem This launcher must live at REPO_ROOT\explorations\html-site\
rem Dragging/copying only the CMD or the html-site folder cannot supply the
rem Python backend; the packaged START_HERE.cmd preserves the full layout.
rem Keep .. segments intact: Windows filesystem resolves them when opening
rem paths. Prior FOR/PUSHD canonicalization attempted to use the wrong directory.
rem The packaged top-level START_HERE.cmd may set SRW_E1_PACKAGE_ROOT.
if defined SRW_E1_PACKAGE_ROOT (
    set "SRW_REPO_ROOT=%SRW_E1_PACKAGE_ROOT%"
) else (
    set "SRW_REPO_ROOT=%~dp0..\.."
)
if not exist "%SRW_REPO_ROOT%\requirements-ci.txt" goto :missing_sources
if not exist "%SRW_REPO_ROOT%\browser_acceptance\serve.py" goto :missing_sources
if not exist "%SRW_REPO_ROOT%\backend\srw\api\app.py" goto :missing_sources
if not exist "%SRW_REPO_ROOT%\convergence_tests\knowledge_fixture.py" goto :missing_sources
if not exist "%SRW_REPO_ROOT%\frontend\dist\index.html" goto :missing_sources
if /i "%~1"=="--check-layout" (
    echo PASS: verified complete SRW E1 source bundle layout.
    echo Root: "%SRW_REPO_ROOT%"
    exit /b 0
)

set "E1_BOOTSTRAP="
where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 -c "import sys; raise SystemExit(sys.version_info[:2] != (3, 12))" >nul 2>&1
    if not errorlevel 1 set "E1_BOOTSTRAP=py -3.12"
)
if not defined E1_BOOTSTRAP (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(sys.version_info[:2] != (3, 12))" >nul 2>&1
        if not errorlevel 1 set "E1_BOOTSTRAP=python"
    )
)
if not defined E1_BOOTSTRAP (
    echo ERROR: Python 3.12 is required, via py -3.12 or python.
    echo Neither installation nor system PATH will be changed.
    if /i "%~1"=="--smoke" exit /b 3
    if /i "%~2"=="--smoke" exit /b 3
    pause
    exit /b 3
)

set "E1_VENV=%~dp0.e1-demo-venv"
set "E1_PYTHON=%E1_VENV%\Scripts\python.exe"
set "E1_READY=%E1_VENV%\deps-20261019.ready"

if not exist "%E1_PYTHON%" (
    echo Creating isolated E1 virtual environment...
    %E1_BOOTSTRAP% -m venv "%E1_VENV%"
    if errorlevel 1 goto :failed
)

if not exist "%E1_READY%" (
    echo Installing pinned C11 source dependencies into E1-only venv...
    "%E1_PYTHON%" -m pip install --disable-pip-version-check -r "%SRW_REPO_ROOT%\requirements-ci.txt"
    if errorlevel 1 goto :failed
    echo ready>"%E1_READY%"
)

set "E1_DEMO_SCRIPT=run_e1_demo.py"
set "E1_DEMO_ARGS=--open-browser"
if /i "%~1"=="--e2" set "E1_DEMO_SCRIPT=run_e2_demo.py"
if /i "%~1"=="--e3" set "E1_DEMO_SCRIPT=run_e3_demo.py"
if /i "%~1"=="--e4" set "E1_DEMO_SCRIPT=run_e4_demo.py"
if /i "%~1"=="--smoke" set "E1_DEMO_ARGS=--smoke"
if /i "%~2"=="--smoke" set "E1_DEMO_ARGS=--smoke"

echo.
echo Starting %E1_DEMO_SCRIPT% with an isolated temporary C11 backend...
echo No user records are used. Browser opens automatically in normal mode.
echo.
rem We CD into the script folder at startup. Pass only the basename here;
rem expanding %%~dp0 adjacent to another %%VAR%% double-prefixed the path on CMD.
"%E1_PYTHON%" "%E1_DEMO_SCRIPT%" %E1_DEMO_ARGS%
set "E1_EXIT=%ERRORLEVEL%"
echo.
if not "%E1_EXIT%"=="0" (
    echo E1 demo did not pass its start-up checks.
    echo See the error above; no real SRW database was used.
)
echo The synthetic server has stopped.
if /i "%E1_DEMO_ARGS%"=="--smoke" exit /b %E1_EXIT%
pause
exit /b %E1_EXIT%

:missing_sources
echo.
echo ERROR: INCOMPLETE SRW E1 SOURCE PACKAGE.
echo This is a source-layout problem, not a C11 backend startup failure.
echo Expected repository root: "%SRW_REPO_ROOT%"
echo.
echo Required sibling folders under that root:
echo   backend\srw\
echo   frontend\dist\
echo   browser_acceptance\serve.py
echo   convergence_tests\knowledge_fixture.py
echo   explorations\html-site\
echo   requirements-ci.txt
echo.
echo FIX: Download the single GitHub Actions demo artifact ZIP.
echo Extract the ENTIRE ZIP, then run START_HERE.cmd at its top level.
echo Do not download only run_e1_demo_windows.cmd or the html-site folder.
echo No real SRW data was opened or modified.
pause
exit /b 2

:failed
echo ERROR: unable to prepare isolated E1 Python environment.
echo The official EXE installation was not modified.
pause
exit /b 4
