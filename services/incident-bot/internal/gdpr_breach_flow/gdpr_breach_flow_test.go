package gdpr_breach_flow

import (
	"context"
	"errors"
	"testing"
	"time"
)

type fakeNotifier struct {
	calls int
	err   error
	last  string
}

func (f *fakeNotifier) NotifyDPO(ctx context.Context, subject, body string) error {
	f.calls++
	f.last = body
	return f.err
}

func fixedClock(t time.Time) func() time.Time { return func() time.Time { return t } }

func TestNew_NilDeps(t *testing.T) {
	if _, err := New(nil, time.Now); err == nil {
		t.Error("nil notifier must error")
	}
	if _, err := New(&fakeNotifier{}, nil); err == nil {
		t.Error("nil clock must error")
	}
}

func TestOpen_SendsDPONotice(t *testing.T) {
	n := &fakeNotifier{}
	detected := time.Unix(1700000000, 0).UTC()
	f, _ := New(n, fixedClock(detected))
	rec, err := f.Open(context.Background(), "INC-1", detected, "email,ip", 42)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	if n.calls != 1 {
		t.Errorf("DPO notify calls = %d want 1", n.calls)
	}
	if rec.Deadline != detected.Add(72*time.Hour) {
		t.Errorf("deadline = %v want detected+72h", rec.Deadline)
	}
	if rec.DPONotifiedAt == nil {
		t.Error("DPONotifiedAt should be set on success")
	}
}

func TestOpen_RetainsRecordOnNotifyFailure(t *testing.T) {
	n := &fakeNotifier{err: errors.New("smtp down")}
	detected := time.Unix(1700000000, 0).UTC()
	f, _ := New(n, fixedClock(detected))
	rec, err := f.Open(context.Background(), "INC-1", detected, "email", 1)
	if err == nil {
		t.Error("notify failure must return error")
	}
	if rec == nil {
		t.Fatal("record must be retained for forensics even on notify failure")
	}
	if rec.DPONotifiedAt != nil {
		t.Error("DPONotifiedAt must be nil when notify failed")
	}
}

func TestOpen_ValidatesInputs(t *testing.T) {
	f, _ := New(&fakeNotifier{}, time.Now)
	if _, err := f.Open(context.Background(), "", time.Now(), "x", 1); err == nil {
		t.Error("empty incident id must error")
	}
	if _, err := f.Open(context.Background(), "INC-1", time.Time{}, "x", 1); err == nil {
		t.Error("zero detected_at must error")
	}
}

func TestDeadlineMath(t *testing.T) {
	detected := time.Unix(1700000000, 0).UTC()
	rec := &BreachRecord{IncidentID: "INC-1", DetectedAt: detected, Deadline: detected.Add(72 * time.Hour)}

	// 1h in: ~71h remaining, not approaching, not missed.
	f1, _ := New(&fakeNotifier{}, fixedClock(detected.Add(time.Hour)))
	if f1.IsApproachingDeadline(rec) {
		t.Error("1h in should not be approaching")
	}
	if f1.IsDeadlineMissed(rec) {
		t.Error("1h in should not be missed")
	}

	// 65h in: 7h remaining → approaching (<=12h).
	f2, _ := New(&fakeNotifier{}, fixedClock(detected.Add(65*time.Hour)))
	if !f2.IsApproachingDeadline(rec) {
		t.Errorf("65h in should be approaching (rem=%v)", f2.TimeRemaining(rec))
	}

	// 73h in: missed.
	f3, _ := New(&fakeNotifier{}, fixedClock(detected.Add(73*time.Hour)))
	if !f3.IsDeadlineMissed(rec) {
		t.Error("73h in should be missed")
	}
	if f3.IsApproachingDeadline(rec) {
		t.Error("missed deadline is not 'approaching'")
	}
}
