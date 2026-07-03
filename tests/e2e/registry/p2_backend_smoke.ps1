# E2E-P2 (backend slice) — mcp_server_registrations CRUD + per-user effective
# resolution + isolation + internal-only guard. Real stack (live Postgres).
# The ai-gateway per-user overlay (REG-P2-03) is a separate slice.
param(
  [string]$BaseUrl = "http://localhost:8099",
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
function Req($method, $path, $token, $body, $hdr) {
  $headers = @{}
  if ($token) { $headers["Authorization"] = "Bearer $token" }
  if ($hdr) { $hdr.GetEnumerator() | ForEach-Object { $headers[$_.Key] = $_.Value } }
  $a = @{ Method = $method; Uri = "$BaseUrl$path"; Headers = $headers; SkipHttpErrorCheck = $true }
  if ($body) { $a["Body"] = ($body | ConvertTo-Json -Depth 8); $a["ContentType"] = "application/json" }
  return Invoke-WebRequest @a
}
$ih = @{ "X-Internal-Token" = $InternalToken }
$a = [guid]::NewGuid().ToString(); $b = [guid]::NewGuid().ToString()
$tokA = New-Jwt $a
Write-Host "== E2E-P2 backend smoke @ $BaseUrl ==" -ForegroundColor Cyan

# internal endpoint → 201 + auto prefix that namespaces (never shadows System)
$r = Req POST "/v1/agent-registry/mcp-servers" $tokA @{ display_name = "homelab"; endpoint_url = "http://host.docker.internal:9100/mcp" } $null
Check ($r.StatusCode -eq 201) "register internal MCP server → 201"
$m = $r.Content | ConvertFrom-Json
Check ($m.tool_name_prefix -match '^u_[0-9a-f]{8}_$') "auto tool_name_prefix u_<hash>_ (anti-shadow)"
$mid = $m.mcp_server_id

# external public host → 400 (P3 security territory)
$r = Req POST "/v1/agent-registry/mcp-servers" $tokA @{ display_name = "ext"; endpoint_url = "https://mcp.example.com/mcp" } $null
Check ($r.StatusCode -eq 400) "external public host rejected → 400 (deferred to P3)"

# resolves in effective-mcp-servers with prefix + version
$eff = Req GET "/internal/effective-mcp-servers?user_id=$a" $null $null $ih
$effObj = $eff.Content | ConvertFrom-Json
Check (($effObj.servers | Where-Object { $_.mcp_server_id -eq $mid }).Count -eq 1) "server in effective resolve"
Check ($effObj.catalog_version -gt 0) "catalog_version present (Q-CACHE etag)"

# per-user isolation — user B does NOT see A's server
$effB = (Req GET "/internal/effective-mcp-servers?user_id=$b" $null $null $ih).Content | ConvertFrom-Json
Check (($effB.servers | Where-Object { $_.mcp_server_id -eq $mid }).Count -eq 0) "per-user isolation (B cannot see A's server)"

# disable → drops from effective (version bumps)
$v1 = $effObj.catalog_version
$r = Req PUT "/v1/agent-registry/mcp-servers/$mid/enablement" $tokA @{ enabled = $false } $null
Check ($r.StatusCode -eq 200) "disable server → 200"
$eff2 = (Req GET "/internal/effective-mcp-servers?user_id=$a" $null $null $ih).Content | ConvertFrom-Json
Check (($eff2.servers | Where-Object { $_.mcp_server_id -eq $mid }).Count -eq 0) "disabled server removed from effective"
Check ($eff2.catalog_version -gt $v1) "catalog_version bumped on toggle"

# delete
$r = Req DELETE "/v1/agent-registry/mcp-servers/$mid" $tokA $null $null
Check ($r.StatusCode -eq 204) "delete server → 204"

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P2 BACKEND E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails P2 CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
