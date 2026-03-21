# Run Module 01 unit tests (auth-service, gateway, frontend). Execute from any cwd.
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "== auth-service (go test -race) ==" -ForegroundColor Cyan
Push-Location (Join-Path $repoRoot "services\auth-service")
try {
  go test -race ./...
} finally {
  Pop-Location
}

Write-Host "== api-gateway-bff (npm test) ==" -ForegroundColor Cyan
Push-Location (Join-Path $repoRoot "services\api-gateway-bff")
try {
  if (-not (Test-Path "node_modules")) {
    npm ci
  }
  npm test
} finally {
  Pop-Location
}

Write-Host "== frontend (npm test) ==" -ForegroundColor Cyan
Push-Location (Join-Path $repoRoot "frontend")
try {
  if (-not (Test-Path "node_modules")) {
    npm ci
  }
  npm test
} finally {
  Pop-Location
}

Write-Host "all module01 tests ok" -ForegroundColor Green
