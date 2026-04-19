package api

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
	"github.com/loreweave/glossary-service/internal/shortdesc"
)

// runK3Migrations applies the full migration chain through K3.
func runK3Migrations(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	runK2aMigrations(t, pool)
	ctx := context.Background()
	if err := migrate.UpShortDescAuto(ctx, pool); err != nil {
		t.Fatalf("migrate.UpShortDescAuto: %v", err)
	}
}

func k3Generate(name, description, kindName string) string {
	return shortdesc.Generate(name, description, kindName, shortdesc.DefaultMaxChars)
}

// ── schema ─────────────────────────────────────────────────────────────────

func TestK3_ShortDescAutoColumnExists(t *testing.T) {
	pool := openTestDB(t)
	runK3Migrations(t, pool)
	ctx := context.Background()
	var present bool
	pool.QueryRow(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM information_schema.columns
			WHERE table_name='glossary_entities'
			  AND column_name='short_description_auto'
		)`).Scan(&present)
	if !present {
		t.Errorf("short_description_auto column missing")
	}
}

// ── backfill ───────────────────────────────────────────────────────────────

func TestK3_BackfillPopulatesShortDescription(t *testing.T) {
	pool := openTestDB(t)
	runK3Migrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-000000033001"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	var nameAttr, descAttr string
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID).Scan(&nameAttr)
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='description' LIMIT 1`, kindID).Scan(&descAttr)

	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	// Entity A: has description
	var idA string
	pool.QueryRow(ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`, bookID, kindID).Scan(&idA)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Alice')`, idA, nameAttr)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','A wandering swordsman. He wields two blades.')`, idA, descAttr)

	// Entity B: no description
	var idB string
	pool.QueryRow(ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`, bookID, kindID).Scan(&idB)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Bob')`, idB, nameAttr)

	// Entity C: CJK description
	var idC string
	pool.QueryRow(ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`, bookID, kindID).Scan(&idC)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','李雲')`, idC, nameAttr)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','一位神秘的刀客。')`, idC, descAttr)

	// Entity D: user-overridden (auto=false) with NULL — must NOT be backfilled
	var idD string
	pool.QueryRow(ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags,short_description_auto) VALUES($1,$2,'active','{}',false) RETURNING entity_id`, bookID, kindID).Scan(&idD)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Denise')`, idD, nameAttr)

	n, err := migrate.BackfillShortDescription(ctx, pool, k3Generate)
	if err != nil {
		t.Fatalf("backfill: %v", err)
	}
	if n < 3 {
		t.Errorf("expected at least 3 entities processed, got %d", n)
	}

	var sdA, sdB, sdC *string
	var sdD *string
	pool.QueryRow(ctx, `SELECT short_description FROM glossary_entities WHERE entity_id=$1`, idA).Scan(&sdA)
	pool.QueryRow(ctx, `SELECT short_description FROM glossary_entities WHERE entity_id=$1`, idB).Scan(&sdB)
	pool.QueryRow(ctx, `SELECT short_description FROM glossary_entities WHERE entity_id=$1`, idC).Scan(&sdC)
	pool.QueryRow(ctx, `SELECT short_description FROM glossary_entities WHERE entity_id=$1`, idD).Scan(&sdD)

	if sdA == nil || *sdA != "A wandering swordsman." {
		t.Errorf("A: want 'A wandering swordsman.', got %v", sdA)
	}
	if sdB == nil {
		t.Errorf("B: want non-nil fallback, got nil")
	}
	if sdC == nil || *sdC != "一位神秘的刀客。" {
		t.Errorf("C: want CJK sentence, got %v", sdC)
	}
	if sdD != nil {
		t.Errorf("D (auto=false): must NOT be backfilled, got %q", *sdD)
	}
}

// TestK3_BackfillCursorForwardProgress is the regression for K3-I1.
// A generator that returns "" for every row would previously loop
// forever because the defensive skip branch never advanced the SELECT
// past the unwritable row. With the entity_id cursor the backfill
// completes after one pass regardless of what the UPDATEs do.
func TestK3_BackfillCursorForwardProgress(t *testing.T) {
	pool := openTestDB(t)
	runK3Migrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-000000033099"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	var nameAttr string
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID).Scan(&nameAttr)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	for i := 0; i < 5; i++ {
		var id string
		pool.QueryRow(ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`, bookID, kindID).Scan(&id)
		pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','CursorTest')`, id, nameAttr)
	}

	// Pathological generator: always returns "" so no row ever gets
	// written. Without a cursor the loop would run forever; with the
	// cursor it terminates cleanly after one pass.
	done := make(chan struct{})
	go func() {
		defer close(done)
		migrate.BackfillShortDescription(ctx, pool, func(name, description, kindName string) string {
			return ""
		})
	}()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("backfill did not terminate within 3s — cursor not advancing")
	}

	// No row should have been written because the generator returned "".
	var remaining int
	pool.QueryRow(ctx, `SELECT count(*) FROM glossary_entities WHERE book_id=$1 AND short_description IS NULL`, bookID).Scan(&remaining)
	if remaining != 5 {
		t.Errorf("expected 5 rows still NULL, got %d", remaining)
	}
}

func TestK3_BackfillIdempotent(t *testing.T) {
	pool := openTestDB(t)
	runK3Migrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-000000033002"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	var nameAttr string
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID).Scan(&nameAttr)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	var id string
	pool.QueryRow(ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`, bookID, kindID).Scan(&id)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Eve')`, id, nameAttr)

	n1, _ := migrate.BackfillShortDescription(ctx, pool, k3Generate)
	n2, _ := migrate.BackfillShortDescription(ctx, pool, k3Generate)
	if n1 < 1 {
		t.Errorf("first run: expected >=1 processed, got %d", n1)
	}
	if n2 != 0 {
		t.Errorf("second run (idempotent): expected 0 processed, got %d", n2)
	}
}

// ── patchAttributeValue auto-regen (K3.3b) ──────────────────────────────────

func TestK3_AutoRegenOnDescriptionUpdate(t *testing.T) {
	pool := openTestDB(t)
	runK3Migrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-000000033003"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	var nameAttr, descAttr string
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID).Scan(&nameAttr)
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='description' LIMIT 1`, kindID).Scan(&descAttr)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	// Seed entity with a name + description; backfill populates short_description.
	var id string
	pool.QueryRow(ctx, `INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`, bookID, kindID).Scan(&id)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Frank')`, id, nameAttr)
	var descAVID string
	pool.QueryRow(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','First sentence. Second sentence.') RETURNING attr_value_id`, id, descAttr).Scan(&descAVID)

	migrate.BackfillShortDescription(ctx, pool, k3Generate)

	var sdBefore *string
	pool.QueryRow(ctx, `SELECT short_description FROM glossary_entities WHERE entity_id=$1`, id).Scan(&sdBefore)
	if sdBefore == nil || *sdBefore != "First sentence." {
		t.Fatalf("before: want 'First sentence.', got %v", sdBefore)
	}

	// Server hook: simulate what patchAttributeValue does after a
	// description edit.
	srv := newExportServer(t, pool)
	// Update the description row directly, then invoke the hook.
	pool.Exec(ctx, `UPDATE entity_attribute_values SET original_value='Brand new first. Second.' WHERE attr_value_id=$1`, descAVID)

	// Capture snapshot_at BEFORE regen — a real short_description change
	// must advance snapshot_at (proves the self-trigger still fires post-
	// guard). Without this, a mis-constructed `IS NOT DISTINCT FROM`
	// guard would still pass the persisted-value assertion below.
	var snapshotBefore string
	pool.QueryRow(ctx,
		`SELECT entity_snapshot->>'snapshot_at' FROM glossary_entities WHERE entity_id=$1`,
		id).Scan(&snapshotBefore)

	entityUUID, _ := uuid.Parse(id)
	if err := srv.regenerateAutoShortDescription(ctx, entityUUID); err != nil {
		t.Fatalf("regenerate: %v", err)
	}

	var sdAfter *string
	var snapshotAfter string
	pool.QueryRow(ctx,
		`SELECT short_description, entity_snapshot->>'snapshot_at'
		 FROM glossary_entities WHERE entity_id=$1`,
		id).Scan(&sdAfter, &snapshotAfter)
	if sdAfter == nil || *sdAfter != "Brand new first." {
		t.Errorf("after: want 'Brand new first.', got %v", sdAfter)
	}
	if snapshotBefore == snapshotAfter {
		t.Errorf("real short_description change did not advance snapshot_at (%s); guard may have inverted", snapshotBefore)
	}
}

func TestK3_AutoRegenSkippedWhenUserOverride(t *testing.T) {
	pool := openTestDB(t)
	runK3Migrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-000000033004"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	var nameAttr, descAttr string
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID).Scan(&nameAttr)
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='description' LIMIT 1`, kindID).Scan(&descAttr)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	var id string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags,short_description,short_description_auto)
		 VALUES($1,$2,'active','{}','USER WROTE THIS',false) RETURNING entity_id`,
		bookID, kindID).Scan(&id)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','Grace')`, id, nameAttr)
	pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh','completely different description text for regeneration')`, id, descAttr)

	srv := newExportServer(t, pool)
	entityUUID, _ := uuid.Parse(id)
	if err := srv.regenerateAutoShortDescription(ctx, entityUUID); err != nil {
		t.Fatalf("regenerate: %v", err)
	}

	var sd *string
	pool.QueryRow(ctx, `SELECT short_description FROM glossary_entities WHERE entity_id=$1`, id).Scan(&sd)
	if sd == nil || *sd != "USER WROTE THIS" {
		t.Errorf("user override was overwritten: want 'USER WROTE THIS', got %v", sd)
	}
}

// T2-close-7 / P-K3-02: regen UPDATE must skip when the recomputed
// short_description is already what's persisted. Without this guard,
// every description PATCH — even a whitespace edit that doesn't change
// the first sentence — fires a second full recalculate_entity_snapshot
// on top of the eav-trigger's one.
//
// The cheapest proof: call regenerateAutoShortDescription twice in a
// row with no description change between them, and observe that the
// snapshot's `snapshot_at` timestamp does NOT advance on the second
// call — proving the UPDATE affected zero rows and the self-trigger
// did not fire.
func TestK3_AutoRegenSkipsWhenShortDescUnchanged(t *testing.T) {
	pool := openTestDB(t)
	runK3Migrations(t, pool)
	ctx := context.Background()

	bookID := "00000000-0000-0000-0000-000000033005"
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM entity_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	var nameAttr, descAttr string
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID).Scan(&nameAttr)
	pool.QueryRow(ctx, `SELECT attr_def_id FROM attribute_definitions WHERE kind_id=$1 AND code='description' LIMIT 1`, kindID).Scan(&descAttr)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	var id string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&id)
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'en','Helga')`,
		id, nameAttr)
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'en','First sentence. Second sentence.')`,
		id, descAttr)

	srv := newExportServer(t, pool)
	entityUUID, _ := uuid.Parse(id)

	// First regen: short_description goes from NULL → "First sentence."
	// This legitimately fires the self-trigger → recalc → snapshot_at
	// advances. We capture the value after this first run as our baseline.
	if err := srv.regenerateAutoShortDescription(ctx, entityUUID); err != nil {
		t.Fatalf("first regen: %v", err)
	}
	var baseline string
	pool.QueryRow(ctx,
		`SELECT entity_snapshot->>'snapshot_at' FROM glossary_entities WHERE entity_id=$1`,
		id).Scan(&baseline)

	// Second regen with no description change — the IS DISTINCT guard
	// must suppress the UPDATE, so the self-trigger must not fire and
	// snapshot_at must stay put.
	if err := srv.regenerateAutoShortDescription(ctx, entityUUID); err != nil {
		t.Fatalf("second regen: %v", err)
	}
	var after string
	pool.QueryRow(ctx,
		`SELECT entity_snapshot->>'snapshot_at' FROM glossary_entities WHERE entity_id=$1`,
		id).Scan(&after)

	if baseline != after {
		t.Errorf("no-op regen should not refire recalc (snapshot_at: %s -> %s)", baseline, after)
	}
}

