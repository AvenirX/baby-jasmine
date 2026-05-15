@echo off
title Baby Jasmine - Setup
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
if %ERRORLEVEL% neq 0 pause
