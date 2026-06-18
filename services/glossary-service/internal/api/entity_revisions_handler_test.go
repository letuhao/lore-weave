package api

// VG-2 — the reconcile round-trip: edit → snapshot → mutate → restore → assert the
// entity EXACTLY matches the snapshot (restored values back + post-revision
// additions pruned). DB-integration; requires GLOSSARY_TEST_DB_URL.

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

func setupRevisionsDB(t *testing.T) *pgxpool.Pool {
	t.Helper()
	pool := openTestDB(t)
	ctx := context.Background()
	for _, fn := range []func(context.Context, *pgxpool.Pool) error{
		migrate.Up, migrate.Seed, migrate.UpSnapshot, migrate.UpSoftDelete,
		migrate.UpOutbox, migrate.UpEntityRevisions,
	} {
		if err := fn(ctx, pool); err != nil {
			t.Fatalf("migrate: %v", err)
		}
	}
	return pool
}

func TestReconcileEntityFromSnapshot_ExactRestoreWithPrune(t *testing.T) {
	pool := setupRevisionsDB(t)
	ctx := context.Background()

	bookID := uuid.MustParse("00000000-0000-0000-0004-0000000f1001")
	var kindID, nameAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx,
		`SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='name' LIMIT 1`,
		kindID).Scan(&nameAttrID)

	var entityID, nameAVID, tVi uuid.UUID
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}')
		 RETURNING entity_id`, bookID, kindID).Scan(&entityID)
	pool.QueryRow(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','提拉米') RETURNING attr_value_id`, entityID, nameAttrID).Scan(&nameAVID)
	pool.QueryRow(ctx,
		`INSERT INTO attribute_translations(attr_value_id,language_code,value,confidence)
		 VALUES($1,'vi','Tirami','verified') RETURNING translation_id`, nameAVID).Scan(&tVi)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	// The snapshot trigger has materialized state V1 → capture it.
	var snapV1 string
	if err := pool.QueryRow(ctx,
		`SELECT entity_snapshot::text FROM glossary_entities WHERE entity_id=$1`, entityID,
	).Scan(&snapV1); err != nil {
		t.Fatalf("read snapshot: %v", err)
	}

	// MUTATE past V1: overwrite the vi translation, ADD an en translation
	// (post-revision), and alter the name's original_value.
	pool.Exec(ctx, `UPDATE attribute_translations SET value='WRONG' WHERE translation_id=$1`, tVi)
	pool.Exec(ctx,
		`INSERT INTO attribute_translations(attr_value_id,language_code,value,confidence)
		 VALUES($1,'en','PostRevisionAddition','machine')`, nameAVID)
	pool.Exec(ctx, `UPDATE entity_attribute_values SET original_value='altered' WHERE attr_value_id=$1`, nameAVID)

	// RESTORE to V1.
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	if err := reconcileEntityFromSnapshot(ctx, tx, entityID, snapV1); err != nil {
		tx.Rollback(ctx)
		t.Fatalf("reconcile: %v", err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("commit: %v", err)
	}

	// 1. The vi translation value is restored.
	var viVal string
	pool.QueryRow(ctx, `SELECT value FROM attribute_translations WHERE translation_id=$1`, tVi).Scan(&viVal)
	if viVal != "Tirami" {
		t.Errorf("vi translation not restored: want Tirami, got %q", viVal)
	}
	// 2. The name's original_value is restored.
	var ov string
	pool.QueryRow(ctx, `SELECT original_value FROM entity_attribute_values WHERE attr_value_id=$1`, nameAVID).Scan(&ov)
	if ov != "提拉米" {
		t.Errorf("original_value not restored: want 提拉米, got %q", ov)
	}
	// 3. The post-revision en translation is PRUNED (exact-restore).
	var enCount int
	pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM attribute_translations WHERE attr_value_id=$1 AND language_code='en'`,
		nameAVID).Scan(&enCount)
	if enCount != 0 {
		t.Errorf("post-revision en translation was not pruned: %d remain", enCount)
	}
}

func TestReconcileEntityFromSnapshot_PrunesPostRevisionAttribute(t *testing.T) {
	pool := setupRevisionsDB(t)
	ctx := context.Background()

	bookID := uuid.MustParse("00000000-0000-0000-0004-0000000f1002")
	var kindID, nameAttrID, aliasAttrID string
	pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	pool.QueryRow(ctx, `SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='name' LIMIT 1`, kindID).Scan(&nameAttrID)
	pool.QueryRow(ctx, `SELECT attr_def_id FROM system_kind_attributes WHERE kind_id=$1 AND code='aliases' LIMIT 1`, kindID).Scan(&aliasAttrID)
	if aliasAttrID == "" {
		t.Skip("no aliases attr_def — skipping attribute-prune case")
	}

	var entityID uuid.UUID
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&entityID)
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','提拉米')`, entityID, nameAttrID)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	var snapV1 string
	pool.QueryRow(ctx, `SELECT entity_snapshot::text FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&snapV1)

	// Add an aliases attribute AFTER the revision.
	pool.Exec(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh','别名')`, entityID, aliasAttrID)

	tx, _ := pool.Begin(ctx)
	if err := reconcileEntityFromSnapshot(ctx, tx, entityID, snapV1); err != nil {
		tx.Rollback(ctx)
		t.Fatalf("reconcile: %v", err)
	}
	tx.Commit(ctx)

	var attrCount int
	pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM entity_attribute_values WHERE entity_id=$1`, entityID).Scan(&attrCount)
	if attrCount != 1 {
		t.Errorf("post-revision aliases attribute not pruned: want 1 attr, got %d", attrCount)
	}
}

// Exercises the entity-level chapter_links reconcile statements (8-9) — a path
// structurally distinct from the attr-nested translations/evidences.
// MED-1 guard: a degenerate snapshot (no 'attributes' key) must be rejected, else
// exact-restore would prune the entity to nothing. Pure (no DB).
func TestSnapshotRestorable(t *testing.T) {
	cases := []struct {
		snap string
		want bool
	}{
		{`{}`, false},                                   // baseline of a snapshot-less entity
		{`{"status":"active"}`, false},                  // object but no attributes key
		{`not json`, false},                             // malformed
		{`[]`, false},                                   // not an object
		{`{"attributes":[]}`, true},                     // genuinely zero attributes — valid
		{`{"attributes":[{"attr_value_id":"x"}]}`, true}, // full snapshot
	}
	for _, c := range cases {
		if got := snapshotRestorable([]byte(c.snap)); got != c.want {
			t.Errorf("snapshotRestorable(%q) = %v, want %v", c.snap, got, c.want)
		}
	}
}

func TestReconcileEntityFromSnapshot_RestoresAndPrunesChapterLinks(t *testing.T) {
	pool := setupRevisionsDB(t)
	ctx := context.Background()

	bookID := uuid.MustParse("00000000-0000-0000-0004-0000000f1003")
	var kindID string
	pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code='character' LIMIT 1`).Scan(&kindID)
	var entityID uuid.UUID
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, kindID).Scan(&entityID)
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID) })

	chKept := uuid.New()
	pool.Exec(ctx,
		`INSERT INTO chapter_entity_links(entity_id,chapter_id,chapter_title,chapter_index,relevance)
		 VALUES($1,$2,'Ch.1',1,'appears')`, entityID, chKept)

	var snapV1 string
	pool.QueryRow(ctx, `SELECT entity_snapshot::text FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&snapV1)

	// Mutate: change the kept link's title + add a post-revision link.
	pool.Exec(ctx, `UPDATE chapter_entity_links SET chapter_title='ALTERED' WHERE entity_id=$1 AND chapter_id=$2`, entityID, chKept)
	pool.Exec(ctx,
		`INSERT INTO chapter_entity_links(entity_id,chapter_id,chapter_title,chapter_index,relevance)
		 VALUES($1,$2,'Ch.2',2,'appears')`, entityID, uuid.New())

	tx, _ := pool.Begin(ctx)
	if err := reconcileEntityFromSnapshot(ctx, tx, entityID, snapV1); err != nil {
		tx.Rollback(ctx)
		t.Fatalf("reconcile: %v", err)
	}
	tx.Commit(ctx)

	var n int
	var title string
	pool.QueryRow(ctx, `SELECT COUNT(*) FROM chapter_entity_links WHERE entity_id=$1`, entityID).Scan(&n)
	if n != 1 {
		t.Errorf("post-revision chapter link not pruned: want 1 link, got %d", n)
	}
	pool.QueryRow(ctx, `SELECT chapter_title FROM chapter_entity_links WHERE entity_id=$1 AND chapter_id=$2`, entityID, chKept).Scan(&title)
	if title != "Ch.1" {
		t.Errorf("chapter link title not restored: want Ch.1, got %q", title)
	}
}
