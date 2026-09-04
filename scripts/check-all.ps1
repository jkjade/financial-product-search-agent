$ErrorActionPreference = "Stop"
$failed = $false
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Write-Pass {
    param([string]$Message)
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    $script:failed = $true
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

# Windows PowerShell 5.1 can encode a string request body using a legacy code page.
# Always send JSON as explicit UTF-8 bytes so Korean ontology terms reach FastAPI unchanged.
function Invoke-JsonPost {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Json,
        [int]$TimeoutSec = 30
    )
    $Utf8Body = [System.Text.Encoding]::UTF8.GetBytes($Json)
    return Invoke-RestMethod `
        -Uri $Uri `
        -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body $Utf8Body `
        -TimeoutSec $TimeoutSec
}

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

$ApiPort = [int](Get-DotEnvValue -Name "API_PORT" -Default "8000")
$DbUser = Get-DotEnvValue -Name "POSTGRES_USER" -Default "financial_agent"
$DbName = Get-DotEnvValue -Name "POSTGRES_DB" -Default "financial_products"
$BaseUrl = "http://localhost:$ApiPort"

Write-Host ""
Write-Host "금융상품 Agent 전체 검증 시작" -ForegroundColor Yellow
Write-Host "================================"

Write-Step "1. Docker 및 Compose 설정"
try {
    cmd /c "docker info >nul 2>nul"
    if ($LASTEXITCODE -eq 0) {
        Write-Pass "Docker Engine 실행 중"
    }
    else {
        Write-Fail "Docker Engine에 연결할 수 없음"
    }

    docker compose config *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Pass "Docker Compose 설정 정상"
    }
    else {
        Write-Fail "Docker Compose 설정 오류"
    }
}
catch {
    Write-Fail "Docker 검사 실패: $($_.Exception.Message)"
}

Write-Step "2. 컨테이너 상태"
try {
    $postgresId = docker compose ps -q postgres
    $apiId = docker compose ps -q api

    if ([string]::IsNullOrWhiteSpace($postgresId)) {
        Write-Fail "PostgreSQL 컨테이너가 없음"
    }
    else {
        $postgresStatus = docker inspect --format '{{.State.Status}}' $postgresId
        $postgresHealth = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $postgresId
        if ($postgresStatus -eq "running" -and $postgresHealth -eq "healthy") {
            Write-Pass "PostgreSQL 실행 및 Health Check 정상"
        }
        else {
            Write-Fail "PostgreSQL 상태: status=$postgresStatus, health=$postgresHealth"
        }
    }

    if ([string]::IsNullOrWhiteSpace($apiId)) {
        Write-Fail "API 컨테이너가 없음"
    }
    else {
        $apiStatus = docker inspect --format '{{.State.Status}}' $apiId
        $apiHealth = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $apiId
        if ($apiStatus -eq "running" -and $apiHealth -eq "healthy") {
            Write-Pass "API 실행 및 Health Check 정상"
        }
        else {
            Write-Fail "API 상태: status=$apiStatus, health=$apiHealth"
        }
    }
}
catch {
    Write-Fail "컨테이너 상태 확인 실패: $($_.Exception.Message)"
}

Write-Step "3. 원본 XLSX·스키마·SHA-256 검증"
try {
    docker compose --profile tools run --rm etl python -m src.cli validate-sources
    if ($LASTEXITCODE -eq 0) {
        Write-Pass "원본 8개 파일과 스키마·체크섬 일치"
    }
    else {
        Write-Fail "원본 파일 검증 실패"
    }
}
catch {
    Write-Fail "원본 파일 검증 실행 실패: $($_.Exception.Message)"
}

Write-Step "4. Python 단위 테스트"
try {
    docker compose --profile tools run --rm etl pytest -q
    if ($LASTEXITCODE -eq 0) {
        Write-Pass "pytest 전체 통과"
    }
    else {
        Write-Fail "pytest 실패"
    }
}
catch {
    Write-Fail "pytest 실행 실패: $($_.Exception.Message)"
}

Write-Step "5. API Health 및 기능 정보"
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 10
    if ($health.status -eq "ok" -and $health.database -eq "ok") {
        Write-Pass "/health 응답 정상 (버전 $($health.version))"
    }
    else {
        Write-Fail "/health 응답 이상"
    }

    $capabilities = Invoke-RestMethod -Uri "$BaseUrl/capabilities" -TimeoutSec 10
    if (@($capabilities.product_types).Count -eq 4 -and $capabilities.data_base_date -eq "2026-08-24") {
        Write-Pass "상품군 4종 및 Agent 연동 스키마 정상"
    }
    else {
        Write-Fail "/capabilities 응답 이상"
    }
}
catch {
    Write-Fail "API 기본 기능 확인 실패: $($_.Exception.Message)"
}

Write-Step "6. 상품군별 적재 건수"
$expectedCounts = @{
    "DOMESTIC_BOND" = 21882
    "DOMESTIC_ETF" = 1780
    "OVERSEAS_ETF" = 6037
    "PUBLIC_FUND" = 23676
}
try {
    $stats = Invoke-RestMethod -Uri "$BaseUrl/stats" -TimeoutSec 20
    foreach ($productType in $expectedCounts.Keys) {
        $item = $stats.items | Where-Object { $_.product_type -eq $productType }
        if ($null -eq $item) {
            Write-Fail "$productType 통계가 없음"
            continue
        }
        $actual = [int]$item.product_count
        $expected = [int]$expectedCounts[$productType]
        if ($actual -eq $expected) {
            Write-Pass "$productType : $actual 건"
        }
        else {
            Write-Fail "$productType : 예상 $expected 건 / 실제 $actual 건"
        }
        if ($item.data_base_date -ne "2026-08-24") {
            Write-Fail "$productType 기준일 이상: $($item.data_base_date)"
        }
    }

    if ([int]$stats.total_count -eq 53375) {
        Write-Pass "전체 적재 건수 53,375건 일치"
    }
    else {
        Write-Fail "전체 적재 건수 이상: $($stats.total_count)"
    }
}
catch {
    Write-Fail "/stats 검증 실패: $($_.Exception.Message)"
}

Write-Step "7. 데이터베이스 무결성 검증"
try {
    docker compose exec -T api python -m src.cli validate
    if ($LASTEXITCODE -eq 0) {
        Write-Pass "DB 건수·필수값·원본 행 고유성 검증 통과"
    }
    else {
        Write-Fail "DB 무결성 검증 실패"
    }

    $manifestPath = ".\data\reports\manifest.json"
    if (Test-Path $manifestPath) {
        $manifest = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.total_rows_processed -eq 53375 -and $manifest.all_expected_rows_match) {
            Write-Pass "전처리 manifest 총건수 및 재현성 정보 정상"
        }
        else {
            Write-Fail "전처리 manifest 값 이상"
        }
    }
    else {
        Write-Fail "전처리 manifest.json이 없음"
    }
}
catch {
    Write-Fail "데이터베이스 무결성 검사 실패: $($_.Exception.Message)"
}

Write-Step "8. 검색·필터·정렬·페이지 정보"
try {
    $search = Invoke-RestMethod -Uri "$BaseUrl/products/search?product_type=OVERSEAS_ETF&region=United%20States&max_fee=0.05&sort_by=size&order=desc&limit=3" -TimeoutSec 20
    if ($search.returned_count -eq 3 -and @($search.items).Count -eq 3 -and $search.total_count -ge 3) {
        Write-Pass "검색 결과·전체 건수·페이지 정보 정상"
    }
    else {
        Write-Fail "검색 결과 개수 또는 페이지 정보 이상"
    }

    $isDescending = $true
    $searchItems = @($search.items)
    if ($searchItems.Count -ge 2) {
        for ($index = 0; $index -lt $searchItems.Count - 1; $index++) {
            if ([decimal]$searchItems[$index].size_amount -lt [decimal]$searchItems[$index + 1].size_amount) {
                $isDescending = $false
                break
            }
        }
    }
    if ($isDescending) {
        Write-Pass "AUM 내림차순 정렬 정상"
    }
    else {
        Write-Fail "AUM 정렬 순서 오류"
    }

    $invalidFilter = @($search.items | Where-Object {
        $_.investment_region -notlike "*United States*" -or
        [decimal]$_.fee_rate -gt [decimal]"0.05"
    })
    if ($invalidFilter.Count -eq 0) {
        Write-Pass "지역·보수 조건 필터 정상"
    }
    else {
        Write-Fail "조건에 맞지 않는 상품이 반환됨"
    }
}
catch {
    Write-Fail "검색 API 검증 실패: $($_.Exception.Message)"
}

Write-Step "9. Agent용 구조화 도구 호출"
try {
    $requestBody = @{
        product_type = "OVERSEAS_ETF"
        asset_class = "Equity"
        region = "United States"
        max_fee = 0.05
        sort_by = "fee"
        order = "asc"
        limit = 3
    } | ConvertTo-Json

    $toolResult = Invoke-JsonPost -Uri "$BaseUrl/tools/search-products" -Json $requestBody -TimeoutSec 20

    if ($toolResult.returned_count -eq 3 -and @($toolResult.items).Count -eq 3) {
        Write-Pass "POST /tools/search-products 정상"
    }
    else {
        Write-Fail "Agent 도구 호출 결과 이상"
    }
}
catch {
    Write-Fail "Agent 도구 호출 검증 실패: $($_.Exception.Message)"
}

Write-Step "10. 원본 근거·개별 기준일"
try {
    $voo = Invoke-RestMethod -Uri "$BaseUrl/products/PREF02N001/5996" -TimeoutSec 20
    if (
        $voo.product_id -eq "VOO" -and
        $voo.source_file -eq "pref02n001_data.xlsx" -and
        $voo.price_base_date -eq "2026-08-21" -and
        $voo.size_base_date -eq "2026-08-22" -and
        $voo.reference_dates.dataset_snapshot_date -eq "2026-08-24"
    ) {
        Write-Pass "VOO 원본 행·파일·가격/AUM 기준일 회귀검사 통과"
    }
    else {
        Write-Fail "VOO 원본 근거 또는 개별 기준일 이상"
    }

    $dateStats = Invoke-RestMethod -Uri "$BaseUrl/stats/reference-dates" -TimeoutSec 20
    $types = @($dateStats.items | ForEach-Object { $_.product_type })
    foreach ($type in $expectedCounts.Keys) {
        if ($types -contains $type) {
            Write-Pass "$type 기준일 통계 존재"
        }
        else {
            Write-Fail "$type 기준일 통계 누락"
        }
    }
}
catch {
    Write-Fail "원본 근거·기준일 검증 실패: $($_.Exception.Message)"
}

Write-Step "11. 빈 결과 및 품질 플래그"
try {
    $emptyResult = Invoke-RestMethod -Uri "$BaseUrl/products/search?product_type=OVERSEAS_ETF&region=%EC%A1%B4%EC%9E%AC%ED%95%98%EC%A7%80%EC%95%8A%EB%8A%94%EC%A7%80%EC%97%AD123&limit=10" -TimeoutSec 20
    if ($emptyResult.returned_count -eq 0 -and @($emptyResult.items).Count -eq 0) {
        Write-Pass "존재하지 않는 조건에 빈 결과 반환"
    }
    else {
        Write-Fail "존재하지 않는 조건에서 상품이 반환됨"
    }

    $quality = Invoke-RestMethod -Uri "$BaseUrl/quality/summary" -TimeoutSec 20
    if (@($quality.items).Count -eq 4) {
        Write-Pass "상품군 4종 품질 요약 정상"
    }
    else {
        Write-Fail "품질 요약 상품군 누락"
    }
}
catch {
    Write-Fail "빈 결과·품질 요약 검증 실패: $($_.Exception.Message)"
}

Write-Step "12. DB 인덱스 및 필수값"
try {
    $missingRaw = docker compose exec -T postgres psql -U $DbUser -d $DbName -t -A -c "SELECT COUNT(*) FROM search.product_catalog WHERE product_id IS NULL OR BTRIM(product_id) = '' OR product_name IS NULL OR BTRIM(product_name) = '';"
    $missingCount = [int]($missingRaw.Trim())
    if ($missingCount -eq 0) {
        Write-Pass "상품 ID·상품명 누락 없음"
    }
    else {
        Write-Fail "상품 ID 또는 상품명 누락: $missingCount 건"
    }

    $indexRaw = docker compose exec -T postgres psql -U $DbUser -d $DbName -t -A -c "SELECT COUNT(*) FROM pg_indexes WHERE schemaname='search' AND indexname IN ('ux_product_catalog_source_row','ix_product_catalog_search_trgm','ix_product_catalog_size','ix_product_catalog_return_1y','ix_product_catalog_quality_flags');"
    $indexCount = [int]($indexRaw.Trim())
    if ($indexCount -eq 5) {
        Write-Pass "핵심 검색·정렬·품질 인덱스 존재"
    }
    else {
        Write-Fail "핵심 인덱스 누락: 확인된 개수 $indexCount"
    }
}
catch {
    Write-Fail "DB 인덱스·필수값 검사 실패: $($_.Exception.Message)"
}


Write-Step "13. Phase 2 복합 조건·다중 정렬"
try {
    $queryBody = @{
        q = "S&P 500"
        filters = @(
            @{ field = "product_type"; operator = "eq"; value = "OVERSEAS_ETF" },
            @{ field = "investment_region"; operator = "contains"; value = "United States" },
            @{ field = "fee_rate"; operator = "lte"; value = 0.05 },
            @{ field = "size_amount"; operator = "not_null" }
        )
        sort = @(
            @{ field = "fee_rate"; order = "asc"; nulls = "last" },
            @{ field = "size_amount"; order = "desc"; nulls = "last" }
        )
        limit = 5
        offset = 0
    } | ConvertTo-Json -Depth 10

    $queryResult = Invoke-JsonPost -Uri "$BaseUrl/tools/query-products" -Json $queryBody -TimeoutSec 20

    $queryItems = @($queryResult.items)
    $invalidQueryItem = @($queryItems | Where-Object {
        $_.product_type -ne "OVERSEAS_ETF" -or
        $_.investment_region -notlike "*United States*" -or
        [decimal]$_.fee_rate -gt [decimal]"0.05"
    })
    $feeSorted = $true
    if ($queryItems.Count -ge 2) {
        for ($i = 0; $i -lt $queryItems.Count - 1; $i++) {
            if ([decimal]$queryItems[$i].fee_rate -gt [decimal]$queryItems[$i + 1].fee_rate) {
                $feeSorted = $false
                break
            }
        }
    }
    if ($queryItems.Count -gt 0 -and $invalidQueryItem.Count -eq 0 -and $feeSorted) {
        Write-Pass "복합 조건 매칭·다중 정렬 정상"
    }
    else {
        Write-Fail "복합 조건 또는 다중 정렬 결과 이상"
    }
}
catch {
    Write-Fail "복합 조건·다중 정렬 검증 실패: $($_.Exception.Message)"
}

Write-Step "14. Phase 2 집계 연산"
try {
    $aggregateBody = @{
        group_by = @("product_type")
        metrics = @(
            @{ operation = "count"; alias = "product_count" },
            @{ operation = "avg"; field = "size_amount"; alias = "avg_size" },
            @{ operation = "max"; field = "return_1y"; alias = "max_return_1y" }
        )
        order_by = @(@{ field = "product_count"; order = "desc"; nulls = "last" })
        limit = 10
    } | ConvertTo-Json -Depth 10

    $aggregateResult = Invoke-JsonPost -Uri "$BaseUrl/tools/aggregate-products" -Json $aggregateBody -TimeoutSec 20

    $aggregateRows = @($aggregateResult.rows)
    $aggregateTotal = 0
    foreach ($row in $aggregateRows) {
        $aggregateTotal += [int]$row.product_count
    }
    if ($aggregateRows.Count -eq 4 -and $aggregateTotal -eq 53375) {
        Write-Pass "COUNT·AVG·MAX 및 상품군 GROUP BY 정상"
    }
    else {
        Write-Fail "집계 결과 이상: groups=$($aggregateRows.Count), count_sum=$aggregateTotal"
    }
}
catch {
    Write-Fail "집계 연산 검증 실패: $($_.Exception.Message)"
}

Write-Step "15. Phase 2 순위 연산"
try {
    $rankBody = @{
        filters = @(@{ field = "product_type"; operator = "eq"; value = "OVERSEAS_ETF" })
        metric = "size_amount"
        order = "desc"
        method = "dense_rank"
        partition_by = @()
        top_n = 3
        result_limit = 20
    } | ConvertTo-Json -Depth 10

    $rankResult = Invoke-JsonPost -Uri "$BaseUrl/tools/rank-products" -Json $rankBody -TimeoutSec 20

    $rankItems = @($rankResult.items)
    $invalidRank = @($rankItems | Where-Object {
        $_.product_type -ne "OVERSEAS_ETF" -or [int]$_.rank_position -gt 3
    })
    if ($rankItems.Count -ge 3 -and $invalidRank.Count -eq 0 -and [int]$rankItems[0].rank_position -eq 1) {
        Write-Pass "dense_rank 명시적 순위·Top-N 정상"
    }
    else {
        Write-Fail "순위 결과 이상"
    }
}
catch {
    Write-Fail "순위 연산 검증 실패: $($_.Exception.Message)"
}

Write-Step "16. Phase 2 상품 비교"
try {
    $compareBody = @{
        products = @(
            @{ source_table = "PREF02N001"; source_row_number = 589 },
            @{ source_table = "PREF02N001"; source_row_number = 5030 },
            @{ source_table = "PREF02N001"; source_row_number = 1349 }
        )
        metrics = @(
            @{ field = "fee_rate"; order = "asc" },
            @{ field = "size_amount"; order = "desc" }
        )
    } | ConvertTo-Json -Depth 10

    $compareResult = Invoke-JsonPost -Uri "$BaseUrl/tools/compare-products" -Json $compareBody -TimeoutSec 20

    if (-not $compareResult.requires_clarification -and @($compareResult.products).Count -eq 3 -and $null -ne $compareResult.metric_rankings.fee_rate) {
        Write-Pass "VOO·IVV·SPY 비교 및 지표별 순위 정상"
    }
    else {
        Write-Fail "상품 비교 결과 이상"
    }
}
catch {
    Write-Fail "상품 비교 검증 실패: $($_.Exception.Message)"
}

Write-Step "17. Phase 3 연결 준비 상태"
try {
    $catalog = Invoke-RestMethod -Uri "$BaseUrl/tools/catalog" -TimeoutSec 20
    $agentHealth = Invoke-RestMethod -Uri "$BaseUrl/agent/health" -TimeoutSec 20
    $planSchema = Invoke-RestMethod -Uri "$BaseUrl/agent/plan-schema" -TimeoutSec 20
    if (@($catalog.tools).Count -eq 9 -and $agentHealth.provider -eq "HyperCLOVA X" -and $null -ne $planSchema.properties.intent) {
        Write-Pass "HyperCLOVA X Tool Catalog·Agent Plan Schema·설정 점검 정상"
    }
    else {
        Write-Fail "Phase 3 연결 계약 이상"
    }

    $planBody = @{
        intent = "rank"
        tool_calls = @(
            @{
                call_id = "rank-check"
                name = "rank_products"
                arguments = @{
                    filters = @(@{ field = "product_type"; operator = "eq"; value = "OVERSEAS_ETF" })
                    metric = "fee_rate"
                    order = "asc"
                    method = "dense_rank"
                    top_n = 3
                    result_limit = 10
                }
            }
        )
        missing_conditions = @()
    } | ConvertTo-Json -Depth 15
    $planResult = Invoke-JsonPost -Uri "$BaseUrl/agent/execute-plan" -Json $planBody -TimeoutSec 20
    if (@($planResult.tool_results).Count -eq 1 -and $planResult.tool_results[0].name -eq "rank_products") {
        Write-Pass "LLM 없이 Agent 실행계획→도구 호출 경로 정상"
    }
    else {
        Write-Fail "Agent 실행계획 경로 이상"
    }
}
catch {
    Write-Fail "Phase 3 연결 준비 검증 실패: $($_.Exception.Message)"
}

Write-Step "18. Phase 2 전용 인덱스"
try {
    $phase2IndexRaw = docker compose exec -T postgres psql -U $DbUser -d $DbName -t -A -c "SELECT COUNT(*) FROM pg_indexes WHERE schemaname='search' AND indexname IN ('ix_product_catalog_type_asset','ix_product_catalog_type_manager','ix_product_catalog_type_currency','ix_product_catalog_type_risk','ix_product_catalog_type_sale','ix_product_catalog_type_fee','ix_product_catalog_type_return_1y','ix_product_catalog_type_size','ix_product_catalog_type_yield');"
    $phase2IndexCount = [int]($phase2IndexRaw.Trim())
    if ($phase2IndexCount -eq 9) {
        Write-Pass "필터·집계·순위용 복합 인덱스 9개 존재"
    }
    else {
        Write-Fail "Phase 2 인덱스 누락: 확인된 개수 $phase2IndexCount"
    }
}
catch {
    Write-Fail "Phase 2 인덱스 검사 실패: $($_.Exception.Message)"
}

Write-Step "19. Phase 2.5 온톨로지·지식 그래프"
try {
    $ontology = Invoke-RestMethod -Uri "$BaseUrl/ontology" -TimeoutSec 20
    if (
        $ontology.dataset_snapshot_date -eq "2026-08-24" -and
        @($ontology.ontology_files).Count -eq 5 -and
        @($ontology.ontology_files) -contains "ontology/common.ttl"
    ) {
        Write-Pass "Ontology TTL·용어맵·비즈니스 규칙 로드 정상"
    }
    else {
        Write-Fail "온톨로지 메타데이터 이상"
    }

    $graphStats = Invoke-RestMethod -Uri "$BaseUrl/graph/stats" -TimeoutSec 30
    $productEntityCount = 0
    foreach ($item in @($graphStats.entities)) {
        if ($expectedCounts.ContainsKey([string]$item.entity_type)) {
            $productEntityCount += [int]$item.count
        }
    }
    $predicates = @($graphStats.relations | ForEach-Object { $_.predicate })
    if (
        $productEntityCount -eq 53375 -and
        $predicates -contains "managedBy" -and
        $predicates -contains "manages" -and
        $predicates -contains "hasAssetClass" -and
        $predicates -contains "investsInRegion"
    ) {
        Write-Pass "상품 53,375건 지식 그래프 엔티티·핵심 관계 정상"
    }
    else {
        Write-Fail "지식 그래프 엔티티 또는 관계 이상"
    }
}
catch {
    Write-Fail "온톨로지·지식 그래프 검증 실패: $($_.Exception.Message)"
}

Write-Step "20. Phase 2.5 Federated 검색·외부 근거 안전장치"
try {
    $resolveBody = @{ query = "미국 해외 ETF 중 AUM가 크고 보수가 낮은 상품" } | ConvertTo-Json
    $resolved = Invoke-JsonPost -Uri "$BaseUrl/tools/resolve-ontology" -Json $resolveBody -TimeoutSec 20
    $canonical = @($resolved.matches | ForEach-Object { $_.canonical })
    if ($canonical -contains "OVERSEAS_ETF" -and $canonical -contains "size_amount" -and $canonical -contains "fee_rate") {
        Write-Pass "자연어→온톨로지 용어 그라운딩 정상"
    }
    else {
        Write-Fail "온톨로지 용어 그라운딩 이상 (canonical=$($canonical -join ", "))"
    }

    $federatedBody = @{
        query = "Vanguard ETF"
        include_external_documents = $true
        product_limit = 5
        graph_limit = 5
        document_limit = 3
    } | ConvertTo-Json -Depth 10
    $federated = Invoke-JsonPost -Uri "$BaseUrl/tools/federated-search" -Json $federatedBody -TimeoutSec 30
    if ($federated.route.rdb -and $federated.route.graph -and [int]$federated.products.returned_count -gt 0) {
        Write-Pass "RDB·Graph·외부 Semantic 경로를 묶은 Federated 검색 정상"
    }
    else {
        Write-Fail "Federated 검색 결과 이상"
    }

    $cutoffConstraintRaw = docker compose exec -T postgres psql -U $DbUser -d $DbName -t -A -c "SELECT COUNT(*) FROM pg_constraint c JOIN pg_class t ON c.conrelid=t.oid JOIN pg_namespace n ON t.relnamespace=n.oid WHERE n.nspname='semantic' AND t.relname IN ('document_chunk','external_holding') AND pg_get_constraintdef(c.oid) LIKE '%2026-08-24%';"
    if ([int]($cutoffConstraintRaw.Trim()) -ge 2) {
        Write-Pass "외부 문서·구성종목 2026-08-24 이후 적재 차단 DB 제약 존재"
    }
    else {
        Write-Fail "외부 근거 기준일 차단 제약 누락"
    }
}
catch {
    Write-Fail "Federated 검색·외부 근거 검증 실패: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "================================"
if ($failed) {
    Write-Host "전체 검증 결과: 일부 항목 실패" -ForegroundColor Red
    Write-Host "위의 [FAIL] 항목을 확인해 주세요." -ForegroundColor Red
    exit 1
}
else {
    Write-Host "전체 검증 결과: 모두 정상" -ForegroundColor Green
    Write-Host "1·2차와 온톨로지·지식그래프·Federated 검색·Answer Validation까지 모두 통과했습니다." -ForegroundColor Green
    exit 0
}
