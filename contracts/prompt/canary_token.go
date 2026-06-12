package prompt

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
)

// CanaryToken is a cryptographically-random sentinel embedded in
// SectionSystem at assembly time (cycle 31 L6.I.2). The post-output
// scanner (CanaryDetector) flags it iff the model regurgitates the
// system prompt — strong injection signal.
//
// **Q-L6L-1 (LOCKED):** foundation V1 ships the token + detector, no
// fail-closed action (the LLM-safety sub-program decides whether to
// page SRE, swap the response, etc.).
//
// **Entropy:** 128 bits via crypto/rand (16 bytes → 32 hex chars).
// Threat model assumes attacker has black-box query oracle access;
// 2^128 search space is intractable.
//
// **Body-never-stored interaction:** the canary token is NEVER
// persisted to prompt_audit (cycle 4) or any other audit row — a
// stored canary becomes a replay-attack handle. Only the ContextHash
// (which already mixes the token bytes via the rendered prompt) is
// persisted; forensics reconstruct the token via deterministic
// per-(audit_id, context_hash) re-derivation when re-running with the
// real LLM-safety sub-program impl.
type CanaryToken struct {
	// Hex is the 32-char hex-encoded random token.
	Hex string
}

// canaryTokenByteLen is the random-byte length (16 bytes = 128 bits
// of entropy). Keep this >= 8 (64-bit lower bound per cycle 31 design
// review — guards against birthday collisions on token reuse for
// per-prompt detection).
const canaryTokenByteLen = 16

// NewCanaryToken returns a fresh cryptographically-random canary.
// Errors only on crypto/rand failure — practically a CSPRNG outage,
// in which case prompt assembly MUST FAIL (cannot ship a prompt
// without an injection canary). Q-L6H-1.
func NewCanaryToken() (CanaryToken, error) {
	buf := make([]byte, canaryTokenByteLen)
	if _, err := rand.Read(buf); err != nil {
		return CanaryToken{}, fmt.Errorf("canary_token: crypto/rand: %w", err)
	}
	return CanaryToken{Hex: hex.EncodeToString(buf)}, nil
}

// Marker returns the wire-form sentinel embedded in SectionSystem.
// Format: `[CANARY:<32-hex>]`. The detector matches on this prefix
// + the hex token exactly.
func (c CanaryToken) Marker() []byte {
	if c.Hex == "" {
		return nil
	}
	out := make([]byte, 0, len(canaryMarkerPrefix)+len(c.Hex)+1)
	out = append(out, canaryMarkerPrefix...)
	out = append(out, []byte(c.Hex)...)
	out = append(out, ']')
	return out
}

// canaryMarkerPrefix is the sentinel prefix the detector scans for.
var canaryMarkerPrefix = []byte("[CANARY:")

// EmbedInSystem injects the canary marker at the END of the SYSTEM
// section. The exact placement (end-of-section, not interleaved with
// instructions) is deliberate — it minimizes the chance of breaking
// model tuning while remaining a clear "this came from the prompt"
// signal if regurgitated.
func EmbedInSystem(systemBytes []byte, canary CanaryToken) []byte {
	marker := canary.Marker()
	if len(marker) == 0 {
		return systemBytes
	}
	out := make([]byte, 0, len(systemBytes)+1+len(marker))
	out = append(out, systemBytes...)
	if len(systemBytes) > 0 && systemBytes[len(systemBytes)-1] != '\n' {
		out = append(out, '\n')
	}
	out = append(out, marker...)
	return out
}

// ErrCanaryInvalid is returned by ParseCanaryHex on malformed input.
var ErrCanaryInvalid = errors.New("canary_token: invalid hex")

// ParseCanaryHex re-hydrates a CanaryToken from its hex form. The
// LLM-safety sub-program uses this when correlating audit rows with
// detection events.
func ParseCanaryHex(s string) (CanaryToken, error) {
	if len(s) != 2*canaryTokenByteLen {
		return CanaryToken{}, fmt.Errorf("%w: expected %d hex chars, got %d", ErrCanaryInvalid, 2*canaryTokenByteLen, len(s))
	}
	if _, err := hex.DecodeString(s); err != nil {
		return CanaryToken{}, fmt.Errorf("%w: %v", ErrCanaryInvalid, err)
	}
	return CanaryToken{Hex: s}, nil
}

// CanaryDetector scans post-LLM-output bytes for canary leak.
// Cycle 31 L6.I.3 — V1 returns a boolean + the matching token; the
// LLM-safety sub-program wires this to PagerDuty / metric emission.
type CanaryDetector interface {
	// Detect returns (true, token) iff output contains a canary marker
	// whose hex tail matches a known CanaryToken. Foundation V1 needs
	// the caller to hold the known tokens (typically the per-turn
	// canary issued at AssemblePrompt). LLM-safety sub-program may
	// extend with a sliding-window cache of recent tokens.
	Detect(output []byte, known []CanaryToken) (bool, CanaryToken)
}

// DefaultCanaryDetector is the foundation V1 implementation — a
// bytes.Contains scan for each known token's marker.
type DefaultCanaryDetector struct{}

// Detect — see CanaryDetector.
func (DefaultCanaryDetector) Detect(output []byte, known []CanaryToken) (bool, CanaryToken) {
	if len(output) == 0 || len(known) == 0 {
		return false, CanaryToken{}
	}
	for _, t := range known {
		if marker := t.Marker(); len(marker) > 0 && bytes.Contains(output, marker) {
			return true, t
		}
	}
	return false, CanaryToken{}
}
