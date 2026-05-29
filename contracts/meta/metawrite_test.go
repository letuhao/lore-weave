package meta

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestMetaWrite_RejectsBadIntent(t *testing.T) {
	cfg, _, _ := newDefaultTestCfg(newStaticAllowlist([]string{"reality_registry"}, nil), nil)

	// empty PK
	_, err := MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:     "reality_registry",
		Operation: OpInsert,
		NewValues: map[string]any{"foo": 1},
		Actor:     Actor{Type: ActorService, ID: "x"},
	})
	if !errors.Is(err, ErrBadIntent) || !strings.Contains(err.Error(), "PK is empty") {
		t.Errorf("want ErrBadIntent PK empty, got %v", err)
	}

	// not-in-allowlist
	_, err = MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:     "not_in_list",
		Operation: OpInsert,
		PK:        map[string]any{"id": "x"},
		NewValues: map[string]any{"foo": 1},
		Actor:     Actor{Type: ActorService, ID: "x"},
	})
	if !errors.Is(err, ErrTableNotAllowlisted) {
		t.Errorf("want ErrTableNotAllowlisted, got %v", err)
	}
}

func TestMetaWrite_InsertEmitsAuditAndOutbox(t *testing.T) {
	allow := newStaticAllowlist(
		[]string{"reality_registry"},
		map[string]map[MetaWriteOp]string{
			"reality_registry": {OpInsert: "reality.created"},
		},
	)
	cfg, db, out := newDefaultTestCfg(allow, nil)

	res, err := MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:     "reality_registry",
		Operation: OpInsert,
		PK:        map[string]any{"reality_id": uuid.New().String()},
		NewValues: map[string]any{
			"db_host":           "pg-shard-0.internal",
			"db_name":           "lw_reality_0",
			"status":            "provisioning",
			"locale":            "en-US",
			"session_max_pcs":   4,
			"session_max_npcs":  6,
			"session_max_total": 10,
			"deploy_cohort":     42,
		},
		Actor: Actor{Type: ActorService, ID: "world-service"},
	})
	if err != nil {
		t.Fatalf("MetaWrite: %v", err)
	}
	if res.RowsAffected != 1 {
		t.Errorf("RowsAffected: got %d want 1", res.RowsAffected)
	}
	if len(db.Txs) != 1 {
		t.Fatalf("expected 1 TX, got %d", len(db.Txs))
	}
	tx := db.Txs[0]
	if !tx.committed {
		t.Errorf("TX not committed")
	}
	// Exec calls: data INSERT (1) + audit INSERT (2) + outbox append (3) — outbox writes through tx
	if len(tx.execs) < 2 {
		t.Errorf("expected ≥2 execs (data + audit), got %d", len(tx.execs))
	}
	// First exec is data INSERT INTO reality_registry
	if !strings.Contains(tx.execs[0].Query, `INSERT INTO "reality_registry"`) {
		t.Errorf("first exec not data insert: %q", tx.execs[0].Query)
	}
	// Second exec is audit INSERT
	if !strings.Contains(tx.execs[1].Query, "INSERT INTO meta_write_audit") {
		t.Errorf("second exec not audit insert: %q", tx.execs[1].Query)
	}
	if len(out.events) != 1 || out.events[0].EventName != "reality.created" {
		t.Errorf("outbox events: %+v", out.events)
	}
}

func TestMetaWrite_NoOutboxWhenAllowlistSilent(t *testing.T) {
	allow := newStaticAllowlist([]string{"publisher_heartbeats"}, nil)
	cfg, _, out := newDefaultTestCfg(allow, nil)

	_, err := MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:     "publisher_heartbeats",
		Operation: OpInsert,
		PK:        map[string]any{"publisher_id": "p1"},
		NewValues: map[string]any{"shard_host": "h1"},
		Actor:     Actor{Type: ActorService, ID: "publisher"},
	})
	if err != nil {
		t.Fatalf("MetaWrite: %v", err)
	}
	if len(out.events) != 0 {
		t.Errorf("expected no outbox emit, got %d", len(out.events))
	}
}

func TestMetaWrite_CASMissReturnsConcurrent(t *testing.T) {
	allow := newStaticAllowlist([]string{"reality_registry"}, nil)
	cfg, db, _ := newDefaultTestCfg(allow, nil)
	cfg.DB = db

	// Pre-program first exec (the data UPDATE) to return 0 rows.
	db.beginErr = nil
	// Need to inject the txResponses BEFORE BeginTx — patch BeginTx wrapper.
	// Simpler: use a setup hook that pushes into the tx after begin. Build
	// a small adapter that pre-queues responses on each new tx.
	dbWithResp := &fakeDBPrequeue{
		queue: [][]txResponse{
			{ // first TX: data UPDATE → 0 rows; audit + outbox never invoked because we return early.
				{rows: 0, err: nil},
			},
		},
	}
	cfg.DB = dbWithResp

	_, err := MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:     "reality_registry",
		Operation: OpUpdate,
		PK:        map[string]any{"reality_id": uuid.New().String()},
		ExpectedBefore: map[string]any{
			"status": "provisioning",
		},
		NewValues: map[string]any{
			"status": "active",
		},
		Actor: Actor{Type: ActorService, ID: "world-service"},
	})
	if !errors.Is(err, ErrConcurrentStateTransition) {
		t.Fatalf("want ErrConcurrentStateTransition, got %v", err)
	}
	if !IsConcurrent(err) {
		t.Errorf("IsConcurrent should return true")
	}
	if !dbWithResp.lastTx.committed && dbWithResp.lastTx.rollbacks == 0 {
		t.Errorf("expected rollback on concurrent miss")
	}
	if dbWithResp.lastTx.committed {
		t.Errorf("TX must NOT be committed on CAS miss")
	}
}

func TestMetaWriteBatch_AllOrNothing(t *testing.T) {
	allow := newStaticAllowlist([]string{"reality_registry", "reality_close_audit"}, nil)
	cfg, _, _ := newDefaultTestCfg(allow, nil)

	// First TX: 1st exec data INSERT ok, 2nd exec audit ok, 3rd exec data INSERT ok,
	// 4th exec audit ok → commit.
	prequeue := &fakeDBPrequeue{queue: [][]txResponse{{
		{rows: 1, err: nil}, // data 1
		{rows: 1, err: nil}, // audit 1
		{rows: 1, err: nil}, // data 2
		{rows: 1, err: nil}, // audit 2
	}}}
	cfg.DB = prequeue

	results, err := MetaWriteBatch(context.Background(), cfg, []MetaWriteIntent{
		{
			Table: "reality_registry", Operation: OpInsert,
			PK:        map[string]any{"reality_id": "11111111-1111-1111-1111-111111111111"},
			NewValues: map[string]any{"db_host": "pg-shard-0.internal", "status": "provisioning"},
			Actor:     Actor{Type: ActorService, ID: "world-service"},
		},
		{
			Table: "reality_close_audit", Operation: OpInsert,
			PK:        map[string]any{"audit_id": "22222222-2222-2222-2222-222222222222"},
			NewValues: map[string]any{"event_type": "close_initiated", "reality_id": "11111111-1111-1111-1111-111111111111"},
			Actor:     Actor{Type: ActorService, ID: "world-service"},
		},
	})
	if err != nil {
		t.Fatalf("MetaWriteBatch: %v", err)
	}
	if len(results) != 2 {
		t.Errorf("results len: got %d want 2", len(results))
	}
	if !prequeue.lastTx.committed {
		t.Errorf("expected commit")
	}
}

func TestMetaWriteBatch_PartialFailureRollsBack(t *testing.T) {
	allow := newStaticAllowlist([]string{"reality_registry", "reality_close_audit"}, nil)
	cfg, _, _ := newDefaultTestCfg(allow, nil)

	// First intent succeeds (data + audit ok). Second intent's data exec
	// returns an error → batch must roll back, no commit.
	prequeue := &fakeDBPrequeue{queue: [][]txResponse{{
		{rows: 1, err: nil}, // data 1 ok
		{rows: 1, err: nil}, // audit 1 ok
		{rows: 0, err: errors.New("disk full")}, // data 2 fails
	}}}
	cfg.DB = prequeue

	_, err := MetaWriteBatch(context.Background(), cfg, []MetaWriteIntent{
		{
			Table: "reality_registry", Operation: OpInsert,
			PK:        map[string]any{"reality_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
			NewValues: map[string]any{"db_host": "pg-shard-0.internal"},
			Actor:     Actor{Type: ActorService, ID: "world-service"},
		},
		{
			Table: "reality_close_audit", Operation: OpInsert,
			PK:        map[string]any{"audit_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"},
			NewValues: map[string]any{"event_type": "close_initiated"},
			Actor:     Actor{Type: ActorService, ID: "world-service"},
		},
	})
	if err == nil || !strings.Contains(err.Error(), "disk full") {
		t.Fatalf("expected disk full error, got %v", err)
	}
	if prequeue.lastTx.committed {
		t.Errorf("TX must NOT be committed on partial failure")
	}
	if prequeue.lastTx.rollbacks == 0 {
		t.Errorf("expected rollback on partial failure")
	}
}

// fakeDBPrequeue lets a test stuff a queue of txResponses onto the next fakeTx
// returned by BeginTx (so the test can assert behavior on specific exec calls
// without racing the library's internal call order).
type fakeDBPrequeue struct {
	queue  [][]txResponse
	lastTx *fakeTx
}

func (d *fakeDBPrequeue) BeginTx(_ context.Context) (Tx, func() error, func() error, error) {
	tx := &fakeTx{}
	if len(d.queue) > 0 {
		tx.responses = d.queue[0]
		d.queue = d.queue[1:]
	}
	d.lastTx = tx
	commit := func() error {
		tx.mu.Lock()
		defer tx.mu.Unlock()
		tx.commits++
		tx.committed = true
		return nil
	}
	rollback := func() error {
		tx.mu.Lock()
		defer tx.mu.Unlock()
		tx.rollbacks++
		return nil
	}
	return tx, commit, rollback, nil
}
