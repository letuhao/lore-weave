# Smoke-check single-port on-prem entry (nginx → BFF → services).
# Usage: .\infra\smoke-onprem.ps1 [BASE_URL]
#   BASE_URL defaults to http://localhost:$env:PUBLIC_HTTP_PORT (5296)
param(
    [string]$BaseUrl = ""
)

$ErrorActionPreference = "Stop"
if (-not $BaseUrl) {
    $port = if ($env:PUBLIC_HTTP_PORT) { $env:PUBLIC_HTTP_PORT } else { "5296" }
    $BaseUrl = "http://localhost:$port"
}
$BaseUrl = $BaseUrl.TrimEnd("/")

$fail = 0
function Test-Route {
    param([string]$Name, [string]$Path, [string]$Expect)
    try {
        $resp = Invoke-WebRequest -Uri "$BaseUrl$Path" -UseBasicParsing -SkipHttpErrorCheck
        $code = [int]$resp.StatusCode
    } catch {
        Write-Host "FAIL $Name — connection error ($BaseUrl$Path)"
        $script:fail = 1
        return
    }
    if ($Expect -and "$code" -ne $Expect) {
        Write-Host "FAIL $Name — expected HTTP $Expect, got $code ($Path)"
        $script:fail = 1
        return
    }
    Write-Host "OK   $Name — HTTP $code $Path"
}

Write-Host "Smoke base: $BaseUrl"
Write-Host ""

Test-Route "gateway health" "/health" "200"
Test-Route "book route (no token)" "/v1/books" "401"
Test-Route "catalog public" "/v1/catalog/books" "200"
Test-Route "llm gateway route exists" "/v1/llm/jobs/fake-id" "401"
Test-Route "languagetool upstream" "/languagetool/v2/languages" "200"
Test-Route "SPA index" "/" "200"

if ($fail -ne 0) {
    Write-Host ""
    Write-Host "Some checks failed. Is the stack healthy? docker compose ps"
    exit 1
}

Write-Host ""
Write-Host "All smoke checks passed."
