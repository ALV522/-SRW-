@echo off
setlocal DisableDelayedExpansion
set "APPROOT=%~dp0"
set "EXE=%APPROOT%windows-host\SmartRecruitmentWorkbench.exe"
set "WORKSPACE=%LOCALAPPDATA%\SRW\DualCarrierV0"
set "DATA=%WORKSPACE%\data"

if not defined LOCALAPPDATA (
  echo [SRW] ERROR: LOCALAPPDATA is unavailable.
  pause
  exit /b 2
)
if not exist "%APPROOT%VERSION" (
  echo [SRW] ERROR: Run this launcher from the extracted Q1R10 application root.
  pause
  exit /b 2
)
if not exist "%EXE%" (
  echo [SRW] ERROR: windows-host\SmartRecruitmentWorkbench.exe was not found.
  pause
  exit /b 2
)
if not exist "%APPROOT%runtime\python.exe" (
  echo [SRW] ERROR: embedded runtime\python.exe was not found.
  pause
  exit /b 2
)
if not exist "%DATA%" mkdir "%DATA%"
if errorlevel 1 (
  echo [SRW] ERROR: Failed to create your private local data directory.
  pause
  exit /b 2
)
echo [SRW] Windows Native entry. Data remains in:
echo        %DATA%
echo [SRW] Close the Local Web terminal before launching this EXE.
"%EXE%" --application-root "%APPROOT%" --data-root "%DATA%"
if errorlevel 1 (
  echo [SRW] Windows application exited with an error. Do not delete lock files.
  echo [SRW] Check the data\logs\host.log in your private local workspace.
  pause
  exit /b 1
)
exit /b 0
