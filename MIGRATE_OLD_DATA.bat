@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SRW v1.0-alpha10 旧版本数据迁移
echo 可输入旧版 Portable 根目录，或其中的 data 目录。
set /p SRW_OLD=旧版本目录: 
if "%SRW_OLD%"=="" exit /b 1
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
"%~dp0runtime\python.exe" "%~dp0scripts\launch_alpha10.py" --migrate-from "%SRW_OLD%"
set EC=%ERRORLEVEL%
echo.
if "%EC%"=="0" (echo 迁移完成。源目录未被修改。) else (echo 迁移失败，请复制本窗口全部内容。)
pause
exit /b %EC%
