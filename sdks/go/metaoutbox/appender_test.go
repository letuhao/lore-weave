package metaoutbox

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
)

// fakeTx captures the Exec call so tests can assert the rendered SQL + args
// without a database. Mirrors the meta.Tx interface (Exec only).
type fakeTx struct {
	query string
	args  []any
	err   error
	calls int
}

func (f *fakeTx) Exec(_ context.Context, query string, args ...any) (int64, error) {
	f.calls++
	f.query = query
	f.args = args
	if f.err != nil {
		return 0, f.err
	}
	return 1, nil
}

func sampleEvent() meta.OutboxEvent {
	return meta.OutboxEvent{
		EventID:     uuid.MustParse("11111111-1111-1111-1111-111111111111"),
		EventName:   "user.consent.revoked",
		AggregateID: "user-42",
		Payload:     map[string]any{"table": "user_consent_ledger", "operation": "UPDATE"},
		RecordedAt:  1717113600000000000,
	}
}

func TestAppend_MetaOnlyEvent_NullTopic(t *testing.T) {
	tx := &fakeTx{}
	a := New(map[string]string{"user.erased": "xreality.user.erased"}) // no mapping for consent.revoked
	if err := a.Append(context.Background(), tx, sampleEvent()); err != nil {
		t.Fatalf("Append: %v", err)
	}
	if tx.calls != 1 {
		t.Fatalf("want 1 Exec, got %d", tx.calls)
	}
	if len(tx.args) != 6 {
		t.Fatalf("want 6 args, got %d: %#v", len(tx.args), tx.args)
	}
	// arg[4] is xreality_topic — must be nil (SQL NULL) for a meta-only event.
	if tx.args[4] != nil {
		t.Errorf("meta-only event must have nil xreality_topic, got %#v", tx.args[4])
	}
	// arg[3] is payload JSON — must be a valid object string.
	js, ok := tx.args[3].(string)
	if !ok {
		t.Fatalf("payload arg must be string, got %T", tx.args[3])
	}
	var obj map[string]any
	if err := json.Unmarshal([]byte(js), &obj); err != nil {
		t.Fatalf("payload not valid json: %v", err)
	}
	if obj["table"] != "user_consent_ledger" {
		t.Errorf("payload table mismatch: %#v", obj)
	}
	// arg[5] is recorded_at_nanos.
	if tx.args[5].(int64) != 1717113600000000000 {
		t.Errorf("recorded_at_nanos mismatch: %#v", tx.args[5])
	}
}

func TestAppend_CrossRealityEvent_StampsTopic(t *testing.T) {
	tx := &fakeTx{}
	a := New(map[string]string{"user.erased": "xreality.user.erased"})
	ev := sampleEvent()
	ev.EventName = "user.erased"
	if err := a.Append(context.Background(), tx, ev); err != nil {
		t.Fatalf("Append: %v", err)
	}
	if tx.args[4] != "xreality.user.erased" {
		t.Errorf("cross-reality event must stamp topic, got %#v", tx.args[4])
	}
}

func TestAppend_NilPayload_NormalisedToObject(t *testing.T) {
	tx := &fakeTx{}
	a := New(nil)
	ev := sampleEvent()
	ev.Payload = nil
	if err := a.Append(context.Background(), tx, ev); err != nil {
		t.Fatalf("Append: %v", err)
	}
	// nil payload must marshal to "{}" (an object), NOT "null", so the
	// jsonb_typeof = 'object' CHECK holds.
	if tx.args[3].(string) != "{}" {
		t.Errorf("nil payload must become {}, got %q", tx.args[3])
	}
}

func TestAppend_Validation(t *testing.T) {
	a := New(nil)
	ctx := context.Background()
	cases := []struct {
		name string
		ev   meta.OutboxEvent
		tx   meta.Tx
	}{
		{"nil tx", sampleEvent(), nil},
		{"zero event_id", func() meta.OutboxEvent { e := sampleEvent(); e.EventID = uuid.Nil; return e }(), &fakeTx{}},
		{"empty event_name", func() meta.OutboxEvent { e := sampleEvent(); e.EventName = ""; return e }(), &fakeTx{}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if err := a.Append(ctx, c.tx, c.ev); err == nil {
				t.Fatalf("want validation error for %s, got nil", c.name)
			}
		})
	}
}

func TestAppend_PropagatesExecError(t *testing.T) {
	sentinel := errors.New("boom")
	tx := &fakeTx{err: sentinel}
	a := New(nil)
	err := a.Append(context.Background(), tx, sampleEvent())
	if err == nil || !errors.Is(err, sentinel) {
		t.Fatalf("want wrapped exec error, got %v", err)
	}
}
