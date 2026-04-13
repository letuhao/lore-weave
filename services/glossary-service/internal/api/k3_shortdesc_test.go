package api

import (
	"context"
	"testing"

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
	entityUUID, _ := uuid.Parse(id)
	if err := srv.regenerateAutoShortDescription(ctx, entityUUID); err != nil {
		t.Fatalf("regenerate: %v", err)
	}

	var sdAfter *string
	pool.QueryRow(ctx, `SELECT short_description FROM glossary_entities WHERE entity_id=$1`, id).Scan(&sdAfter)
	if sdAfter == nil || *sdAfter != "Brand new first." {
		t.Errorf("after: want 'Brand new first.', got %v", sdAfter)
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

