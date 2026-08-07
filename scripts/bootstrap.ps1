param(
    [switch]$SkipValidation
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Get-DotEnvValue {
    param(
        [string]$Name,
        [string]$Default
    )
    if (-not (Test-Path ".env")) {
        return $Default
    }
    $line = Get-Content ".env" -Encoding UTF8 |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Name))\s*=" } |
        Select-Object -First 1
    if ($null -eq $line) {
        return $Default
    }
    $value = ($line -split "=", 2)[1].Trim()
    return $value.Trim('"').Trim("'")
}

function Assert-LastExitCode {
    param([string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

Write-Host ""
Write-Host "금융상품 Agent 데이터 파이프라인 v2.5.1" -ForegroundColor Yellow
Write-Host "========================================="

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker 명령을 찾을 수 없습니다. Docker Desktop을 설치하고 실행해 주세요."
}

cmd /c "docker info >nul 2>nul"
Assert-LastExitCode "Docker Engine에 연결할 수 없습니다. Docker Desktop 실행 상태를 확인해 주세요."

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[준비] .env.example을 복사해 .env를 생성했습니다."
}

$requiredFiles = @(
    "data\raw\PRBD01N001_datarows.xlsx",
    "data\raw\PREF01N001_datarows.xlsx",
    "data\raw\PREF02N001_datarows.xlsx",
    "data\raw\PRFD01N001_datarows.xlsx",
    "data\raw\CHECKSUMS.sha256"
)
foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        throw "필수 원본 파일이 없습니다: $file"
    }
}

Write-Host "[1/7] Docker Compose 설정 검사"
docker compose config *> $null
Assert-LastExitCode "docker-compose.yml 또는 .env 설정이 올바르지 않습니다."

Write-Host "[2/7] API·ETL 이미지 빌드"
docker compose --profile tools build api etl
Assert-LastExitCode "Docker 이미지 빌드에 실패했습니다."

Write-Host "[3/7] 기존 API 중지 및 PostgreSQL 실행"
docker compose stop api *> $null
docker compose up -d postgres
Assert-LastExitCode "PostgreSQL 실행에 실패했습니다."

Write-Host "[4/7] 원본 검증·전처리·PostgreSQL 적재·색인·지식그래프 재구축"
docker compose --profile tools run --rm etl
Assert-LastExitCode "ETL 파이프라인 실행에 실패했습니다."

Write-Host "[5/7] 선택적 historical 외부 근거 재적재"
if (Test-Path ".\external_data\holdings.jsonl") {
    docker compose --profile tools run --rm etl python -m src.semantic.ingest_holdings /app/external_data/holdings.jsonl
    Assert-LastExitCode "ETF 구성종목 외부 데이터 적재에 실패했습니다."
    Write-Host "[외부근거] holdings.jsonl 적재 완료"
}
if (Test-Path ".\external_data\documents.jsonl") {
    docker compose --profile tools run --rm etl python -m src.semantic.ingest /app/external_data/documents.jsonl
    Assert-LastExitCode "외부 문서 데이터 적재에 실패했습니다."
    Write-Host "[외부근거] documents.jsonl 적재 완료 (embedding은 별도 --embed 실행)"
}

Write-Host "[6/7] API 실행"
docker compose up -d --force-recreate api
Assert-LastExitCode "API 실행에 실패했습니다."

$ApiPort = [int](Get-DotEnvValue -Name "API_PORT" -Default "8000")
$HealthUrl = "http://localhost:$ApiPort/health"
$ready = $false
for ($attempt = 1; $attempt -le 45; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3
        if ($health.status -eq "ok") {
            $ready = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) {
    docker compose logs --tail 100 api
    throw "API가 제한 시간 안에 준비되지 않았습니다."
}

Write-Host "[7/7] 전체 검증"
if (-not $SkipValidation) {
    & powershell -ExecutionPolicy Bypass -File ".\scripts\check-all.ps1"
    if ($LASTEXITCODE -ne 0) {
        throw "전체 검증에서 실패 항목이 발견되었습니다."
    }
}
else {
    Write-Host "SkipValidation 옵션으로 전체 검증을 건너뛰었습니다." -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "완료되었습니다." -ForegroundColor Green
Write-Host "API 문서: http://localhost:$ApiPort/docs"
Write-Host "상태 확인: $HealthUrl"
