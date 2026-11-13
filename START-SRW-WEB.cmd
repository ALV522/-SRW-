@echo off
setlocal DisableDelayedExpansion
set "APPROOT=%~dp0"
set "PYTHON=%APPROOT%runtime\python.exe"
set "WORKSPACE=%LOCALAPPDATA%\SRW\DualCarrierV0"
set "KNOWLEDGE=%APPROOT%knowledge\active"
set "REUSE="

if not defined LOCALAPPDATA (
  echo [SRW] ERROR: LOCALAPPDATA is unavailable.
  pause
  exit /b 2
)
if not exist "%APPROOT%VERSION_POLICY.json" (
  echo [SRW] ERROR: Run this launcher from the extracted Q1R10 application root.
  pause
  exit /b 2
)
if not exist "%PYTHON%" (
  echo [SRW] ERROR: embedded runtime\python.exe was not found.
  pause
  exit /b 2
)
if not exist "%APPROOT%scripts\start_local_web.py" (
  echo [SRW] ERROR: scripts\start_local_web.py was not found.
  pause
  exit /b 2
)
if not exist "%APPROOT%frontend\dist\index.html" (
  echo [SRW] ERROR: frontend\dist\index.html was not found.
  pause
  exit /b 2
)
if not exist "%KNOWLEDGE%\taxonomy\knowledge.db" (
  echo [SRW] ERROR: production Knowledge databases are missing.
  pause
  exit /b 2
)
if exist "%WORKSPACE%\data\srw_v1.db" set "REUSE=--reuse-workspace"

rem The one-time pairing code is printed only to this interactive console.
rem Never add a token to command arguments, URL, log files, or repository.
set "RECRUITMENT_SESSION_ENFORCE=1"
echo [SRW] Local Web entry: http://127.0.0.1:8765/v1
echo [SRW] You will be shown a one-time pairing code here. Enter it in the browser.
echo [SRW] Your files remain in %WORKSPACE%\data.
echo [SRW] Close the Windows EXE before starting Local Web.
echo [SRW] Press Ctrl+C in this window to stop the Web server cleanly.
"%PYTHON%" -I -B "%APPROOT%scripts\start_local_web.py" --workspace "%WORKSPACE%" --knowledge-root "%KNOWLEDGE%" --port 8765 %REUSE%
set "SRW_RC=%ERRORLEVEL%"
if not "%SRW_RC%"=="0" (
  echo [SRW] Web did not start or exited with error %SRW_RC%.
  echo [SRW] Never delete a foreign app.lock or reuse another user's workspace.
  pause
)
exit /b %SRW_RC%
