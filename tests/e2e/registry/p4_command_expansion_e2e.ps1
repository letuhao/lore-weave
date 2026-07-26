# E2E-P4-A — command expansion through a REAL chat turn (consumer path + effect).
# Registers a command whose template tells the model to echo a marker, sends
# "/echotest hello" through the real BFF chat endpoint (local lm_studio model, $0),
# and asserts BOTH the persisted user message == the EXPANDED template AND the
# assistant echoed the marker. Proves the router seam expands + reaches the model.
# Requires lm_studio UP (host.docker.internal:1234) + the stack rebuilt.
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
Write-Host "== E2E-P4-A command expansion through a real turn ==" -ForegroundColor Cyan

$cbody = @{ name = "echotest"; template_md = "Reply with exactly this and nothing else: MARKER-{{topic}}-END"; arg_schema = @{ properties = @{ topic = @{ type = "string" } } } } | ConvertTo-Json -Depth 8
$cr = Invoke-WebRequest -Method POST -Uri "$Reg/v1/agent-registry/commands" -SkipHttpErrorCheck -Headers $H -ContentType "application/json" -Body $cbody
Check ($cr.StatusCode -eq 201) "register /echotest command → 201"
$cid = ($cr.Content | ConvertFrom-Json).command_id

try {
  $sb = @{ title = "p4 e2e"; model_source = "user_model"; model_ref = $ModelRef } | ConvertTo-Json
  $sr = Invoke-WebRequest -Method POST -Uri "$Bff/v1/chat/sessions" -SkipHttpErrorCheck -Headers $H -ContentType "application/json" -Body $sb
  Check ($sr.StatusCode -eq 201) "create session → 201"
  $sid = ($sr.Content | ConvertFrom-Json).session_id

  $mb = @{ content = "/echotest hello" } | ConvertTo-Json
  $mr = Invoke-WebRequest -Method POST -Uri "$Bff/v1/chat/sessions/$sid/messages" -SkipHttpErrorCheck -Headers $H -ContentType "application/json" -Body $mb -TimeoutSec 120
  Check ($mr.StatusCode -eq 200) "send /echotest hello → turn 200"

  # EFFECT: the persisted user message is the EXPANDED template (not the raw command)
  $userMsg = (docker exec $PgContainer psql -U loreweave -d loreweave_chat -tAc "SELECT content FROM chat_messages WHERE session_id='$sid' AND role='user' ORDER BY sequence_num LIMIT 1" | ForEach-Object { "$_".Trim() } | Where-Object { $_ }) -join " "
  Check ($userMsg -match "MARKER-hello-END") "persisted user message is the EXPANDED template (/echotest → template with {{topic}}=hello)"
  Check (-not ($userMsg -match "^/echotest")) "raw '/echotest' did NOT reach the model (expanded in place)"

  # EFFECT: the model responded to the template (echoed the marker)
  $asst = (docker exec $PgContainer psql -U loreweave -d loreweave_chat -tAc "SELECT content FROM chat_messages WHERE session_id='$sid' AND role='assistant' ORDER BY sequence_num DESC LIMIT 1" | ForEach-Object { "$_".Trim() } | Where-Object { $_ }) -join " "
  Check ($asst -match "MARKER-hello-END") "assistant echoed the expanded marker (template reached the model)"
}
finally {
  Invoke-WebRequest -Method DELETE -Uri "$Reg/v1/agent-registry/commands/$cid" -SkipHttpErrorCheck -Headers $H | Out-Null
}

Write-Host ""
if ($fails -eq 0) { Write-Host "P4-A COMMAND EXPANSION E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
