//go:build prod

package logging_test

import (
	"bytes"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/logging"
)

// Build with: go test -tags=prod ./contracts/logging/...
// These tests assert PROD-build invariants: Debug dropped, Sensitive
// dropped at all levels, NoopRedactor rejected by NewLogger.

func TestProdBuild_RejectsNoopRedactor(t *testing.T) {
	if !logging.IsProdBuild {
		t.Fatal("prod build tag must flip IsProdBuild to true")
	}
	_, err := logging.NewLogger(logging.LoggerConfig{
		MinLevel: logging.LevelInfo,
		Sink:     &bytes.Buffer{},
		Redactor: logging.NoopRedactor(),
	})
	if !errors.Is(err, logging.ErrNilRedactor) {
		t.Errorf("prod build should reject NoopRedactor, got %v", err)
	}
}

func TestProdBuild_RejectsNilRedactor(t *testing.T) {
	_, err := logging.NewLogger(logging.LoggerConfig{
		MinLevel: logging.LevelInfo,
		Sink:     &bytes.Buffer{},
		Redactor: nil,
	})
	if !errors.Is(err, logging.ErrNilRedactor) {
		t.Errorf("prod build should reject nil Redactor, got %v", err)
	}
}

func TestProdBuild_DebugDroppedAtCompileBoundary(t *testing.T) {
	buf := &bytes.Buffer{}
	lg, err := logging.NewLogger(logging.LoggerConfig{
		MinLevel: logging.LevelDebug, // even if min=Debug, prod drops Debug
		Sink:     buf,
		Redactor: &alwaysMask{},
		Clock:    func() time.Time { return time.Unix(0, 0).UTC() },
	})
	if err != nil {
		t.Fatalf("NewLogger: %v", err)
	}
	red := lg.Emit(logging.LevelDebug, "should drop")
	if red != 0 {
		t.Errorf("prod Debug should drop, got %d redactions", red)
	}
	if buf.Len() != 0 {
		t.Errorf("prod Debug should produce no output, got %q", buf.String())
	}
}

func TestProdBuild_SensitiveDroppedAtAllLevels(t *testing.T) {
	buf := &bytes.Buffer{}
	lg, _ := logging.NewLogger(logging.LoggerConfig{
		MinLevel: logging.LevelInfo,
		Sink:     buf,
		Redactor: &alwaysMask{},
		Clock:    func() time.Time { return time.Unix(0, 0).UTC() },
	})
	red := lg.Emit(logging.LevelError, "boom", logging.Sensitive("ip", "10.0.0.1"))
	if red != 1 {
		t.Errorf("prod Sensitive at Error should redact (drop), got %d", red)
	}
	if strings.Contains(buf.String(), "10.0.0.1") {
		t.Errorf("prod Sensitive leaked: %q", buf.String())
	}
}

type alwaysMask struct{}

func (alwaysMask) Redact(v any) (any, bool) { return logging.MaskedString("***"), true }
