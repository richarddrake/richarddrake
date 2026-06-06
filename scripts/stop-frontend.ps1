param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 5173
)

$ErrorActionPreference = "Stop"

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

$listeners = @(Get-PortListeners)
if ($listeners.Count -eq 0) {
    Write-Host "No frontend service is listening on ${HostAddress}:$Port."
    exit 0
}

$processIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($processId in $processIds) {
    if ($processId -eq $PID) {
        Write-Host "Skipping current PowerShell process $processId."
        continue
    }

    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-Host "PID $processId is no longer running."
        continue
    }

    Write-Host ("Stopping frontend PID {0} ({1}) on port {2}..." -f $processId, $process.ProcessName, $Port)
    Stop-Process -Id $processId -Force
}

Start-Sleep -Milliseconds 400
$remaining = @(Get-PortListeners)
if ($remaining.Count -gt 0) {
    Write-Error "Port $Port is still in use. Try running PowerShell as Administrator."
    exit 1
}

Write-Host "Frontend port $Port has been released."
