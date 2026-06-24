package drain

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/loreweave/foundation/services/publisher/pkg/retry"
)

// fakeBatch records Mark* calls + commit/rollback.
type fakeBatch struct {
	rows         []Row
	published    []string
	retried      []string
	deadLettered []string
	committed    bool
	rolledBack   bool
	markErr      error
}

func (b *fakeBatch) Rows() []Row { return b.rows }
func (b *fakeBatch) MarkPublished(_ context.Context, id string) error {
	if b.markErr != nil {
		return b.markErr
	}
	b.published = append(b.published, id)
	return nil
}
func (b *fakeBatch) MarkRetry(_ context.Context, id string, _ int, _ string) error {
	b.retried = append(b.retried, id)
	return nil
}
func (b *fakeBatch) MarkDeadLetter(_ context.Context, id string, _ int, _ string) error {
	b.deadLettered = append(b.deadLettered, id)
	return nil
}
func (b *fakeBatch) Commit(_ context.Context) error   { b.committed = true; return nil }
func (b *fakeBatch) Rollback(_ context.Context) error { b.rolledBack = true; return nil }

type fakeSource struct {
	batch    *fakeBatch
	beginErr error
}

func (s *fakeSource) Begin(_ context.Context, _ int) (Batch, error) {
	if s.beginErr != nil {
		return nil, s.beginErr
	}
	return s.batch, nil
}

// fakeEmitter records emits + lets tests inject per-stream errors.
type fakeEmitter struct {
	homeEmits     []string
	xrealityEmits []string
	homeErr       error
	xrealityErr   error
}

func (e *fakeEmitter) Emit(_ context.Context, row Row) error {
	if e.homeErr != nil {
		return e.homeErr
	}
	e.homeEmits = append(e.homeEmits, row.EventID)
	return nil
}
func (e *fakeEmitter) EmitXReality(_ context.Context, row Row) error {
	if e.xrealityErr != nil {
		return e.xrealityErr
	}
	e.xrealityEmits = append(e.xrealityEmits, row.EventID)
	return nil
}

func testPolicy() retry.Policy {
	return retry.Policy{MaxAttempts: 3, BaseBackoff: time.Millisecond, MaxBackoff: time.Second}
}

func newLoop(t *testing.T, src Source, em Emitter) *Loop {
	t.Helper()
	l, err := New(Config{Source: src, Emitter: em, Policy: testPolicy()})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return l
}

func TestRun_MetaOnlyRow_PublishesHomeOnly(t *testing.T) {
	batch := &fakeBatch{rows: []Row{{EventID: "e1", EventName: "user.consent.revoked"}}}
	em := &fakeEmitter{}
	l := newLoop(t, &fakeSource{batch: batch}, em)

	stats, err := l.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if stats.Published != 1 || stats.XRealityOK != 0 {
		t.Errorf("stats: %+v", stats)
	}
	if len(em.homeEmits) != 1 || len(em.xrealityEmits) != 0 {
		t.Errorf("home=%v xreality=%v", em.homeEmits, em.xrealityEmits)
	}
	if !batch.committed {
		t.Error("batch must commit")
	}
}

func TestRun_CrossRealityRow_PublishesBothStreams(t *testing.T) {
	batch := &fakeBatch{rows: []Row{{EventID: "e2", EventName: "user.erased", XRealityTopic: "xreality.user.erased"}}}
	em := &fakeEmitter{}
	l := newLoop(t, &fakeSource{batch: batch}, em)

	stats, err := l.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if stats.Published != 1 || stats.XRealityOK != 1 {
		t.Errorf("stats: %+v", stats)
	}
	if len(em.homeEmits) != 1 || len(em.xrealityEmits) != 1 {
		t.Errorf("home=%v xreality=%v", em.homeEmits, em.xrealityEmits)
	}
}

func TestRun_XRealityFailure_RetriesWholeRow_NotPublished(t *testing.T) {
	// Home XADD ok, xreality XADD fails → both-or-neither: the row must NOT be
	// marked published; it retries (re-emits both next tick, consumers dedupe).
	batch := &fakeBatch{rows: []Row{{EventID: "e3", EventName: "user.erased", XRealityTopic: "xreality.user.erased", Attempts: 0}}}
	em := &fakeEmitter{xrealityErr: errors.New("redis down")}
	l := newLoop(t, &fakeSource{batch: batch}, em)

	stats, err := l.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if stats.Published != 0 || stats.Retried != 1 {
		t.Errorf("xreality failure must retry, not publish: %+v", stats)
	}
	if len(batch.published) != 0 || len(batch.retried) != 1 {
		t.Errorf("published=%v retried=%v", batch.published, batch.retried)
	}
}

func TestRun_HomeFailureAtMaxAttempts_DeadLetters(t *testing.T) {
	// Attempts=2, MaxAttempts=3 → next=3 >= max → dead-letter.
	batch := &fakeBatch{rows: []Row{{EventID: "e4", EventName: "x", Attempts: 2}}}
	em := &fakeEmitter{homeErr: errors.New("redis down")}
	l := newLoop(t, &fakeSource{batch: batch}, em)

	stats, err := l.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if stats.DeadLettered != 1 {
		t.Errorf("want dead-letter at max attempts: %+v", stats)
	}
}

func TestRun_HomeFailureBelowMax_Retries(t *testing.T) {
	batch := &fakeBatch{rows: []Row{{EventID: "e5", EventName: "x", Attempts: 0}}}
	em := &fakeEmitter{homeErr: errors.New("redis blip")}
	l := newLoop(t, &fakeSource{batch: batch}, em)

	stats, err := l.Run(context.Background())
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if stats.Retried != 1 || stats.Published != 0 {
		t.Errorf("want retry below max: %+v", stats)
	}
	// xreality must NOT be attempted when the home emit failed.
	if len(em.xrealityEmits) != 0 {
		t.Errorf("xreality emitted despite home failure: %v", em.xrealityEmits)
	}
}

func TestRun_MarkErrorRollsBack(t *testing.T) {
	batch := &fakeBatch{rows: []Row{{EventID: "e6", EventName: "x"}}, markErr: errors.New("db lost")}
	em := &fakeEmitter{}
	l := newLoop(t, &fakeSource{batch: batch}, em)

	_, err := l.Run(context.Background())
	if err == nil {
		t.Fatal("want error when Mark fails")
	}
	if !batch.rolledBack {
		t.Error("batch must roll back on Mark error")
	}
	if batch.committed {
		t.Error("batch must NOT commit on Mark error")
	}
}

func TestRun_BeginError(t *testing.T) {
	l := newLoop(t, &fakeSource{beginErr: errors.New("no conn")}, &fakeEmitter{})
	if _, err := l.Run(context.Background()); err == nil {
		t.Fatal("want begin error")
	}
}

func TestNew_Validation(t *testing.T) {
	if _, err := New(Config{Emitter: &fakeEmitter{}, Policy: testPolicy()}); err == nil {
		t.Error("want error on nil Source")
	}
	if _, err := New(Config{Source: &fakeSource{}, Policy: testPolicy()}); err == nil {
		t.Error("want error on nil Emitter")
	}
	if _, err := New(Config{Source: &fakeSource{}, Emitter: &fakeEmitter{}, Policy: retry.Policy{}}); err == nil {
		t.Error("want error on invalid Policy")
	}
}
