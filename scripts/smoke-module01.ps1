# Requires: auth + gateway running, jq optional
$base = if ($env:GATEWAY_URL) { $env:GATEWAY_URL } else { "http://localhost:3000" }
$email = "smoke+$([guid]::NewGuid().ToString('n').Substring(0,8))@example.com"
$pass = "SmokePass1"

Write-Host "POST register $email"
$reg = Invoke-RestMethod -Method Post -Uri "$base/v1/auth/register" -ContentType "application/json" -Body (@{
  email = $email
  password = $pass
} | ConvertTo-Json)

Write-Host "user_id:" $reg.user_id

Write-Host "POST login"
$login = Invoke-RestMethod -Method Post -Uri "$base/v1/auth/login" -ContentType "application/json" -Body (@{
  email = $email
  password = $pass
} | ConvertTo-Json)

$hdr = @{ Authorization = "Bearer $($login.access_token)" }
Write-Host "GET profile"
Invoke-RestMethod -Method Get -Uri "$base/v1/account/profile" -Headers $hdr | ConvertTo-Json -Depth 5

Write-Host "POST logout"
Invoke-WebRequest -Method Post -Uri "$base/v1/auth/logout" -Headers $hdr | Out-Null
Write-Host "smoke ok"
