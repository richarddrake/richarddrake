@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-frontend.ps1" %*
exit /b %ERRORLEVEL%
