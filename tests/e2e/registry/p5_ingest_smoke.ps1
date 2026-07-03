# E2E-P5-C — REG-P5-03 official-registry ingest + admin curation, through the REAL
# agent-registry HTTP API + real DB. Part 1 seeds queue rows and drives the real
# admin approve/reject/dedup/idempotency handlers (deterministic). Part 2 pulls the
# REAL official registry (best-effort — proves the SSRF-safe fetch + mapper on real
# upstream data). The SSRF/model-cap reject-on-approve paths are deterministic units
# (TestApproveIngest_*) since the dev container runs with allow-internal on.
param(
  [string]$Registry = "http://localhost:8230",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
  [string]$PgContainer = "infra-postgres-1",
  [string]$Db = "loreweave_agent_registry",
  [string]$AdminSub = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
)
$ErrorActionPreference = "Stop"
$fails = 0
function Ok($m) { Write-Host "  PASS  $m" -ForegroundColor Green }
function Bad($m) { $script:fails++; Write-Host "  FAIL  $m" -ForegroundColor Red }
function Warn($m) { Write-Host "  WARN  $m" -ForegroundColor Yellow }
function Check($c, $m) { if ($c) { Ok $m } else { Bad $m } }
function B64Url([byte[]]$b) { [Convert]::ToBase64String($b).TrimEnd('=').Replace('+','-').Replace('/','_') }
function New-Jwt([string]$sub, [string]$role) {
  $exp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + 3600
  $h = B64Url([Text.Encoding]::UTF8.GetBytes('{"alg":"HS256","typ":"JWT"}'))
  $p = B64Url([Text.Encoding]::UTF8.GetBytes("{""sub"":""$sub"",""role"":""$role"",""exp"":$exp}"))
  $hmac = [Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($JwtSecret))
  return "$h.$p." + (B64Url($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes("$h.$p"))))
}
function Req($method, $path, $token, $body) {
  $headers = @{}
  if ($token) { $headers["Authorization"] = "Bearer $token" }
  $a = @{ Method = $method; Uri = "$Registry$path"; Headers = $headers; SkipHttpErrorCheck = $true }
  if ($body) { $a["Body"] = ($body | ConvertTo-Json -Depth 8); $a["ContentType"] = "application/json" }
  return Invoke-WebRequest @a
}
function Sql($q) { return (docker exec $PgContainer psql -U loreweave -d $Db -tA -c $q 2>$null | Out-String).Trim() }

$admin = New-Jwt $AdminSub "admin"
$user  = New-Jwt $AdminSub "user"
# a RESOLVABLE public host (approve resolves DNS via the P3 SSRF guard) that is not a
# model endpoint. example.com is reserved + public; the async scan will fail to MCP-probe
# it (→ status error), which is fine — we assert the System row was created, not scanned clean.
$EP = "https://example.com/mcp"
Write-Host "== E2E-P5-C registry ingest @ $Registry ==" -ForegroundColor Cyan

# clean any prior smoke residue
Sql "DELETE FROM registry_ingest_queue WHERE registry_id LIKE 'e2e.ingest/%';" | Out-Null
Sql "DELETE FROM mcp_server_registrations WHERE tier='system' AND endpoint_url='$EP';" | Out-Null

# seed 3 pending queue rows (A public, B same-endpoint-as-A for dedup, C to reject)
Sql "INSERT INTO registry_ingest_queue (source,registry_id,name,endpoint_url,status) VALUES
 ('official','e2e.ingest/pub','e2e pub','$EP','pending'),
 ('official','e2e.ingest/dup','e2e dup','$EP','pending'),
 ('official','e2e.ingest/rej','e2e rej','https://mcp.e2e-ingest-smoke.example/other','pending');" | Out-Null
$aId = (Sql "SELECT ingest_id FROM registry_ingest_queue WHERE registry_id='e2e.ingest/pub';").Trim()
$bId = (Sql "SELECT ingest_id FROM registry_ingest_queue WHERE registry_id='e2e.ingest/dup';").Trim()
$cId = (Sql "SELECT ingest_id FROM registry_ingest_queue WHERE registry_id='e2e.ingest/rej';").Trim()

# --- admin gate ---
$r = Req GET "/v1/agent-registry/admin/ingest/queue?status=pending" $user $null
Check ($r.StatusCode -eq 403) "non-admin → 403 on queue"

$q = (Req GET "/v1/agent-registry/admin/ingest/queue?status=pending" $admin $null).Content | ConvertFrom-Json
Check (($q.items | Where-Object { $_.registry_id -like 'e2e.ingest/*' }).Count -eq 3) "admin lists the 3 seeded pending rows"

# --- approve A → System row + scan ---
$r = Req POST "/v1/agent-registry/admin/ingest/queue/$aId/approve" $admin $null
$ja = $r.Content | ConvertFrom-Json
Check ($r.StatusCode -eq 200 -and $ja.mcp_server_id) "approve A → 200 + System mcp_server_id"
$sid = $ja.mcp_server_id
$sysCount = (Sql "SELECT count(*) FROM mcp_server_registrations WHERE mcp_server_id='$sid' AND tier='system' AND is_external AND endpoint_url='$EP';").Trim()
Check ($sysCount -eq "1") "a System-tier is_external registration was created for the endpoint"
$prefix = (Sql "SELECT tool_name_prefix FROM mcp_server_registrations WHERE mcp_server_id='$sid';").Trim()
Check ($prefix -match '^s_[0-9a-f]{8}_$') "ingested external System server is namespaced (s_<hash>_ — can't shadow platform tools): '$prefix'"
$aStatus = (Sql "SELECT status FROM registry_ingest_queue WHERE ingest_id='$aId';").Trim()
Check ($aStatus -eq "approved") "queue row A → approved + linked"

# --- re-approve A → 409 ---
$r = Req POST "/v1/agent-registry/admin/ingest/queue/$aId/approve" $admin $null
Check ($r.StatusCode -eq 409) "re-approve A → 409 (already reviewed)"

# --- approve B (same endpoint) → dedup-links to the SAME System row ---
$r = Req POST "/v1/agent-registry/admin/ingest/queue/$bId/approve" $admin $null
$jb = $r.Content | ConvertFrom-Json
Check ($r.StatusCode -eq 200 -and $jb.linked_existing -eq $true -and $jb.mcp_server_id -eq $sid) "approve B (dup endpoint) → links existing System row, no duplicate"
$sysDup = (Sql "SELECT count(*) FROM mcp_server_registrations WHERE tier='system' AND endpoint_url='$EP';").Trim()
Check ($sysDup -eq "1") "still exactly ONE System row for the endpoint (dedup held)"

# --- reject C ---
$r = Req POST "/v1/agent-registry/admin/ingest/queue/$cId/reject" $admin @{ reason = "spam" }
Check ($r.StatusCode -eq 200) "reject C → 200"
$cStatus = (Sql "SELECT status FROM registry_ingest_queue WHERE ingest_id='$cId';").Trim()
Check ($cStatus -eq "rejected") "queue row C → rejected"

# --- idempotent upsert (DB-constraint level): same (source,registry_id) twice = ONE row.
# The Go upsertIngest ON-CONFLICT path itself is covered by Part 2 (updated>0) + the
# TestPullOfficialRegistry unit; this asserts the underlying unique constraint. ---
Sql "INSERT INTO registry_ingest_queue (source,registry_id,name,endpoint_url) VALUES ('official','e2e.ingest/idem','x','$EP')
 ON CONFLICT (source,registry_id) DO UPDATE SET name=EXCLUDED.name, updated_at=now();" | Out-Null
Sql "INSERT INTO registry_ingest_queue (source,registry_id,name,endpoint_url) VALUES ('official','e2e.ingest/idem','x2','$EP')
 ON CONFLICT (source,registry_id) DO UPDATE SET name=EXCLUDED.name, updated_at=now();" | Out-Null
$idemCount = (Sql "SELECT count(*) FROM registry_ingest_queue WHERE registry_id='e2e.ingest/idem';").Trim()
Check ($idemCount -eq "1") "re-upsert same (source,registry_id) → exactly ONE row (idempotent)"

# --- Part 2: pull the REAL official registry (best-effort) ---
Write-Host "-- Part 2: real upstream pull (best-effort) --" -ForegroundColor Cyan
$r = Req POST "/v1/agent-registry/admin/ingest/pull" $admin $null
if ($r.StatusCode -eq 200) {
  $counts = $r.Content | ConvertFrom-Json
  Ok "pull → 200 (fetched=$($counts.fetched) new=$($counts.new) updated=$($counts.updated) skipped_no_remote=$($counts.skipped_no_remote))"
  if ($counts.fetched -gt 0) {
    $realPending = (Sql "SELECT count(*) FROM registry_ingest_queue WHERE registry_id NOT LIKE 'e2e.ingest/%' AND status='pending';").Trim()
    Check ([int]$realPending -gt 0) "real upstream entries landed in the queue as pending"
  } else { Warn "upstream returned 0 servers (schema drift or empty) — mapper unit-tested against fixtures" }
} else {
  Warn "real-registry pull returned $($r.StatusCode) (no outbound internet from the container?) — SSRF-safe fetch path is exercised; mapper is unit-tested"
}

# cleanup (leave the real pulled rows; remove only smoke residue)
Sql "DELETE FROM registry_ingest_queue WHERE registry_id LIKE 'e2e.ingest/%';" | Out-Null
Sql "DELETE FROM mcp_server_registrations WHERE tier='system' AND endpoint_url='$EP';" | Out-Null

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P5-C INGEST E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
