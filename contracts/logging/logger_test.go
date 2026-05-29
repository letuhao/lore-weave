package logging_test

import (
	"bytes"
	"encoding/json"
	"errors"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/logging"
)

// fakeRedactor masks the marker string "PII:" prefix into "***" — and
// reports redacted=true on each application. Tests use this as the cycle-22
// PII SDK stand-in.
type fakeRedactor struct {
	calls atomic.Int64
}

func (f *fakeRedactor) Redact(v any) (any, bool) {
	f.calls.Add(1)
	s, ok := v.(string)
	if !ok {
		return v, false
	}
	if strings.HasPrefix(s, "PII:") {
		return logging.MaskedString("***"), true
	}
	return s, false
}

func fixedClock(t time.Time) func() time.Time { return func() time.Time { return t } }

func mustParse(t *testing.T, line []byte) map[string]any {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal(line, &m); err != nil {
		t.Fatalf("invalid JSON line %q: %v", string(line), err)
	}
	return m
}

func newTestLogger(t *testing.T, min logging.Level) (*bytes.Buffer, *fakeRedactor, logging.Logger) {
	t.Helper()
	buf := &bytes.Buffer{}
	r := &fakeRedactor{}
	clk := fixedClock(time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC))
	lg, err := logging.NewLogger(logging.LoggerConfig{MinLevel: min, Sink: buf, Redactor: r, Clock: clk})
	if err != nil {
		t.Fatalf("NewLogger: %v", err)
	}
	return buf, r, lg
}

func TestLevel_StringAndParse(t *testing.T) {
	cases := []struct {
		l    logging.Level
		want string
	}{
		{logging.LevelDebug, "debug"},
		{logging.LevelInfo, "info"},
		{logging.LevelWarn, "warn"},
		{logging.LevelError, "error"},
	}
	for _, c := range cases {
		if got := c.l.String(); got != c.want {
			t.Errorf("Level(%d).String() = %q, want %q", int(c.l), got, c.want)
		}
		if !c.l.IsValid() {
			t.Errorf("Level(%d) should be valid", int(c.l))
		}
		parsed, err := logging.ParseLevel(c.want)
		if err != nil || parsed != c.l {
			t.Errorf("ParseLevel(%q) = (%d,%v), want (%d,nil)", c.want, parsed, err, c.l)
		}
	}
	if _, err := logging.ParseLevel("foo"); !errors.Is(err, logging.ErrInvalidLevel) {
		t.Errorf("ParseLevel(\"foo\") should wrap ErrInvalidLevel, got %v", err)
	}
	bad := logging.Level(99)
	if bad.IsValid() {
		t.Errorf("Level(99) should be invalid")
	}
	if got := bad.String(); !strings.Contains(got, "invalid") {
		t.Errorf("Level(99).String() should contain \"invalid\", got %q", got)
	}
}

func TestFieldKind_StringAndValidity(t *testing.T) {
	cases := []struct {
		k    logging.FieldKind
		want string
	}{
		{logging.FieldKindNormal, "normal"},
		{logging.FieldKindSensitive, "sensitive"},
		{logging.FieldKindPII, "pii"},
	}
	for _, c := range cases {
		if got := c.k.String(); got != c.want {
			t.Errorf("FieldKind(%d).String() = %q, want %q", int(c.k), got, c.want)
		}
		if !c.k.IsValid() {
			t.Errorf("FieldKind(%d) should be valid", int(c.k))
		}
	}
	bad := logging.FieldKind(7)
	if bad.IsValid() {
		t.Errorf("FieldKind(7) should be invalid")
	}
	if got := bad.String(); !strings.Contains(got, "invalid") {
		t.Errorf("FieldKind(7).String() should contain \"invalid\", got %q", got)
	}
}

func TestNewField_RejectsInvalid(t *testing.T) {
	if _, err := logging.NewField("", "v", logging.FieldKindNormal); !errors.Is(err, logging.ErrInvalidField) {
		t.Errorf("empty name should yield ErrInvalidField, got %v", err)
	}
	if _, err := logging.NewField("k", "v", logging.FieldKind(5)); !errors.Is(err, logging.ErrInvalidField) {
		t.Errorf("invalid kind should yield ErrInvalidField, got %v", err)
	}
	f, err := logging.NewField("k", "v", logging.FieldKindPII)
	if err != nil {
		t.Fatalf("valid input should not error: %v", err)
	}
	if f.Kind != logging.FieldKindPII {
		t.Errorf("Kind=%v, want FieldKindPII", f.Kind)
	}
}

func TestHelpers_SetCorrectKind(t *testing.T) {
	if logging.PII("x", 1).Kind != logging.FieldKindPII {
		t.Error("PII helper must produce FieldKindPII")
	}
	if logging.Sensitive("x", 1).Kind != logging.FieldKindSensitive {
		t.Error("Sensitive helper must produce FieldKindSensitive")
	}
	if logging.Normal("x", 1).Kind != logging.FieldKindNormal {
		t.Error("Normal helper must produce FieldKindNormal")
	}
}

func TestNewLogger_RejectsBadConfig(t *testing.T) {
	if _, err := logging.NewLogger(logging.LoggerConfig{}); err == nil {
		t.Error("nil Sink should be rejected")
	}
	if _, err := logging.NewLogger(logging.LoggerConfig{Sink: &bytes.Buffer{}, MinLevel: logging.Level(7)}); err == nil {
		t.Error("invalid MinLevel should be rejected")
	}
}

func TestEmit_BelowFloor_Dropped(t *testing.T) {
	buf, _, lg := newTestLogger(t, logging.LevelWarn)
	red := lg.Emit(logging.LevelDebug, "should drop")
	if red != 0 {
		t.Errorf("Debug below Warn floor should return 0 redactions, got %d", red)
	}
	if buf.Len() != 0 {
		t.Errorf("Debug below Warn floor should produce no output, got %q", buf.String())
	}
}

func TestEmit_JSONShape_Stable(t *testing.T) {
	buf, _, lg := newTestLogger(t, logging.LevelInfo)
	lg.Emit(logging.LevelInfo, "hello", logging.Normal("count", 7))
	m := mustParse(t, bytes.TrimSpace(buf.Bytes()))
	if m["level"] != "info" {
		t.Errorf("level field = %v, want \"info\"", m["level"])
	}
	if m["msg"] != "hello" {
		t.Errorf("msg = %v, want \"hello\"", m["msg"])
	}
	if m["ts"] == nil {
		t.Error("ts missing")
	}
	fields, ok := m["fields"].(map[string]any)
	if !ok {
		t.Fatalf("fields = %T, want map", m["fields"])
	}
	if fields["count"] != float64(7) {
		t.Errorf("fields.count = %v, want 7", fields["count"])
	}
	// no trace correlation when not set
	if _, ok := m["trace_id"]; ok {
		t.Error("trace_id should be omitted when not set")
	}
}

func TestEmit_PII_RedactedViaInterface(t *testing.T) {
	buf, r, lg := newTestLogger(t, logging.LevelInfo)
	red := lg.Emit(logging.LevelInfo, "hi", logging.PII("email", "PII:alice@example.com"))
	if red != 1 {
		t.Errorf("expected 1 redaction, got %d", red)
	}
	if r.calls.Load() != 1 {
		t.Errorf("Redactor.Redact should have been called once, got %d", r.calls.Load())
	}
	m := mustParse(t, bytes.TrimSpace(buf.Bytes()))
	fields := m["fields"].(map[string]any)
	got, ok := fields["email"].(string)
	if !ok || got != "***" {
		t.Errorf("PII field email = %v, want \"***\"", fields["email"])
	}
	// Belt-and-suspenders: raw plaintext MUST NOT appear anywhere.
	if strings.Contains(buf.String(), "alice@example.com") {
		t.Errorf("PII plaintext leaked in output: %q", buf.String())
	}
}

func TestEmit_PII_NotRedactedWhenRedactorPassThrough(t *testing.T) {
	// The fake redactor only masks "PII:" prefix — without the prefix, it
	// passes through and reports redacted=false.
	buf, r, lg := newTestLogger(t, logging.LevelInfo)
	red := lg.Emit(logging.LevelInfo, "hi", logging.PII("user_id", "u-42"))
	if red != 0 {
		t.Errorf("expected 0 redactions when redactor passes through, got %d", red)
	}
	if r.calls.Load() != 1 {
		t.Errorf("Redactor should still be invoked (defense pattern), got %d", r.calls.Load())
	}
	m := mustParse(t, bytes.TrimSpace(buf.Bytes()))
	fields := m["fields"].(map[string]any)
	if fields["user_id"] != "u-42" {
		t.Errorf("user_id = %v, want \"u-42\"", fields["user_id"])
	}
}

func TestEmit_Sensitive_DroppedAtInfo_VisibleAtDebug(t *testing.T) {
	// In dev build (default !prod), Sensitive is visible at Debug.
	if logging.IsProdBuild {
		t.Skip("test runs only in dev build")
	}
	buf, _, lg := newTestLogger(t, logging.LevelDebug)
	// Info should drop
	red := lg.Emit(logging.LevelInfo, "hi", logging.Sensitive("ip", "10.0.0.1"))
	if red != 1 {
		t.Errorf("Info+Sensitive should redact, got %d", red)
	}
	if strings.Contains(buf.String(), "10.0.0.1") {
		t.Errorf("Sensitive at Info leaked: %q", buf.String())
	}
	buf.Reset()
	// Debug should show
	red = lg.Emit(logging.LevelDebug, "hi2", logging.Sensitive("ip", "10.0.0.1"))
	if red != 0 {
		t.Errorf("Debug+Sensitive should NOT redact in dev, got %d", red)
	}
	if !strings.Contains(buf.String(), "10.0.0.1") {
		t.Errorf("Sensitive at Debug should be visible in dev, got %q", buf.String())
	}
}

func TestEmit_Normal_PassesThrough(t *testing.T) {
	buf, _, lg := newTestLogger(t, logging.LevelInfo)
	red := lg.Emit(logging.LevelInfo, "hi", logging.Normal("count", 5))
	if red != 0 {
		t.Errorf("Normal should never redact, got %d", red)
	}
	if !strings.Contains(buf.String(), `"count":5`) {
		t.Errorf("Normal value missing: %q", buf.String())
	}
}

func TestEmit_InvalidKindFieldSkipped(t *testing.T) {
	buf, _, lg := newTestLogger(t, logging.LevelInfo)
	bad := logging.Field{Name: "x", Value: 1, Kind: logging.FieldKind(99)}
	red := lg.Emit(logging.LevelInfo, "hi", bad, logging.Normal("ok", 1))
	if red != 0 {
		t.Errorf("invalid-kind field should not redact, got %d", red)
	}
	if strings.Contains(buf.String(), `"x":`) {
		t.Errorf("invalid-kind field should be skipped: %q", buf.String())
	}
	if !strings.Contains(buf.String(), `"ok":1`) {
		t.Errorf("valid field after invalid should still emit: %q", buf.String())
	}
}

func TestEmit_InvalidLevelPromotedAndAnnotated(t *testing.T) {
	buf, _, lg := newTestLogger(t, logging.LevelDebug)
	lg.Emit(logging.Level(99), "hi")
	m := mustParse(t, bytes.TrimSpace(buf.Bytes()))
	if m["level"] != "warn" {
		t.Errorf("invalid level should promote to warn, got %v", m["level"])
	}
	fields := m["fields"].(map[string]any)
	if fields["logging_invalid_level_recovered"] != true {
		t.Errorf("recovery field missing: %v", fields)
	}
}

func TestWithTrace_InjectsCorrelation(t *testing.T) {
	buf, _, lg := newTestLogger(t, logging.LevelInfo)
	tc := logging.TraceCorrelation{TraceID: "abc", SpanID: "def", CorrelationID: "ghi"}
	tlg := lg.WithTrace(tc)
	tlg.Emit(logging.LevelInfo, "hi")
	m := mustParse(t, bytes.TrimSpace(buf.Bytes()))
	if m["trace_id"] != "abc" || m["span_id"] != "def" || m["correlation_id"] != "ghi" {
		t.Errorf("trace correlation missing: %v", m)
	}
}

func TestWithTrace_ZeroOmitsKeys(t *testing.T) {
	buf, _, lg := newTestLogger(t, logging.LevelInfo)
	tlg := lg.WithTrace(logging.TraceCorrelation{})
	tlg.Emit(logging.LevelInfo, "hi")
	m := mustParse(t, bytes.TrimSpace(buf.Bytes()))
	for _, k := range []string{"trace_id", "span_id", "correlation_id"} {
		if _, has := m[k]; has {
			t.Errorf("zero TraceCorrelation should omit %q", k)
		}
	}
}

func TestWithRedactionCounter_FiresPerRedactedField(t *testing.T) {
	_, _, lg := newTestLogger(t, logging.LevelInfo)
	var piiCount, sensCount atomic.Int64
	clg := lg.WithRedactionCounter(func(k logging.FieldKind) {
		switch k {
		case logging.FieldKindPII:
			piiCount.Add(1)
		case logging.FieldKindSensitive:
			sensCount.Add(1)
		}
	})
	clg.Emit(logging.LevelInfo, "hi",
		logging.PII("email", "PII:bob@example.com"),
		logging.Sensitive("ip", "10.0.0.1"),
	)
	if piiCount.Load() != 1 {
		t.Errorf("PII counter = %d, want 1", piiCount.Load())
	}
	if sensCount.Load() != 1 {
		t.Errorf("Sensitive counter = %d, want 1", sensCount.Load())
	}
}

func TestTraceCorrelation_IsZero(t *testing.T) {
	if !(logging.TraceCorrelation{}).IsZero() {
		t.Error("empty TraceCorrelation must be IsZero")
	}
	if (logging.TraceCorrelation{TraceID: "a"}).IsZero() {
		t.Error("nonempty TraceCorrelation must not be IsZero")
	}
}

func TestNoopRedactor_NeverRedacts(t *testing.T) {
	r := logging.NoopRedactor()
	out, applied := r.Redact("anything")
	if applied {
		t.Error("NoopRedactor.Redact applied=true, want false")
	}
	if out != "anything" {
		t.Errorf("NoopRedactor changed value: %v", out)
	}
}

func TestNewLogger_DevBuildAcceptsNoopRedactor(t *testing.T) {
	if logging.IsProdBuild {
		t.Skip("dev-build-only test")
	}
	buf := &bytes.Buffer{}
	if _, err := logging.NewLogger(logging.LoggerConfig{
		MinLevel: logging.LevelInfo,
		Sink:     buf,
		Redactor: logging.NoopRedactor(),
	}); err != nil {
		t.Errorf("dev build should accept NoopRedactor, got %v", err)
	}
}
