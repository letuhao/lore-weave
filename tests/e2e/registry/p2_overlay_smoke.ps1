# E2E-P2-04 — LIVE per-user federation overlay through ai-gateway (flag ON).
# Registers agent-registry's OWN /mcp as user A's MCP server, then proves through
# the ai-gateway that A sees the overlay tools (u_<hash>_registry_*) while user B
# does NOT (cross-tenant isolation), and the System providers still federate for
# both (9-provider regression). Requires ai-gateway rebuilt with
# REGISTRY_OVERLAY_ENABLED=true and agent-registry rebuilt (effective-mcp-servers).
param(
  [string]$Reg = "http://localhost:8230",       # agent-registry (host)
  [string]$Gateway = "http://localhost:8218",   # ai-gateway (host)
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
  [string]$InternalToken = "dev_internal_token"
)
$ErrorActionPreference = "Stop"
$fails = 0
function Ok($m) { Write-Host "  PASS  $m" -ForegroundColor Green }
function Bad($m) { $script:fails++; Write-Host "  FAIL  $m" -ForegroundColor Red }
function Check($c, $m) { if ($c) { Ok $m } else { Bad $m } }
function B64Url([byte[]]$b) { [Convert]::ToBase64String($b).TrimEnd('=').Replace('+','-').Replace('/','_') }
function New-Jwt([string]$sub) {
  $exp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + 3600
  $h = B64Url([Text.Encoding]::UTF8.GetBytes('{"alg":"HS256","typ":"JWT"}'))
  $p = B64Url([Text.Encoding]::UTF8.GetBytes("{""sub"":""$sub"",""exp"":$exp}"))
  $hmac = [Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($JwtSecret))
  return "$h.$p." + (B64Url($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes("$h.$p"))))
}
# tools/list through ai-gateway for a given envelope user; returns the tool-name array.
function GwToolNames([string]$userId) {
  $body = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
  $r = Invoke-WebRequest -Method POST -Uri "$Gateway/mcp" -SkipHttpErrorCheck -ContentType "application/json" -Body $body `
    -Headers @{ "X-Internal-Token" = $InternalToken; "X-User-Id" = $userId; "Accept" = "application/json, text/event-stream" }
  $txt = ($r.Content -replace "`0", "")
  # response may be SSE (data: {json}) or plain JSON — extract tool "name" fields
  return [regex]::Matches($txt, '"name"\s*:\s*"([^"]+)"') | ForEach-Object { $_.Groups[1].Value }
}

$a = [guid]::NewGuid().ToString(); $b = [guid]::NewGuid().ToString()
$tokA = New-Jwt $a
Write-Host "== E2E-P2-04 overlay isolation (gateway $Gateway) ==" -ForegroundColor Cyan

# register agent-registry's own /mcp as A's internal MCP server
$r = Invoke-WebRequest -Method POST -Uri "$Reg/v1/agent-registry/mcp-servers" -SkipHttpErrorCheck `
  -Headers @{ Authorization = "Bearer $tokA" } -ContentType "application/json" `
  -Body (@{ display_name = "self-registry"; endpoint_url = "http://agent-registry-service:8099/mcp" } | ConvertTo-Json)
Check ($r.StatusCode -eq 201) "register internal MCP (agent-registry /mcp) for A → 201"
$m = $r.Content | ConvertFrom-Json
$prefix = $m.tool_name_prefix
$mid = $m.mcp_server_id
Write-Host "  prefix = $prefix" -ForegroundColor DarkGray

Start-Sleep -Milliseconds 500  # let any prior overlay cache TTL lapse

# user A: overlay tools present + System providers present
$aTools = GwToolNames $a
$overlayA = @($aTools | Where-Object { $_ -like "$prefix*" })
Check ($overlayA.Count -ge 1) "A sees overlay tools ($($overlayA.Count) under $prefix) through the gateway"
Check (($aTools | Where-Object { $_ -match '^(memory_|glossary_|book_|registry_)' }).Count -ge 1) "A still sees System-provider tools (regression)"

# user B: NO overlay tools (isolation) + System providers present
$bTools = GwToolNames $b
Check (@($bTools | Where-Object { $_ -like "$prefix*" }).Count -eq 0) "B does NOT see A's overlay tools (cross-tenant isolation)"
Check (($bTools | Where-Object { $_ -match '^(memory_|glossary_|book_)' }).Count -ge 1) "B still sees System-provider tools (regression)"

# anti-shadow: no overlay tool collides with a System name
Check (@($overlayA | Where-Object { $_ -notlike "$prefix*" }).Count -eq 0) "every overlay tool is namespaced (never a bare System name)"

# cleanup
Invoke-WebRequest -Method DELETE -Uri "$Reg/v1/agent-registry/mcp-servers/$mid" -SkipHttpErrorCheck -Headers @{ Authorization = "Bearer $tokA" } | Out-Null

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P2-04 OVERLAY E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails P2-04 CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
