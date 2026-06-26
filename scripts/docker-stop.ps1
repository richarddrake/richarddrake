# 这个脚本负责停止 Docker Compose 演示环境，可选删除 MySQL 数据卷。
param(
    [switch]$Volumes,
    [string]$EnvFile = ".env.docker"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvFilePath = Join-Path $ProjectRoot $EnvFile

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
