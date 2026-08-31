# iso.ps1 — drive the ISOLATED local stack from PowerShell. See iso.sh for the full story.
#
#     .\iso.ps1 up -d postgres redis neo4j glossary-service knowledge-service worker-infra
#     .\iso.ps1 build knowledge-service
#     .\iso.ps1 ps
#     .\iso.ps1 down                 # containers only; volumes survive
#     .\iso.ps1 down -v              # ⚠️ destroys the isolated DATA too
#
# Dropping `-p lw-iso` from the underlying command applies the isolated PORT MAP to the
# SHARED project — recreating the base stack's containers on shifted ports against the
# base stack's volumes. That is why this exists instead of a documented command line.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$project = if ($env:LW_ISO_PROJECT) { $env:LW_ISO_PROJECT } else { 'lw-iso' }

if ($args.Count -eq 0) {
    Get-Content $MyInvocation.MyCommand.Path -TotalCount 12 |
        ForEach-Object { $_ -replace '^# ?', '' }
    exit 2
}

# A stale override publishes a new service on its BASE port — a collision that reads as
# "the other stack is broken".
& python (Join-Path $here 'gen-isolated-compose.py') --check | Out-Null
if ($LASTEXITCODE -ne 0) {
    & python (Join-Path $here 'gen-isolated-compose.py') --check
    Write-Host ''
    Write-Host 'iso.ps1: refusing to run against a stale port map.'
    exit 1
}

& docker compose `
    -p $project `
    -f (Join-Path $here 'docker-compose.yml') `
    -f (Join-Path $here 'docker-compose.isolated.yml') `
    @args
exit $LASTEXITCODE
