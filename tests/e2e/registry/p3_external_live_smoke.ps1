# E2E-P3-07 — the REAL external-MCP end-to-end (clears D-REG-P3-EXTERNAL-LIVE).
# Registers a genuine PUBLIC third-party MCP server (DeepWiki — no auth, streamable-http),
# proves it is classified EXTERNAL + quarantined, scans its REAL tools, federates it into
# the user's overlay through ai-gateway, and CALLS one of its tools through the gateway —
# the pinned egress dispatcher connecting to the real external host (no internal token
# leaked). Cross-tenant isolation checked. Requires the dev stack with the gateway overlay ON.
param(
  [string]$Reg = "http://localhost:8230",
  [string]$Gateway = "http://localhost:8218",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
  [string]$InternalToken = "dev_internal_token",
  [string]$Endpoint = "https://mcp.deepwiki.com/mcp"
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
function RegReq($method, $path, $token, $body) {
  $headers = @{ Authorization = "Bearer $token" }
  $a = @{ Method = $method; Uri = "$Reg$path"; Headers = $headers; SkipHttpErrorCheck = $true }
  if ($body) { $a["Body"] = ($body | ConvertTo-Json -Depth 8); $a["ContentType"] = "application/json" }
  return Invoke-WebRequest @a
}
function Gw($userId, $bodyJson) {
  return Invoke-WebRequest -Method POST -Uri "$Gateway/mcp" -SkipHttpErrorCheck -ContentType "application/json" -Body $bodyJson `
    -Headers @{ "X-Internal-Token" = $InternalToken; "X-User-Id" = $userId; "Accept" = "application/json, text/event-stream" }
}
$a = [guid]::NewGuid().ToString(); $b = [guid]::NewGuid().ToString()
$tokA = New-Jwt $a
Write-Host "== E2E-P3-07 REAL external MCP ($Endpoint) ==" -ForegroundColor Cyan

# 1) register the REAL public server → EXTERNAL + QUARANTINED
$r = RegReq POST "/v1/agent-registry/mcp-servers" $tokA @{ display_name = "DeepWiki"; endpoint_url = $Endpoint }
Check ($r.StatusCode -eq 201) "register real public MCP → 201"
$m = $r.Content | ConvertFrom-Json
$mid = $m.mcp_server_id
Check ($m.is_external -eq $true) "classified is_external=true (SSRF guard allowed a public host)"
Check ($m.status -eq "pending") "QUARANTINED on register (status=pending, not yet federated)"

# 2) scan the REAL server (probe fetches its actual tools/list) → clean → active
$sc = (RegReq POST "/v1/agent-registry/mcp-servers/$mid/rescan" $tokA $null).Content | ConvertFrom-Json
Check ($sc.last_health.ok -eq $true) "probe reached the REAL external server (health.ok)"
Check ($sc.scan_result.tool_count -ge 1) "tools/list returned $($sc.scan_result.tool_count) real tools"
$hasReadStruct = ($sc.scan_result.tools | Where-Object { $_.name -eq "read_wiki_structure" }).Count -ge 1
Check $hasReadStruct "DeepWiki's real tool 'read_wiki_structure' is in the scan"
Check ($sc.scan_result.clean -eq $true) "supply-chain scan CLEAN → status active"
Check ($sc.status -eq "active") "external server cleared quarantine → active"

# 3) it federates into A's overlay through the gateway (prefixed, never bare)
$prefix = $m.tool_name_prefix
$namesA = ([regex]::Matches((Gw $a '{"jsonrpc":"2.0","id":1,"method":"tools/list"}').Content, '"name"\s*:\s*"([^"]+)"') | ForEach-Object { $_.Groups[1].Value })
Check ($namesA -contains "$($prefix)read_wiki_structure") "gateway federates '$($prefix)read_wiki_structure' into A's catalog"

# 4) CALL the real external tool through the gateway (pinned egress dispatcher → real host)
$call = '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"' + $prefix + 'read_wiki_structure","arguments":{"repoName":"modelcontextprotocol/servers"}}}'
$cr = Gw $a $call
$body = $cr.Content
Check ($cr.StatusCode -eq 200) "gateway tools/call → 200"
$isError = $body -match '"isError"\s*:\s*true'
Check ((-not $isError) -and ($body -match 'result')) "REAL external tool returned a result through the pinned egress path (no error)"
Check ($body -match 'topic|wiki|page|structure|documentation|##|-') "result carries real DeepWiki content"

# 5) cross-tenant isolation — user B does NOT see A's external server
$namesB = ([regex]::Matches((Gw $b '{"jsonrpc":"2.0","id":1,"method":"tools/list"}').Content, '"name"\s*:\s*"([^"]+)"') | ForEach-Object { $_.Groups[1].Value })
Check (-not ($namesB -contains "$($prefix)read_wiki_structure")) "user B does NOT see A's external server (isolation)"

# cleanup
RegReq DELETE "/v1/agent-registry/mcp-servers/$mid" $tokA $null | Out-Null

Write-Host ""
if ($fails -eq 0) { Write-Host "REAL EXTERNAL-MCP E2E PASSED — D-REG-P3-EXTERNAL-LIVE CLEARED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
