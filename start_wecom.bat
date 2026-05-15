@echo off
title Baby Jasmine - WeCom
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_wecom.ps1"
if %ERRORLEVEL% neq 0 pause
