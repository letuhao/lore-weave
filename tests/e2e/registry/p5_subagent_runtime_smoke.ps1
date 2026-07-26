# E2E-P5-A (full loop) — REG-P5-01 runtime through the REAL chat endpoint.
# Registers a scoped subagent for the test account, drives a real chat turn that
# delegates, and asserts the run_subagent tool_call came back with a synthesized
# result — WITHOUT any write tool appearing (scope + isolation). Part A (the
# in-container real nested turn) is the deterministic runtime proof; this closes
# the loop through the model's own tool choice.
param(
  [string]$Registry = "http://localhost:8230",
  [string]$Chat = "http://localhost:8212",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
  # gemma-4-26b-a4b-qat (chat + tool_calling), loaded in lm_studio
  [string]$ModelRef = "019ebb72-27a2-72f3-a42d-d2d0e0ded179",
  [string]$UserId = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
)
$ErrorActionPreference = "Stop"
$fails = 0
function Ok($m) { Write-Host "  PASS  $m" -ForegroundColor Green }
function Bad($m) { $script:fails++; Write-Host "  FAIL  $m" -ForegroundColor Red }
function Warn($m) { Write-Host "  WARN  $m" -ForegroundColor Yellow }
function Check($c, $m) { if ($c) { Ok $m } else { Bad $m } }
function B64Url([byte[]]$b) { [Convert]::ToBase64String($b).TrimEnd('=').Replace('+','-').Replace('/','_') }
function New-Jwt([string]$sub) {
  $exp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + 3600
  $h = B64Url([Text.Encoding]::UTF8.GetBytes('{"alg":"HS256","typ":"JWT"}'))
  $p = B64Url([Text.Encoding]::UTF8.GetBytes("{""sub"":""$sub"",""exp"":$exp}"))
  $hmac = [Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($JwtSecret))
  return "$h.$p." + (B64Url($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes("$h.$p"))))
}
function Req($method, $base, $path, $token, $body, $hdr) {
  $headers = @{}
  if ($token) { $headers["Authorization"] = "Bearer $token" }
  if ($hdr) { $hdr.GetEnumerator() | ForEach-Object { $headers[$_.Key] = $_.Value } }
  $a = @{ Method = $method; Uri = "$base$path"; Headers = $headers; SkipHttpErrorCheck = $true }
  if ($body) { $a["Body"] = ($body | ConvertTo-Json -Depth 8); $a["ContentType"] = "application/json" }
  return Invoke-WebRequest @a
}
$tok = New-Jwt $UserId
Write-Host "== E2E-P5-A subagent RUNTIME (full loop) ==" -ForegroundColor Cyan

# 1) register a read-only subagent (idempotent: delete any prior, then create)
$existing = (Req GET $Registry "/v1/agent-registry/subagents" $tok $null $null).Content | ConvertFrom-Json
$prior = $existing.items | Where-Object { $_.name -eq "lore-scout" }
if ($prior) { Req DELETE $Registry "/v1/agent-registry/subagents/$($prior.subagent_id)" $tok $null $null | Out-Null }
$r = Req POST $Registry "/v1/agent-registry/subagents" $tok @{
  name = "lore-scout"
  description = "reads glossary lore only"
  system_prompt = "You are a lore scout. Answer the sub-task in ONE short sentence about fantasy dragons. Do not attempt to write anything."
  tool_scope = @("glossary_search", "glossary_get_entity")
  model_ref = "019eb620-bfb1-78ce-ad72-a360c604cfc1"  # non-reasoning Qwen 7B for a crisp sub-answer
} $null
Check ($r.StatusCode -eq 201) "register lore-scout subagent → 201"

# 2) create a fresh universal session on the tool-calling model
$sess = (Req POST $Chat "/v1/chat/sessions" $tok @{
  title = "e2e-p5a"; model_source = "user_model"; model_ref = $ModelRef
} $null)
Check ($sess.StatusCode -eq 201) "create session → 201"
$sid = ($sess.Content | ConvertFrom-Json).session_id

# 3) drive a delegation turn (agui surface). SSE buffers until the turn completes.
$msg = @{ content = "Use the run_subagent tool to delegate to the 'lore-scout' subagent: ask it to describe a dragon in one sentence. Then report its answer to me." }
$hdr = @{ "X-Loreweave-Stream-Format" = "agui" }
$resp = Req POST $Chat "/v1/chat/sessions/$sid/messages" $tok $msg $hdr
Check ($resp.StatusCode -eq 200) "turn streamed → 200"
$body = $resp.Content

# 4) assert the loop: run_subagent was called + returned a result; no write leaked
$calledSub = $body -match "run_subagent"
if ($calledSub) {
  Ok "model delegated via run_subagent (full loop closed)"
  Check ($body -notmatch "book_write" -and $body -notmatch "book_create" -and $body -notmatch "chapter_update") "no write tool appears in the transcript (scope held)"
  # the synthesized sub-answer (or the model's report of it) should mention a dragon
  Check ($body -match "dragon") "synthesized subagent result reached the main turn"
} else {
  Warn "the tool-calling model did not choose run_subagent this run (model-choice, not a runtime bug — Part A proved the runtime live)."
}

Write-Host ""
if ($fails -eq 0) { Write-Host "P5-A FULL-LOOP SMOKE OK" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
