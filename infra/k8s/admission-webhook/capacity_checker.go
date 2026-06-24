// Package webhook implements the L6.G K8s ValidatingAdmissionWebhook
// that rejects pod / deployment specs which exceed `contracts/capacity/
// budgets.yaml` entries.
//
// Q-L6G-1 LOCKED: K8s ValidatingWebhookConfiguration (matches CLAUDE.md
// infra direction). An ECS-equivalent variant is V2+ scope.
//
// Wire flow:
//
//   1. K8s apiserver receives a `pods` or `deployments` CREATE/UPDATE.
//   2. K8s posts an AdmissionReview JSON to https://<webhook>/validate.
//   3. Checker.Review:
//        a. Parse pod / deployment spec → resolve the service name from
//           the `app.kubernetes.io/name` label (the deployment-of-record
//           label used everywhere in infra/k8s/).
//        b. Look up the service in budgets.yaml (cycle 19 contract).
//        c. If unknown → DENY ("service missing from budgets.yaml").
//        d. If over the v1/v3 max_replicas → DENY.
//        e. If over budget BUT an active override exists → ALLOW
//           with annotation `lw.capacity.override-id=<grant_id>`.
//   4. Webhook returns AdmissionReview with allowed=true|false and a
//      human-readable status.message.
//
// Acceptance criterion (layer plan §195): P99 latency < 100ms. The
// checker is allocation-light + uses the cycle-19 capacity.Admission
// snapshot (in-memory lookup). No DB call on hot path — overrides
// cached 60s by capacity.OverrideHandler.
package webhook

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"sync/atomic"
	"time"

	"github.com/loreweave/foundation/contracts/capacity"
)

// Decision is the four-valued outcome emitted by the webhook (matches
// the `lw_capacity_admission_decisions_total{decision}` label set in
// inventory.yaml).
type Decision string

const (
	DecisionAllow            Decision = "allow"
	DecisionDenyNoBudget     Decision = "deny_no_budget"
	DecisionDenyOverBudget   Decision = "deny_over_budget"
	DecisionAllowViaOverride Decision = "allow_via_override"
)

// Tier is which capacity tier the deployment targets. Pods carry
// `app.kubernetes.io/version` (or our `lw.deployment.tier`) hinting
// which budget slice to enforce.
type Tier string

const (
	TierV1 Tier = "v1"
	TierV3 Tier = "v3"
)

// AdmissionRequest is a trimmed AdmissionReview shape. The full K8s
// API ships through k8s.io/api/admission/v1 in production; cycle-30
// ships a hand-rolled subset so the foundation Go module stays
// dependency-light. Production wires the real type later via go.sum
// addition.
//
// Fields we care about:
//   * UID — opaque admission-request id, echoed back in response.
//   * Kind — "Pod" or "Deployment" (we accept either, treat pods as
//     having implicit replicas=1).
//   * Operation — "CREATE" or "UPDATE".
//   * Object — raw object JSON (pod spec or deployment spec).
type AdmissionRequest struct {
	UID       string          `json:"uid"`
	Kind      string          `json:"kind"`
	Operation string          `json:"operation"`
	Object    json.RawMessage `json:"object"`
}

// AdmissionResponse is the K8s AdmissionReview response payload.
type AdmissionResponse struct {
	UID     string         `json:"uid"`
	Allowed bool           `json:"allowed"`
	Status  ResponseStatus `json:"status"`
}

// ResponseStatus is the human-visible portion (kubectl shows
// status.message on rejection).
type ResponseStatus struct {
	Code    int32  `json:"code"`
	Message string `json:"message"`
	Reason  string `json:"reason,omitempty"`
}

// Errors.
var (
	ErrServiceLabelMissing = errors.New("webhook: app.kubernetes.io/name label missing — every pod MUST self-declare its service")
	ErrBudgetMissing       = errors.New("webhook: service not in budgets.yaml")
	ErrOverBudget          = errors.New("webhook: requested replicas exceed budget")
	ErrUnsupportedKind     = errors.New("webhook: unsupported request kind (expect Pod or Deployment)")
)

// Checker is the webhook engine. Construct once at boot via
// NewChecker. Holds the budgets snapshot + override handler.
type Checker struct {
	adm      *capacity.Admission
	overr    *capacity.OverrideHandler
	clock    func() time.Time
	emitter  MetricsEmitter

	decisions atomic.Uint64
	denies    atomic.Uint64
}

// MetricsEmitter is the callback invoked once per decision so the
// caller can push `lw_capacity_admission_decisions_total{decision}` +
// `lw_capacity_admission_latency_seconds` into Prometheus.
//
// Implementations MUST be non-blocking + side-effect-only (the
// webhook returns to K8s as soon as Review() returns; a slow emitter
// must not block the apiserver).
type MetricsEmitter func(decision Decision, latency time.Duration)

// NewChecker constructs a webhook checker.
func NewChecker(adm *capacity.Admission, overr *capacity.OverrideHandler, emitter MetricsEmitter) *Checker {
	if adm == nil {
		panic("webhook: nil capacity.Admission")
	}
	if overr == nil {
		panic("webhook: nil capacity.OverrideHandler")
	}
	if emitter == nil {
		emitter = func(Decision, time.Duration) {}
	}
	return &Checker{
		adm:     adm,
		overr:   overr,
		clock:   func() time.Time { return time.Now().UTC() },
		emitter: emitter,
	}
}

// WithClock overrides the clock — tests use this to control latency
// measurement.
func (c *Checker) WithClock(f func() time.Time) *Checker {
	if f != nil {
		c.clock = f
	}
	return c
}

// Stats returns (totalDecisions, denials) — used by the SRE dashboard
// + the cycle-30 verify script.
func (c *Checker) Stats() (decisions, denials uint64) {
	return c.decisions.Load(), c.denies.Load()
}

// Review is the request entry point. Pure function — does NOT do I/O
// against K8s. The HTTP handler in deployment.yaml wraps this.
//
// Latency invariant (L6.G acceptance §195): P99 < 100ms. We measure
// per-call latency and pass to the emitter.
func (c *Checker) Review(ctx context.Context, req AdmissionRequest) AdmissionResponse {
	start := c.clock()
	c.decisions.Add(1)

	decision, msg := c.decide(ctx, req)
	if decision != DecisionAllow && decision != DecisionAllowViaOverride {
		c.denies.Add(1)
	}

	latency := c.clock().Sub(start)
	c.emitter(decision, latency)

	resp := AdmissionResponse{
		UID:     req.UID,
		Allowed: decision == DecisionAllow || decision == DecisionAllowViaOverride,
		Status: ResponseStatus{
			Code:    statusCode(decision),
			Message: msg,
			Reason:  string(decision),
		},
	}
	return resp
}

func statusCode(d Decision) int32 {
	if d == DecisionAllow || d == DecisionAllowViaOverride {
		return 200
	}
	return 403
}

// decide is the core admission rule.
func (c *Checker) decide(ctx context.Context, req AdmissionRequest) (Decision, string) {
	switch req.Kind {
	case "Pod", "Deployment":
	default:
		return DecisionDenyNoBudget, fmt.Sprintf("%v: kind=%q", ErrUnsupportedKind, req.Kind)
	}

	meta, err := parseRequest(req)
	if err != nil {
		return DecisionDenyNoBudget, err.Error()
	}

	// Lookup the budget. capacity.Admission.RegisterService both
	// validates presence AND records the registration for downstream
	// dashboards (idempotent).
	svc, err := c.adm.RegisterService(meta.ServiceName)
	if err != nil {
		// Service not in budgets.yaml — check for an override (rare:
		// admin grants an exemption for a brand-new service mid-deploy).
		if allowed, _ := c.overr.IsAllowed(ctx, meta.ServiceName); allowed {
			return DecisionAllowViaOverride, fmt.Sprintf("service %q not in budgets.yaml but active override grants admission", meta.ServiceName)
		}
		return DecisionDenyNoBudget, fmt.Sprintf("%v: %s", ErrBudgetMissing, meta.ServiceName)
	}

	// Resolve tier — default v1 if unset.
	tier := meta.Tier
	if tier == "" {
		tier = TierV1
	}
	maxR := tierMax(svc, tier)
	if meta.Replicas <= maxR {
		return DecisionAllow, fmt.Sprintf("service=%s tier=%s replicas=%d max=%d", meta.ServiceName, tier, meta.Replicas, maxR)
	}

	// Over budget — last chance is an active override.
	if allowed, ov := c.overr.IsAllowed(ctx, meta.ServiceName); allowed {
		return DecisionAllowViaOverride, fmt.Sprintf("service=%s tier=%s replicas=%d max=%d override_by=%q expires=%s", meta.ServiceName, tier, meta.Replicas, maxR, ov.GrantedBy, ov.ExpiresAt.Format(time.RFC3339))
	}
	return DecisionDenyOverBudget, fmt.Sprintf("%v: service=%s tier=%s replicas=%d max=%d (no active override)", ErrOverBudget, meta.ServiceName, tier, meta.Replicas, maxR)
}

func tierMax(s capacity.Service, t Tier) int {
	switch t {
	case TierV3:
		return s.V3.MaxReplicas
	default:
		return s.V1.MaxReplicas
	}
}

// requestMeta is the shape extracted from the AdmissionRequest.Object.
type requestMeta struct {
	ServiceName string
	Tier        Tier
	Replicas    int
}

// objectMeta is the JSON shape we pull out of the request object. We
// only parse the fields we need so the parser is allocation-light.
type objectMeta struct {
	Metadata struct {
		Labels map[string]string `json:"labels"`
	} `json:"metadata"`
	Spec struct {
		// Deployment.spec.replicas
		Replicas *int `json:"replicas,omitempty"`
	} `json:"spec"`
}

func parseRequest(req AdmissionRequest) (requestMeta, error) {
	if len(req.Object) == 0 {
		return requestMeta{}, fmt.Errorf("webhook: empty object payload")
	}
	var obj objectMeta
	if err := json.Unmarshal(req.Object, &obj); err != nil {
		return requestMeta{}, fmt.Errorf("webhook: parse object: %w", err)
	}
	svc := obj.Metadata.Labels["app.kubernetes.io/name"]
	if svc == "" {
		return requestMeta{}, ErrServiceLabelMissing
	}
	tier := Tier(obj.Metadata.Labels["lw.deployment.tier"])
	if tier == "" {
		// Optional cross-check: app.kubernetes.io/version
		if v := obj.Metadata.Labels["app.kubernetes.io/version"]; v != "" {
			tier = Tier(v)
		}
	}
	replicas := 1
	if obj.Spec.Replicas != nil {
		replicas = *obj.Spec.Replicas
	} else if r := obj.Metadata.Labels["lw.deployment.replicas"]; r != "" {
		// Pods don't carry replicas; some operators stamp the desired
		// scale into this hint label so the webhook can still see
		// fleet size.
		if parsed, err := strconv.Atoi(r); err == nil && parsed > 0 {
			replicas = parsed
		}
	}
	return requestMeta{ServiceName: svc, Tier: tier, Replicas: replicas}, nil
}
