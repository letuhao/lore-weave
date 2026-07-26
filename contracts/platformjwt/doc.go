// Package platformjwt is the shared contract for LoreWeave *platform user*
// JWTs (SDK-2 / SEC-2, audit Area 8). It is the single, machine-checked home
// for the claim shape and the HS256 verification rules that ~8 Go services
// (agent-registry / book / glossary / notification / provider-registry /
// sharing / usage-billing) had copy-pasted inline as their own
// `accessClaims{}` + `jwt.ParseWithClaims(... SigningMethodHS256)` blocks.
//
// Trust model:
//   - auth-service mints the user access token as an HS256 JWT signed with a
//     SHARED SYMMETRIC SECRET (the platform JWT secret, injected via env). The
//     same secret is distributed to every domain service that must authenticate
//     a user Bearer token locally without a round-trip to auth-service.
//   - Because the secret is symmetric and secret, verification is the inverse
//     of signing: a caller who can forge a token already holds the secret. The
//     verifier's job is therefore to (a) pin the algorithm so an attacker can
//     never downgrade the token to an unsigned or asymmetric form, and (b)
//     enforce expiry so a leaked token does not live forever.
//
// Security posture — Verify is strict and fail-closed:
//   - HS256 ONLY. WithValidMethods rejects `alg:none` and any RS/EC/PS variant,
//     and the keyfunc re-asserts *jwt.SigningMethodHMAC (defense in depth
//     against an alg-confusion downgrade — e.g. a token minted with an RS256
//     header hoping the verifier feeds the HMAC secret to an RSA path).
//   - exp is REQUIRED and enforced (WithExpirationRequired). A token with no
//     expiry is rejected. Real platform tokens always carry exp; requiring it
//     closes the "forever token" hole the inline verifiers left open.
//   - `sub` MUST parse as a UUID. Every consumer used the subject as the user's
//     UUID (uuid.Parse(claims.Subject)); Verify performs that parse so a token
//     whose sub is not a UUID is rejected here rather than downstream.
//
// Unlike contracts/adminjwt (RS256, iss/aud/kid pinned) the platform user token
// pins NEITHER issuer NOR audience — the inline verifiers never checked them and
// auth-service does not set them on user tokens, so pinning here would reject
// every live token. Keeping parity is deliberate: this package is a drop-in
// replacement for the existing per-service logic, not a behavior change.
package platformjwt
