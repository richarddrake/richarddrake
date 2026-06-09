@REM 这个脚本负责调用 PowerShell 前端停服脚本，释放前端开发端口。
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-frontend.ps1" %*
exit /b %ERRORLEVEL%
