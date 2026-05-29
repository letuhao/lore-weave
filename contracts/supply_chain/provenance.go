package supply_chain

import (
	"context"
	"fmt"
)

// VerifyResult is the outcome of a provenance check.
type VerifyResult struct {
	Verified      bool
	Signer        string // cosign | sigstore | gpg
	SignerIdentity string // e.g., cosign email, gpg key fingerprint
	Notes         string // human-readable detail
}

// Verifier is the runtime provenance interface. Implementations live
// outside this package (cycle 21+ cosign / sigstore wiring).
//
// Cycle 19 ships:
//   - the interface
//   - a NoopVerifier that always returns ErrSignatureUnverified
//     (so calling code can compile + tests can exercise the failure path)
//   - a PolicyAwareVerifier that returns Verified=true when
//     policy.Provenance.Enabled = false (V1 default) — making the
//     stub harmless in dev/test environments per policy.AllowFailureModes.
type Verifier interface {
	Verify(ctx context.Context, artifactRef string, signatureRef string) (VerifyResult, error)
}

// NoopVerifier always returns ErrSignatureUnverified. Use only for
// tests that need to exercise the failure path.
type NoopVerifier struct{}

// Verify returns ErrSignatureUnverified unconditionally.
func (NoopVerifier) Verify(_ context.Context, artifactRef, _ string) (VerifyResult, error) {
	return VerifyResult{Verified: false, Notes: fmt.Sprintf("NoopVerifier: %s unverified", artifactRef)}, ErrSignatureUnverified
}

// PolicyAwareVerifier wraps a real implementation but short-circuits
// to Verified=true when policy.Provenance.Enabled = false. This is
// the production-safe default for the V1 adoption window per SR10
// §12AM — provenance enforcement flips on at V1+30d.
type PolicyAwareVerifier struct {
	Policy   Policy
	Delegate Verifier // wraps a real cosign/sigstore impl
}

// Verify consults the policy: if provenance.enabled=false, returns
// Verified=true immediately (no delegate call). Otherwise delegates.
//
// If the delegate is nil AND provenance is enabled, returns
// ErrSignatureUnverified (fail-closed when wiring is incomplete).
func (v PolicyAwareVerifier) Verify(ctx context.Context, artifactRef, signatureRef string) (VerifyResult, error) {
	if !v.Policy.Provenance.Enabled {
		return VerifyResult{
			Verified: true,
			Signer:   v.Policy.Provenance.Signer,
			Notes:    "provenance disabled by policy (V1 adoption window)",
		}, nil
	}
	if v.Delegate == nil {
		return VerifyResult{Verified: false, Notes: "policy requires verification but no delegate wired"}, ErrSignatureUnverified
	}
	return v.Delegate.Verify(ctx, artifactRef, signatureRef)
}
