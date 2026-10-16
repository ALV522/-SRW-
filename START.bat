@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
"%~dp0runtime\python.exe" "%~dp0scripts\launch_alpha10.py"
if errorlevel 1 (
  echo.
  echo 启动失败。请先运行 CHECK.bat，并把完整输出发给开发者。
  pause
)
