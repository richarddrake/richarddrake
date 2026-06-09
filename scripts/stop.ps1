# 这个脚本负责关闭占用后端端口的进程，并尽量清理关联的 Uvicorn 进程树。
param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000
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

function Get-ProcessInfo($ProcessId) {
    try {
        Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
    }
    catch {
        $null
    }
}

function Add-UniqueProcessId([int[]]$ProcessIds, [int]$ProcessId) {
    if ($ProcessId -le 0) {
        return $ProcessIds
    }
    if ($ProcessIds -contains $ProcessId) {
        return $ProcessIds
    }
    return @($ProcessIds + $ProcessId)
}

$listeners = @(Get-PortListeners)
if ($listeners.Count -eq 0) {
    Write-Host "No service is listening on ${HostAddress}:$Port."
    exit 0
}

$processIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($processId in @($processIds)) {
    $processInfo = Get-ProcessInfo $processId
    if (-not $processInfo) {
        continue
    }

    $parentInfo = Get-ProcessInfo $processInfo.ParentProcessId
    if ($parentInfo) {
        $parentText = "$($parentInfo.Name) $($parentInfo.CommandLine)"
        if ($parentText -match "uvicorn|app\.main:app") {
            $processIds = Add-UniqueProcessId $processIds ([int]$parentInfo.ProcessId)
        }
    }
}

try {
    $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    foreach ($processInfo in $allProcesses) {
        if ($processIds -contains ([int]$processInfo.ParentProcessId)) {
            $processText = "$($processInfo.Name) $($processInfo.CommandLine)"
            if ($processText -match "uvicorn|app\.main:app") {
                $processIds = Add-UniqueProcessId $processIds ([int]$processInfo.ProcessId)
            }
        }
    }
}
catch {
    Write-Host "Process tree lookup is unavailable; stopping listener processes only."
}

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

    Write-Host ("Stopping PID {0} ({1}) on port {2}..." -f $processId, $process.ProcessName, $Port)
    Stop-Process -Id $processId -Force
}

Start-Sleep -Milliseconds 400
$remaining = @(Get-PortListeners)
if ($remaining.Count -gt 0) {
    Write-Error "Port $Port is still in use. Try running PowerShell as Administrator."
    exit 1
}

Write-Host "Port $Port has been released."
