@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
set PYTHONPATH=%~dp0backend
"%~dp0runtime\python.exe" "%~dp0scripts\run_convergence_verification.py"
set EC=%ERRORLEVEL%
echo.
if "%EC%"=="0" (echo Capability Recovery 验证通过。) else (echo Capability Recovery 验证失败。)
pause
exit /b %EC%
