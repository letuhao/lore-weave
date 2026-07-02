# E2E-P1 (edge slice) — through-the-real-edge, post-stack-rebuild. Proves the
# BFF proxy, ai-gateway federation of the registry_ MCP tools, and the full
# agent self-registration path through the gateway. Run against the live compose
# stack (rebuilt images). The full-turn LLM injection (E2E-P1-B/D) is a separate
# manual/live check (needs lm_studio) — see the plan; result recorded 2026-07-03:
# a published user skill's body reached a real Qwen-7B turn (asst emitted the
# skill's marker "XYZZY-INJECTED", context_breakdown persisted).
param(
  [string]$Bff = "http://localhost:3123",
  [string]$Gateway = "http://localhost:8218",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
  [string]$InternalToken = "dev_internal_token",
  [string]$PgContainer = "infra-postgres-1"
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

$u = [guid]::NewGuid().ToString()
$tok = New-Jwt $u
Write-Host "== E2E-P1 edge smoke (BFF $Bff · gateway $Gateway) ==" -ForegroundColor Cyan

# 1) BFF proxy CRUD
$name = "io.github.edge/pack-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$r = Invoke-WebRequest -Method POST -Uri "$Bff/v1/agent-registry/plugins" -Headers @{Authorization = "Bearer $tok" } -Body (@{name = $name; description = "edge" } | ConvertTo-Json) -ContentType "application/json" -SkipHttpErrorCheck
Check ($r.StatusCode -eq 201) "BFF proxy: create plugin 201"
$plug = ($r.Content | ConvertFrom-Json).plugin_id
$r = Invoke-WebRequest -Method GET -Uri "$Bff/v1/agent-registry/plugins?limit=5" -Headers @{Authorization = "Bearer $tok" } -SkipHttpErrorCheck
Check ($r.StatusCode -eq 200) "BFF proxy: list 200"
$r = Invoke-WebRequest -Method DELETE -Uri "$Bff/v1/agent-registry/plugins/$plug" -Headers @{Authorization = "Bearer $tok" } -SkipHttpErrorCheck
Check ($r.StatusCode -eq 204) "BFF proxy: delete 204"

# 2) ai-gateway federation of the registry_ MCP tools
$mcpHeaders = @{ "X-Internal-Token" = $InternalToken; "X-User-Id" = $u; "Accept" = "application/json, text/event-stream" }
$r = Invoke-WebRequest -Method POST -Uri "$Gateway/mcp" -Headers $mcpHeaders -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' -ContentType "application/json" -SkipHttpErrorCheck
$body = $r.Content
$expected = @("registry_list_skills", "registry_get_skill", "registry_propose_skill", "registry_update_skill", "registry_set_skill_enabled")
$missing = $expected | Where-Object { $body -notmatch [regex]::Escape($_) }
Check ($missing.Count -eq 0) "ai-gateway federates all 5 registry_ tools (prefix enforced)"

# 3) agent self-registration THROUGH the gateway → proposal row (owner from envelope)
$slug = "edge-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() % 100000)"
$callBody = @{ jsonrpc = "2.0"; id = 2; method = "tools/call"; params = @{ name = "registry_propose_skill"; arguments = @{ slug = $slug; description = "via gateway"; body_md = "# Edge" } } } | ConvertTo-Json -Depth 8
$r = Invoke-WebRequest -Method POST -Uri "$Gateway/mcp" -Headers $mcpHeaders -Body $callBody -ContentType "application/json" -SkipHttpErrorCheck
Check ($r.Content -match "Awaiting the user") "registry_propose_skill through gateway returns propose-pattern message"
$row = (docker exec $PgContainer psql -U loreweave -d loreweave_agent_registry -tAc "SELECT status FROM skill_proposals WHERE owner_user_id='$u' AND slug='$slug'" 2>$null | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
Check ($row -eq "pending") "proposal row created with envelope owner (federation carried X-User-Id)"

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P1 EDGE E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails EDGE CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
