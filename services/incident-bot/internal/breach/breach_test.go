package breach

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
	gbf "github.com/loreweave/foundation/services/incident-bot/internal/gdpr_breach_flow"
)

type fakeEmitter struct {
	mu         sync.Mutex
	opened     []incidents.GDPRBreachOpenedV1
	notice     []incidents.GDPRDPONoticeRequiredV1
	deadline   []incidents.GDPRBreachDeadlineV1
	failOpened bool
	failNotice bool
}

func (f *fakeEmitter) EmitBreachOpened(_ context.Context, ev incidents.GDPRBreachOpenedV1) error {
	if f.failOpened {
		return errors.New("opened boom")
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	f.opened = append(f.opened, ev)
	return nil
}

func (f *fakeEmitter) EmitDPONoticeRequired(_ context.Context, ev incidents.GDPRDPONoticeRequiredV1) error {
	if f.failNotice {
		return errors.New("notice boom")
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	f.notice = append(f.notice, ev)
	return nil
}

func (f *fakeEmitter) EmitBreachDeadline(_ context.Context, ev incidents.GDPRBreachDeadlineV1) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.deadline = append(f.deadline, ev)
	return nil
}

const tok = "s3cr3t-internal-token"

func doReq(t *testing.T, h *Handler, header, body string) *httptest.ResponseRecorder {
	t.Helper()
	r := httptest.NewRequest(http.MethodPost, "/internal/breach", strings.NewReader(body))
	if header != "" {
		r.Header.Set("X-Internal-Token", header)
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}

func fixedNow(at time.Time) func() time.Time { return func() time.Time { return at } }

func TestHandler_Auth(t *testing.T) {
	now := time.Date(2026, 5, 31, 12, 0, 0, 0, time.UTC)
	body := `{"incident_id":"INC-1","detected_at":"2026-05-31T11:00:00Z","data_categories":"email","affected_count":3}`

	// Token unset → fail-closed 503.
	disabled := NewHandler(&fakeEmitter{}, NewMonitor(&fakeEmitter{}, fixedNow(now), time.Minute), fixedNow(now), "", 0)
	if w := doReq(t, disabled, tok, body); w.Code != http.StatusServiceUnavailable {
		t.Fatalf("unset token must disable intake (503), got %d", w.Code)
	}
	h := NewHandler(&fakeEmitter{}, NewMonitor(&fakeEmitter{}, fixedNow(now), time.Minute), fixedNow(now), tok, 0)
	if w := doReq(t, h, "wrong", body); w.Code != http.StatusUnauthorized {
		t.Fatalf("wrong token must be 401, got %d", w.Code)
	}
	if w := doReq(t, h, "", body); w.Code != http.StatusUnauthorized {
		t.Fatalf("missing token must be 401, got %d", w.Code)
	}
}

func TestHandler_AnchorClamp(t *testing.T) {
	now := time.Date(2026, 5, 31, 12, 0, 0, 0, time.UTC)
	h := NewHandler(&fakeEmitter{}, NewMonitor(&fakeEmitter{}, fixedNow(now), time.Minute), fixedNow(now), tok, 0)

	// Future anchor → 400 (can't backdate the future).
	future := `{"incident_id":"INC-1","detected_at":"2026-05-31T13:00:00Z","data_categories":"email","affected_count":1}`
	if w := doReq(t, h, tok, future); w.Code != http.StatusBadRequest {
		t.Fatalf("future detected_at must be 400, got %d", w.Code)
	}
	// Older than 7d → 400 (no backdating to instant-missed).
	old := `{"incident_id":"INC-1","detected_at":"2026-05-20T12:00:00Z","data_categories":"email","affected_count":1}`
	if w := doReq(t, h, tok, old); w.Code != http.StatusBadRequest {
		t.Fatalf("over-backdated detected_at must be 400, got %d", w.Code)
	}
}

func TestHandler_ValidBreach_EmitsAndTracks(t *testing.T) {
	now := time.Date(2026, 5, 31, 12, 0, 0, 0, time.UTC)
	em := &fakeEmitter{}
	mon := NewMonitor(em, fixedNow(now), time.Minute)
	h := NewHandler(em, mon, fixedNow(now), tok, 0)
	body := `{"incident_id":"INC-9","detected_at":"2026-05-31T11:00:00Z","data_categories":"email,display_name","affected_count":42}`

	w := doReq(t, h, tok, body)
	if w.Code != http.StatusOK {
		t.Fatalf("valid breach must be 200, got %d (%s)", w.Code, w.Body.String())
	}
	var resp breachResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode resp: %v", err)
	}
	if resp.DPONotice != "obligation-emitted-pending-delivery" {
		t.Errorf("dpo_notice must say obligation-emitted (not delivered), got %q", resp.DPONotice)
	}
	if len(em.opened) != 1 || em.opened[0].IncidentID != "INC-9" {
		t.Errorf("expected 1 BreachOpened for INC-9, got %+v", em.opened)
	}
	if len(em.notice) != 1 || em.notice[0].IncidentID != "INC-9" {
		t.Errorf("expected 1 DPONoticeRequired for INC-9, got %+v", em.notice)
	}
	// Deadline = detected + 72h.
	wantDeadline := time.Date(2026, 6, 3, 11, 0, 0, 0, time.UTC)
	if !em.opened[0].Deadline.Equal(wantDeadline) {
		t.Errorf("deadline = %s, want %s", em.opened[0].Deadline, wantDeadline)
	}
	// WARN2: the opened anchor's deadline + the DPO-notice obligation's deadline
	// must agree (single formula) so the replay anchor + the obligation never
	// diverge from the monitored record.
	if !em.notice[0].Deadline.Equal(wantDeadline) {
		t.Errorf("notice deadline = %s, want %s (must equal opened deadline)", em.notice[0].Deadline, wantDeadline)
	}
	if mon.OpenCount() != 1 {
		t.Errorf("monitor should track 1 breach, got %d", mon.OpenCount())
	}
}

func TestHandler_LateDiscovery_BornMissed(t *testing.T) {
	// A breach discovered late (detected_at 5d ago — within the 7d clamp) is
	// born past its 72h deadline. It must be ACCEPTED + recorded, and the
	// monitor must flag it "missed" on the first tick + prune it (Art.33 late
	// discovery must still be recorded, not rejected).
	now := time.Date(2026, 5, 31, 12, 0, 0, 0, time.UTC)
	em := &fakeEmitter{}
	mon := NewMonitor(em, fixedNow(now), time.Minute)
	h := NewHandler(em, mon, fixedNow(now), tok, 0)
	det := now.Add(-5 * 24 * time.Hour)
	body := `{"incident_id":"INC-LATE","detected_at":"` + det.Format(time.RFC3339) + `","data_categories":"email","affected_count":1}`

	if w := doReq(t, h, tok, body); w.Code != http.StatusOK {
		t.Fatalf("late-discovery breach must be accepted (200), got %d (%s)", w.Code, w.Body.String())
	}
	if mon.OpenCount() != 1 {
		t.Fatalf("breach should be tracked, got %d", mon.OpenCount())
	}
	mon.tick(context.Background()) // deadline already passed → missed + prune
	if len(em.deadline) != 1 || em.deadline[0].State != incidents.BreachDeadlineMissed {
		t.Fatalf("born-missed breach must emit 'missed' on first tick, got %+v", em.deadline)
	}
	if mon.OpenCount() != 0 {
		t.Errorf("born-missed breach must be pruned after the missed emit, got %d", mon.OpenCount())
	}
}

func TestHandler_EmptyDataCategories_Rejected(t *testing.T) {
	now := time.Date(2026, 5, 31, 12, 0, 0, 0, time.UTC)
	h := NewHandler(&fakeEmitter{}, NewMonitor(&fakeEmitter{}, fixedNow(now), time.Minute), fixedNow(now), tok, 0)
	body := `{"incident_id":"INC-1","detected_at":"2026-05-31T11:00:00Z","data_categories":"  ","affected_count":1}`
	if w := doReq(t, h, tok, body); w.Code != http.StatusBadRequest {
		t.Fatalf("empty data_categories must be 400, got %d", w.Code)
	}
}

func TestHandler_NoticeEmitFails_RetainsBreach(t *testing.T) {
	now := time.Date(2026, 5, 31, 12, 0, 0, 0, time.UTC)
	em := &fakeEmitter{failNotice: true} // DPONoticeRequired emit fails
	mon := NewMonitor(em, fixedNow(now), time.Minute)
	h := NewHandler(em, mon, fixedNow(now), tok, 0)
	body := `{"incident_id":"INC-7","detected_at":"2026-05-31T11:00:00Z","data_categories":"email","affected_count":1}`

	w := doReq(t, h, tok, body)
	if w.Code != http.StatusOK {
		t.Fatalf("notice-emit failure must still 200 (breach recorded), got %d", w.Code)
	}
	var resp breachResponse
	_ = json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.DPONotice != "emit-failed-retry" {
		t.Errorf("failed notice emit must report emit-failed-retry, got %q", resp.DPONotice)
	}
	if len(em.opened) != 1 { // the breach IS recorded
		t.Errorf("breach-opened must be emitted even if notice fails, got %d", len(em.opened))
	}
	if mon.OpenCount() != 1 { // and tracked
		t.Errorf("breach must be tracked even if notice fails, got %d", mon.OpenCount())
	}
}

func TestHandler_BreachOpenedEmitFails_500(t *testing.T) {
	now := time.Date(2026, 5, 31, 12, 0, 0, 0, time.UTC)
	em := &fakeEmitter{failOpened: true}
	h := NewHandler(em, NewMonitor(em, fixedNow(now), time.Minute), fixedNow(now), tok, 0)
	body := `{"incident_id":"INC-5","detected_at":"2026-05-31T11:00:00Z","data_categories":"email","affected_count":1}`
	if w := doReq(t, h, tok, body); w.Code != http.StatusInternalServerError {
		t.Fatalf("unrecordable breach must 500, got %d", w.Code)
	}
}

func TestMonitor_OncePerState(t *testing.T) {
	det := time.Date(2026, 5, 31, 0, 0, 0, 0, time.UTC)
	em := &fakeEmitter{}
	var nowVal time.Time
	m := NewMonitor(em, func() time.Time { return nowVal }, time.Minute)
	m.Track(&gbf.BreachRecord{IncidentID: "INC-1", DetectedAt: det, Deadline: det.Add(72 * time.Hour)})

	nowVal = det.Add(1 * time.Hour) // 71h remaining > 12h
	m.tick(context.Background())
	if len(em.deadline) != 0 {
		t.Fatalf("no alert when >12h remaining, got %d", len(em.deadline))
	}
	nowVal = det.Add(61 * time.Hour) // 11h remaining ≤12h → approaching
	m.tick(context.Background())
	m.tick(context.Background()) // dedup: still once
	if len(em.deadline) != 1 || em.deadline[0].State != incidents.BreachDeadlineApproaching {
		t.Fatalf("expected exactly 1 approaching, got %+v", em.deadline)
	}
	nowVal = det.Add(73 * time.Hour) // -1h → missed
	m.tick(context.Background())
	m.tick(context.Background()) // dedup + prune means the 2nd tick is a no-op
	if len(em.deadline) != 2 || em.deadline[1].State != incidents.BreachDeadlineMissed {
		t.Fatalf("expected approaching then exactly 1 missed, got %+v", em.deadline)
	}
	// BLOCK fix: a "missed" (terminal) breach is pruned from the open set.
	if m.OpenCount() != 0 {
		t.Errorf("missed breach must be pruned, OpenCount=%d", m.OpenCount())
	}
}

func TestEmitNotifier_EmitsObligation(t *testing.T) {
	em := &fakeEmitter{}
	dl := time.Now().Add(72 * time.Hour)
	n := &emitNotifier{emitter: em, incidentID: "INC-3", deadline: dl}
	if err := n.NotifyDPO(context.Background(), "subj", "body"); err != nil {
		t.Fatalf("NotifyDPO: %v", err)
	}
	if len(em.notice) != 1 || em.notice[0].IncidentID != "INC-3" || em.notice[0].Subject != "subj" {
		t.Fatalf("expected 1 obligation event for INC-3, got %+v", em.notice)
	}
}
