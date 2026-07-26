# E2E-P3 (M2 slice) — REG-P3-05: supply-chain scan + quarantine + rescan + detail,
# probed against a REAL running MCP server (agent-registry's OWN /mcp, reachable in
# the docker network). Proves the Go MCP probe client + scan linter + status machine
# end-to-end on a live server.
param(
  [string]$BaseUrl = "http://localhost:8230",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
  [string]$InternalToken = "dev_internal_token",
  # in-docker-network URL the probe (running INSIDE the container) dials:
  [string]$SelfMcp = "http://agent-registry-service:8099/mcp"
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
function Req($method, $path, $token, $body) {
  $headers = @{}
  if ($token) { $headers["Authorization"] = "Bearer $token" }
  $a = @{ Method = $method; Uri = "$BaseUrl$path"; Headers = $headers; SkipHttpErrorCheck = $true }
  if ($body) { $a["Body"] = ($body | ConvertTo-Json -Depth 8); $a["ContentType"] = "application/json" }
  return Invoke-WebRequest @a
}
$u = [guid]::NewGuid().ToString()
$tok = New-Jwt $u
Write-Host "== E2E-P3 M2 (scan + quarantine) @ $BaseUrl ==" -ForegroundColor Cyan

# register the registry's own /mcp (internal under the dev flag → active)
$r = Req POST "/v1/agent-registry/mcp-servers" $tok @{ display_name = "self-registry"; endpoint_url = $SelfMcp }
Check ($r.StatusCode -eq 201) "register self /mcp → 201"
$mid = ($r.Content | ConvertFrom-Json).mcp_server_id

# synchronous rescan → probe the live server, scan its tools
$r = Req POST "/v1/agent-registry/mcp-servers/$mid/rescan" $tok $null
Check ($r.StatusCode -eq 200) "rescan → 200"
$sc = $r.Content | ConvertFrom-Json
Check ($sc.last_health.ok -eq $true) "probe reached the live MCP server (health.ok)"
Check ($sc.scan_result.tool_count -ge 1) "tools/list returned $($sc.scan_result.tool_count) tools"
Check ($sc.scan_result.clean -eq $true) "registry's own tools scan CLEAN (no injection markers)"
Check ($sc.status -eq "active") "clean scan → status active"
Check (($sc.scan_result.tools | Measure-Object).Count -ge 1) "per-tool summary present (detail tool browser)"

# detail endpoint reflects the scan
$d = (Req GET "/v1/agent-registry/mcp-servers/$mid" $tok $null).Content | ConvertFrom-Json
Check ($d.scan_result.tool_count -ge 1) "detail carries scan_result"
Check ($d.last_scanned_at -ne $null) "detail carries last_scanned_at"
Check ($d.last_health.ok -eq $true) "detail carries last_health"

# a DOWN server → probe fails → status error (register a dead in-network port)
$r = Req POST "/v1/agent-registry/mcp-servers" $tok @{ display_name = "dead"; endpoint_url = "http://agent-registry-service:9999/mcp" }
$dead = ($r.Content | ConvertFrom-Json).mcp_server_id
$r = Req POST "/v1/agent-registry/mcp-servers/$dead/rescan" $tok $null
$dsc = $r.Content | ConvertFrom-Json
Check ($dsc.status -eq "error") "unreachable server → status error (won't federate)"
Check ($dsc.last_health.ok -eq $false) "down server health.ok=false"

# accept-risk on a non-quarantined server → 409
$r = Req POST "/v1/agent-registry/mcp-servers/$mid/accept-risk" $tok $null
Check ($r.StatusCode -eq 409) "accept-risk on an active (non-quarantined) server → 409"

# cleanup
Req DELETE "/v1/agent-registry/mcp-servers/$mid" $tok $null | Out-Null
Req DELETE "/v1/agent-registry/mcp-servers/$dead" $tok $null | Out-Null

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P3-M2 E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails P3-M2 CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
