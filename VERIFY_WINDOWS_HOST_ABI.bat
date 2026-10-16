@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
set PYTHONPATH=%~dp0backend
"%~dp0runtime\python.exe" -m unittest convergence_tests.test_convergence07 -v
set EC=%ERRORLEVEL%
echo.
if "%EC%"=="0" (echo Windows Host ABI / CSV Import 验证通过。) else (echo Windows Host ABI / CSV Import 验证失败。)
pause
exit /b %EC%
