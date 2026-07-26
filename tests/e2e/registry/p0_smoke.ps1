# E2E-P0-A/B — agent-registry-service foundation smoke (real stack).
#
# Real-run per §6: hits the running service (via BFF when -BaseUrl points at the
# gateway, or the service directly for a service-level run). Proves plugin CRUD +
# cross-tenant isolation (anti-oracle 404) + System-tier admin gate + effective-
# catalog parity + per-user enablement override isolation + catalog version bump.
#
# Usage:
#   pwsh tests/e2e/registry/p0_smoke.ps1 -BaseUrl http://localhost:8099 -InternalToken dev_internal_token
#   (BaseUrl = the BFF http://localhost:3123 for the through-the-edge run)
param(
  [string]$BaseUrl = "http://localhost:8099",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
  [string]$InternalToken = "dev_internal_token"
)
$ErrorActionPreference = "Stop"
$fails = 0
function Ok($m)   { Write-Host "  PASS  $m" -ForegroundColor Green }
function Bad($m)  { $script:fails++; Write-Host "  FAIL  $m" -ForegroundColor Red }
function Check($cond, $m) { if ($cond) { Ok $m } else { Bad $m } }

function B64Url([byte[]]$b) { [Convert]::ToBase64String($b).TrimEnd('=').Replace('+','-').Replace('/','_') }
function New-Jwt([string]$sub, [string]$role) {
  $exp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + 3600
  $header = '{"alg":"HS256","typ":"JWT"}'
  if ($role) { $payload = "{""sub"":""$sub"",""role"":""$role"",""exp"":$exp}" }
  else       { $payload = "{""sub"":""$sub"",""exp"":$exp}" }
  $h = B64Url([Text.Encoding]::UTF8.GetBytes($header))
  $p = B64Url([Text.Encoding]::UTF8.GetBytes($payload))
  $si = "$h.$p"
  $hmac = [Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($JwtSecret))
  $sig = B64Url($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($si)))
  return "$si.$sig"
}
function Req($method, $path, $token, $body, $extraHeaders) {
  $headers = @{}
  if ($token) { $headers["Authorization"] = "Bearer $token" }
  if ($extraHeaders) { $extraHeaders.GetEnumerator() | ForEach-Object { $headers[$_.Key] = $_.Value } }
  $args = @{ Method = $method; Uri = "$BaseUrl$path"; Headers = $headers; SkipHttpErrorCheck = $true }
  if ($body) { $args["Body"] = ($body | ConvertTo-Json -Depth 8); $args["ContentType"] = "application/json" }
  return Invoke-WebRequest @args
}

$userA  = [guid]::NewGuid().ToString()
$userB  = [guid]::NewGuid().ToString()
$tokA   = New-Jwt $userA ""
$tokB   = New-Jwt $userB ""
$tokAdm = New-Jwt ([guid]::NewGuid().ToString()) "admin"

Write-Host "== E2E-P0 agent-registry smoke @ $BaseUrl ==" -ForegroundColor Cyan

# health
$h = Req GET "/health" $null $null $null
Check ($h.StatusCode -eq 200) "health 200"

# E2E-P0-A: create as userA
$name = "io.github.e2e/pack-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$r = Req POST "/v1/agent-registry/plugins" $tokA @{ name = $name; description = "p0 smoke" } $null
Check ($r.StatusCode -eq 201) "create plugin 201"
$plugId = ($r.Content | ConvertFrom-Json).plugin_id
$owner = ($r.Content | ConvertFrom-Json).owner_user_id
Check ($owner -eq $userA) "owner derived from token (not body)"

# userA lists it
$r = Req GET "/v1/agent-registry/plugins?limit=100" $tokA $null $null
$items = ($r.Content | ConvertFrom-Json).items
Check (($items | Where-Object { $_.plugin_id -eq $plugId }).Count -eq 1) "userA sees own plugin in list"

# cross-tenant: userB get → 404 (anti-oracle)
$r = Req GET "/v1/agent-registry/plugins/$plugId" $tokB $null $null
Check ($r.StatusCode -eq 404) "userB get userA plugin → 404 (anti-oracle)"
$r = Req GET "/v1/agent-registry/plugins?limit=100" $tokB $null $null
$bItems = ($r.Content | ConvertFrom-Json).items
Check (($bItems | Where-Object { $_.plugin_id -eq $plugId }).Count -eq 0) "userB list excludes userA plugin"

# patch own
$r = Req PATCH "/v1/agent-registry/plugins/$plugId" $tokA @{ description = "edited" } $null
Check ($r.StatusCode -eq 200) "userA patch own plugin 200"

# tenancy: regular user cannot create System tier
$r = Req POST "/v1/agent-registry/plugins" $tokA @{ name = "io.x/sys"; tier = "system" } $null
Check ($r.StatusCode -eq 403) "regular user create System-tier → 403"

# E2E-P0-B: admin creates a System plugin; catalog parity + enablement override
$sysName = "dev.loreweave/e2e-sys-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$r = Req POST "/v1/agent-registry/plugins" $tokAdm @{ name = $sysName; tier = "system" } $null
Check ($r.StatusCode -eq 201) "admin create System plugin 201"
$sysId = ($r.Content | ConvertFrom-Json).plugin_id

$hdr = @{ "X-Internal-Token" = $InternalToken }
$r = Req GET "/internal/effective-catalog?user_id=$userA" $null $null $hdr
$cat = $r.Content | ConvertFrom-Json
$v1 = $cat.catalog_version
Check (($cat.plugins | Where-Object { $_.plugin_id -eq $sysId }).Count -eq 1) "System plugin present in userA catalog"

# userA disables the System plugin (override — System row never mutated)
$r = Req PUT "/v1/agent-registry/plugins/$sysId/enablement" $tokA @{ scope = "user"; enabled = $false } $null
Check ($r.StatusCode -eq 200) "userA disable System plugin (override) 200"

$r = Req GET "/internal/effective-catalog?user_id=$userA" $null $null $hdr
$cat = $r.Content | ConvertFrom-Json
Check (($cat.plugins | Where-Object { $_.plugin_id -eq $sysId }).Count -eq 0) "System plugin now absent from userA catalog"
Check ($cat.catalog_version -gt $v1) "catalog_version bumped after mutation"

# isolation: userB still sees it (override is per-user)
$r = Req GET "/internal/effective-catalog?user_id=$userB" $null $null $hdr
$catB = $r.Content | ConvertFrom-Json
Check (($catB.plugins | Where-Object { $_.plugin_id -eq $sysId }).Count -eq 1) "userB catalog unaffected by userA override"

# internal token required
$r = Req GET "/internal/effective-catalog?user_id=$userA" $null $null $null
Check ($r.StatusCode -eq 401) "effective-catalog without internal token → 401"

# cascade-preview + delete
$r = Req GET "/v1/agent-registry/plugins/$plugId/cascade-preview" $tokA $null $null
Check ($r.StatusCode -eq 200) "cascade-preview 200"
$r = Req DELETE "/v1/agent-registry/plugins/$plugId" $tokA $null $null
Check ($r.StatusCode -eq 204) "userA delete own plugin 204"
$r = Req GET "/v1/agent-registry/plugins/$plugId" $tokA $null $null
Check ($r.StatusCode -eq 404) "deleted plugin → 404"

# usage + audit
$r = Req GET "/v1/agent-registry/usage" $tokA $null $null
$u = $r.Content | ConvertFrom-Json
Check ($u.skills.limit -eq 50 -and $u.mcp_servers.limit -eq 10) "usage quota limits surfaced (D2)"
$r = Req GET "/v1/agent-registry/audit?limit=100" $tokA $null $null
$aud = ($r.Content | ConvertFrom-Json).items
Check ($aud.Count -ge 3) "audit trail has userA rows (create/patch/enable/delete)"

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P0 E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails E2E CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
