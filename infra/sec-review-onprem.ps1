# Go-live network isolation audit (Windows wrapper).
param([string]$Base = "http://localhost:$($env:PUBLIC_HTTP_PORT ?? '5296')")

$bash = Get-Command bash -ErrorAction SilentlyContinue
if (-not $bash) {
    Write-Error "Git Bash required to run infra/sec-review-onprem.sh"
}
& bash (Join-Path $PSScriptRoot "sec-review-onprem.sh") $Base
exit $LASTEXITCODE
