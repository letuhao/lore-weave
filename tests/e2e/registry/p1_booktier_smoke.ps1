# E2E-P1 (book-tier slice) — /review-impl fixes: book-tier skills resolve+inject
# for their book context, are book-scoped (no leak), and are grant-gated manageable
# (create→get→delete). Needs the test account (real grant on an owned book) + the
# service with BOOK_SERVICE_INTERNAL_URL wired.
param(
  [string]$BaseUrl = "http://localhost:8099",
  [string]$Bff = "http://localhost:3123",
  [string]$InternalToken = "dev_internal_token",
  [string]$UserId = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c",
  [string]$BookId = "019d872f-f3a3-7076-88b8-6c902054860f"
)
$ErrorActionPreference = "Stop"
$fails = 0
function Ok($m) { Write-Host "  PASS  $m" -ForegroundColor Green }
function Bad($m) { $script:fails++; Write-Host "  FAIL  $m" -ForegroundColor Red }
function Check($c, $m) { if ($c) { Ok $m } else { Bad $m } }

$login = Invoke-RestMethod -Method POST -Uri "$Bff/v1/auth/login" -ContentType "application/json" -Body (@{ email = "claude-test@loreweave.dev"; password = "Claude@Test2026" } | ConvertTo-Json)
$tok = $login.access_token
if (-not $tok) { throw "login failed" }
$h = @{ Authorization = "Bearer $tok" }
$ih = @{ "X-Internal-Token" = $InternalToken }
Write-Host "== E2E-P1 book-tier smoke @ $BaseUrl ==" -ForegroundColor Cyan

$slug = "booktier-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() % 1000000)"
# create on an OWNED + active book → grant≥edit + Active pass
$r = Invoke-WebRequest -Method POST -Uri "$BaseUrl/v1/agent-registry/skills" -Headers $h -SkipHttpErrorCheck `
  -ContentType "application/json" -Body (@{ slug = $slug; tier = "book"; book_id = $BookId; description = "book skill"; body_md = "# Book"; surfaces = @("chat") } | ConvertTo-Json)
Check ($r.StatusCode -eq 201) "create book-tier skill on owned+active book → 201"
$sid = ($r.Content | ConvertFrom-Json).skill_id

# resolves/injects for that book context
$inj = Invoke-RestMethod -Uri "$BaseUrl/internal/skills?user_id=$UserId&book_id=$BookId&surface=chat" -Headers $ih
Check (($inj.skills | Where-Object { $_.slug -eq $slug }).Count -eq 1) "book skill INJECTED for its book context"

# book-scoped — absent for a different book
$other = Invoke-RestMethod -Uri "$BaseUrl/internal/skills?user_id=$UserId&book_id=99999999-9999-9999-9999-999999999999&surface=chat" -Headers $ih
Check (($other.skills | Where-Object { $_.slug -eq $slug }).Count -eq 0) "book skill NOT leaked to another book"

# grant-gated management (create-can't-delete hole closed)
$r = Invoke-WebRequest -Method GET -Uri "$BaseUrl/v1/agent-registry/skills/$sid" -Headers $h -SkipHttpErrorCheck
Check ($r.StatusCode -eq 200) "get book-tier skill (grant-gated read) → 200"
$r = Invoke-WebRequest -Method DELETE -Uri "$BaseUrl/v1/agent-registry/skills/$sid" -Headers $h -SkipHttpErrorCheck
Check ($r.StatusCode -eq 204) "delete book-tier skill (grant-gated) → 204"

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P1 BOOK-TIER E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails BOOK-TIER CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
