@echo off
REM 这个脚本负责在 Windows 上调用 PowerShell 停止 Docker Compose 演示环境。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker-stop.ps1" %*
exit /b %ERRORLEVEL%
