@REM 这个脚本负责调用 PowerShell 前端启动脚本，保持固定的 Windows 启动入口。
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-frontend.ps1" %*
exit /b %ERRORLEVEL%
