# On-prem / ngrok-first deploy: full stack, single public port (default :5296).
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$infraDir = Join-Path $repoRoot "infra"
$envFile = Join-Path $infraDir ".env"

if (-not (Test-Path $envFile)) {
    Write-Error "Missing $envFile — copy from infra/.env.example and set JWT_SECRET (>= 32 chars)."
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        Set-Item -Path "env:$name" -Value $value
    }
}

if (-not $env:JWT_SECRET -or $env:JWT_SECRET.Length -lt 32) {
    Write-Error "JWT_SECRET must be set in infra/.env (>= 32 characters)."
}

if (-not $env:INTERNAL_SERVICE_TOKEN -or $env:INTERNAL_SERVICE_TOKEN.Length -lt 32) {
    Write-Error "INTERNAL_SERVICE_TOKEN must be set in infra/.env (>= 32 characters, different from JWT_SECRET)."
}
if ($env:INTERNAL_SERVICE_TOKEN -eq "dev_internal_token") {
    Write-Error "INTERNAL_SERVICE_TOKEN must not be the dev default (dev_internal_token)."
}
if ($env:JWT_SECRET -eq $env:INTERNAL_SERVICE_TOKEN) {
    Write-Error "JWT_SECRET and INTERNAL_SERVICE_TOKEN must be different."
}

if (-not $env:PUBLIC_HTTP_PORT) { $env:PUBLIC_HTTP_PORT = "5296" }

& bash (Join-Path $repoRoot "scripts/validate-compose-secrets.sh")

Write-Host "[deploy-onprem] Building stack..."
& (Join-Path $repoRoot "scripts/build-stack.sh")

Write-Host "[deploy-onprem] Starting prod overlay on host port $($env:PUBLIC_HTTP_PORT)..."
Push-Location $infraDir
try {
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Stack is up. Public entry: http://localhost:$($env:PUBLIC_HTTP_PORT)"
Write-Host ""
Write-Host "Next steps (ngrok):"
Write-Host "  1. ngrok http $($env:PUBLIC_HTTP_PORT)"
Write-Host "  2. Set PUBLIC_APP_URL in infra/.env to the ngrok HTTPS URL"
Write-Host "  3. docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
Write-Host ""
Write-Host "Docs: infra/ON_PREM_DEPLOY.md"
