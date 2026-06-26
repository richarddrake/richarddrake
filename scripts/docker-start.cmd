@echo off
REM Start Docker Compose demo environment.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker-start.ps1" %*
exit /b %ERRORLEVEL%
