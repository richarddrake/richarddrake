param(
    [switch]$Volumes,
    [string]$EnvFile = ".env.docker"
)

# Stop Docker Compose demo environment. Use -Volumes to remove MySQL data.
$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvFilePath = Join-Path $ProjectRoot $EnvFile

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker CLI was not found. Please install and start Docker Desktop, then reopen the terminal and retry." -ForegroundColor Red
    exit 1
}

$composeArgs = @("compose")
if (Test-Path $EnvFilePath) {
    $composeArgs += @("--env-file", $EnvFilePath)
}

$composeArgs += "down"
if ($Volumes) {
    $composeArgs += "-v"
}

Push-Location $ProjectRoot
try {
    & docker @composeArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
