@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
"%~dp0runtime\python.exe" "%~dp0scripts\launch_alpha10.py" --check
set EC=%ERRORLEVEL%
echo.
if "%EC%"=="0" (echo 自检通过。) else (echo 自检失败，请复制本窗口全部内容。)
pause
exit /b %EC%
