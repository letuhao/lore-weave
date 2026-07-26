# E2E-P3 (M4 slice) — REG-P3-03: OAuth 2.1 + PKCE(S256) + RFC 8707. Live-proves the
# /oauth/start DB flow (real authorization_url with S256 + resource) AND the full
# callback loop against a HOST fake AS reachable from the container at
# host.docker.internal (like lm_studio). Starts/stops the fake AS itself.
param(
  [string]$BaseUrl = "http://localhost:8230",
  [string]$JwtSecret = "loreweave_local_dev_jwt_secret_change_me_32chars",
  [string]$InternalToken = "dev_internal_token",
  [int]$AsPort = 8791
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
function Req($method, $path, $token, $body) {
  $headers = @{}
  if ($token) { $headers["Authorization"] = "Bearer $token" }
  $a = @{ Method = $method; Uri = "$BaseUrl$path"; Headers = $headers; SkipHttpErrorCheck = $true }
  if ($body) { $a["Body"] = ($body | ConvertTo-Json -Depth 8); $a["ContentType"] = "application/json" }
  return Invoke-WebRequest @a
}
# Capture a 302 without following it, via HttpClient (Invoke-WebRequest is awkward here).
function ReqRedirect($path) {
  $handler = [System.Net.Http.HttpClientHandler]::new()
  $handler.AllowAutoRedirect = $false
  $client = [System.Net.Http.HttpClient]::new($handler)
  try {
    $resp = $client.GetAsync("$BaseUrl$path").Result
    $loc = if ($resp.Headers.Location) { $resp.Headers.Location.ToString() } else { "" }
    return @{ Status = [int]$resp.StatusCode; Location = $loc }
  } finally { $client.Dispose() }
}
$ih = @{ "X-Internal-Token" = $InternalToken }
$u = [guid]::NewGuid().ToString()
$tok = New-Jwt $u
Write-Host "== E2E-P3 M4 (OAuth 2.1 + PKCE) @ $BaseUrl ==" -ForegroundColor Cyan

# start the host fake AS (reachable from the container at host.docker.internal:$AsPort)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$as = Start-Process -FilePath "python" -ArgumentList "`"$here\fake_oauth_as.py`" $AsPort" -PassThru -WindowStyle Hidden
Start-Sleep 2
try {
  $tokenEp = "http://host.docker.internal:$AsPort/token"
  $authEp = "http://host.docker.internal:$AsPort/authorize"

  # register an oauth2 server (endpoint public-resolvable; oauth endpoints = fake AS)
  $r = Req POST "/v1/agent-registry/mcp-servers" $tok @{
    display_name = "oauth server"; endpoint_url = "https://example.com/mcp"; auth_kind = "oauth2";
    oauth = @{ authorization_endpoint = $authEp; token_endpoint = $tokenEp; client_id = "cid-1"; scopes = @("mcp.tools") }
  }
  Check ($r.StatusCode -eq 201) "register oauth2 server → 201"
  $m = $r.Content | ConvertFrom-Json
  $mid = $m.mcp_server_id
  Check ($m.auth_kind -eq "oauth2") "auth_kind=oauth2 persisted"
  Check ($m.has_secret -eq $false) "no token yet (has_secret=false pre-flow)"

  # /oauth/start → authorization_url with PKCE S256 + RFC 8707 resource
  $st = Req POST "/v1/agent-registry/mcp-servers/$mid/oauth/start" $tok $null
  Check ($st.StatusCode -eq 200) "/oauth/start → 200"
  $so = $st.Content | ConvertFrom-Json
  $au = [uri]$so.authorization_url
  $q = [System.Web.HttpUtility]::ParseQueryString($au.Query)
  Check ($q["code_challenge_method"] -eq "S256") "authorization_url has code_challenge_method=S256"
  Check ($q["code_challenge"].Length -gt 20) "authorization_url has a code_challenge"
  Check ($q["resource"] -eq "https://example.com/mcp") "authorization_url has RFC 8707 resource=<server>"
  Check ($q["client_id"] -eq "cid-1") "authorization_url has client_id"
  Check ($so.state.Length -gt 10) "flow state minted"

  # /oauth/callback (as the AS would redirect the browser) → exchange at the fake AS → seal
  $cb = ReqRedirect "/v1/agent-registry/oauth/callback?code=the-code&state=$($so.state)"
  Check ($cb.Status -eq 302) "/oauth/callback → 302 redirect"
  Check ($cb.Location -match "mcp_oauth=connected") "callback redirects to mcp_oauth=connected"

  # token sealed: has_secret now true; internal credentials returns the access token
  $d = (Req GET "/v1/agent-registry/mcp-servers/$mid" $tok $null).Content | ConvertFrom-Json
  Check ($d.has_secret -eq $true) "after callback: has_secret=true (token sealed in vault)"
  $cr = Invoke-WebRequest -Method GET -Uri "$BaseUrl/internal/mcp-servers/$mid/credentials?user_id=$u" -SkipHttpErrorCheck -Headers $ih
  Check ((($cr.Content | ConvertFrom-Json).secret) -eq "AT-authcode") "sealed access token decrypts via internal creds route"

  # state is single-use: replaying the callback fails
  $cb2 = ReqRedirect "/v1/agent-registry/oauth/callback?code=the-code&state=$($so.state)"
  Check ($cb2.Location -match "mcp_oauth=error") "replayed state → error (single-use)"

  Req DELETE "/v1/agent-registry/mcp-servers/$mid" $tok $null | Out-Null
}
finally {
  if ($as -and -not $as.HasExited) { Stop-Process -Id $as.Id -Force -ErrorAction SilentlyContinue }
}

Write-Host ""
if ($fails -eq 0) { Write-Host "ALL P3-M4 E2E PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "$fails P3-M4 CHECK(S) FAILED" -ForegroundColor Red; exit 1 }
