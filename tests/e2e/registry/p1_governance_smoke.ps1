# E2E-P1 (governance slice) — D-REG-BOOK-GRANT + REG-X-02 quota. Real stack.
# Requires the service running with BOOK_SERVICE_INTERNAL_URL set (grant wired)
# and book-service reachable. Self-cleaning (uses a throwaway user id).
param(
  [string]$BaseUrl = "http://localhost:8099",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
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
function Req($method, $path, $token, $body) {
  $a = @{ Method = $method; Uri = "$BaseUrl$path"; Headers = @{Authorization = "Bearer $token" }; SkipHttpErrorCheck = $true }
  if ($body) { $a["Body"] = ($body | ConvertTo-Json -Depth 8); $a["ContentType"] = "application/json" }
  return Invoke-WebRequest @a
}
function Psql($sql) { docker exec $PgContainer psql -U loreweave -d loreweave_agent_registry -tAc $sql 2>$null }

$u = [guid]::NewGuid().ToString()
$tok = New-Jwt $u
Write-Host "== E2E-P1 governance smoke (grant + quota) @ $BaseUrl ==" -ForegroundColor Cyan

# D-REG-BOOK-GRANT: book-tier write for a book the user holds no grant on → fail-closed.
$book = [guid]::NewGuid().ToString()
$r = Req POST "/v1/agent-registry/plugins" $tok @{ name = "io.x/bookpack"; tier = "book"; book_id = $book }
# 404 = grant wired + forbidden (fail-closed); 501 = grant client not configured; 503 = authority down.
Check ($r.StatusCode -in @(404, 501, 503)) "book-tier without grant is refused fail-closed (http=$($r.StatusCode))"
if ($r.StatusCode -eq 404) { Ok "  (grant client wired — ErrForbidden → 404 anti-oracle)" }

# REG-X-02: seed 50 user skills, 51st via API → 429.
for ($i = 1; $i -le 50; $i++) {
  Psql "INSERT INTO skills (tier, owner_user_id, slug, description, body_md) VALUES ('user','$u','quota-$i','d','b')" | Out-Null
}
$cnt = (Psql "SELECT COUNT(*) FROM skills WHERE tier='user' AND owner_user_id='$u'").Trim()
Check ($cnt -eq "50") "seeded 50 user skills"
$r = Req POST "/v1/agent-registry/skills" $tok @{ slug = "over-limit"; description = "d"; body_md = "b" }
Check ($r.StatusCode -eq 429) "51st skill create → 429 QUOTA_EXCEEDED"

# cleanup
Psql "DELETE FROM skills WHERE owner_user_id='$u'" | Out-Null

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P1 GOVERNANCE E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails GOVERNANCE CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
