# E2E-P1 (REST slice) — skills CRUD + seed + /internal/skills + shadow + import/export +
# per-user toggle + proposal approve/reject/expiry. Real stack (live Postgres).
# The agent-proposes-via-MCP loop (E2E-P1-E) is a separate MCP smoke; here we seed a
# proposal row directly to prove the approve/reject/expiry spine.
param(
  [string]$BaseUrl = "http://localhost:8099",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
  [string]$InternalToken = "dev_internal_token",
  [string]$PgContainer = "infra-postgres-1"
)
$ErrorActionPreference = "Stop"
$fails = 0
function Ok($m)  { Write-Host "  PASS  $m" -ForegroundColor Green }
function Bad($m) { $script:fails++; Write-Host "  FAIL  $m" -ForegroundColor Red }
function Check($c, $m) { if ($c) { Ok $m } else { Bad $m } }
function B64Url([byte[]]$b) { [Convert]::ToBase64String($b).TrimEnd('=').Replace('+','-').Replace('/','_') }
function New-Jwt([string]$sub, [string]$role) {
  $exp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + 3600
  if ($role) { $pl = "{""sub"":""$sub"",""role"":""$role"",""exp"":$exp}" } else { $pl = "{""sub"":""$sub"",""exp"":$exp}" }
  $h = B64Url([Text.Encoding]::UTF8.GetBytes('{"alg":"HS256","typ":"JWT"}'))
  $p = B64Url([Text.Encoding]::UTF8.GetBytes($pl))
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
function Psql($sql) { docker exec $PgContainer psql -U loreweave -d loreweave_agent_registry -tAc $sql 2>$null }

$userA = [guid]::NewGuid().ToString()
$tokA  = New-Jwt $userA ""
Write-Host "== E2E-P1 REST smoke @ $BaseUrl ==" -ForegroundColor Cyan

# E2E-P1-C: 5 System skills seeded
$r = Req GET "/v1/agent-registry/skills?tier=system&limit=100" $tokA $null $null
$sys = ($r.Content | ConvertFrom-Json).items
$slugs = ($sys | ForEach-Object { $_.slug }) | Sort-Object
Check ((@('admin','glossary','knowledge','plan_forge','universal') | Where-Object { $slugs -contains $_ }).Count -eq 5) "5 System skills seeded (byte-identical slugs)"

# E2E-P1-A: create user skill (draft) → publish → list → in /internal/skills → toggle off → gone
$slug = "e2e-recap-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() % 100000)"
$r = Req POST "/v1/agent-registry/skills" $tokA @{ slug = $slug; description = "recap format"; body_md = "# Recap`nrules"; status = "draft"; surfaces = @("chat") } $null
Check ($r.StatusCode -eq 201) "create user skill (draft) 201"
$sid = ($r.Content | ConvertFrom-Json).skill_id

# draft not in /internal/skills
$hdr = @{ "X-Internal-Token" = $InternalToken }
$r = Req GET "/internal/skills?user_id=$userA&surface=chat" $null $null $hdr
$inj = ($r.Content | ConvertFrom-Json).skills
Check (($inj | Where-Object { $_.slug -eq $slug }).Count -eq 0) "draft skill NOT injected"

# publish → snapshot revision
$r = Req PATCH "/v1/agent-registry/skills/$sid" $tokA @{ status = "published" } $null
Check ($r.StatusCode -eq 200) "publish 200"
$r = Req GET "/internal/skills?user_id=$userA&surface=chat" $null $null $hdr
$inj = ($r.Content | ConvertFrom-Json).skills
$mine = $inj | Where-Object { $_.slug -eq $slug }
Check ($mine.Count -eq 1) "published skill injected in /internal/skills"
Check ($mine[0].l1_line -like "* $slug *") "L1 metadata line present"

# revisions
$r = Req GET "/v1/agent-registry/skills/$sid/revisions" $tokA $null $null
Check ((($r.Content | ConvertFrom-Json).items).Count -ge 1) "revision snapshot on publish"

# surface filter: not injected for a non-matching surface
$r = Req GET "/internal/skills?user_id=$userA&surface=translate" $null $null $hdr
Check ((($r.Content | ConvertFrom-Json).skills | Where-Object { $_.slug -eq $slug }).Count -eq 0) "surface filter excludes non-chat surface"

# per-user toggle off → gone from injection
$r = Req PUT "/v1/agent-registry/skills/$sid/enablement" $tokA @{ enabled = $false } $null
Check ($r.StatusCode -eq 200) "toggle skill off 200"
$r = Req GET "/internal/skills?user_id=$userA&surface=chat" $null $null $hdr
Check ((($r.Content | ConvertFrom-Json).skills | Where-Object { $_.slug -eq $slug }).Count -eq 0) "toggled-off skill not injected"

# shadow-check + shadow behavior: create a user skill named 'glossary' (shadows System)
$r = Req GET "/v1/agent-registry/skills/shadow-check?slug=glossary" $tokA $null $null
Check ((($r.Content | ConvertFrom-Json).shadows_system) -eq $true) "shadow-check flags System slug"
$r = Req POST "/v1/agent-registry/skills" $tokA @{ slug = "glossary"; description = "my glossary override"; body_md = "override"; surfaces = @("chat") } $null
Check ($r.StatusCode -eq 201) "create user skill shadowing System slug 201"
$r = Req GET "/internal/skills?user_id=$userA&surface=chat" $null $null $hdr
$body = $r.Content | ConvertFrom-Json
Check ($body.shadowed_system -contains "glossary") "shadowed_system reports the override"
# /review-impl fix: shadowed_system must EXCLUDE a user slug with no System counterpart
Check (-not ($body.shadowed_system -contains $slug)) "shadowed_system excludes non-colliding user slug"

# /review-impl fix: duplicate user slug → 409 (robust SQLSTATE detection, was untested)
$dup = "dupe-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() % 100000)"
$r = Req POST "/v1/agent-registry/skills" $tokA @{ slug = $dup; description = "d"; body_md = "b" } $null
Check ($r.StatusCode -eq 201) "create skill for dup test 201"
$r = Req POST "/v1/agent-registry/skills" $tokA @{ slug = $dup; description = "d"; body_md = "b" } $null
Check ($r.StatusCode -eq 409) "duplicate slug → 409 DUPLICATE"

# validation: oversize body + bad slug + scripts smuggle
$big = "x" * 70000
$r = Req POST "/v1/agent-registry/skills" $tokA @{ slug = "toobig"; description = "d"; body_md = $big } $null
Check ($r.StatusCode -eq 400) "oversize body → 400"
$r = Req POST "/v1/agent-registry/skills" $tokA @{ slug = "Bad Slug"; description = "d"; body_md = "x" } $null
Check ($r.StatusCode -eq 400) "bad slug → 400"
$r = Req POST "/v1/agent-registry/skills" $tokA @{ slug = "scripty"; description = "d"; body_md = "scripts/run.sh" } $null
Check ($r.StatusCode -eq 400) "scripts/ smuggle → 400 (prompt-only)"

# import / export roundtrip
$md = "---`nname: imported-skill-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() % 100000)`ndescription: from md`nsurfaces: [chat, compose]`n---`n`n# Body`nline one"
$r = Req POST "/v1/agent-registry/skills/import" $tokA @{ markdown = $md } $null
Check ($r.StatusCode -eq 201) "import SKILL.md 201"
$impId = ($r.Content | ConvertFrom-Json).skill_id
$r = Req GET "/v1/agent-registry/skills/$impId/export" $tokA $null $null
Check ($r.Content -like "*name: imported-skill*" -and $r.Content -like "*# Body*") "export roundtrips SKILL.md"

# usage reflects skills count
$r = Req GET "/v1/agent-registry/usage" $tokA $null $null
$u = $r.Content | ConvertFrom-Json
Check ($u.skills.used -ge 3 -and $u.skills.limit -eq 50) "usage skills count reflects (D2 limit 50)"

# E2E-P1-F (spine): seed a proposal row via SQL, approve it → skill created.
function Uuid($out) { @($out | ForEach-Object { "$_".Trim() } | Where-Object { $_ -match '^[0-9a-fA-F-]{36}$' })[0] }
$pslug = "proposed-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() % 100000)"
$propId = Uuid (Psql "INSERT INTO skill_proposals (owner_user_id, action, slug, description, body_md, confirm_token) VALUES ('$userA','create','$pslug','proposed skill','# proposed','tok-$([guid]::NewGuid())') RETURNING proposal_id")
Check ($propId -and $propId.Length -eq 36) "proposal seeded"
$r = Req GET "/v1/agent-registry/proposals?status=pending&limit=50" $tokA $null $null
Check ((($r.Content | ConvertFrom-Json).items | Where-Object { $_.slug -eq $pslug }).Count -eq 1) "proposal in inbox (pending)"
$r = Req PUT "/v1/agent-registry/proposals/$propId/approve" $tokA $null $null
Check ($r.StatusCode -eq 200) "approve proposal 200"
$r = Req GET "/v1/agent-registry/skills?q=$pslug&limit=10" $tokA $null $null
Check ((($r.Content | ConvertFrom-Json).items | Where-Object { $_.slug -eq $pslug }).Count -eq 1) "approved proposal created the skill"
# double-approve → not pending
$r = Req PUT "/v1/agent-registry/proposals/$propId/approve" $tokA $null $null
Check ($r.StatusCode -eq 409) "re-approve → 409 (not pending)"

# expiry: seed an already-expired pending proposal → approve directly (no list, which
# would lazy-expire it first) → proposal_expired.
$eslug = "exp-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() % 100000)"
$expPropId = Uuid (Psql "INSERT INTO skill_proposals (owner_user_id, action, slug, description, body_md, confirm_token, expires_at) VALUES ('$userA','create','$eslug','d','#b','tok-$([guid]::NewGuid())', now() - interval '1 day') RETURNING proposal_id")
$r = Req PUT "/v1/agent-registry/proposals/$expPropId/approve" $tokA $null $null
$code = ($r.Content | ConvertFrom-Json).code
Check ($r.StatusCode -eq 409 -and $code -eq "proposal_expired") "expired proposal approve → proposal_expired"

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P1 REST E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails E2E CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
