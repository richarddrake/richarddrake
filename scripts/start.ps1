# 这个脚本负责检查后端端口占用情况，并启动 FastAPI 服务。
param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$StopExisting,
    [switch]$Reload,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Get-PortListeners {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Where-Object {
            $_.LocalAddress -eq $HostAddress -or
            $_.LocalAddress -eq "0.0.0.0" -or
            $_.LocalAddress -eq "::" -or
            ($HostAddress -eq "0.0.0.0" -and $_.LocalAddress -eq "127.0.0.1") -or
            ($HostAddress -eq "::" -and $_.LocalAddress -eq "::1")
        } |
        Sort-Object -Property OwningProcess -Unique
}

function Show-PortListeners($Listeners) {
    foreach ($listener in $Listeners) {
        $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
        $processName = if ($process) { $process.ProcessName } else { "unknown" }
        Write-Host ("- {0}:{1} is used by PID {2} ({3})" -f $listener.LocalAddress, $listener.LocalPort, $listener.OwningProcess, $processName)
    }
}

$listeners = @(Get-PortListeners)
if ($listeners.Count -gt 0) {
    if ($StopExisting) {
        & "$PSScriptRoot\stop.ps1" -HostAddress $HostAddress -Port $Port
    }
    else {
        Write-Host "Port $Port is already in use:"
        Show-PortListeners $listeners
        Write-Host ""
        Write-Host "Stop it with:"
        Write-Host ".\scripts\stop.cmd -Port $Port"
        Write-Host ""
        Write-Host "Or start on another port:"
        Write-Host ".\scripts\start.cmd -Port 8001"
        exit 1
    }
}

$uvicornArgs = @(
    "-m", "uvicorn",
    "app.main:app",
    "--host", $HostAddress,
    "--port", [string]$Port
)

if ($Reload -and -not $NoReload) {
    $uvicornArgs += "--reload"
}

Write-Host "Starting test case generation API..."
Write-Host "Project: $ProjectRoot"
Write-Host "API: http://${HostAddress}:$Port"
Write-Host "Docs: http://${HostAddress}:$Port/docs"
if ($Reload -and -not $NoReload) {
    Write-Host "Reload: enabled"
}
else {
    Write-Host "Reload: disabled"
}
Write-Host "Press Ctrl+C to stop."
Write-Host ""

& python @uvicornArgs
exit $LASTEXITCODE
