@REM 这个脚本负责调用 PowerShell 后端停服脚本，释放后端 API 端口。
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1" %*
exit /b %ERRORLEVEL%
