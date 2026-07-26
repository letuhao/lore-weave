package observability

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"testing"

	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

// lastJSON decodes the last JSON line written to buf.
func lastJSON(t *testing.T, buf *bytes.Buffer) map[string]any {
	t.Helper()
	var rec map[string]any
	if err := json.Unmarshal(bytes.TrimSpace(buf.Bytes()), &rec); err != nil {
		t.Fatalf("log line not JSON: %v (%q)", err, buf.String())
	}
	return rec
}

// spanCtx starts a real span on a fresh provider and returns its context + trace id.
func spanCtx(t *testing.T) (context.Context, string, func()) {
	t.Helper()
	tp := sdktrace.NewTracerProvider()
	ctx, span := tp.Tracer("test").Start(context.Background(), "test-span")
	return ctx, span.SpanContext().TraceID().String(), func() { span.End() }
}

func TestTraceHandler_InjectsOtelTraceID(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(&traceHandler{Handler: slog.NewJSONHandler(&buf, nil)})

	ctx, wantTID, end := spanCtx(t)
	logger.InfoContext(ctx, "inside a span")
	end()

	rec := lastJSON(t, &buf)
	if rec["otel_trace_id"] != wantTID {
		t.Fatalf("otel_trace_id = %v, want %s", rec["otel_trace_id"], wantTID)
	}
}

func TestTraceHandler_NoTraceIDWithoutSpan(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(&traceHandler{Handler: slog.NewJSONHandler(&buf, nil)})

	// ctx-less log → context.Background() → no span.
	logger.Info("no span")
	if _, ok := lastJSON(t, &buf)["otel_trace_id"]; ok {
		t.Fatal("otel_trace_id must be absent for a ctx-less log")
	}

	// InfoContext with a span-less context → also absent (the line still emits).
	buf.Reset()
	logger.InfoContext(context.Background(), "span-less ctx")
	if _, ok := lastJSON(t, &buf)["otel_trace_id"]; ok {
		t.Fatal("otel_trace_id must be absent for a span-less ctx")
	}
}

// TestTraceHandler_SurvivesWithAttrs is the MONEY test: SetupLogging does
// slog.New(h).With("service", name), which derives a child handler via WithAttrs.
// If WithAttrs returned the INNER handler (dropping the traceHandler wrapper),
// trace injection would silently vanish on every real logger (they all carry the
// "service" attr). This proves the re-wrap holds.
func TestTraceHandler_SurvivesWithAttrs(t *testing.T) {
	var buf bytes.Buffer
	base := &traceHandler{Handler: slog.NewJSONHandler(&buf, nil)}
	logger := slog.New(base).With("service", "book-service") // exactly what SetupLogging does

	ctx, wantTID, end := spanCtx(t)
	logger.InfoContext(ctx, "after .With")
	end()

	rec := lastJSON(t, &buf)
	if rec["otel_trace_id"] != wantTID {
		t.Fatalf("trace injection lost after .With(): otel_trace_id=%v want %s", rec["otel_trace_id"], wantTID)
	}
	if rec["service"] != "book-service" {
		t.Fatalf("service attr missing after .With(): %v", rec["service"])
	}
}

// TestTraceHandler_WithGroupNestsTraceID pins a KNOWN edge: a WithGroup-derived
// logger nests otel_trace_id UNDER the group, because slog opens the group for all
// of a record's attrs — including handler-added ones. No fleet service logs through
// a top-level group (SetupLogging installs a flat `.With("service")` logger, so
// otel_trace_id is always top-level in practice), but this pins the grouped shape so
// a future change to make it group-invariant is a conscious one, not an accident.
func TestTraceHandler_WithGroupNestsTraceID(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(&traceHandler{Handler: slog.NewJSONHandler(&buf, nil)}).WithGroup("req")

	ctx, wantTID, end := spanCtx(t)
	logger.InfoContext(ctx, "grouped")
	end()

	rec := lastJSON(t, &buf)
	if _, ok := rec["otel_trace_id"]; ok {
		t.Fatal("under a group, otel_trace_id is expected NESTED, not top-level")
	}
	grp, _ := rec["req"].(map[string]any)
	if grp["otel_trace_id"] != wantTID {
		t.Fatalf("otel_trace_id under group = %v, want %s", grp["otel_trace_id"], wantTID)
	}
}
