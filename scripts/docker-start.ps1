# 这个脚本负责启动 Docker Compose 演示环境，并在存在 .env.docker 时自动加载它。
param(
    [switch]$Detached,
    [switch]$NoBuild,
    [string]$EnvFile = ".env.docker"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvFilePath = Join-Path $ProjectRoot $EnvFile

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
