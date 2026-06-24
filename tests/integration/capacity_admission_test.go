//go:build integration

package integration

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/capacity"
	webhook "github.com/loreweave/foundation/infra/k8s/admission-webhook"
)

// TestCapacityAdmissionWebhook_RejectsAndAdmits — L6.G integration smoke.
//
// Wires the cycle-19 capacity.Budgets + cycle-30 OverrideHandler +
// cycle-30 webhook.Checker end-to-end and exercises the four decision
// paths declared in the inventory metric:
//
//   * allow                — well-formed pod under budget
//   * deny_no_budget       — pod for a service missing from budgets.yaml
//   * deny_over_budget     — pod replicas > tier max, no override
//   * allow_via_override   — same as deny_over_budget but with active override
//
// Q-L6G-1 LOCKED: K8s ValidatingWebhookConfiguration shape (CLAUDE.md
// infra match).
func TestCapacityAdmissionWebhook_RejectsAndAdmits(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)

	// Construct budgets fixture matching cycle-30 verify expectations.
	cpu := 0.5
	b := capacity.Budgets{
		Version: 1,
		Services: []capacity.Service{
			{
				Name: "publisher", Class: capacity.ClassWorker,
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
	adm := capacity.NewAdmission(b)
	store := capacity.NewInMemOverrideStore()
	overrides := capacity.NewOverrideHandler(store,
		capacity.WithClock(func() time.Time { return now }),
		capacity.WithCacheTTL(60*time.Second),
	)

	// Spy emitter so we can assert per-decision counters are firing
	// (the deployed prom adapter would push these into Prometheus).
	emittedDecisions := map[webhook.Decision]int{}
	emitter := func(d webhook.Decision, _ time.Duration) {
		emittedDecisions[d]++
	}
	checker := webhook.NewChecker(adm, overrides, emitter)
	checker.WithClock(func() time.Time { return now })

	makeReq := func(svc string, replicas int, tier string) webhook.AdmissionRequest {
		labels := map[string]string{"app.kubernetes.io/name": svc}
		if tier != "" {
			labels["lw.deployment.tier"] = tier
		}
		obj := map[string]any{
			"metadata": map[string]any{"labels": labels},
			"spec":     map[string]any{"replicas": replicas},
		}
		raw, _ := json.Marshal(obj)
		return webhook.AdmissionRequest{UID: "uid-" + svc, Kind: "Deployment", Operation: "CREATE", Object: raw}
	}

	// ── allow: well-formed pod under budget.
	r := checker.Review(context.Background(), makeReq("publisher", 2, ""))
	if !r.Allowed || r.Status.Reason != string(webhook.DecisionAllow) {
		t.Fatalf("expected allow; got allowed=%v reason=%q msg=%s", r.Allowed, r.Status.Reason, r.Status.Message)
	}

	// ── deny_no_budget: service not in budgets.yaml.
	r = checker.Review(context.Background(), makeReq("mystery-service", 1, ""))
	if r.Allowed || r.Status.Reason != string(webhook.DecisionDenyNoBudget) {
		t.Fatalf("expected deny_no_budget; got allowed=%v reason=%q", r.Allowed, r.Status.Reason)
	}
	if !strings.Contains(r.Status.Message, "not in budgets.yaml") {
		t.Fatalf("missing 'not in budgets.yaml' in message: %q", r.Status.Message)
	}

	// ── deny_over_budget: replicas=5 vs v1.max=4 with no override.
	r = checker.Review(context.Background(), makeReq("publisher", 5, ""))
	if r.Allowed || r.Status.Reason != string(webhook.DecisionDenyOverBudget) {
		t.Fatalf("expected deny_over_budget; got allowed=%v reason=%q", r.Allowed, r.Status.Reason)
	}

	// ── allow_via_override: grant 24h override, same over-budget request now passes.
	if err := store.Grant(capacity.Override{
		ServiceName: "publisher",
		GrantedBy:   "sre-oncall@loreweave.dev",
		GrantedAt:   now,
		ExpiresAt:   now.Add(24 * time.Hour),
		Reason:      "incident-2026-publisher-fanout-storm extra headroom",
		Action:      capacity.OverrideAllow,
	}); err != nil {
		t.Fatalf("Grant: %v", err)
	}
	// Force a cache refresh by recreating handler (60s cache otherwise
	// blocks the new grant from showing).
	freshOverrides := capacity.NewOverrideHandler(store,
		capacity.WithClock(func() time.Time { return now }),
		capacity.WithCacheTTL(60*time.Second),
	)
	freshChecker := webhook.NewChecker(adm, freshOverrides, emitter)
	freshChecker.WithClock(func() time.Time { return now })
	r = freshChecker.Review(context.Background(), makeReq("publisher", 5, ""))
	if !r.Allowed || r.Status.Reason != string(webhook.DecisionAllowViaOverride) {
		t.Fatalf("expected allow_via_override; got allowed=%v reason=%q", r.Allowed, r.Status.Reason)
	}

	// Verify the metric emitter saw all four decisions at least once.
	for _, want := range []webhook.Decision{
		webhook.DecisionAllow,
		webhook.DecisionDenyNoBudget,
		webhook.DecisionDenyOverBudget,
		webhook.DecisionAllowViaOverride,
	} {
		if emittedDecisions[want] == 0 {
			t.Fatalf("decision %q never emitted to metrics", want)
		}
	}
}

// TestCapacityAdmissionWebhook_OverrideExpiry24h — S5 Tier 2 enforcement.
//
// Asserts that an override granted at T0 STOPS allowing deploys at T0+24h
// exactly. Catches the cycle-30 IsActive() boundary regression.
func TestCapacityAdmissionWebhook_OverrideExpiry24h(t *testing.T) {
	t0 := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	cpu := 0.5
	b := capacity.Budgets{
		Version: 1,
		Services: []capacity.Service{{
			Name: "publisher", Class: capacity.ClassWorker,
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
		}},
	}
	adm := capacity.NewAdmission(b)
	store := capacity.NewInMemOverrideStore()
	_ = store.Grant(capacity.Override{
		ServiceName: "publisher", GrantedBy: "sre@loreweave.dev",
		GrantedAt: t0, ExpiresAt: t0.Add(24 * time.Hour),
		Reason: "valid sixteen-character minimum reason field here",
		Action: capacity.OverrideAllow,
	})

	makeReq := func(replicas int) webhook.AdmissionRequest {
		obj := map[string]any{
			"metadata": map[string]any{"labels": map[string]string{"app.kubernetes.io/name": "publisher"}},
			"spec":     map[string]any{"replicas": replicas},
		}
		raw, _ := json.Marshal(obj)
		return webhook.AdmissionRequest{UID: "uid", Kind: "Deployment", Operation: "CREATE", Object: raw}
	}

	// Just before 24h boundary — override still active.
	tWithin := t0.Add(23*time.Hour + 59*time.Minute)
	h := capacity.NewOverrideHandler(store, capacity.WithClock(func() time.Time { return tWithin }))
	c := webhook.NewChecker(adm, h, nil).WithClock(func() time.Time { return tWithin })
	if r := c.Review(context.Background(), makeReq(5)); !r.Allowed {
		t.Fatalf("within 24h: expected allow_via_override; got %s", r.Status.Message)
	}

	// At 24h boundary — override expired (IsActive(now) == false).
	tBoundary := t0.Add(24 * time.Hour)
	h2 := capacity.NewOverrideHandler(store, capacity.WithClock(func() time.Time { return tBoundary }))
	c2 := webhook.NewChecker(adm, h2, nil).WithClock(func() time.Time { return tBoundary })
	if r := c2.Review(context.Background(), makeReq(5)); r.Allowed {
		t.Fatalf("AT 24h boundary: override must have expired; got allowed=true")
	}
}
