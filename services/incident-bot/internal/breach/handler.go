package breach

import (
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
	gbf "github.com/loreweave/foundation/services/incident-bot/internal/gdpr_breach_flow"
)

// DefaultMaxBackdate bounds how far in the past detected_at may be — anti-forgery
// of the 72h anchor (adversary BLOCK#1). Legitimate breaches are declared
// promptly; a week bounds the forgery window.
//
// NOTE: detected_at older than 72h IS permitted (legitimate LATE DISCOVERY) and
// yields a breach BORN past its deadline — the monitor flags it "missed" on the
// first tick. That is intended: an Art.33 breach discovered late must still be
// recorded + flagged as past-deadline, not rejected.
const DefaultMaxBackdate = 7 * 24 * time.Hour

type breachRequest struct {
	IncidentID     string `json:"incident_id"`
	DetectedAt     string `json:"detected_at"` // RFC3339
	DataCategories string `json:"data_categories"`
	AffectedCount  int    `json:"affected_count"`
}

type breachResponse struct {
	IncidentID string `json:"incident_id"`
	DetectedAt string `json:"detected_at"`
	Deadline   string `json:"deadline"`
	// DPONotice is "obligation-emitted-pending-delivery" (NOT "delivered" — a
	// downstream consumer delivers; D-BREACH-DELIVERY-CONSUMER) or
	// "emit-failed-retry" when the obligation event could not be emitted.
	DPONotice string `json:"dpo_notice"`
	Warning   string `json:"warning,omitempty"`
}

// Handler serves POST /internal/breach. Fail-closed auth: an unset
// INCIDENT_INTERNAL_TOKEN disables intake entirely; otherwise the request must
// present a matching X-Internal-Token (constant-time compared). detected_at is
// operator-attested + clamped so the 72h legal clock cannot be forged.
type Handler struct {
	emitter     EventEmitter
	monitor     *Monitor
	now         func() time.Time
	token       string
	maxBackdate time.Duration
}

// NewHandler wires the breach intake. internalToken="" → intake disabled
// (fail-closed). maxBackdate<=0 → DefaultMaxBackdate.
func NewHandler(emitter EventEmitter, monitor *Monitor, now func() time.Time, internalToken string, maxBackdate time.Duration) *Handler {
	if now == nil {
		now = time.Now
	}
	if maxBackdate <= 0 {
		maxBackdate = DefaultMaxBackdate
	}
	return &Handler{emitter: emitter, monitor: monitor, now: now, token: internalToken, maxBackdate: maxBackdate}
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	// Fail-closed: no configured secret → no unauthenticated breach intake.
	if h.token == "" {
		http.Error(w, "breach intake disabled: INCIDENT_INTERNAL_TOKEN unset", http.StatusServiceUnavailable)
		return
	}
	got := []byte(r.Header.Get("X-Internal-Token"))
	if subtle.ConstantTimeCompare(got, []byte(h.token)) != 1 {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}

	var req breachRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
		http.Error(w, "invalid JSON body", http.StatusBadRequest)
		return
	}
	if req.IncidentID == "" {
		http.Error(w, "missing incident_id", http.StatusBadRequest)
		return
	}
	detectedAt, err := time.Parse(time.RFC3339, req.DetectedAt)
	if err != nil {
		http.Error(w, "detected_at must be RFC3339", http.StatusBadRequest)
		return
	}
	now := h.now()
	if detectedAt.After(now) {
		http.Error(w, "detected_at is in the future (the 72h anchor must be <= now)", http.StatusBadRequest)
		return
	}
	if now.Sub(detectedAt) > h.maxBackdate {
		http.Error(w, fmt.Sprintf("detected_at older than the max backdate window (%s)", h.maxBackdate), http.StatusBadRequest)
		return
	}
	if req.AffectedCount < 0 {
		http.Error(w, "affected_count must be >= 0", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(req.DataCategories) == "" {
		http.Error(w, "data_categories is required (an Art.33 notice must state the affected data categories)", http.StatusBadRequest)
		return
	}

	deadline := detectedAt.Add(gbf.NotificationDeadline)

	// Emit the breach-opened anchor FIRST — the durable record a future consumer
	// replays to rebuild the monitor. If we can't even record it, fail loudly
	// rather than silently losing a breach.
	//
	// At-least-once: a caller that retries after an "emit-failed-retry" response
	// re-emits this opened anchor, so consumers MUST dedup on incident_id (the
	// anchor stream is keyed, idempotent-by-incident_id — standard for the
	// outbox/publisher event backbone). deadline below is the SINGLE formula
	// detectedAt + gbf.NotificationDeadline — identical to rec.Deadline from
	// Flow.Open (asserted in the handler test) so the anchor + the monitored
	// record never diverge.
	opened := incidents.NewGDPRBreachOpenedV1(req.IncidentID, detectedAt, deadline, req.DataCategories, req.AffectedCount)
	if err := h.emitter.EmitBreachOpened(r.Context(), opened); err != nil {
		http.Error(w, "failed to record breach: "+err.Error(), http.StatusInternalServerError)
		return
	}

	// Open the flow → composes + emits the DPO-notice OBLIGATION via emitNotifier.
	notifier := &emitNotifier{emitter: h.emitter, incidentID: req.IncidentID, deadline: deadline}
	flow, ferr := gbf.New(notifier, h.now)
	if ferr != nil {
		http.Error(w, "internal: "+ferr.Error(), http.StatusInternalServerError)
		return
	}
	rec, openErr := flow.Open(r.Context(), req.IncidentID, detectedAt, req.DataCategories, req.AffectedCount)

	// The breach IS open (the clock has started) regardless of obligation-emit
	// success — track it for deadline monitoring.
	h.monitor.Track(rec)

	resp := breachResponse{
		IncidentID: rec.IncidentID,
		DetectedAt: detectedAt.UTC().Format(time.RFC3339),
		Deadline:   deadline.UTC().Format(time.RFC3339),
		DPONotice:  "obligation-emitted-pending-delivery",
	}
	if openErr != nil {
		resp.DPONotice = "emit-failed-retry"
		resp.Warning = openErr.Error()
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(resp)
}
