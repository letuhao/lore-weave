# Pre-merge / post-deploy review (PowerShell).
param([string]$BaseUrl = "")

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== Layer 0: offline ==="
Push-Location (Join-Path $repoRoot "services/api-gateway-bff")
try { npm test } finally { Pop-Location }

if (-not (Test-Path (Join-Path $repoRoot "infra/.env"))) {
    $env:JWT_SECRET = "loreweave_local_dev_jwt_secret_change_me_32chars"
}
Push-Location (Join-Path $repoRoot "infra")
try {
    docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
    Write-Host "compose config OK"
} finally { Pop-Location }

if (-not $BaseUrl) {
    Write-Host ""
    Write-Host "Layer 1/2 skipped. Re-run with:"
    Write-Host "  .\infra\review-onprem.ps1 http://localhost:5296"
    exit 0
}

Write-Host ""
Write-Host "=== Layer 1: smoke ==="
& (Join-Path $repoRoot "infra/smoke-onprem.ps1") -BaseUrl $BaseUrl

Write-Host ""
Write-Host "=== Layer 2: real test (bash) ==="
Write-Host "Run in Git Bash: infra/realtest-onprem.sh $BaseUrl"
Write-Host "(PowerShell realtest not yet ported — use Git Bash or WSL)"
