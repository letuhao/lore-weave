// Package pii is the canonical SDK developers use to access PII at
// runtime (cycle 22 / L4.Q). It INTEGRATES with the cycle-3 crypto-shred
// mechanism rather than re-implementing it:
//
//   - GetPII(ctx, user_ref_id)   → uses cycle-3 contracts/meta.OpenPII
//   - SetPII(ctx, user_ref_id, blob, rotation?)
//                                → wraps the cycle-3 KMSClient envelope
//                                  write path; rotation handled via the
//                                  KEKManager hook.
//   - ErasePII(ctx, user_ref_id) → triggers KEK destroy via the cycle-3
//                                  pii_kek.destroyed_at column (the
//                                  crypto-shred mechanism). NEVER hard-
//                                  deletes any row — that would break
//                                  the regulator audit trail.
//
// Q-L4-1 — Rust mirror lives in `crates/dp-kernel::pii_sdk`. Both
// languages MUST agree byte-for-byte on the audit-row shape + the
// "plaintext never cached" invariant.
//
// CRITICAL invariants (load-bearing — code review enforced):
//
//  1. GetPII NEVER caches plaintext in this package. The PIIRecord
//     value returned by cycle-3 OpenPII contains plaintext; this
//     package's caller MUST treat it as one-shot and zeroize after use.
//     We do not stash ciphertext in this package either (the cycle-3
//     library owns DB reads).
//
//  2. ErasePII actually destroys the KEK. The KEKManager.DestroyKEK call
//     is the ONE side-effect that satisfies GDPR Art. 17 — failure to
//     destroy the KEK = compliance failure. Tests assert the KEK row
//     transitions to destroyed_at IS NOT NULL.
//
//  3. Sensitive-read tag MUST be one of the cycle-3 enumerated set
//     (`meta-sensitive-read-paths.yml`). The cycle-22 PII SDK adds
//     `pii_user_get` and `pii_user_erase` to the set; defense-in-depth
//     verifies the tag at SDK call time so a typo doesn't slip through
//     to a missed audit row.
//
// This package does NOT directly talk to AWS KMS or HashiCorp Vault —
// production deployments wire one of those via the cycle-3 KMSClient
// interface. The SDK is vendor-agnostic by construction.
package pii
