package handler

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
	"github.com/loreweave/foundation/services/breach-notifier/internal/consume"
	"github.com/loreweave/foundation/services/breach-notifier/internal/deliver"
	"github.com/loreweave/foundation/services/breach-notifier/internal/store"
)

type fakeNotifier struct {
	ch    string
	err   error
	calls int
}

func (f *fakeNotifier) Deliver(context.Context, deliver.DPONotice) (string, error) {
	f.calls++
	return f.ch, f.err
}

type fakeStore struct {
	delivered map[string]bool
	recorded  []store.Delivery
	checkErr  error
}

func (f *fakeStore) AlreadyDelivered(_ context.Context, id string) (bool, error) {
	if f.checkErr != nil {
		return false, f.checkErr
	}
	return f.delivered[id], nil
}
func (f *fakeStore) RecordAttempt(_ context.Context, d store.Delivery, _ time.Time) error {
	f.recorded = append(f.recorded, d)
	if d.Status == store.StatusDelivered {
		if f.delivered == nil {
			f.delivered = map[string]bool{}
		}
		f.delivered[d.IncidentID] = true
	}
	return nil
}

func noticeMsg(t *testing.T, id string) consume.Message {
	t.Helper()
	ev := incidents.NewGDPRDPONoticeRequiredV1(id, "subj", "body", time.Now().Add(72*time.Hour))
	b, _ := json.Marshal(ev)
	return consume.Message{ID: "m-" + id, Fields: map[string]any{
		"event_type": ev.Type, "incident_id": id, "payload": string(b),
	}}
}

func TestHandle_NonNoticeIgnored(t *testing.T) {
	h, _ := New(&fakeNotifier{ch: "log"}, &fakeStore{}, time.Now, nil)
	o, _ := h.Handle(context.Background(), consume.Message{Fields: map[string]any{"event_type": incidents.TypeGDPRBreachOpenedV1}})
	if o != consume.OutcomeIgnored {
		t.Errorf("opened event should be ignored, got %v", o)
	}
}

func TestHandle_DeliversAndRecords(t *testing.T) {
	fn := &fakeNotifier{ch: "log"}
	fs := &fakeStore{}
	h, _ := New(fn, fs, time.Now, nil)
	o, err := h.Handle(context.Background(), noticeMsg(t, "a"))
	if err != nil || o != consume.OutcomeDelivered {
		t.Fatalf("want delivered, got %v %v", o, err)
	}
	if fn.calls != 1 {
		t.Errorf("notifier should be called once, got %d", fn.calls)
	}
	if len(fs.recorded) != 1 || fs.recorded[0].Status != store.StatusDelivered {
		t.Errorf("should record delivered: %+v", fs.recorded)
	}
}

func TestHandle_Idempotent(t *testing.T) {
	fn := &fakeNotifier{ch: "log"}
	fs := &fakeStore{delivered: map[string]bool{"a": true}}
	h, _ := New(fn, fs, time.Now, nil)
	o, _ := h.Handle(context.Background(), noticeMsg(t, "a"))
	if o != consume.OutcomeSkippedDuplicate {
		t.Errorf("already-delivered should skip, got %v", o)
	}
	if fn.calls != 0 {
		t.Errorf("must NOT re-deliver an already-delivered notice")
	}
}

func TestHandle_DeliveryFailRecordsFailedNoConfirm(t *testing.T) {
	fn := &fakeNotifier{ch: "log", err: errors.New("slack down")}
	fs := &fakeStore{}
	h, _ := New(fn, fs, time.Now, nil)
	o, err := h.Handle(context.Background(), noticeMsg(t, "a"))
	if o != consume.OutcomeFailed || err == nil {
		t.Fatalf("delivery fail should be OutcomeFailed+err, got %v %v", o, err)
	}
	if len(fs.recorded) != 1 || fs.recorded[0].Status != store.StatusFailed {
		t.Errorf("should record a failed attempt: %+v", fs.recorded)
	}
	if ok, _ := fs.AlreadyDelivered(context.Background(), "a"); ok {
		t.Errorf("a failed delivery must NOT be confirmed (so it retries)")
	}
}

func TestHandle_StoreCheckErrorRetries(t *testing.T) {
	h, _ := New(&fakeNotifier{ch: "log"}, &fakeStore{checkErr: errors.New("db down")}, time.Now, nil)
	o, err := h.Handle(context.Background(), noticeMsg(t, "a"))
	if o != consume.OutcomeFailed || err == nil {
		t.Errorf("store-check error should retry (Failed), got %v %v", o, err)
	}
}

func TestHandle_MalformedDropped(t *testing.T) {
	fn := &fakeNotifier{ch: "log"}
	h, _ := New(fn, &fakeStore{}, time.Now, nil)
	o, _ := h.Handle(context.Background(), consume.Message{Fields: map[string]any{
		"event_type": incidents.TypeGDPRDPONoticeRequiredV1, "payload": "{bad",
	}})
	if o != consume.OutcomeMalformed {
		t.Errorf("malformed notice should be OutcomeMalformed (acked + counted, no redelivery loop), got %v", o)
	}
	if fn.calls != 0 {
		t.Errorf("malformed notice must not reach the notifier")
	}
}

func TestHandle_MissingBodyRejected(t *testing.T) {
	// The contract Validate rejects an empty body → malformed (M4: consumer acceptance
	// stays aligned with the contract's own validator, not a re-implemented subset).
	ev := incidents.NewGDPRDPONoticeRequiredV1("a", "subj", "", time.Now().Add(72*time.Hour))
	b, _ := json.Marshal(ev)
	h, _ := New(&fakeNotifier{ch: "log"}, &fakeStore{}, time.Now, nil)
	o, _ := h.Handle(context.Background(), consume.Message{Fields: map[string]any{
		"event_type": incidents.TypeGDPRDPONoticeRequiredV1, "payload": string(b),
	}})
	if o != consume.OutcomeMalformed {
		t.Errorf("a notice failing contract Validate (empty body) should be malformed, got %v", o)
	}
}

func TestNew_NilGuards(t *testing.T) {
	if _, err := New(nil, &fakeStore{}, nil, nil); err == nil {
		t.Errorf("nil notifier should error")
	}
	if _, err := New(&fakeNotifier{}, nil, nil, nil); err == nil {
		t.Errorf("nil store should error")
	}
}
