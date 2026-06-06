param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 5173,
    [switch]$StopExisting
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "frontend"

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

if (-not (Test-Path (Join-Path $FrontendRoot "package.json"))) {
    Write-Error "Frontend package.json was not found: $FrontendRoot"
    exit 1
}

$listeners = @(Get-PortListeners)
if ($listeners.Count -gt 0) {
    if ($StopExisting) {
        & "$PSScriptRoot\stop-frontend.ps1" -HostAddress $HostAddress -Port $Port
    }
    else {
        Write-Host "Port $Port is already in use:"
        Show-PortListeners $listeners
        Write-Host ""
        Write-Host "Stop it with:"
        Write-Host ".\scripts\stop-frontend.cmd -Port $Port"
        Write-Host ""
        Write-Host "Or start on another port:"
        Write-Host ".\scripts\start-frontend.cmd -Port 5174"
        exit 1
    }
}

Set-Location $FrontendRoot

if (-not (Test-Path (Join-Path $FrontendRoot "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Write-Host "Starting Vue frontend..."
Write-Host "Project: $FrontendRoot"
Write-Host "URL: http://${HostAddress}:$Port"
Write-Host "Backend API should be running at http://127.0.0.1:8000"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

& npm.cmd run dev -- --host $HostAddress --port $Port
exit $LASTEXITCODE
