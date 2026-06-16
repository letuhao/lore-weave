// Package adminjwt is the shared contract for LoreWeave admin JWTs (DEFERRED
// 074/075). It is imported by BOTH the signer (auth-service, go 1.25) and the
// verifier (admin-cli, go 1.22) so the claim shape, the RS256 verification
// rules, the public-key decode, and the break-glass policy are pinned in ONE
// place and cannot drift between the two modules.
//
// Trust model:
//   - auth-service holds the RSA private key in AWS KMS and signs admin tokens
//     via kms.Sign (the private key never leaves KMS). The token header carries
//     a kid = KeyFingerprint(public key) so a verifier can prove key identity.
//   - admin-cli holds ONLY the RSA public key (SPKI PEM via env) and calls
//     Verify. Public keys are not secret.
//
// Security posture: Verify is strict — RS256 only (no alg:none / HS downgrade),
// expiration required, issuer + audience pinned, and the kid must match the
// configured key so a stale/wrong public key fails loudly instead of silently
// rejecting every token.
package adminjwt
