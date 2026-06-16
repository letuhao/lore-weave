package meta

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"

	"github.com/google/uuid"
)

// fakeClock returns a monotonically-increasing unix-nanos value per call.
type fakeClock struct {
	cur atomic.Int64
}

func newFakeClock(start int64) *fakeClock {
	c := &fakeClock{}
	c.cur.Store(start)
	return c
}
func (c *fakeClock) NowUnixNano() int64 { return c.cur.Add(1) }

// fakeUUIDGen returns deterministic UUIDs (v4-shaped) keyed by an internal counter.
type fakeUUIDGen struct{ n atomic.Uint64 }

func (g *fakeUUIDGen) New() uuid.UUID {
	x := g.n.Add(1)
	var u uuid.UUID
	for i := 0; i < 8; i++ {
		u[15-i] = byte(x >> (i * 8))
	}
	return u
}

// fakeExec captures a single SQL exec call.
type fakeExec struct {
	Query string
	Args  []any
}

// fakeTx is a Tx that records exec calls + lets tests inject rowsAffected/err per call.
type fakeTx struct {
	mu        sync.Mutex
	execs     []fakeExec
	// programmable per-call response: queue of (rows, err); falls back to (1, nil).
	responses []txResponse
	commits   int
	rollbacks int
	committed bool
}

type txResponse struct {
	rows int64
	err  error
}

func (t *fakeTx) Exec(ctx context.Context, q string, args ...any) (int64, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.execs = append(t.execs, fakeExec{Query: q, Args: args})
	if len(t.responses) > 0 {
		r := t.responses[0]
		t.responses = t.responses[1:]
		return r.rows, r.err
	}
	return 1, nil
}

// fakeDB hands out a single fakeTx per BeginTx (recorded in Txs).
type fakeDB struct {
	mu        sync.Mutex
	Txs       []*fakeTx
	beginErr  error
	commitErr error
	rollbackErr error
}

func (d *fakeDB) BeginTx(ctx context.Context) (Tx, func() error, func() error, error) {
	if d.beginErr != nil {
		return nil, nil, nil, d.beginErr
	}
	tx := &fakeTx{}
	d.mu.Lock()
	d.Txs = append(d.Txs, tx)
	d.mu.Unlock()
	commit := func() error {
		tx.mu.Lock()
		defer tx.mu.Unlock()
		tx.commits++
		tx.committed = true
		return d.commitErr
	}
	rollback := func() error {
		tx.mu.Lock()
		defer tx.mu.Unlock()
		tx.rollbacks++
		return d.rollbackErr
	}
	return tx, commit, rollback, nil
}

// staticAllowlist is a minimal Allowlist for tests.
type staticAllowlist struct {
	tables map[string]struct{}
	events map[string]map[MetaWriteOp]string
}

func newStaticAllowlist(tables []string, events map[string]map[MetaWriteOp]string) *staticAllowlist {
	a := &staticAllowlist{
		tables: make(map[string]struct{}, len(tables)),
		events: events,
	}
	for _, t := range tables {
		a.tables[t] = struct{}{}
	}
	if a.events == nil {
		a.events = make(map[string]map[MetaWriteOp]string)
	}
	return a
}

func (a *staticAllowlist) AllowsTable(t string) bool { _, ok := a.tables[t]; return ok }
func (a *staticAllowlist) EmitsEvent(t string, op MetaWriteOp) (string, bool) {
	ops, ok := a.events[t]
	if !ok {
		return "", false
	}
	n, ok := ops[op]
	return n, ok
}
func (a *staticAllowlist) Tables() []string {
	out := make([]string, 0, len(a.tables))
	for t := range a.tables {
		out = append(out, t)
	}
	return out
}

// captureOutbox records every Append call.
type captureOutbox struct {
	mu     sync.Mutex
	events []OutboxEvent
}

func (c *captureOutbox) Append(_ context.Context, _ Tx, ev OutboxEvent) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.events = append(c.events, ev)
	return nil
}

func newDefaultTestCfg(allow Allowlist, transitions *TransitionGraph) (*Config, *fakeDB, *captureOutbox) {
	db := &fakeDB{}
	out := &captureOutbox{}
	cfg := &Config{
		DB:           db,
		Allowlist:    allow,
		Transitions:  transitions,
		Outbox:       out,
		QueryBuilder: PostgresQueryBuilder{},
		Clock:        newFakeClock(1_700_000_000_000_000_000),
		UUIDGen:      &fakeUUIDGen{},
	}
	return cfg, db, out
}

// helper: error contains check (avoids importing strings in many test files).
func errorContains(err error, sub string) bool {
	if err == nil {
		return false
	}
	return fmt.Sprintf("%v", err) != "" && contains(err.Error(), sub)
}

func contains(s, sub string) bool {
	if sub == "" {
		return true
	}
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
