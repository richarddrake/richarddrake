@echo off
REM Stop Docker Compose demo environment.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker-stop.ps1" %*
exit /b %ERRORLEVEL%
