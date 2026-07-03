# E2E-P4-B — hook engine through a REAL chat turn. Registers a pre_turn inject_text
# hook whose text tells the model to emit a marker, sends a normal message, and asserts
# the assistant reply carries the marker — proving the hook was resolved (/internal/hooks)
# + injected into the system prompt + reached the model. Local lm_studio model, $0.
param(
  [string]$Bff = "http://localhost:3123",
  [string]$Reg = "http://localhost:8230",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
  [string]$Uid = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c",
  [string]$ModelRef = "019eb620-bfb1-78ce-ad72-a360c604cfc1",
  [string]$PgContainer = "infra-postgres-1"
)
$ErrorActionPreference = "Stop"
$fails = 0
function Ok($m) { Write-Host "  PASS  $m" -ForegroundColor Green }
function Bad($m) { $script:fails++; Write-Host "  FAIL  $m" -ForegroundColor Red }
function Check($c, $m) { if ($c) { Ok $m } else { Bad $m } }
function B64Url([byte[]]$b) { [Convert]::ToBase64String($b).TrimEnd('=').Replace('+','-').Replace('/','_') }
$exp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + 3600
$h = B64Url([Text.Encoding]::UTF8.GetBytes('{"alg":"HS256","typ":"JWT"}'))
$p = B64Url([Text.Encoding]::UTF8.GetBytes("{""sub"":""$Uid"",""exp"":$exp}"))
$hmac = [Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($JwtSecret))
$tok = "$h.$p." + (B64Url($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes("$h.$p"))))
$H = @{ Authorization = "Bearer $tok" }
Write-Host "== E2E-P4-B hook inject_text through a real turn ==" -ForegroundColor Cyan

# Retrieval proof (compliance-independent): inject a secret the model can ONLY know
# from the hook, then ask for it. If it answers with the secret, the injection reached it.
$marker = "ZORP-777"
$hb = @{ name = "secret"; on_event = "pre_turn"; action = @{ kind = "inject_text"; text = "Context fact: the secret passphrase for this session is $marker." } } | ConvertTo-Json -Depth 8
$hr = Invoke-WebRequest -Method POST -Uri "$Reg/v1/agent-registry/hooks" -SkipHttpErrorCheck -Headers $H -ContentType "application/json" -Body $hb
Check ($hr.StatusCode -eq 201) "register pre_turn inject_text hook → 201"
$hid = ($hr.Content | ConvertFrom-Json).hook_id

try {
  $sb = @{ title = "p4 hook e2e"; model_source = "user_model"; model_ref = $ModelRef } | ConvertTo-Json
  $sid = ((Invoke-WebRequest -Method POST -Uri "$Bff/v1/chat/sessions" -SkipHttpErrorCheck -Headers $H -ContentType "application/json" -Body $sb).Content | ConvertFrom-Json).session_id
  $mb = @{ content = "What is the secret passphrase for this session? Reply with only the passphrase." } | ConvertTo-Json
  $mr = Invoke-WebRequest -Method POST -Uri "$Bff/v1/chat/sessions/$sid/messages" -SkipHttpErrorCheck -Headers $H -ContentType "application/json" -Body $mb -TimeoutSec 120
  Check ($mr.StatusCode -eq 200) "turn → 200"
  $asst = (docker exec $PgContainer psql -U loreweave -d loreweave_chat -tAc "SELECT content FROM chat_messages WHERE session_id='$sid' AND role='assistant' ORDER BY sequence_num DESC LIMIT 1" | ForEach-Object { "$_".Trim() } | Where-Object { $_ }) -join " "
  Check ($asst -match $marker) "assistant emitted the injected hook marker ($marker) — pre_turn inject_text reached the model"
}
finally {
  Invoke-WebRequest -Method DELETE -Uri "$Reg/v1/agent-registry/hooks/$hid" -SkipHttpErrorCheck -Headers $H | Out-Null
}

Write-Host ""
if ($fails -eq 0) { Write-Host "P4-B HOOK ENGINE E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
