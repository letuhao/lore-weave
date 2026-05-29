package logging

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sync"
	"sync/atomic"
	"time"
)

// piiFloorMask is the hard fallback applied to any FieldKindPII value the
// Redactor declines to mask (PRR-28). It guarantees raw PII never reaches the
// sink even in a misconfigured or non-prod build (where a NoopRedactor would
// otherwise pass the raw value through). A real Redactor that wants smarter
// rendering returns (masked, true) and is used instead.
const piiFloorMask = "[REDACTED:PII]"

// Logger is the typed structured-logging surface every LoreWeave service
// uses. Concrete impl is JSONLogger below. Tests may swap a CapturingLogger
// (logger_test.go).
//
// Emit emits ONE structured event. The (level, msg, fields) tuple is the
// full payload; trace correlation is injected via WithTrace (returns a
// derived logger) so callers do not pass TraceCorrelation per call.
type Logger interface {
	// Emit writes ONE log event.
	//
	// Behavior:
	//   - PROD build: drops LevelDebug; drops FieldKindSensitive; masks PII.
	//   - DEV build: emits all levels; FieldKindSensitive visible at Debug only.
	//
	// Returns the count of redactions applied (drives the cycle-19
	// inventory.yaml lw_log_redactions_total counter — services bind a
	// counter callback via WithRedactionCounter).
	Emit(level Level, msg string, fields ...Field) (redactions int)

	// WithTrace returns a derived Logger that injects the TraceCorrelation
	// on every Emit. The returned Logger MUST share the same sink + level
	// + redactor as the parent.
	WithTrace(tc TraceCorrelation) Logger

	// WithRedactionCounter returns a derived Logger that invokes cb on
	// every redaction event (passed the FieldKind that was redacted —
	// FieldKindPII or FieldKindSensitive). Used by services to bind to
	// the cycle-19 lw_log_redactions_total Prometheus counter.
	WithRedactionCounter(cb func(kind FieldKind)) Logger
}

// LoggerConfig is the typed config struct passed to NewLogger.
type LoggerConfig struct {
	// MinLevel is the floor — emits below this are dropped. PROD build
	// implicitly enforces LevelInfo floor (LevelDebug is dropped at compile).
	MinLevel Level

	// Sink is the io.Writer that receives the JSON bytes. Tests pass a
	// bytes.Buffer; production passes os.Stdout (Vector tails stdout).
	Sink io.Writer

	// Redactor is the cycle-22 PII SDK adapter. NIL is REJECTED in PROD
	// build (ErrNilRedactor); allowed in DEV (defaults to NoopRedactor).
	Redactor Redactor

	// Clock is the time source — tests override with a fixed clock.
	// Defaults to time.Now when nil.
	Clock func() time.Time
}

// NewLogger constructs the production JSONLogger.
//
// PROD build defense: if cfg.Redactor == nil OR cfg.Redactor is a
// NoopRedactor, NewLogger returns ErrNilRedactor. DEV build accepts both.
func NewLogger(cfg LoggerConfig) (Logger, error) {
	if cfg.Sink == nil {
		return nil, errors.New("logging: NewLogger requires non-nil Sink")
	}
	if !cfg.MinLevel.IsValid() {
		return nil, fmt.Errorf("logging: NewLogger invalid MinLevel: %w", ErrInvalidLevel)
	}
	if IsProdBuild {
		if cfg.Redactor == nil {
			return nil, ErrNilRedactor
		}
		if _, isNoop := cfg.Redactor.(noopRedactor); isNoop {
			return nil, ErrNilRedactor
		}
	}
	if cfg.Redactor == nil {
		cfg.Redactor = NoopRedactor()
	}
	if cfg.Clock == nil {
		cfg.Clock = time.Now
	}
	return &jsonLogger{
		minLevel: cfg.MinLevel,
		sink:     cfg.Sink,
		redactor: cfg.Redactor,
		clock:    cfg.Clock,
	}, nil
}

// jsonLogger is the canonical Logger implementation. JSON-line shape
// (one event = one newline-terminated JSON object on the sink).
type jsonLogger struct {
	minLevel       Level
	sink           io.Writer
	redactor       Redactor
	clock          func() time.Time
	trace          TraceCorrelation
	redactionCount atomic.Int64
	redactionCb    func(kind FieldKind)
	mu             sync.Mutex // guards sink writes (multi-goroutine safe)
}

// shallowCopy returns a child logger sharing sink+redactor+clock but with
// its own trace + redaction counter callback. Used by WithTrace +
// WithRedactionCounter.
func (l *jsonLogger) shallowCopy() *jsonLogger {
	return &jsonLogger{
		minLevel:    l.minLevel,
		sink:        l.sink,
		redactor:    l.redactor,
		clock:       l.clock,
		trace:       l.trace,
		redactionCb: l.redactionCb,
		// redactionCount intentionally fresh — children count their own
		// redactions for the metric, parent does its own
		// (matches "scope of derived logger" usage pattern).
	}
}

// WithTrace returns a child logger that injects tc on every Emit.
func (l *jsonLogger) WithTrace(tc TraceCorrelation) Logger {
	c := l.shallowCopy()
	c.trace = tc
	return c
}

// WithRedactionCounter returns a child logger that invokes cb on each
// redacted field. cb MUST be non-blocking (it runs on the hot path).
func (l *jsonLogger) WithRedactionCounter(cb func(kind FieldKind)) Logger {
	c := l.shallowCopy()
	c.redactionCb = cb
	return c
}

// Emit writes ONE log event. See Logger.Emit for behavior.
func (l *jsonLogger) Emit(level Level, msg string, fields ...Field) int {
	if !level.IsValid() {
		// Defensive: caller passed invalid level. Promote to Warn and
		// emit a meta-field so the bug is discoverable.
		level = LevelWarn
		fields = append(fields, Normal("logging_invalid_level_recovered", true))
	}

	// PROD compile-time drop: LevelDebug below-floor in PROD build
	// because cycle-32 spec says DEBUG disabled at compile-time.
	if IsProdBuild && level == LevelDebug {
		return 0
	}

	if level < l.minLevel {
		return 0
	}

	// Build the output map: stable JSON shape.
	out := map[string]any{
		"ts":    l.clock().UTC().Format(time.RFC3339Nano),
		"level": level.String(),
		"msg":   msg,
	}
	if !l.trace.IsZero() {
		if l.trace.TraceID != "" {
			out["trace_id"] = l.trace.TraceID
		}
		if l.trace.SpanID != "" {
			out["span_id"] = l.trace.SpanID
		}
		if l.trace.CorrelationID != "" {
			out["correlation_id"] = l.trace.CorrelationID
		}
	}

	redactions := 0
	if len(fields) > 0 {
		fieldMap := make(map[string]any, len(fields))
		for _, f := range fields {
			if !f.Kind.IsValid() {
				continue // defensive: skip malformed
			}
			// FieldKindSensitive: dropped in PROD; dev-build visible only at Debug.
			if f.Kind == FieldKindSensitive {
				if IsProdBuild {
					redactions++
					if l.redactionCb != nil {
						l.redactionCb(FieldKindSensitive)
					}
					continue
				}
				if level != LevelDebug {
					redactions++
					if l.redactionCb != nil {
						l.redactionCb(FieldKindSensitive)
					}
					continue
				}
			}
			// FieldKindPII: ALWAYS routed through Redactor, with a hard mask
			// FLOOR (PRR-28). If the redactor declines (e.g. NoopRedactor in a
			// non-prod build), we MUST NOT pass the raw value to the sink —
			// apply piiFloorMask so raw PII never leaks regardless of build tag.
			if f.Kind == FieldKindPII {
				if masked, applied := l.redactor.Redact(f.Value); applied {
					fieldMap[f.Name] = masked
				} else {
					fieldMap[f.Name] = piiFloorMask
				}
				redactions++
				if l.redactionCb != nil {
					l.redactionCb(FieldKindPII)
				}
				continue
			}
			// FieldKindNormal: pass through.
			fieldMap[f.Name] = f.Value
		}
		if len(fieldMap) > 0 {
			out["fields"] = fieldMap
		}
	}

	if redactions > 0 {
		l.redactionCount.Add(int64(redactions))
	}

	buf, err := json.Marshal(out)
	if err != nil {
		// JSON marshal of map[string]any should never fail for serializable
		// values — but defensively, emit a structured error line.
		buf = []byte(fmt.Sprintf(`{"ts":%q,"level":"error","msg":"logging: json.Marshal failed","fields":{"err":%q}}`,
			l.clock().UTC().Format(time.RFC3339Nano), err.Error()))
	}

	l.mu.Lock()
	defer l.mu.Unlock()
	l.sink.Write(buf)
	l.sink.Write([]byte("\n"))
	return redactions
}

// RedactionCount returns the count of redactions emitted by this logger
// since construction. Test-only helper — production uses
// WithRedactionCounter to wire a Prometheus counter.
func (l *jsonLogger) RedactionCount() int64 {
	return l.redactionCount.Load()
}
