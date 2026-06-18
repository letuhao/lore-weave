package events

// VG-1 — tests for the revision projection's DB writer (recordRevision).
// DB-integration; requires GLOSSARY_TEST_DB_URL and skips otherwise.

import (
	"context"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/glossary-service/internal/migrate"
)

func setupDB(t *testing.T) *pgxpool.Pool {
	t.Helper()
	url := os.Getenv("GLOSSARY_TEST_DB_URL")
	if url == "" {
		t.Skip("GLOSSARY_TEST_DB_URL not set — skipping DB integration test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	for _, m := range []struct {
		name string
		fn   func(context.Context, *pgxpool.Pool) error
	}{
		{"Up", migrate.Up}, {"Seed", migrate.Seed},
		{"UpSnapshot", migrate.UpSnapshot}, {"UpSoftDelete", migrate.UpSoftDelete},
		{"UpEntityRevisions", migrate.UpEntityRevisions},
	} {
		if err := m.fn(ctx, pool); err != nil {
			t.Fatalf("migrate %s: %v", m.name, err)
		}
	}
	return pool
}

func seedEntity(t *testing.T, pool *pgxpool.Pool, bookID uuid.UUID) uuid.UUID {
	t.Helper()
	ctx := context.Background()
	var kindID string
	if err := pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).
		Scan(&kindID); err != nil {
		t.Fatalf("kind lookup: %v", err)
	}
	var eid uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}')
		 RETURNING entity_id`, bookID, kindID,
	).Scan(&eid); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	return eid
}

func revisionCount(t *testing.T, pool *pgxpool.Pool, entityID uuid.UUID, actorType string) int {
	t.Helper()
	var n int
	q := `SELECT COUNT(*) FROM entity_revisions WHERE entity_id=$1`
	args := []any{entityID}
	if actorType != "" {
		q += ` AND actor_type=$2`
		args = append(args, actorType)
	}
	if err := pool.QueryRow(context.Background(), q, args...).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	return n
}

func TestRecordRevision_UserEditCapturesSequentialRevisions(t *testing.T) {
	pool := setupDB(t)
	ctx := context.Background()
	bookID := uuid.MustParse("00000000-0000-0000-0003-0000000e1001")
	eid := seedEntity(t, pool, bookID)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	ins, err := recordRevision(ctx, pool, eid, uuid.New(), "updated", "user", uuid.New().String())
	if err != nil || !ins {
		t.Fatalf("first revision: ins=%v err=%v", ins, err)
	}
	ins2, err := recordRevision(ctx, pool, eid, uuid.New(), "updated", "user", "")
	if err != nil || !ins2 {
		t.Fatalf("second revision: ins=%v err=%v", ins2, err)
	}

	var maxNum int
	var snapshot string
	var actor string
	pool.QueryRow(ctx,
		`SELECT MAX(revision_num) FROM entity_revisions WHERE entity_id=$1`, eid).Scan(&maxNum)
	pool.QueryRow(ctx,
		`SELECT snapshot::text, actor_type FROM entity_revisions WHERE entity_id=$1 AND revision_num=1`,
		eid).Scan(&snapshot, &actor)
	if maxNum != 2 {
		t.Errorf("want revision_num up to 2, got %d", maxNum)
	}
	if actor != "user" {
		t.Errorf("want actor_type=user, got %q", actor)
	}
	if len(snapshot) < 2 { // a real entity_snapshot JSONB, not empty
		t.Errorf("snapshot not captured: %q", snapshot)
	}
}

func TestRecordRevision_IdempotentOnEventID(t *testing.T) {
	pool := setupDB(t)
	ctx := context.Background()
	bookID := uuid.MustParse("00000000-0000-0000-0003-0000000e1002")
	eid := seedEntity(t, pool, bookID)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	ev := uuid.New()
	ins1, _ := recordRevision(ctx, pool, eid, ev, "updated", "user", "")
	ins2, err := recordRevision(ctx, pool, eid, ev, "updated", "user", "") // redelivery
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if !ins1 || ins2 {
		t.Errorf("want first inserted, redelivery skipped; got %v %v", ins1, ins2)
	}
	if n := revisionCount(t, pool, eid, ""); n != 1 {
		t.Errorf("redelivery double-wrote: want 1 revision, got %d", n)
	}
}

func TestRecordRevision_PipelineRollingNAndUserKept(t *testing.T) {
	pool := setupDB(t)
	ctx := context.Background()
	bookID := uuid.MustParse("00000000-0000-0000-0003-0000000e1003")
	eid := seedEntity(t, pool, bookID)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	// One precious USER revision first — must never be pruned.
	recordRevision(ctx, pool, eid, uuid.New(), "updated", "user", "")
	// Then many pipeline writes — pruned to a rolling last-N.
	for i := 0; i < pipelineKeepN+3; i++ {
		if _, err := recordRevision(ctx, pool, eid, uuid.New(), "updated", "pipeline", ""); err != nil {
			t.Fatalf("pipeline revision %d: %v", i, err)
		}
	}

	if got := revisionCount(t, pool, eid, "pipeline"); got != pipelineKeepN {
		t.Errorf("pipeline rolling-N: want %d, got %d", pipelineKeepN, got)
	}
	if got := revisionCount(t, pool, eid, "user"); got != 1 {
		t.Errorf("user revision was pruned: want 1, got %d", got)
	}
}

func TestRecordRevision_VanishedEntityIsNoOp(t *testing.T) {
	pool := setupDB(t)
	ctx := context.Background()
	ins, err := recordRevision(ctx, pool, uuid.New(), uuid.New(), "updated", "user", "")
	if err != nil || ins {
		t.Errorf("vanished entity: want (false,nil), got (%v,%v)", ins, err)
	}
}

func TestBackfillEntityRevisions_SeedsBaselineOnce(t *testing.T) {
	pool := setupDB(t)
	ctx := context.Background()
	bookID := uuid.MustParse("00000000-0000-0000-0003-0000000e1004")
	e1 := seedEntity(t, pool, bookID)
	e2 := seedEntity(t, pool, bookID)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	if err := migrate.BackfillEntityRevisions(ctx, pool); err != nil {
		t.Fatalf("backfill: %v", err)
	}
	for _, e := range []uuid.UUID{e1, e2} {
		var op string
		var num int
		pool.QueryRow(ctx,
			`SELECT op, revision_num FROM entity_revisions WHERE entity_id=$1`, e).Scan(&op, &num)
		if op != "baseline" || num != 1 {
			t.Errorf("entity %s: want baseline/1, got %q/%d", e, op, num)
		}
	}
	// Idempotent: re-run does not duplicate.
	if err := migrate.BackfillEntityRevisions(ctx, pool); err != nil {
		t.Fatalf("backfill re-run: %v", err)
	}
	if n := revisionCount(t, pool, e1, ""); n != 1 {
		t.Errorf("re-run duplicated baseline: want 1, got %d", n)
	}
	// An entity that ALREADY has a revision is left alone (no baseline injected).
	e3 := seedEntity(t, pool, bookID)
	recordRevision(ctx, pool, e3, uuid.New(), "updated", "user", "")
	migrate.BackfillEntityRevisions(ctx, pool)
	var hasBaseline bool
	pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM entity_revisions WHERE entity_id=$1 AND op='baseline')`,
		e3).Scan(&hasBaseline)
	if hasBaseline {
		t.Error("entity with an existing revision wrongly got a baseline")
	}
}

// ── processMessage (parse layer — the path the recordRevision tests bypass) ───

func msgFor(entityID, outboxID, eventType, payloadJSON string) redis.XMessage {
	return redis.XMessage{ID: "1-0", Values: map[string]any{
		"event_type":   eventType,
		"aggregate_id": entityID,
		"outbox_id":    outboxID,
		"payload":      payloadJSON,
	}}
}

func TestProcessMessage_CapturesAndNormalizesActor(t *testing.T) {
	pool := setupDB(t)
	ctx := context.Background()
	bookID := uuid.MustParse("00000000-0000-0000-0003-0000000e1005")
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })
	c := &RevisionConsumer{pool: pool} // rdb unused by processMessage

	// actor_type=user → captured as user
	eUser := seedEntity(t, pool, bookID)
	if err := c.processMessage(ctx, msgFor(eUser.String(), uuid.New().String(),
		entityUpdated, `{"actor_type":"user","op":"updated"}`)); err != nil {
		t.Fatalf("user event: %v", err)
	}
	// missing actor_type → normalized to system (not user/pipeline)
	eSys := seedEntity(t, pool, bookID)
	if err := c.processMessage(ctx, msgFor(eSys.String(), uuid.New().String(),
		entityUpdated, `{"op":"updated"}`)); err != nil {
		t.Fatalf("no-actor event: %v", err)
	}

	var ua, sa string
	pool.QueryRow(ctx, `SELECT actor_type FROM entity_revisions WHERE entity_id=$1`, eUser).Scan(&ua)
	pool.QueryRow(ctx, `SELECT actor_type FROM entity_revisions WHERE entity_id=$1`, eSys).Scan(&sa)
	if ua != "user" {
		t.Errorf("want actor_type=user, got %q", ua)
	}
	if sa != "system" {
		t.Errorf("missing actor_type should normalize to system, got %q", sa)
	}
}

func TestProcessMessage_SkipsNonEntityUpdated(t *testing.T) {
	pool := setupDB(t)
	ctx := context.Background()
	bookID := uuid.MustParse("00000000-0000-0000-0003-0000000e1006")
	eid := seedEntity(t, pool, bookID)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })
	c := &RevisionConsumer{pool: pool}

	if err := c.processMessage(ctx, msgFor(eid.String(), uuid.New().String(),
		"glossary.entity_merged", `{}`)); err != nil {
		t.Fatalf("err: %v", err)
	}
	if n := revisionCount(t, pool, eid, ""); n != 0 {
		t.Errorf("non-entity_updated event created a revision: %d", n)
	}
}

func TestProcessMessage_MalformedIDsAreSkippedNotErrored(t *testing.T) {
	pool := setupDB(t)
	ctx := context.Background()
	c := &RevisionConsumer{pool: pool}
	// A bad aggregate_id or outbox_id must be a clean skip (nil) — poison, not a
	// transient error that would wedge the stream as pending.
	if err := c.processMessage(ctx, msgFor("not-a-uuid", uuid.New().String(),
		entityUpdated, `{}`)); err != nil {
		t.Errorf("bad aggregate_id: want nil skip, got %v", err)
	}
	if err := c.processMessage(ctx, msgFor(uuid.New().String(), "not-a-uuid",
		entityUpdated, `{}`)); err != nil {
		t.Errorf("bad outbox_id: want nil skip, got %v", err)
	}
}

func TestStrCoercion(t *testing.T) {
	if str("x") != "x" || str(42) != "" || str(nil) != "" {
		t.Error("str coercion wrong")
	}
}
