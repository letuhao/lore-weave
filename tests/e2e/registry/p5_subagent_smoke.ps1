# E2E-P5 (subagent CRUD) — REG-P5-01 storage/CRUD/resolver + tenancy. The scoped-
# execution RUNTIME is D-REG-P5-SUBAGENT-RUNTIME (deferred, gate #2).
param(
  [string]$BaseUrl = "http://localhost:8230",
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
Write-Host "== E2E-P5 subagent CRUD @ $BaseUrl ==" -ForegroundColor Cyan

$r = Req POST "/v1/agent-registry/subagents" $tokA @{ name = "lore-scout"; description = "reads lore only"; system_prompt = "You scout the glossary + KG. Do not write."; tool_scope = @("glossary_search", "kg_*"); model_ref = "" } $null
Check ($r.StatusCode -eq 201) "create subagent → 201"
$saId = ($r.Content | ConvertFrom-Json).subagent_id
Check ((($r.Content | ConvertFrom-Json).tool_scope) -match "kg_\*") "tool_scope persisted (subset filter)"

$r = Req POST "/v1/agent-registry/subagents" $tokA @{ name = "lore-scout"; system_prompt = "dup" } $null
Check ($r.StatusCode -eq 409) "duplicate name → 409"

$lst = (Req GET "/v1/agent-registry/subagents" $tokA $null $null).Content | ConvertFrom-Json
Check (($lst.items | Where-Object { $_.name -eq "lore-scout" }).Count -eq 1) "list shows the subagent"

$res = (Req GET "/internal/subagents?user_id=$a" $null $null $ih).Content | ConvertFrom-Json
Check (($res.subagents | Where-Object { $_.name -eq "lore-scout" }).Count -eq 1) "/internal/subagents resolves it (system_prompt + tool_scope for the runtime)"
$resB = (Req GET "/internal/subagents?user_id=$b" $null $null $ih).Content | ConvertFrom-Json
Check (($resB.subagents | Where-Object { $_.name -eq "lore-scout" }).Count -eq 0) "tenancy: B does NOT see A's subagent"

# patch (disable) → drops from resolver
Req PATCH "/v1/agent-registry/subagents/$saId" $tokA @{ enabled = $false } $null | Out-Null
$res2 = (Req GET "/internal/subagents?user_id=$a" $null $null $ih).Content | ConvertFrom-Json
Check (($res2.subagents | Where-Object { $_.name -eq "lore-scout" }).Count -eq 0) "disabled subagent drops from the resolver"

Req DELETE "/v1/agent-registry/subagents/$saId" $tokA $null $null | Out-Null

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P5 SUBAGENT-CRUD E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
