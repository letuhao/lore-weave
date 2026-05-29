package errors

import (
	"testing"
	"time"
)

func TestAllErrorClasses_FourValues(t *testing.T) {
	all := AllErrorClasses()
	if len(all) != 4 {
		t.Fatalf("want 4 classes; got %d", len(all))
	}
	for _, c := range all {
		if !c.IsValid() {
			t.Fatalf("%q must validate", c)
		}
	}
	if ErrorClass("bogus").IsValid() {
		t.Fatal("bogus must not validate")
	}
}

func TestClassRetryAndPageDefaults(t *testing.T) {
	if !ClassTransient.IsRetryable() {
		t.Fatal("transient must be retryable")
	}
	if ClassUserError.IsRetryable() || ClassSystemError.IsRetryable() || ClassPermanent.IsRetryable() {
		t.Fatal("only transient should be retryable by default")
	}
	if !ClassSystemError.IsPageable() {
		t.Fatal("system_error must be pageable")
	}
	if ClassUserError.IsPageable() || ClassTransient.IsPageable() || ClassPermanent.IsPageable() {
		t.Fatal("only system_error should be pageable by default")
	}
}

// TestAllCodesAreExhaustive asserts every const ErrorCode appears in
// classOfCode. If you add a new code, also add it to the map; this test
// catches drift.
func TestAllCodesAreExhaustive(t *testing.T) {
	// Hand-enumerate codes via const trick — list all consts here:
	declared := []ErrorCode{
		CodeAuthRequired, CodeAuthExpired, CodeAuthForbidden, CodeValidationFailed,
		CodeQuotaExceeded, CodeRateLimitExceeded, CodeBadInputFormat, CodeUnsupportedClient,
		CodeConsentRequired,
		CodeInternalAssertion, CodeProjectionCorruption, CodeMetaWriteFailed,
		CodeOutboxDrained, CodeUpstreamMisconfigured, CodeSchemaViolation,
		CodeUpstreamTimeout, CodeUpstreamRateLimit, CodeUpstreamUnavailable,
		CodeCircuitOpen, CodeBulkheadFull, CodeConcurrentStateChange,
		CodeDegradedMode, CodeCacheUnavailable,
		CodeEntityDropped, CodeEntityArchived, CodeRealityFrozen,
		CodeUserErased, CodeFeatureRetired,
	}
	if len(declared) != 28 {
		t.Fatalf("V1 declares 28 codes; counted %d", len(declared))
	}
	if len(classOfCode) != 28 {
		t.Fatalf("classOfCode has %d; want 28", len(classOfCode))
	}
	for _, c := range declared {
		if _, ok := classOfCode[c]; !ok {
			t.Fatalf("code %q missing classOfCode entry", c)
		}
		if !c.IsValid() {
			t.Fatalf("code %q not valid", c)
		}
	}
}

func TestClassDistribution(t *testing.T) {
	counts := map[ErrorClass]int{}
	for _, cls := range classOfCode {
		counts[cls]++
	}
	want := map[ErrorClass]int{
		ClassUserError:   9,
		ClassSystemError: 6,
		ClassTransient:   8,
		ClassPermanent:   5,
	}
	for k, v := range want {
		if counts[k] != v {
			t.Fatalf("class %q count=%d want %d", k, counts[k], v)
		}
	}
}

func TestCodeClassRoundtrip(t *testing.T) {
	cls, err := CodeAuthRequired.Class()
	if err != nil || cls != ClassUserError {
		t.Fatalf("%v %v", cls, err)
	}
	if _, err := ErrorCode("bogus").Class(); err == nil {
		t.Fatal("bogus must error")
	}
}

func TestNewBuildsValidatedEnvelope(t *testing.T) {
	t0 := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	env, err := New(CodeUpstreamTimeout, "timed out talking to llm", t0)
	if err != nil {
		t.Fatal(err)
	}
	if env.Class != ClassTransient || env.Code != CodeUpstreamTimeout {
		t.Fatalf("env=%+v", env)
	}
	if env.Error() == "" {
		t.Fatal("Error() empty")
	}
	if _, err := New(ErrorCode("bogus"), "x", t0); err == nil {
		t.Fatal("bogus code must error")
	}
}

func TestRetryAfterOnlyAppliedForTransient(t *testing.T) {
	t0 := time.Now()
	transient := MustNew(CodeUpstreamTimeout, "t", t0).WithRetryAfter(5 * time.Second)
	if transient.RetryAfter != 5*time.Second {
		t.Fatalf("retry_after=%v", transient.RetryAfter)
	}
	userErr := MustNew(CodeAuthRequired, "u", t0).WithRetryAfter(5 * time.Second)
	if userErr.RetryAfter != 0 {
		t.Fatalf("user_error must not accept retry_after; got %v", userErr.RetryAfter)
	}
}

func TestEnvelopeWithModifiers(t *testing.T) {
	t0 := time.Now()
	env := MustNew(CodeAuthExpired, "expired", t0).
		WithHTTPStatus(401).
		WithTraceID("trace-abc")
	if env.HTTPStatus != 401 || env.TraceID != "trace-abc" {
		t.Fatalf("env=%+v", env)
	}
}
