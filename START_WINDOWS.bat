@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0windows-host\SmartRecruitmentWorkbench.exe" (
  start "" "%~dp0windows-host\SmartRecruitmentWorkbench.exe" --application-root "%~dp0"
  exit /b 0
)
echo [SRW] 当前包已具备 Windows Host ABI，但未包含继承的 WPF Host 二进制。
echo [SRW] 如需原生桌面模式，请把精确的 SRW_v0.8.8_Windows_Portable.zip 放到本目录，运行 BUILD_WINDOWS_NATIVE.bat。
echo [SRW] 现在回退到浏览器 Portable。
call "%~dp0START.bat"
