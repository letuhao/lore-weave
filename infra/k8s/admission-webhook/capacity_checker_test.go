package webhook

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/capacity"
)

// budgetsForTest constructs a minimal capacity.Budgets fixture: one
// service `publisher` with v1 max=4 + v3 max=8. Loaded directly (no
// YAML round-trip) for unit-test speed.
func budgetsForTest(t *testing.T) capacity.Budgets {
	t.Helper()
	cpu := 0.5
	return capacity.Budgets{
		Version: 1,
		Services: []capacity.Service{
			{
				Name:  "publisher",
				Class: capacity.ClassWorker,
				V1: capacity.Tier{
					MinReplicas: 1, MaxReplicas: 4,
					CPUPerReplica: &cpu, MemoryPerReplica: "512Mi",
					ScaleTrigger: "outbox_lag>1000",
				},
				V3: capacity.Tier{
					MinReplicas: 2, MaxReplicas: 8,
					CPUPerReplica: &cpu, MemoryPerReplica: "1Gi",
					ScaleTrigger: "outbox_lag>1000",
				},
			},
		},
	}
}

func newChecker(t *testing.T, store *capacity.InMemOverrideStore, clockNow time.Time) *Checker {
	t.Helper()
	b := budgetsForTest(t)
	adm := capacity.NewAdmission(b)
	if store == nil {
		store = capacity.NewInMemOverrideStore()
	}
	overr := capacity.NewOverrideHandler(store,
		capacity.WithClock(func() time.Time { return clockNow }),
		capacity.WithCacheTTL(60*time.Second),
	)
	emitter := func(_ Decision, _ time.Duration) {}
	c := NewChecker(adm, overr, emitter)
	c.WithClock(func() time.Time { return clockNow })
	return c
}

func mkRequest(t *testing.T, kind string, labels map[string]string, replicas *int) AdmissionRequest {
	t.Helper()
	obj := map[string]any{
		"metadata": map[string]any{"labels": labels},
		"spec":     map[string]any{},
	}
	if replicas != nil {
		obj["spec"].(map[string]any)["replicas"] = *replicas
	}
	raw, err := json.Marshal(obj)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return AdmissionRequest{
		UID:       "test-uid-1",
		Kind:      kind,
		Operation: "CREATE",
		Object:    raw,
	}
}

func TestReview_AdmitWellFormedService(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	c := newChecker(t, nil, now)
	repl := 2
	req := mkRequest(t, "Deployment", map[string]string{"app.kubernetes.io/name": "publisher"}, &repl)
	resp := c.Review(context.Background(), req)
	if !resp.Allowed {
		t.Fatalf("expected allowed; got %v (msg=%s)", resp.Allowed, resp.Status.Message)
	}
	if resp.Status.Reason != string(DecisionAllow) {
		t.Fatalf("expected reason=allow; got %q", resp.Status.Reason)
	}
}

func TestReview_RejectMissingBudgetService(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	c := newChecker(t, nil, now)
	repl := 1
	req := mkRequest(t, "Deployment", map[string]string{"app.kubernetes.io/name": "mystery-service"}, &repl)
	resp := c.Review(context.Background(), req)
	if resp.Allowed {
		t.Fatalf("expected deny; got allowed")
	}
	if !strings.Contains(resp.Status.Message, "not in budgets.yaml") {
		t.Fatalf("expected message about budgets.yaml; got %q", resp.Status.Message)
	}
	if resp.Status.Reason != string(DecisionDenyNoBudget) {
		t.Fatalf("expected reason=deny_no_budget; got %q", resp.Status.Reason)
	}
}

func TestReview_RejectOverBudgetWithoutOverride(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	c := newChecker(t, nil, now)
	repl := 5 // v1 max=4
	req := mkRequest(t, "Deployment", map[string]string{"app.kubernetes.io/name": "publisher"}, &repl)
	resp := c.Review(context.Background(), req)
	if resp.Allowed {
		t.Fatalf("expected deny; over v1 budget without override")
	}
	if resp.Status.Reason != string(DecisionDenyOverBudget) {
		t.Fatalf("expected reason=deny_over_budget; got %q", resp.Status.Reason)
	}
}

func TestReview_AllowOverBudgetViaActiveOverride(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	store := capacity.NewInMemOverrideStore()
	ov := capacity.Override{
		ServiceName: "publisher",
		GrantedBy:   "sre-oncall@loreweave.dev",
		GrantedAt:   now,
		ExpiresAt:   now.Add(24 * time.Hour),
		Reason:      "incident-2024-publisher-fanout-storm requires headroom",
		Action:      capacity.OverrideAllow,
	}
	if err := store.Grant(ov); err != nil {
		t.Fatalf("grant: %v", err)
	}
	c := newChecker(t, store, now)
	repl := 6 // v1 max=4 — over budget
	req := mkRequest(t, "Deployment", map[string]string{"app.kubernetes.io/name": "publisher"}, &repl)
	resp := c.Review(context.Background(), req)
	if !resp.Allowed {
		t.Fatalf("expected allow_via_override; got deny: %s", resp.Status.Message)
	}
	if resp.Status.Reason != string(DecisionAllowViaOverride) {
		t.Fatalf("expected reason=allow_via_override; got %q", resp.Status.Reason)
	}
	if !strings.Contains(resp.Status.Message, "override_by") {
		t.Fatalf("override message should name granter; got %q", resp.Status.Message)
	}
}

func TestReview_DenyAfterOverrideExpires24h(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	store := capacity.NewInMemOverrideStore()
	_ = store.Grant(capacity.Override{
		ServiceName: "publisher", GrantedBy: "sre@loreweave.dev",
		GrantedAt: now, ExpiresAt: now.Add(24 * time.Hour),
		Reason: "valid reason field for the override row here",
		Action: capacity.OverrideAllow,
	})

	// Fast-forward 25h past grant — override expired per S5 Tier 2.
	clockNow := now.Add(25 * time.Hour)
	c := newChecker(t, store, clockNow)
	repl := 5
	req := mkRequest(t, "Deployment", map[string]string{"app.kubernetes.io/name": "publisher"}, &repl)
	resp := c.Review(context.Background(), req)
	if resp.Allowed {
		t.Fatalf("override should auto-expire at 24h; expected deny")
	}
	if resp.Status.Reason != string(DecisionDenyOverBudget) {
		t.Fatalf("expected reason=deny_over_budget post-expiry; got %q", resp.Status.Reason)
	}
}

func TestReview_RejectMissingLabel(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	c := newChecker(t, nil, now)
	repl := 1
	req := mkRequest(t, "Deployment", map[string]string{}, &repl)
	resp := c.Review(context.Background(), req)
	if resp.Allowed {
		t.Fatalf("expected deny for missing service label")
	}
	if !strings.Contains(resp.Status.Message, "app.kubernetes.io/name") {
		t.Fatalf("expected explicit label-missing message; got %q", resp.Status.Message)
	}
}

func TestReview_UnsupportedKind(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	c := newChecker(t, nil, now)
	repl := 1
	req := mkRequest(t, "StatefulSet", map[string]string{"app.kubernetes.io/name": "publisher"}, &repl)
	resp := c.Review(context.Background(), req)
	if resp.Allowed {
		t.Fatalf("StatefulSet should be denied (cycle-30 supports Pod + Deployment only)")
	}
	if !strings.Contains(resp.Status.Message, "unsupported request kind") {
		t.Fatalf("expected unsupported-kind message; got %q", resp.Status.Message)
	}
}

func TestReview_LatencyMeasured(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	b := budgetsForTest(t)
	adm := capacity.NewAdmission(b)
	store := capacity.NewInMemOverrideStore()
	overr := capacity.NewOverrideHandler(store,
		capacity.WithClock(func() time.Time { return now }),
	)
	var emittedDec Decision
	var emittedLat time.Duration
	emitter := func(d Decision, l time.Duration) { emittedDec = d; emittedLat = l }
	c := NewChecker(adm, overr, emitter)

	// Use a fake clock that advances by 5ms inside Review() to simulate
	// work — start vs end differ deterministically.
	tick := now
	advance := 0
	c.WithClock(func() time.Time {
		t := tick
		advance++
		if advance == 2 {
			t = t.Add(5 * time.Millisecond)
		}
		return t
	})

	repl := 1
	req := mkRequest(t, "Deployment", map[string]string{"app.kubernetes.io/name": "publisher"}, &repl)
	resp := c.Review(context.Background(), req)
	if !resp.Allowed {
		t.Fatalf("expected allow")
	}
	if emittedDec != DecisionAllow {
		t.Fatalf("emitter did not see DecisionAllow; got %q", emittedDec)
	}
	if emittedLat != 5*time.Millisecond {
		t.Fatalf("expected latency=5ms; got %v", emittedLat)
	}
}

func TestReview_V3TierBudget(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	c := newChecker(t, nil, now)
	repl := 6 // v3 max=8, so 6 is OK; v1 max=4 so we MUST honor the tier label
	req := mkRequest(t, "Deployment", map[string]string{
		"app.kubernetes.io/name": "publisher",
		"lw.deployment.tier":     "v3",
	}, &repl)
	resp := c.Review(context.Background(), req)
	if !resp.Allowed {
		t.Fatalf("expected allow under v3 tier; got %s", resp.Status.Message)
	}
}

// Stats counters increment per decision.
func TestStats_CountsDecisionsAndDenials(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	c := newChecker(t, nil, now)
	allowed := 1
	denied := 9
	req1 := mkRequest(t, "Deployment", map[string]string{"app.kubernetes.io/name": "publisher"}, &allowed)
	req2 := mkRequest(t, "Deployment", map[string]string{"app.kubernetes.io/name": "publisher"}, &denied)

	c.Review(context.Background(), req1)
	c.Review(context.Background(), req2)
	c.Review(context.Background(), req2)

	dec, deny := c.Stats()
	if dec != 3 {
		t.Fatalf("expected 3 decisions; got %d", dec)
	}
	if deny != 2 {
		t.Fatalf("expected 2 denials; got %d", deny)
	}
}
