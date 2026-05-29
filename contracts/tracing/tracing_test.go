package tracing_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/tracing"
)

// ── TraceContext ──────────────────────────────────────────────────────────

func TestNewTraceContext_RandomAndNonZero(t *testing.T) {
	tc, err := tracing.NewTraceContext()
	if err != nil {
		t.Fatalf("NewTraceContext: %v", err)
	}
	if tc.IsZero() {
		t.Error("NewTraceContext returned zero")
	}
	if tc.Sampled() {
		t.Error("NewTraceContext should not be sampled by default")
	}
	// Hex form length checks
	if len(tc.TraceIDHex()) != 32 {
		t.Errorf("TraceIDHex len = %d, want 32", len(tc.TraceIDHex()))
	}
	if len(tc.SpanIDHex()) != 16 {
		t.Errorf("SpanIDHex len = %d, want 16", len(tc.SpanIDHex()))
	}
}

func TestFormatAndParse_Roundtrip(t *testing.T) {
	tc, _ := tracing.NewTraceContext()
	tc.Flags = 0x01 // sampled
	s := tracing.FormatTraceparent(tc)
	if len(s) != 55 {
		t.Errorf("traceparent len = %d, want 55", len(s))
	}
	parsed, err := tracing.ParseTraceparent(s)
	if err != nil {
		t.Fatalf("ParseTraceparent(%q): %v", s, err)
	}
	if parsed != tc {
		t.Errorf("parsed != original: %v vs %v", parsed, tc)
	}
	if !parsed.Sampled() {
		t.Error("parsed should be sampled")
	}
}

func TestParseTraceparent_Rejects(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want error
	}{
		{"too-short", "00-aa-bb-01", tracing.ErrInvalidTraceparent},
		{"wrong-version", "01-" + strings.Repeat("a", 32) + "-" + strings.Repeat("b", 16) + "-01", tracing.ErrInvalidTraceparent},
		{"uppercase-hex", "00-" + strings.Repeat("A", 32) + "-" + strings.Repeat("b", 16) + "-01", tracing.ErrInvalidTraceparent},
		{"non-hex", "00-" + strings.Repeat("z", 32) + "-" + strings.Repeat("b", 16) + "-01", tracing.ErrInvalidTraceparent},
		{"zero-trace-id", "00-" + strings.Repeat("0", 32) + "-" + strings.Repeat("b", 16) + "-01", tracing.ErrZeroTraceID},
		{"zero-span-id", "00-" + strings.Repeat("a", 32) + "-" + strings.Repeat("0", 16) + "-01", tracing.ErrZeroSpanID},
		{"empty", "", tracing.ErrInvalidTraceparent},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := tracing.ParseTraceparent(c.in)
			if !errors.Is(err, c.want) {
				t.Errorf("ParseTraceparent(%q) err = %v, want wraps %v", c.in, err, c.want)
			}
		})
	}
}

func TestTraceContext_IsZeroAndSampled(t *testing.T) {
	if !(tracing.TraceContext{}).IsZero() {
		t.Error("default TraceContext must be IsZero")
	}
	tc := tracing.TraceContext{Flags: 0x00}
	if tc.Sampled() {
		t.Error("Flags=0 must not be sampled")
	}
	tc.Flags = 0x01
	if !tc.Sampled() {
		t.Error("Flags=1 must be sampled")
	}
}

func TestFormatTraceparent_ZeroReturnsEmpty(t *testing.T) {
	if got := tracing.FormatTraceparent(tracing.TraceContext{}); got != "" {
		t.Errorf("FormatTraceparent(zero) = %q, want \"\"", got)
	}
}

// ── Propagation ──────────────────────────────────────────────────────────

func TestPropagation_InjectExtract_RoundTrip(t *testing.T) {
	tc, _ := tracing.NewTraceContext()
	tc.Flags = 0x01
	tc.State = "vendor1=foo,vendor2=bar"
	h := tracing.MapHeaders{}
	if !tracing.Inject(tc, h) {
		t.Fatal("Inject returned false for non-zero context")
	}
	if h["traceparent"] == "" {
		t.Errorf("traceparent header not set: %v", h)
	}
	extracted, ok := tracing.Extract(h)
	if !ok {
		t.Fatal("Extract returned false after Inject")
	}
	if extracted.TraceIDHex() != tc.TraceIDHex() {
		t.Errorf("TraceID round-trip failed")
	}
	if extracted.State != tc.State {
		t.Errorf("State round-trip failed: %q vs %q", extracted.State, tc.State)
	}
}

func TestPropagation_InjectZero_NoOp(t *testing.T) {
	h := tracing.MapHeaders{}
	if tracing.Inject(tracing.TraceContext{}, h) {
		t.Error("Inject(zero) should return false")
	}
	if len(h) != 0 {
		t.Errorf("Inject(zero) should not write headers, got %v", h)
	}
}

func TestPropagation_ExtractMissing(t *testing.T) {
	h := tracing.MapHeaders{}
	if _, ok := tracing.Extract(h); ok {
		t.Error("Extract(empty) should return false")
	}
}

func TestPropagation_NilCarrier_Defensive(t *testing.T) {
	tc, _ := tracing.NewTraceContext()
	if tracing.Inject(tc, nil) {
		t.Error("Inject(nil) should return false")
	}
	if _, ok := tracing.Extract(nil); ok {
		t.Error("Extract(nil) should return false")
	}
}

func TestPropagation_HeaderCaseInsensitive(t *testing.T) {
	tc, _ := tracing.NewTraceContext()
	h := tracing.MapHeaders{}
	h.Set("TraceParent", tracing.FormatTraceparent(tc))
	// Get via lowercase should find it
	if h.Get("traceparent") == "" {
		t.Error("MapHeaders.Get should be case-insensitive")
	}
}

// ── Sampling ─────────────────────────────────────────────────────────────

func TestAlwaysOnSampler(t *testing.T) {
	s := tracing.AlwaysOnSampler{}
	if d := s.ShouldSample(tracing.TraceContext{}, "x.y", tracing.SamplingHint{}); d != tracing.SamplingRecordAndSample {
		t.Errorf("AlwaysOnSampler decision = %v, want SamplingRecordAndSample", d)
	}
}

func TestAlwaysOffSampler(t *testing.T) {
	s := tracing.AlwaysOffSampler{}
	if d := s.ShouldSample(tracing.TraceContext{}, "x.y", tracing.SamplingHint{Force: true}); d != tracing.SamplingDrop {
		t.Errorf("AlwaysOffSampler honors Force-? force should NOT bypass — but actually AlwaysOff does drop regardless; got %v", d)
	}
}

func TestProbabilisticSampler_ForceWins(t *testing.T) {
	s := tracing.NewProbabilisticSampler(0.0) // 0% rate
	d := s.ShouldSample(tracing.TraceContext{}, "x.y", tracing.SamplingHint{Force: true})
	if d != tracing.SamplingRecordAndSample {
		t.Errorf("Force hint with 0%% rate = %v, want SamplingRecordAndSample", d)
	}
}

func TestProbabilisticSampler_DropWins(t *testing.T) {
	s := tracing.NewProbabilisticSampler(1.0) // 100% rate
	d := s.ShouldSample(tracing.TraceContext{}, "x.y", tracing.SamplingHint{Drop: true})
	if d != tracing.SamplingDrop {
		t.Errorf("Drop hint with 100%% rate = %v, want SamplingDrop", d)
	}
}

func TestProbabilisticSampler_InheritsParent(t *testing.T) {
	s := tracing.NewProbabilisticSampler(0.0) // 0% rate
	parent, _ := tracing.NewTraceContext()
	parent.Flags = 0x01 // sampled
	d := s.ShouldSample(parent, "x.y", tracing.SamplingHint{})
	if d != tracing.SamplingRecordAndSample {
		t.Errorf("Sampled parent must propagate, got %v", d)
	}
}

func TestProbabilisticSampler_ZeroRateDrops(t *testing.T) {
	s := tracing.NewProbabilisticSampler(0.0)
	d := s.ShouldSample(tracing.TraceContext{}, "x.y", tracing.SamplingHint{})
	if d != tracing.SamplingDrop {
		t.Errorf("0 percent rate must drop, got %v", d)
	}
	dropped, sampled := s.Stats()
	if dropped != 1 || sampled != 0 {
		t.Errorf("stats = (drop=%d, sampled=%d), want (1,0)", dropped, sampled)
	}
}

func TestProbabilisticSampler_FullRateSamples(t *testing.T) {
	s := tracing.NewProbabilisticSampler(1.0)
	d := s.ShouldSample(tracing.TraceContext{}, "x.y", tracing.SamplingHint{})
	if d != tracing.SamplingRecordAndSample {
		t.Errorf("100 percent rate must sample, got %v", d)
	}
}

func TestProbabilisticSampler_RateClamps(t *testing.T) {
	s := tracing.NewProbabilisticSampler(-1.0)
	if d := s.ShouldSample(tracing.TraceContext{}, "x.y", tracing.SamplingHint{}); d != tracing.SamplingDrop {
		t.Errorf("rate clamped to 0 percent should drop, got %v", d)
	}
	s2 := tracing.NewProbabilisticSampler(2.5)
	if d := s2.ShouldSample(tracing.TraceContext{}, "x.y", tracing.SamplingHint{}); d != tracing.SamplingRecordAndSample {
		t.Errorf("rate clamped to 100 percent should sample, got %v", d)
	}
}

func TestSamplingDecision_String(t *testing.T) {
	if tracing.SamplingDrop.String() != "drop" {
		t.Error("SamplingDrop.String")
	}
	if tracing.SamplingRecord.String() != "record" {
		t.Error("SamplingRecord.String")
	}
	if tracing.SamplingRecordAndSample.String() != "record_and_sample" {
		t.Error("SamplingRecordAndSample.String")
	}
}

// ── Span name validation ─────────────────────────────────────────────────

func TestValidateSpanName(t *testing.T) {
	good := []string{
		"auth.handler.login",
		"meta_worker.write",
		"single",
		"a.b.c.d",
	}
	bad := []string{
		"",
		"Auth.handler",           // uppercase
		"auth-handler",           // dash
		".starts.with.dot",       // leading dot
		"ends.with.dot.",         // trailing dot
		"two..dots",              // empty segment
		"1starts_with_digit",     // leading digit
	}
	for _, n := range good {
		if err := tracing.ValidateSpanName(n); err != nil {
			t.Errorf("good name %q rejected: %v", n, err)
		}
	}
	for _, n := range bad {
		if err := tracing.ValidateSpanName(n); !errors.Is(err, tracing.ErrInvalidSpanName) {
			t.Errorf("bad name %q must be rejected, got %v", n, err)
		}
	}
}

// ── Span behavior ────────────────────────────────────────────────────────

type fakeRedactor struct{ calls int }

func (f *fakeRedactor) Redact(v any) (any, bool) {
	f.calls++
	if s, ok := v.(string); ok && strings.HasPrefix(s, "PII:") {
		return "***", true
	}
	return v, false
}

func TestTracer_StartSpan_Basic(t *testing.T) {
	exp := tracing.NewInMemoryExporter(100)
	tr, _ := tracing.NewTracer(tracing.TracerConfig{
		Sampler:  tracing.AlwaysOnSampler{},
		Exporter: exp,
	})
	span, ctx, err := tr.StartSpan(context.Background(), "svc.test", tracing.SpanOptions{Kind: tracing.SpanKindServer})
	if err != nil {
		t.Fatalf("StartSpan: %v", err)
	}
	if span == nil {
		t.Fatal("span is nil")
	}
	if tracing.SpanFromContext(ctx) != span {
		t.Error("span not attached to derived ctx")
	}
	if !span.SpanContext().Sampled() {
		t.Error("span context should be sampled")
	}
	span.End()
	if exp.Len() != 1 {
		t.Errorf("exporter.Len = %d, want 1", exp.Len())
	}
	snap := exp.Spans()[0]
	if snap.Name != "svc.test" || snap.Kind != tracing.SpanKindServer {
		t.Errorf("snapshot mismatch: %+v", snap)
	}
}

func TestTracer_RejectsInvalidName(t *testing.T) {
	tr, _ := tracing.NewTracer(tracing.TracerConfig{})
	_, _, err := tr.StartSpan(context.Background(), "BadName", tracing.SpanOptions{})
	if !errors.Is(err, tracing.ErrInvalidSpanName) {
		t.Errorf("expected ErrInvalidSpanName, got %v", err)
	}
}

func TestTracer_PropagatesParentTraceID(t *testing.T) {
	exp := tracing.NewInMemoryExporter(10)
	tr, _ := tracing.NewTracer(tracing.TracerConfig{Exporter: exp})
	parent, _ := tracing.NewTraceContext()
	parent.Flags = 0x01

	ctx := tracing.WithRemoteParent(context.Background(), parent)
	span, _, err := tr.StartSpan(ctx, "svc.handler", tracing.SpanOptions{Kind: tracing.SpanKindServer})
	if err != nil {
		t.Fatalf("StartSpan: %v", err)
	}
	if span.SpanContext().TraceIDHex() != parent.TraceIDHex() {
		t.Errorf("child should inherit parent TraceID")
	}
	if span.SpanContext().SpanIDHex() == parent.SpanIDHex() {
		t.Errorf("child must have fresh SpanID")
	}
	span.End()
}

func TestTracer_PIIAttribute_Redacted(t *testing.T) {
	exp := tracing.NewInMemoryExporter(10)
	r := &fakeRedactor{}
	tr, _ := tracing.NewTracer(tracing.TracerConfig{
		Exporter:         exp,
		Redactor:         r,
		PIIAttributeKeys: []string{"user.email"},
	})
	span, _, _ := tr.StartSpan(context.Background(), "svc.x", tracing.SpanOptions{})
	span.SetAttribute("user.email", "PII:alice@example.com")
	span.SetAttribute("count", 7)
	span.End()

	if r.calls < 1 {
		t.Errorf("Redactor should be called for PII attr, got calls=%d", r.calls)
	}
	snap := exp.Spans()[0]
	if got := snap.Attributes["user.email"]; got != "***" {
		t.Errorf("PII attribute not redacted: %v", got)
	}
	if got := snap.Attributes["count"]; got != 7 {
		t.Errorf("non-PII attribute mangled: %v", got)
	}
}

func TestTracer_NonPIIAttribute_NotRedacted(t *testing.T) {
	exp := tracing.NewInMemoryExporter(10)
	r := &fakeRedactor{}
	tr, _ := tracing.NewTracer(tracing.TracerConfig{
		Exporter:         exp,
		Redactor:         r,
		PIIAttributeKeys: []string{"user.email"},
	})
	span, _, _ := tr.StartSpan(context.Background(), "svc.x", tracing.SpanOptions{})
	span.SetAttribute("not_pii", "PII:alice@example.com") // PREFIX but NOT in allow-list
	span.End()
	if r.calls != 0 {
		t.Errorf("Redactor should NOT be invoked for non-allow-listed key, got calls=%d", r.calls)
	}
}

func TestTracer_SampleDrop_Exporter_NotCalled(t *testing.T) {
	exp := tracing.NewInMemoryExporter(10)
	tr, _ := tracing.NewTracer(tracing.TracerConfig{
		Sampler:  tracing.AlwaysOffSampler{},
		Exporter: exp,
	})
	span, _, _ := tr.StartSpan(context.Background(), "svc.x", tracing.SpanOptions{})
	if span.SpanContext().Sampled() {
		t.Error("dropped span should NOT have sampled bit")
	}
	span.End()
	if exp.Len() != 0 {
		t.Errorf("dropped span MUST NOT export, exp.Len = %d", exp.Len())
	}
}

func TestTracer_EndIdempotent(t *testing.T) {
	exp := tracing.NewInMemoryExporter(10)
	tr, _ := tracing.NewTracer(tracing.TracerConfig{Exporter: exp})
	span, _, _ := tr.StartSpan(context.Background(), "svc.x", tracing.SpanOptions{})
	span.End()
	span.End() // must not export twice
	if exp.Len() != 1 {
		t.Errorf("double-End exported twice: exp.Len = %d", exp.Len())
	}
}

func TestSpan_RecordError(t *testing.T) {
	exp := tracing.NewInMemoryExporter(10)
	tr, _ := tracing.NewTracer(tracing.TracerConfig{Exporter: exp})
	span, _, _ := tr.StartSpan(context.Background(), "svc.x", tracing.SpanOptions{})
	span.RecordError(errors.New("boom"))
	span.RecordError(nil) // defensive: nil err is no-op
	span.End()
	snap := exp.Spans()[0]
	if snap.Status != tracing.StatusError {
		t.Errorf("status = %v, want StatusError", snap.Status)
	}
	if len(snap.Errors) != 1 {
		t.Errorf("errors count = %d, want 1", len(snap.Errors))
	}
}

func TestSpan_SetStatus(t *testing.T) {
	exp := tracing.NewInMemoryExporter(10)
	tr, _ := tracing.NewTracer(tracing.TracerConfig{Exporter: exp})
	span, _, _ := tr.StartSpan(context.Background(), "svc.x", tracing.SpanOptions{})
	span.SetStatus(tracing.StatusOK)
	span.End()
	if exp.Spans()[0].Status != tracing.StatusOK {
		t.Error("SetStatus(OK) not applied")
	}
}

func TestSpanKind_String(t *testing.T) {
	cases := map[tracing.SpanKind]string{
		tracing.SpanKindInternal: "internal",
		tracing.SpanKindServer:   "server",
		tracing.SpanKindClient:   "client",
		tracing.SpanKindProducer: "producer",
		tracing.SpanKindConsumer: "consumer",
	}
	for k, want := range cases {
		if got := k.String(); got != want {
			t.Errorf("SpanKind(%d).String = %q, want %q", k, got, want)
		}
	}
}

func TestStatus_String(t *testing.T) {
	if tracing.StatusUnset.String() != "unset" {
		t.Error("StatusUnset")
	}
	if tracing.StatusOK.String() != "ok" {
		t.Error("StatusOK")
	}
	if tracing.StatusError.String() != "error" {
		t.Error("StatusError")
	}
}

func TestSpanSnapshot_Duration(t *testing.T) {
	snap := tracing.SpanSnapshot{
		StartedAt: time.Unix(1000, 0),
		EndedAt:   time.Unix(1003, 0),
	}
	if d := snap.Duration(); d != 3*time.Second {
		t.Errorf("Duration = %v, want 3s", d)
	}
}

// ── Exporter ─────────────────────────────────────────────────────────────

func TestInMemoryExporter_RingEviction(t *testing.T) {
	exp := tracing.NewInMemoryExporter(2)
	for i := 0; i < 5; i++ {
		exp.Export(tracing.SpanSnapshot{Name: "x"})
	}
	if exp.Len() != 2 {
		t.Errorf("Len = %d, want 2", exp.Len())
	}
	if exp.Dropped() != 3 {
		t.Errorf("Dropped = %d, want 3", exp.Dropped())
	}
}

func TestNoopExporter_NoPanic(t *testing.T) {
	tracing.NoopExporter{}.Export(tracing.SpanSnapshot{})
}

func TestNoopTracer_Works(t *testing.T) {
	span, _, err := tracing.NoopTracer{}.StartSpan(context.Background(), "svc.x", tracing.SpanOptions{})
	if err != nil {
		t.Fatalf("NoopTracer.StartSpan: %v", err)
	}
	span.End()
}

func TestNoopTracer_RejectsBadName(t *testing.T) {
	_, _, err := tracing.NoopTracer{}.StartSpan(context.Background(), "BadName", tracing.SpanOptions{})
	if !errors.Is(err, tracing.ErrInvalidSpanName) {
		t.Errorf("NoopTracer should validate span name, got %v", err)
	}
}

func TestNewTracer_RejectsEmptyPIIKey(t *testing.T) {
	_, err := tracing.NewTracer(tracing.TracerConfig{
		PIIAttributeKeys: []string{""},
	})
	if !errors.Is(err, tracing.ErrInvalidConfig) {
		t.Errorf("empty PII key should be rejected, got %v", err)
	}
}

func TestContextWithSpan_NilCtx(t *testing.T) {
	exp := tracing.NewInMemoryExporter(10)
	tr, _ := tracing.NewTracer(tracing.TracerConfig{Exporter: exp})
	span, _, _ := tr.StartSpan(context.Background(), "svc.x", tracing.SpanOptions{})
	ctx := tracing.ContextWithSpan(nil, span)
	if tracing.SpanFromContext(ctx) != span {
		t.Error("ContextWithSpan(nil) should still work")
	}
}

func TestSpanFromContext_NilCtxNoPanic(t *testing.T) {
	if tracing.SpanFromContext(nil) != nil {
		t.Error("SpanFromContext(nil) should return nil")
	}
}

func TestRemoteParentFromContext_NilCtxNoPanic(t *testing.T) {
	if _, ok := tracing.RemoteParentFromContext(nil); ok {
		t.Error("RemoteParentFromContext(nil) should return false")
	}
}
