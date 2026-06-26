param(
    [switch]$Detached,
    [switch]$NoBuild,
    [string]$EnvFile = ".env.docker"
)

# Start Docker Compose demo environment and load .env.docker when it exists.
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

$composeArgs += "up"
if (-not $NoBuild) {
    $composeArgs += "--build"
}
if ($Detached) {
    $composeArgs += "-d"
}

Push-Location $ProjectRoot
try {
    & docker @composeArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
