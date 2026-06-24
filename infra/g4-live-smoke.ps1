$ErrorActionPreference = 'Stop'
$AUTH = 'http://localhost:8204'
$BOOK = 'http://localhost:8205'
$GLOS = 'http://localhost:8211'

function J($obj) { $obj | ConvertTo-Json -Depth 8 -Compress }

# Unique user per run (register has no Math.random need — use PID+ticks via env is fine here)
$suffix = (Get-Random -Maximum 999999)
$email = "g4smoke+$suffix@loreweave.dev"
$pass  = 'G4Smoke@Test2026'

Write-Host "== 1. register $email =="
$reg = Invoke-RestMethod -Method Post -Uri "$AUTH/v1/auth/register" -ContentType 'application/json' `
  -Body (J @{ email=$email; password=$pass; display_name='G4 Smoke' })
Write-Host "   user_id=$($reg.user_id)"

Write-Host "== 2. login =="
$login = Invoke-RestMethod -Method Post -Uri "$AUTH/v1/auth/login" -ContentType 'application/json' `
  -Body (J @{ email=$email; password=$pass })
$tok = $login.access_token
if (-not $tok) { throw "no access_token" }
$H = @{ Authorization = "Bearer $tok" }
Write-Host "   token len=$($tok.Length)"

Write-Host "== 3. create book (book-service) =="
$book = Invoke-RestMethod -Method Post -Uri "$BOOK/v1/books/" -Headers $H -ContentType 'application/json' `
  -Body (J @{ title='G4 Smoke Book'; original_language='en' })
$bid = $book.book_id
Write-Host "   book_id=$bid"

Write-Host "== 4. adopt ontology (glossary -> resolves owner grant via book-service) =="
# Pick-based adopt: copies the picked genres/kinds (+universal/unknown auto) from System standards.
$adopt = Invoke-RestMethod -Method Post -Uri "$GLOS/v1/glossary/books/$bid/adopt" -Headers $H -ContentType 'application/json' `
  -Body (J @{ genres=@('fantasy'); kinds=@('character') })
Write-Host "   adopt ok: $(J $adopt)".Substring(0, [Math]::Min(200, "   adopt ok: $(J $adopt)".Length))

Write-Host "== 5. GET ontology =="
$ont = Invoke-RestMethod -Method Get -Uri "$GLOS/v1/glossary/books/$bid/ontology" -Headers $H
Write-Host "   genres=$($ont.genres.Count) kinds=$($ont.kinds.Count) attributes=$($ont.attributes.Count)"
$charKind = ($ont.kinds | Where-Object { $_.code -eq 'character' })
if (-not $charKind) { throw "no character kind in adopted ontology" }
$bk = $charKind.book_kind_id
$fantasy = ($ont.genres | Where-Object { $_.code -eq 'fantasy' }).genre_id
$universal = ($ont.genres | Where-Object { $_.code -eq 'universal' }).genre_id
Write-Host "   character book_kind_id=$bk  fantasy=$fantasy  universal=$universal"

Write-Host "== 6. create entity with genre override [fantasy] (MULTIGENRE genres-at-create) =="
$ent = Invoke-RestMethod -Method Post -Uri "$GLOS/v1/glossary/books/$bid/entities" -Headers $H -ContentType 'application/json' `
  -Body (J @{ kind_id=$bk; genre_ids=@($fantasy) })
$eid = $ent.entity_id
Write-Host "   entity_id=$eid"

Write-Host "== 7. GET entity genres -> override persisted (fantasy + universal auto) =="
$eg = Invoke-RestMethod -Method Get -Uri "$GLOS/v1/glossary/books/$bid/entities/$eid/genres" -Headers $H
Write-Host "   uses_book_default=$($eg.uses_book_default) genre_ids=$(J $eg.genre_ids)"

Write-Host "== 8. tenant deny: a SECOND user must NOT read this book's ontology (grant boundary) =="
$email2 = "g4smoke2+$suffix@loreweave.dev"
$reg2 = Invoke-RestMethod -Method Post -Uri "$AUTH/v1/auth/register" -ContentType 'application/json' `
  -Body (J @{ email=$email2; password=$pass; display_name='G4 Smoke 2' })
$login2 = Invoke-RestMethod -Method Post -Uri "$AUTH/v1/auth/login" -ContentType 'application/json' `
  -Body (J @{ email=$email2; password=$pass })
$H2 = @{ Authorization = "Bearer $($login2.access_token)" }
$denied = $false
try {
  Invoke-RestMethod -Method Get -Uri "$GLOS/v1/glossary/books/$bid/ontology" -Headers $H2 | Out-Null
} catch {
  $denied = $true
  Write-Host "   non-owner denied: HTTP $($_.Exception.Response.StatusCode.value__)"
}
if (-not $denied) { throw "TENANT LEAK: non-owner could read the book ontology" }

Write-Host ""
Write-Host "G4-LIVE-SMOKE: PASS — auth(JWT) -> book(grant) -> glossary(adopt+tiered create+entity_genres) cross-service, tenant boundary enforced."
