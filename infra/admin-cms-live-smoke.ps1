$ErrorActionPreference = 'Stop'
$GW = 'http://localhost:3123'
function J($o){ $o | ConvertTo-Json -Depth 6 -Compress }

Write-Host "== 1. login claude-test (admin principal) =="
$login = Invoke-RestMethod -Method Post -Uri "$GW/v1/auth/login" -ContentType 'application/json' `
  -Body (J @{ email='claude-test@loreweave.dev'; password='Claude@Test2026' })
$userTok = $login.access_token
$H = @{ Authorization = "Bearer $userTok" }
Write-Host "   user token len=$($userTok.Length)"

Write-Host "== 2. exchange for an admin session (RS256 admin JWT) =="
$sess = Invoke-RestMethod -Method Post -Uri "$GW/v1/admin/session" -Headers $H
$adminTok = $sess.token
$AH = @{ Authorization = "Bearer $adminTok" }
Write-Host "   admin token len=$($adminTok.Length) role=$($sess.role)"

Write-Host "== 3. admin CREATE a system genre (through the gateway -> glossary) =="
$g = Invoke-RestMethod -Method Post -Uri "$GW/v1/glossary/system-genres" -Headers $AH -ContentType 'application/json' `
  -Body (J @{ name='Steampunk'; code='steampunk_cms'; icon='⚙️' })
Write-Host "   created genre_id=$($g.genre_id) code=$($g.code)"

Write-Host "== 4. admin PATCH it =="
$p = Invoke-RestMethod -Method Patch -Uri "$GW/v1/glossary/system-genres/$($g.genre_id)" -Headers $AH -ContentType 'application/json' `
  -Body (J @{ name='Steam' })
Write-Host "   patched name=$($p.name)"

Write-Host "== 5. TENANCY: the plain USER token must NOT write System tier (expect 401) =="
$denied = $false
try { Invoke-RestMethod -Method Post -Uri "$GW/v1/glossary/system-genres" -Headers $H -ContentType 'application/json' -Body (J @{ name='Hack' }) | Out-Null }
catch { $denied = $true; Write-Host "   user token denied: HTTP $($_.Exception.Response.StatusCode.value__)" }
if (-not $denied) { throw 'TENANCY LEAK: a regular user wrote the System tier' }

Write-Host "== 6. admin DELETE the genre (cleanup) =="
Invoke-RestMethod -Method Delete -Uri "$GW/v1/glossary/system-genres/$($g.genre_id)" -Headers $AH | Out-Null
Write-Host "   deleted"

Write-Host "== 7. a NON-admin user cannot get an admin session (expect 403) =="
$sfx = Get-Random -Maximum 999999
$email2 = "cms_nonadmin+$sfx@loreweave.dev"
Invoke-RestMethod -Method Post -Uri "$GW/v1/auth/register" -ContentType 'application/json' -Body (J @{ email=$email2; password='Claude@Test2026'; display_name='NonAdmin' }) | Out-Null
$login2 = Invoke-RestMethod -Method Post -Uri "$GW/v1/auth/login" -ContentType 'application/json' -Body (J @{ email=$email2; password='Claude@Test2026' })
$H2 = @{ Authorization = "Bearer $($login2.access_token)" }
$na = $false
try { Invoke-RestMethod -Method Post -Uri "$GW/v1/admin/session" -Headers $H2 | Out-Null }
catch { $na = $true; Write-Host "   non-admin denied: HTTP $($_.Exception.Response.StatusCode.value__)" }
if (-not $na) { throw 'NON-ADMIN got an admin session' }

Write-Host ""
Write-Host "ADMIN-CMS-LIVE-SMOKE: PASS — login -> admin/session (RS256) -> System-tier CRUD; user token + non-admin both denied."
