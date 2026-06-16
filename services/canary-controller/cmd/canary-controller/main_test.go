package main

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
	"github.com/loreweave/foundation/services/canary-controller/internal/controller"
	"github.com/loreweave/foundation/services/canary-controller/internal/metrics"
)

func scrape(t *testing.T, m *metrics.Metrics) string {
	t.Helper()
	rec := httptest.NewRecorder()
	m.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	return rec.Body.String()
}

// applyTickResult is the load-bearing per-tick metric logic (the abort-count +
// gauge-reset rules from the review). These assert the dangerous cases:
// failed-rollback aborts ARE counted; read-errors are NOT; terminal actions and
// "no active canary" clear the live gauges.
func TestApplyTickResult(t *testing.T) {
	t.Run("successful abort counts + clears gauges", func(t *testing.T) {
		m := metrics.New()
		m.SetStage(2)
		m.SetObservedBurn(1.5)
		applyTickResult(m, controller.TickResult{Action: canary.ActionAbort, Stage: canary.Stage10pct}, true, nil)
		out := scrape(t, m)
		assertContains(t, out, "lw_canary_abort_total 1")
		assertContains(t, out, "lw_canary_stage -1")
		assertContains(t, out, "lw_canary_controller_observed_burn 0")
	})

	t.Run("failed-rollback abort STILL counts (err != nil)", func(t *testing.T) {
		m := metrics.New()
		m.SetStage(2)
		// Tick on an abort whose rollback failed returns (res{Abort}, true, err).
		applyTickResult(m, controller.TickResult{Action: canary.ActionAbort, Stage: canary.Stage10pct}, true, errors.New("rollback failed"))
		out := scrape(t, m)
		assertContains(t, out, "lw_canary_abort_total 1") // counted despite err
		// On a transient error the gauges are left untouched (no false -1).
		assertContains(t, out, "lw_canary_stage 2")
	})

	t.Run("ActiveCanary read-error does NOT count an abort", func(t *testing.T) {
		m := metrics.New()
		// read error returns (TickResult{}, false, err): ok=false, zero Action.
		applyTickResult(m, controller.TickResult{}, false, errors.New("db down"))
		assertContains(t, scrape(t, m), "lw_canary_abort_total 0")
	})

	t.Run("no active canary clears stage + burn", func(t *testing.T) {
		m := metrics.New()
		m.SetStage(3)
		m.SetObservedBurn(0.4)
		applyTickResult(m, controller.TickResult{}, false, nil)
		out := scrape(t, m)
		assertContains(t, out, "lw_canary_stage -1")
		assertContains(t, out, "lw_canary_controller_observed_burn 0")
		assertContains(t, out, "lw_canary_abort_total 0")
	})

	t.Run("advance sets the stage, no abort", func(t *testing.T) {
		m := metrics.New()
		applyTickResult(m, controller.TickResult{Action: canary.ActionAdvance, Stage: canary.Stage50pct}, true, nil)
		out := scrape(t, m)
		assertContains(t, out, "lw_canary_stage 3")
		assertContains(t, out, "lw_canary_abort_total 0")
	})

	t.Run("complete clears the live gauges", func(t *testing.T) {
		m := metrics.New()
		m.SetStage(4)
		m.SetObservedBurn(0.1)
		applyTickResult(m, controller.TickResult{Action: canary.ActionComplete, Stage: canary.StageFull}, true, nil)
		out := scrape(t, m)
		assertContains(t, out, "lw_canary_stage -1")
		assertContains(t, out, "lw_canary_controller_observed_burn 0")
	})
}

// repoRoot resolves the monorepo root from this test file's location so the
// real events_allowlist.yaml can be used (4 levels up from cmd/canary-controller).
func repoRoot(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Join(filepath.Dir(thisFile), "..", "..", "..", "..")
}

func setAllEnv(t *testing.T, allowPath string) {
	t.Helper()
	t.Setenv("PROM_URL", "http://prometheus:9090")
	t.Setenv("GITHUB_TOKEN", "ghp_test")
	t.Setenv("GITHUB_REPO", "acme/widgets")
	t.Setenv("PAGERDUTY_INTEGRATION_KEY", "rk-test")
	t.Setenv("LW_META_DSN", "postgres://u:p@localhost:5432/db?sslmode=disable") // lazy; never connects
	t.Setenv("META_ALLOWLIST_PATH", allowPath)
}

func TestBuildControllerMissingEnv(t *testing.T) {
	// Clear every required var; expect a "missing env" error listing all 6.
	for _, k := range []string{"PROM_URL", "GITHUB_TOKEN", "GITHUB_REPO", "PAGERDUTY_INTEGRATION_KEY", "LW_META_DSN", "META_ALLOWLIST_PATH"} {
		t.Setenv(k, "")
	}
	ctrl, closeFn, err := buildController(context.Background(), metrics.New())
	if err == nil || ctrl != nil {
		t.Fatalf("all-missing env must error with nil controller, got ctrl=%v err=%v", ctrl, err)
	}
	if !strings.Contains(err.Error(), "missing env") {
		t.Fatalf("error should name missing env, got %v", err)
	}
	closeFn() // must be the safe no-op
}

func TestBuildControllerPartialEnv(t *testing.T) {
	allow := filepath.Join(repoRoot(t), "contracts", "meta", "events_allowlist.yaml")
	setAllEnv(t, allow)
	t.Setenv("PAGERDUTY_INTEGRATION_KEY", "") // drop exactly one
	_, closeFn, err := buildController(context.Background(), metrics.New())
	if err == nil || !strings.Contains(err.Error(), "PAGERDUTY_INTEGRATION_KEY") {
		t.Fatalf("one-missing env must name it, got %v", err)
	}
	closeFn()
}

func TestBuildControllerBadAllowlist(t *testing.T) {
	setAllEnv(t, filepath.Join(t.TempDir(), "does-not-exist.yaml"))
	_, closeFn, err := buildController(context.Background(), metrics.New())
	if err == nil || !strings.Contains(err.Error(), "allowlist") {
		t.Fatalf("missing allowlist file must error, got %v", err)
	}
	closeFn()
}

func TestBuildControllerBadRepoClosesPool(t *testing.T) {
	allow := filepath.Join(repoRoot(t), "contracts", "meta", "events_allowlist.yaml")
	if _, err := os.Stat(allow); err != nil {
		t.Skipf("real allowlist not found (%v); skipping pool-close path test", err)
	}
	setAllEnv(t, allow)
	t.Setenv("GITHUB_REPO", "no-slash") // executor construction fails AFTER the pool opens
	ctrl, closeFn, err := buildController(context.Background(), metrics.New())
	if err == nil || ctrl != nil {
		t.Fatalf("bad repo must error with nil controller (and have closed the pool), got ctrl=%v err=%v", ctrl, err)
	}
	closeFn() // returned noop — must not double-close/panic
}

func TestBuildControllerSuccess(t *testing.T) {
	allow := filepath.Join(repoRoot(t), "contracts", "meta", "events_allowlist.yaml")
	if _, err := os.Stat(allow); err != nil {
		t.Skipf("real allowlist not found (%v); skipping success-path test", err)
	}
	setAllEnv(t, allow)
	ctrl, closeFn, err := buildController(context.Background(), metrics.New())
	if err != nil || ctrl == nil {
		t.Fatalf("all valid env (lazy DSN, never connects) must build a controller, got ctrl=%v err=%v", ctrl, err)
	}
	closeFn() // release the (unconnected) pool
}

func TestMeteredSLIRecordsOnSuccessOnly(t *testing.T) {
	m := metrics.New()
	w := meteredSLI{inner: fakeSLI{burn: 0.7}, m: m}
	if _, err := w.Observe(context.Background(), "d", canary.Stage1pct); err != nil {
		t.Fatal(err)
	}
	assertContains(t, scrape(t, m), "lw_canary_controller_observed_burn 0.7")

	// On an Observe error the burn must NOT be overwritten (stays 0.7).
	w2 := meteredSLI{inner: fakeSLI{err: errors.New("prom down")}, m: m}
	if _, err := w2.Observe(context.Background(), "d", canary.Stage1pct); err == nil {
		t.Fatal("expected error")
	}
	assertContains(t, scrape(t, m), "lw_canary_controller_observed_burn 0.7")
}

type fakeSLI struct {
	burn float64
	err  error
}

func (f fakeSLI) Observe(_ context.Context, _ string, _ canary.Stage) (canary.Observation, error) {
	if f.err != nil {
		return canary.Observation{}, f.err
	}
	return canary.Observation{CohortBurn: f.burn, ErrorRate: f.burn}, nil
}

func assertContains(t *testing.T, haystack, needle string) {
	t.Helper()
	if !strings.Contains(haystack, needle) {
		t.Fatalf("expected %q in:\n%s", needle, haystack)
	}
}
