package main

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/loreweave/foundation/services/admin-cli/internal/framework"
)

// TestWireCommandHandler guards D-ADMIN-NOTWIRED-EXIT (121): a wiring-builder
// ERROR (config present but invalid) must be FATAL so the caller exits non-zero,
// instead of silently falling through to the tier-3 NotWiredHandler (a calm
// "recognised but not wired" message with exit 0). The legit "no config →
// (nil handler, nil err)" path must stay non-fatal so the dispatcher's tier
// policy decides.
func TestWireCommandHandler(t *testing.T) {
	noop := func() {}

	t.Run("wiring error → FATAL + real error reported (no silent exit-0)", func(t *testing.T) {
		var buf bytes.Buffer
		reg := framework.NewHandlerRegistry()
		closer, fatal := wireCommandHandler(&buf, reg, "archive fetch", func() (framework.Handler, func(), error) {
			return nil, noop, errors.New("archive fetch needs MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY")
		})
		closer()
		if !fatal {
			t.Fatal("a real wiring error must be FATAL (caller exits non-zero), not a silent NotWired fall-through")
		}
		if !strings.Contains(buf.String(), "MINIO_ENDPOINT") {
			t.Fatalf("the real config error must be surfaced to the operator, got %q", buf.String())
		}
		// The command must NOT be registered — it stays NotWired (but the caller
		// aborts before dispatch, so the tier-3 calm message is never printed).
	})

	t.Run("no-config (nil handler, nil err) → NOT fatal, stays NotWired", func(t *testing.T) {
		var buf bytes.Buffer
		reg := framework.NewHandlerRegistry()
		closer, fatal := wireCommandHandler(&buf, reg, "reality stats", func() (framework.Handler, func(), error) {
			return nil, noop, nil // no META_DATABASE_URL → leave NotWired
		})
		closer()
		if fatal {
			t.Fatal("the no-config nil-err path must NOT be fatal — the dispatcher's tier policy decides")
		}
		if buf.Len() != 0 {
			t.Fatalf("the legit no-config path must print nothing, got %q", buf.String())
		}
		// Resolve still yields the fail-closed NotWiredHandler (tier-3 informs,
		// tier-1/2 error) — that's the dispatcher's job, not the wiring's.
		if got := reg.Resolve(&framework.Command{Name: "reality stats", ImpactClass: framework.Tier3Informational}); got == nil {
			t.Fatal("Resolve must always return a handler")
		}
	})

	t.Run("successful wiring → handler registered, not fatal", func(t *testing.T) {
		var buf bytes.Buffer
		reg := framework.NewHandlerRegistry()
		want := "stats-output"
		ok := framework.Handler(func(_ context.Context, _ framework.Invocation) (string, error) {
			return want, nil
		})
		closer, fatal := wireCommandHandler(&buf, reg, "reality stats", func() (framework.Handler, func(), error) {
			return ok, noop, nil
		})
		closer()
		if fatal {
			t.Fatal("a clean wiring must not be fatal")
		}
		h := reg.Resolve(&framework.Command{Name: "reality stats", ImpactClass: framework.Tier3Informational})
		out, err := h(context.Background(), framework.Invocation{})
		if err != nil || out != want {
			t.Fatalf("the registered handler must be resolved, got out=%q err=%v", out, err)
		}
	})
}
