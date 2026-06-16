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

// failingOutbox always errors on Append — proves the same-TX atomicity
// (P2/101 /review-impl #3): a failed outbox append MUST roll back the data +
// audit write, not leave them committed. This property became load-bearing in
// 101 (the first production caller to set a non-nil cfg.Outbox).
type failingOutbox struct{ err error }

func (f failingOutbox) Append(context.Context, Tx, OutboxEvent) error { return f.err }

func TestMetaWrite_OutboxAppendFailureRollsBack(t *testing.T) {
	allow := newStaticAllowlist(
		[]string{"reality_registry"},
		map[string]map[MetaWriteOp]string{"reality_registry": {OpInsert: "reality.created"}},
	)
	db := &fakeDB{}
	appendErr := errors.New("outbox table missing")
	cfg := &Config{
		DB:           db,
		Allowlist:    allow,
		Outbox:       failingOutbox{err: appendErr},
		QueryBuilder: PostgresQueryBuilder{},
		Clock:        newFakeClock(1_700_000_000_000_000_000),
		UUIDGen:      &fakeUUIDGen{},
	}
	_, err := MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:     "reality_registry",
		Operation: OpInsert,
		PK:        map[string]any{"reality_id": uuid.New().String()},
		NewValues: map[string]any{"status": "provisioning"},
		Actor:     Actor{Type: ActorService, ID: "world-service"},
		Reason:    "atomicity test",
	})
	if err == nil || !errors.Is(err, appendErr) {
		t.Fatalf("want wrapped outbox append error, got %v", err)
	}
	if len(db.Txs) != 1 {
		t.Fatalf("expected 1 TX, got %d", len(db.Txs))
	}
	tx := db.Txs[0]
	if tx.committed {
		t.Error("TX must NOT commit when outbox append fails (data + audit write must roll back)")
	}
	if tx.rollbacks < 1 {
		t.Error("TX must be rolled back when outbox append fails")
	}
}

func TestMetaWrite_OutboxPayloadOverride(t *testing.T) {
	allow := newStaticAllowlist(
		[]string{"pii_kek"},
		map[string]map[MetaWriteOp]string{"pii_kek": {OpUpdate: "user.erased"}},
	)
	cfg, _, out := newDefaultTestCfg(allow, nil)

	domain := map[string]any{"user_id": "u-123", "erased_at": "2026-05-31T00:00:00Z"}
	res, err := MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:          "pii_kek",
		Operation:      OpUpdate,
		PK:             map[string]any{"kek_id": "k-1"},
		ExpectedBefore: map[string]any{"destroyed_at": nil},
		NewValues:      map[string]any{"destroyed_at": "2026-05-31T00:00:00Z"},
		Actor:          Actor{Type: ActorAdmin, ID: "op"},
		Reason:         "gdpr erasure",
		OutboxPayload:  domain, // P2/113 — emit the DOMAIN shape, not the CDC view
	})
	if err != nil {
		t.Fatalf("MetaWrite: %v", err)
	}
	if len(out.events) != 1 {
		t.Fatalf("want 1 outbox event, got %d", len(out.events))
	}
	got := out.events[0]
	if got.EventName != "user.erased" {
		t.Errorf("event_name = %q", got.EventName)
	}
	// Payload must be the EXACT domain map — not the generic {table,operation,pk,after}.
	if got.Payload["user_id"] != "u-123" || got.Payload["erased_at"] != "2026-05-31T00:00:00Z" {
		t.Errorf("override payload not used: %#v", got.Payload)
	}
	if _, leaked := got.Payload["table"]; leaked {
		t.Errorf("generic CDC keys must NOT appear when OutboxPayload is set: %#v", got.Payload)
	}
	// /review-impl #1: the override must NOT bleed into the data write / audit
	// path — those still reflect the real change (NewValues). The result echoes
	// the data write's NewValues, so it must carry destroyed_at, not user_id.
	if res.NewValues["destroyed_at"] != "2026-05-31T00:00:00Z" {
		t.Errorf("data write must keep NewValues (the real change), got %#v", res.NewValues)
	}
	if _, bled := res.NewValues["user_id"]; bled {
		t.Errorf("OutboxPayload (domain) must NOT leak into the data write/audit NewValues: %#v", res.NewValues)
	}
}

func TestMetaWrite_DefaultOutboxPayloadWhenNoOverride(t *testing.T) {
	allow := newStaticAllowlist(
		[]string{"reality_registry"},
		map[string]map[MetaWriteOp]string{"reality_registry": {OpInsert: "reality.created"}},
	)
	cfg, _, out := newDefaultTestCfg(allow, nil)
	_, err := MetaWrite(context.Background(), cfg, MetaWriteIntent{
		Table:     "reality_registry",
		Operation: OpInsert,
		PK:        map[string]any{"reality_id": uuid.New().String()},
		NewValues: map[string]any{"status": "provisioning"},
		Actor:     Actor{Type: ActorService, ID: "world-service"},
		// no OutboxPayload → generic CDC default
	})
	if err != nil {
		t.Fatalf("MetaWrite: %v", err)
	}
	if len(out.events) != 1 || out.events[0].Payload["table"] != "reality_registry" {
		t.Errorf("expected generic CDC payload with table key, got %#v", out.events[0].Payload)
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
		{rows: 1, err: nil},                     // data 1 ok
		{rows: 1, err: nil},                     // audit 1 ok
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
	txs    []*fakeTx // every TX handed out, in order (S13 atomicity assertions)
	begins int       // number of BeginTx calls (S13 atomicity: success path must be 1)
}

func (d *fakeDBPrequeue) BeginTx(_ context.Context) (Tx, func() error, func() error, error) {
	d.begins++
	tx := &fakeTx{}
	if len(d.queue) > 0 {
		tx.responses = d.queue[0]
		d.queue = d.queue[1:]
	}
	d.lastTx = tx
	d.txs = append(d.txs, tx)
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
