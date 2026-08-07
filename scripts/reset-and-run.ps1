param(
    [switch]$SkipValidation
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

Write-Host "PostgreSQL 볼륨과 기존 컨테이너를 초기화합니다." -ForegroundColor Yellow
docker compose down -v --remove-orphans
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose 초기화에 실패했습니다."
}

& powershell -ExecutionPolicy Bypass -File ".\scripts\bootstrap.ps1" -SkipValidation:$SkipValidation
exit $LASTEXITCODE
