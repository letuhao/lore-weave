# E2E-P4 (backend) — slash_commands + hooks CRUD + /internal resolvers + tenancy.
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
Write-Host "== E2E-P4 commands + hooks @ $BaseUrl ==" -ForegroundColor Cyan

# --- commands ---
$r = Req POST "/v1/agent-registry/commands" $tokA @{ name = "plan-scene"; description = "expand a scene plan"; template_md = "Plan a scene about {{topic}} in the current chapter."; arg_schema = @{ topic = @{ type = "string" } } } $null
Check ($r.StatusCode -eq 201) "create command /plan-scene → 201"
$cid = ($r.Content | ConvertFrom-Json).command_id
Check (($r.Content | ConvertFrom-Json).expand_side -eq "server") "expand_side defaults to server"

$r = Req POST "/v1/agent-registry/commands" $tokA @{ name = "think"; template_md = "x" } $null
Check ($r.StatusCode -eq 409) "reserved built-in /think rejected → 409"

$r = Req POST "/v1/agent-registry/commands" $tokA @{ name = "plan-scene"; template_md = "y" } $null
Check ($r.StatusCode -eq 409) "duplicate name → 409"

$lst = Req GET "/v1/agent-registry/commands" $tokA $null $null
Check ((($lst.Content | ConvertFrom-Json).items | Where-Object { $_.name -eq "plan-scene" }).Count -eq 1) "list shows the command"

# /internal/commands resolver returns it for A, NOT for B
$ic = (Req GET "/internal/commands?user_id=$a" $null $null $ih).Content | ConvertFrom-Json
Check (($ic.commands | Where-Object { $_.name -eq "plan-scene" }).Count -eq 1) "/internal/commands resolves A's command (template present)"
Check (($ic.commands | Where-Object { $_.name -eq "plan-scene" }).template_md -match "topic") "resolver carries template_md for expansion"
$icB = (Req GET "/internal/commands?user_id=$b" $null $null $ih).Content | ConvertFrom-Json
Check (($icB.commands | Where-Object { $_.name -eq "plan-scene" }).Count -eq 0) "tenancy: B does NOT see A's command"

# patch (disable) → drops from resolver
Req PATCH "/v1/agent-registry/commands/$cid" $tokA @{ enabled = $false } $null | Out-Null
$ic2 = (Req GET "/internal/commands?user_id=$a" $null $null $ih).Content | ConvertFrom-Json
Check (($ic2.commands | Where-Object { $_.name -eq "plan-scene" }).Count -eq 0) "disabled command drops from the resolver"

# --- hooks ---
$r = Req POST "/v1/agent-registry/hooks" $tokA @{ name = "block-danger"; on_event = "pre_tool_call"; match = @{ tool_pattern = "glossary_delete_*" }; action = @{ kind = "deny"; message = "deletes are blocked" } } $null
Check ($r.StatusCode -eq 201) "create pre_tool_call deny hook → 201"
$hid = ($r.Content | ConvertFrom-Json).hook_id

$r = Req POST "/v1/agent-registry/hooks" $tokA @{ on_event = "on_boot"; action = @{ kind = "deny" } } $null
Check ($r.StatusCode -eq 400) "invalid on_event → 400"

$r = Req POST "/v1/agent-registry/hooks" $tokA @{ on_event = "pre_tool_call"; action = @{ kind = "exec"; cmd = "rm -rf /" } } $null
Check ($r.StatusCode -eq 400) "code-execution action rejected → 400 (declarative only)"

$r = Req POST "/v1/agent-registry/hooks" $tokA @{ name = "tone"; on_event = "pre_turn"; action = @{ kind = "inject_text"; text = "Keep a wry tone." } } $null
Check ($r.StatusCode -eq 201) "create pre_turn inject_text hook → 201"

$ih2 = (Req GET "/internal/hooks?user_id=$a" $null $null $ih).Content | ConvertFrom-Json
Check (($ih2.hooks | Where-Object { $_.on_event -eq "pre_tool_call" }).Count -ge 1) "/internal/hooks resolves the deny hook"
Check (($ih2.hooks | Where-Object { $_.on_event -eq "pre_turn" }).Count -ge 1) "/internal/hooks resolves the inject_text hook"
$ihB = (Req GET "/internal/hooks?user_id=$b" $null $null $ih).Content | ConvertFrom-Json
Check (($ihB.hooks).Count -eq 0) "tenancy: B has no hooks"

# cleanup
Req DELETE "/v1/agent-registry/commands/$cid" $tokA $null $null | Out-Null
Req DELETE "/v1/agent-registry/hooks/$hid" $tokA $null $null | Out-Null

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P4 BACKEND E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails P4 CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
