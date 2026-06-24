package logging

import (
	"errors"
)

// Redactor is the seam between this logging library and the cycle 22 PII
// SDK (`contracts/pii`). The logging library NEVER imports the PII SDK
// directly — that would create a dep cycle (cycle 22 already uses
// `contracts/meta` which is also a downstream consumer of logging).
//
// Production services bind a `pii.Redactor` adapter (cycle 22 ships the
// adapter in the PII SDK). Tests use FakeRedactor (in redactor_test.go).
//
// # Contract
//
//   - Redactor.Redact MUST be allocation-bounded (no log-emit allocation
//     storms).
//   - Redactor.Redact MUST be deterministic in PROD build (same input →
//     same output) — log search relies on the hashed/masked form being
//     stable.
//   - Redactor.Redact returns the redacted bytes AND a boolean indicating
//     whether redaction was applied (used by the lw_log_redactions_total
//     counter — added to inventory.yaml this cycle).
//
// Cycle 22 reminder: NEVER use a bare regex for PII redaction. Cycle 22
// L4.Q PII SDK is the SSOT. This interface is the contract; the
// implementation lives in cycle 22 and any future PII sub-program.
type Redactor interface {
	// Redact masks the value if it is PII. Returns (masked, true) when
	// applied; (original, false) when not.
	//
	// The interface accepts any (not just string) because PII can be
	// embedded in numbers (user_ref_id as int), structs (Address{...}),
	// or maps (free-form user profile dump).
	Redact(value any) (masked any, redacted bool)
}

// ErrNilRedactor is returned by NewLogger when a nil Redactor is passed
// in PROD build (defense-in-depth — prod build with no redactor is a
// security incident).
var ErrNilRedactor = errors.New("logging: PROD build requires non-nil Redactor (cycle 22 PII SDK)")

// noopRedactor is the default for dev/test. Returns the value untouched
// and reports redacted=false. PROD build refuses to start with a nil
// Redactor — see Logger config validation (logger.go).
type noopRedactor struct{}

// NoopRedactor returns a Redactor that performs NO redaction. Use ONLY
// in dev/test — PROD build refuses it (see logger.go).
func NoopRedactor() Redactor { return noopRedactor{} }

// Redact returns the value untouched and reports redacted=false.
func (noopRedactor) Redact(value any) (any, bool) { return value, false }

// MaskedString is a sentinel type used in tests to mark a value as
// having been masked by a Redactor — production redactors typically
// return strings like "***@***.***" or hash digests, but tests find it
// useful to assert "this exact value was masked, that exact value was
// not" without a fragile substring match.
type MaskedString string
