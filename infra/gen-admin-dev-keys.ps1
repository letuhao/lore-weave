# Generates a DEV RSA keypair for admin-JWT signing (self-hosted / no-KMS path).
# Prints two base64-of-PEM values to paste into your shell before `docker compose up`:
#   ADMIN_JWT_LOCAL_PRIVATE_KEY_PEM → auth-service (signs admin JWTs)
#   ADMIN_JWT_PUBLIC_KEY_PEM        → glossary-service (verifies them)
# DEV ONLY — production should use KMS (KMS_ADMIN_SIGNING_KEY_ID). Do NOT commit keys.
$ErrorActionPreference = 'Stop'
$rsa = [System.Security.Cryptography.RSA]::Create(2048)
function ToPem([byte[]]$der, [string]$label) {
  $b64 = [Convert]::ToBase64String($der, 'InsertLineBreaks')
  "-----BEGIN $label-----`n$b64`n-----END $label-----`n"
}
$privPem = ToPem $rsa.ExportPkcs8PrivateKey() 'PRIVATE KEY'
$pubPem  = ToPem $rsa.ExportSubjectPublicKeyInfo() 'PUBLIC KEY'
$privB64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($privPem))
$pubB64  = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pubPem))
Write-Host "ADMIN_JWT_LOCAL_PRIVATE_KEY_PEM=$privB64"
Write-Host "ADMIN_JWT_PUBLIC_KEY_PEM=$pubB64"
