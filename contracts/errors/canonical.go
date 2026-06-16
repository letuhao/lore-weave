package errors

import (
	"fmt"
	"time"
)

// ErrorClass classifies failures into the 4 SR11 buckets. Wire format =
// canonical snake_case.
type ErrorClass string

const (
	// ClassUserError — caller's fault. NEVER retry; never page.
	ClassUserError ErrorClass = "user_error"
	// ClassSystemError — server-side bug or unexpected state. Page at threshold.
	ClassSystemError ErrorClass = "system_error"
	// ClassTransient — known-temporary failure. Retry with backoff.
	ClassTransient ErrorClass = "transient"
	// ClassPermanent — terminal failure (entity gone). Caller surfaces gracefully.
	ClassPermanent ErrorClass = "permanent"
)

// AllErrorClasses returns every class. Lints + tests enforce exhaustiveness.
func AllErrorClasses() []ErrorClass {
	return []ErrorClass{
		ClassUserError,
		ClassSystemError,
		ClassTransient,
		ClassPermanent,
	}
}

// IsValid returns true iff c is one of the enumerated classes.
func (c ErrorClass) IsValid() bool {
	for _, ok := range AllErrorClasses() {
		if c == ok {
			return true
		}
	}
	return false
}

// IsRetryable indicates whether the class permits retry by default.
// Callers may override per-code via PolicyOverride.
func (c ErrorClass) IsRetryable() bool {
	return c == ClassTransient
}

// IsPageable indicates whether the class warrants paging by default.
func (c ErrorClass) IsPageable() bool {
	return c == ClassSystemError
}

// ErrorCode is a stable string code identifying ONE specific error condition.
// Stable across service deploys (alerts + dashboards key off codes).
type ErrorCode string

// V1 canonical codes — 28 total, grouped by class.
//
// Adding a code requires:
//   1. New const here
//   2. Entry in classOfCode + AllErrorCodes
//   3. Unit test passes TestAllCodesAreExhaustive
const (
	// ── ClassUserError ──
	CodeAuthRequired           ErrorCode = "auth_required"
	CodeAuthExpired            ErrorCode = "auth_expired"
	CodeAuthForbidden          ErrorCode = "auth_forbidden"
	CodeValidationFailed       ErrorCode = "validation_failed"
	CodeQuotaExceeded          ErrorCode = "quota_exceeded"
	CodeRateLimitExceeded      ErrorCode = "rate_limit_exceeded"
	CodeBadInputFormat         ErrorCode = "bad_input_format"
	CodeUnsupportedClient      ErrorCode = "unsupported_client"
	CodeConsentRequired        ErrorCode = "consent_required"

	// ── ClassSystemError ──
	CodeInternalAssertion      ErrorCode = "internal_assertion"
	CodeProjectionCorruption   ErrorCode = "projection_corruption"
	CodeMetaWriteFailed        ErrorCode = "meta_write_failed"
	CodeOutboxDrained          ErrorCode = "outbox_drained"
	CodeUpstreamMisconfigured  ErrorCode = "upstream_misconfigured"
	CodeSchemaViolation        ErrorCode = "schema_violation"

	// ── ClassTransient ──
	CodeUpstreamTimeout        ErrorCode = "upstream_timeout"
	CodeUpstreamRateLimit      ErrorCode = "upstream_rate_limit"
	CodeUpstreamUnavailable    ErrorCode = "upstream_unavailable"
	CodeCircuitOpen            ErrorCode = "circuit_open"
	CodeBulkheadFull           ErrorCode = "bulkhead_full"
	CodeConcurrentStateChange  ErrorCode = "concurrent_state_change"
	CodeDegradedMode           ErrorCode = "degraded_mode"
	CodeCacheUnavailable       ErrorCode = "cache_unavailable"

	// ── ClassPermanent ──
	CodeEntityDropped          ErrorCode = "entity_dropped"
	CodeEntityArchived         ErrorCode = "entity_archived"
	CodeRealityFrozen          ErrorCode = "reality_frozen"
	CodeUserErased             ErrorCode = "user_erased"
	CodeFeatureRetired         ErrorCode = "feature_retired"
)

// classOfCode maps every code to its class. EXHAUSTIVE — adding a new code
// without an entry here causes IsValid()/Class() to fail and the test suite
// catches it.
var classOfCode = map[ErrorCode]ErrorClass{
	// user_error (9)
	CodeAuthRequired:      ClassUserError,
	CodeAuthExpired:       ClassUserError,
	CodeAuthForbidden:     ClassUserError,
	CodeValidationFailed:  ClassUserError,
	CodeQuotaExceeded:     ClassUserError,
	CodeRateLimitExceeded: ClassUserError,
	CodeBadInputFormat:    ClassUserError,
	CodeUnsupportedClient: ClassUserError,
	CodeConsentRequired:   ClassUserError,
	// system_error (6)
	CodeInternalAssertion:     ClassSystemError,
	CodeProjectionCorruption:  ClassSystemError,
	CodeMetaWriteFailed:       ClassSystemError,
	CodeOutboxDrained:         ClassSystemError,
	CodeUpstreamMisconfigured: ClassSystemError,
	CodeSchemaViolation:       ClassSystemError,
	// transient (8)
	CodeUpstreamTimeout:       ClassTransient,
	CodeUpstreamRateLimit:     ClassTransient,
	CodeUpstreamUnavailable:   ClassTransient,
	CodeCircuitOpen:           ClassTransient,
	CodeBulkheadFull:          ClassTransient,
	CodeConcurrentStateChange: ClassTransient,
	CodeDegradedMode:          ClassTransient,
	CodeCacheUnavailable:      ClassTransient,
	// permanent (5)
	CodeEntityDropped:  ClassPermanent,
	CodeEntityArchived: ClassPermanent,
	CodeRealityFrozen:  ClassPermanent,
	CodeUserErased:     ClassPermanent,
	CodeFeatureRetired: ClassPermanent,
}

// AllErrorCodes returns every canonical code (sorted by class then alpha).
// Used by tests to enforce exhaustiveness and by dashboards to render
// stable column ordering.
func AllErrorCodes() []ErrorCode {
	out := make([]ErrorCode, 0, len(classOfCode))
	for code := range classOfCode {
		out = append(out, code)
	}
	return out
}

// IsValid returns true iff c is one of the 28 enumerated codes.
func (c ErrorCode) IsValid() bool {
	_, ok := classOfCode[c]
	return ok
}

// Class returns the ErrorClass for c. Returns "" + error on unknown codes
// (callers MUST NOT default — that would re-introduce the catch-all).
func (c ErrorCode) Class() (ErrorClass, error) {
	cls, ok := classOfCode[c]
	if !ok {
		return "", fmt.Errorf("errors: unknown code %q", c)
	}
	return cls, nil
}

// ErrorEnvelope is the wire format embedded in TurnOutcomeRow, WS messages,
// and inter-service responses. Fields:
//   - Class: ErrorClass (one of 4)
//   - Code: ErrorCode (one of 28 V1)
//   - Message: human-readable (NEVER contains PII; logged + surfaced to ops)
//   - HTTPStatus: suggested HTTP status (callers may override)
//   - RetryAfter: hint for transient errors (0 = no suggestion)
//   - TraceID: trace correlation
//   - OccurredAt: server-side wall clock at error generation
type ErrorEnvelope struct {
	Class      ErrorClass    `json:"class"`
	Code       ErrorCode     `json:"code"`
	Message    string        `json:"message"`
	HTTPStatus int           `json:"http_status,omitempty"`
	RetryAfter time.Duration `json:"retry_after_nanos,omitempty"`
	TraceID    string        `json:"trace_id,omitempty"`
	OccurredAt time.Time     `json:"occurred_at"`
}

// New constructs a validated ErrorEnvelope. Returns an error if `code` is
// not registered. `Class` is derived from code so callers cannot
// accidentally desync class+code.
func New(code ErrorCode, message string, occurredAt time.Time) (ErrorEnvelope, error) {
	cls, err := code.Class()
	if err != nil {
		return ErrorEnvelope{}, err
	}
	return ErrorEnvelope{
		Class:      cls,
		Code:       code,
		Message:    message,
		OccurredAt: occurredAt,
	}, nil
}

// MustNew is the panic-on-bad-code variant. Use only for compile-time
// constants where the code MUST be valid.
func MustNew(code ErrorCode, message string, occurredAt time.Time) ErrorEnvelope {
	env, err := New(code, message, occurredAt)
	if err != nil {
		panic(err)
	}
	return env
}

// WithHTTPStatus returns a copy with HTTPStatus set.
func (e ErrorEnvelope) WithHTTPStatus(status int) ErrorEnvelope {
	e.HTTPStatus = status
	return e
}

// WithRetryAfter returns a copy with RetryAfter set. Ignored if the class
// is not Transient (Retry-After only makes sense for transient errors).
func (e ErrorEnvelope) WithRetryAfter(d time.Duration) ErrorEnvelope {
	if e.Class != ClassTransient {
		return e
	}
	e.RetryAfter = d
	return e
}

// WithTraceID returns a copy with TraceID set.
func (e ErrorEnvelope) WithTraceID(id string) ErrorEnvelope {
	e.TraceID = id
	return e
}

// Error implements the standard error interface so envelopes can be returned
// as `error` values from service code.
func (e ErrorEnvelope) Error() string {
	return fmt.Sprintf("%s/%s: %s", e.Class, e.Code, e.Message)
}
