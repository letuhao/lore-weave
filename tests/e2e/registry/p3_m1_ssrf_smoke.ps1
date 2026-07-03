# E2E-P3 (M1 slice) — REG-P3-01/02: SSRF guard + capability rejection + external
# quarantine + bearer secret vault (has_secret only). Real stack (live agent-registry
# on :8230, dev flag AGENT_REGISTRY_ALLOW_INTERNAL_MCP=1 so in-cluster targets pass).
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
$a = [guid]::NewGuid().ToString()
$tokA = New-Jwt $a
Write-Host "== E2E-P3 M1 (SSRF + capability + vault) @ $BaseUrl ==" -ForegroundColor Cyan

# NOTE: the live dev stack runs with AGENT_REGISTRY_ALLOW_INTERNAL_MCP=1, which
# RE-PERMITS internal/loopback/metadata targets (so in-cluster MCP servers stay
# smokeable). The SSRF *rejection* behaviour (prod posture, flag OFF) is proven by
# the unit fixture suite TestClassifyRegistrationURL_SSRF (10+ payloads incl. the
# DNS-rebind shape). Here we live-prove the flag-INDEPENDENT rejects + the vault.

# --- model-capability rejection (flag-independent, provider-gateway invariant) ---
$r = Req POST "/v1/agent-registry/mcp-servers" $tokA @{ display_name = "ollama box"; endpoint_url = "http://ollama-host.example.com:11434/mcp" } $null
Check ($r.StatusCode -eq 400 -and ($r.Content | ConvertFrom-Json).code -eq "MODEL_CAPABILITY_NOT_ALLOWED") "ollama-style URL → 400 MODEL_CAPABILITY_NOT_ALLOWED"

$r = Req POST "/v1/agent-registry/mcp-servers" $tokA @{ display_name = "embed svc"; endpoint_url = "https://api.openai.com/v1/embeddings" } $null
Check ($r.StatusCode -eq 400 -and ($r.Content | ConvertFrom-Json).code -eq "MODEL_CAPABILITY_NOT_ALLOWED") "openai embeddings URL → 400 MODEL_CAPABILITY_NOT_ALLOWED"

# --- wrong scheme / unparseable → 400 SSRF_BLOCKED ---
$r = Req POST "/v1/agent-registry/mcp-servers" $tokA @{ display_name = "ftp"; endpoint_url = "ftp://host/mcp" } $null
Check ($r.StatusCode -eq 400) "non-http scheme rejected → 400"

# --- bearer secret vault: register with a bearer token, verify has_secret + no leak ---
$r = Req POST "/v1/agent-registry/mcp-servers" $tokA @{ display_name = "secured tools"; endpoint_url = "http://host.docker.internal:9200/mcp"; auth_kind = "bearer"; bearer_token = "super-secret-xyz" } $null
Check ($r.StatusCode -eq 201) "register bearer-auth internal server → 201"
$m = $r.Content | ConvertFrom-Json
$mid = $m.mcp_server_id
Check ($m.has_secret -eq $true) "public serializer exposes has_secret=true"
Check ($m.auth_kind -eq "bearer") "auth_kind=bearer persisted"
Check (-not ($r.Content -match "super-secret-xyz")) "plaintext secret NEVER echoed on the public create response"
Check (-not ($r.Content -match "secret_ciphertext")) "ciphertext field NEVER in the public serializer"

# bearer without token → 400
$r = Req POST "/v1/agent-registry/mcp-servers" $tokA @{ display_name = "bad"; endpoint_url = "http://host.docker.internal:9201/mcp"; auth_kind = "bearer" } $null
Check ($r.StatusCode -eq 400) "bearer auth without token → 400"

# --- internal credentials route decrypts (internal-token only) ---
$cr = Req GET "/internal/mcp-servers/$mid/credentials?user_id=$a" $null $null $ih
Check ($cr.StatusCode -eq 200 -and ($cr.Content | ConvertFrom-Json).secret -eq "super-secret-xyz") "internal credentials route decrypts the sealed secret (round-trip)"

# --- list shows the row with has_secret, never the ciphertext ---
$lst = Req GET "/v1/agent-registry/mcp-servers" $tokA $null $null
Check (-not ($lst.Content -match "super-secret-xyz")) "list never leaks plaintext"

# cleanup
Req DELETE "/v1/agent-registry/mcp-servers/$mid" $tokA $null $null | Out-Null

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P3-M1 E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails P3-M1 CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
