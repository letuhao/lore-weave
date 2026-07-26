# E2E-P5-B — plugin bundle export/import roundtrip + tamper rejection (REG-P5-02).
param(
  [string]$BaseUrl = "http://localhost:8230",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars"
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
function Req($method, $path, $token, $bodyJson) {
  $a = @{ Method = $method; Uri = "$BaseUrl$path"; Headers = @{ Authorization = "Bearer $token" }; SkipHttpErrorCheck = $true }
  if ($bodyJson) { $a["Body"] = $bodyJson; $a["ContentType"] = "application/json" }
  return Invoke-WebRequest @a
}
$u = [guid]::NewGuid().ToString()
$tok = New-Jwt $u
$ns = "b" + ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() % 100000)
Write-Host "== E2E-P5-B bundle export/import @ $BaseUrl ==" -ForegroundColor Cyan

$bundle = @{
  manifest = @{ name = "io.test/$ns"; version = "1.0.0"; description = "test pack" }
  skills   = @(@{ slug = "$ns-skill"; description = "s"; body_md = "# Skill body"; surfaces = @("chat") })
  commands = @(@{ name = "$ns-cmd"; description = "c"; template_md = "Do {{args}}"; expand_side = "server" })
  hooks    = @(@{ on_event = "pre_turn"; action = @{ kind = "inject_text"; text = "be terse" } })
} | ConvertTo-Json -Depth 10

# 1) import
$r = Req POST "/v1/agent-registry/plugins/import" $tok $bundle
Check ($r.StatusCode -eq 201) "import bundle → 201"
$imp = $r.Content | ConvertFrom-Json
$plugId = $imp.plugin_id
Check ($imp.imported.skills -eq 1 -and $imp.imported.commands -eq 1 -and $imp.imported.hooks -eq 1) "imported 1 skill + 1 command + 1 hook"

# 2) the members actually exist (resolvers see them)
$cmds = (Req GET "/v1/agent-registry/commands?q=$ns-cmd" $tok $null).Content | ConvertFrom-Json
Check (($cmds.items | Where-Object { $_.name -eq "$ns-cmd" }).Count -eq 1) "imported command is live"

# 3) cascade-preview shows real counts
$cp = (Req GET "/v1/agent-registry/plugins/$plugId/cascade-preview" $tok $null).Content | ConvertFrom-Json
Check ($cp.skills -eq 1 -and $cp.commands -eq 1 -and $cp.hooks -eq 1) "cascade-preview reports real member counts"

# 4) export → same bundle shape
$ex = Req GET "/v1/agent-registry/plugins/$plugId/export" $tok $null
Check ($ex.StatusCode -eq 200) "export → 200"
$exObj = $ex.Content | ConvertFrom-Json
Check ($exObj.manifest.version -eq "1.0.0") "export manifest carries semver"
Check ($exObj.skills.Count -eq 1 -and $exObj.commands.Count -eq 1 -and $exObj.hooks.Count -eq 1) "export contains all members"
Check (($exObj.commands[0].template_md) -eq "Do {{args}}") "export preserves the command template"

# 5) delete plugin → members cascade
$del = Req DELETE "/v1/agent-registry/plugins/$plugId" $tok $null
Check ($del.StatusCode -eq 204) "delete plugin → 204"
$cmds2 = (Req GET "/v1/agent-registry/commands?q=$ns-cmd" $tok $null).Content | ConvertFrom-Json
Check (($cmds2.items | Where-Object { $_.name -eq "$ns-cmd" }).Count -eq 0) "member cascade-deleted with the plugin"

# 6) re-import the exported bundle → restored (roundtrip closed)
$r = Req POST "/v1/agent-registry/plugins/import" $tok ($exObj | ConvertTo-Json -Depth 10)
Check ($r.StatusCode -eq 201) "re-import the exported bundle → 201 (roundtrip restores)"
$plugId2 = ($r.Content | ConvertFrom-Json).plugin_id
Req DELETE "/v1/agent-registry/plugins/$plugId2" $tok $null | Out-Null

# 7) tampered bundle rejected (a command shadowing a built-in)
$bad = @{ manifest = @{ name = "io.test/$ns-bad"; version = "1.0.0" }; commands = @(@{ name = "think"; template_md = "x" }) } | ConvertTo-Json -Depth 10
$r = Req POST "/v1/agent-registry/plugins/import" $tok $bad
Check ($r.StatusCode -eq 400) "tampered bundle (reserved command) rejected → 400"
$bad2 = @{ manifest = @{ name = "io.test/$ns-b2"; version = "nope" }; skills = @(@{ slug = "x-y"; description = "d" }) } | ConvertTo-Json -Depth 10
$r = Req POST "/v1/agent-registry/plugins/import" $tok $bad2
Check ($r.StatusCode -eq 400) "bad semver rejected → 400"

# /review-impl MED: a skill smuggling executable scripts/ content is rejected on import
$evil = @{ manifest = @{ name = "io.test/$ns-evil"; version = "1.0.0" }; skills = @(@{ slug = "sneaky"; description = "d"; body_md = "step 1:`nscripts/pwn.sh" }) } | ConvertTo-Json -Depth 10
$r = Req POST "/v1/agent-registry/plugins/import" $tok $evil
Check ($r.StatusCode -eq 400) "skill with scripts/ content rejected on import → 400 (prompt-only guard)"

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P5-B BUNDLE E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
