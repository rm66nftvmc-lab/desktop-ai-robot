@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_bridge.ps1" -OpenBrowser
if errorlevel 1 pause
