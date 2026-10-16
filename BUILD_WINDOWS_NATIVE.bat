@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows_native_from_v088.ps1"
if errorlevel 1 pause
