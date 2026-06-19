package api

// M4d-2b — extract-entities with a per-entity target translation writes/updates
// the name attr's attribute_translations at confidence='machine', NEVER
// overwriting a verified (human) translation. DB-integration; skips without
// GLOSSARY_TEST_DB_URL.

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// nameTranslation returns the (value, confidence) of an entity's name translation
// in a given language, by original_value, plus whether it exists.
func nameTranslation(t *testing.T, pool *pgxpool.Pool, bookID, name, lang string) (string, string, bool) {
	t.Helper()
	var value, confidence string
	err := pool.QueryRow(context.Background(), `
		SELECT at.value, at.confidence
		FROM attribute_translations at
		JOIN entity_attribute_values eav ON eav.attr_value_id = at.attr_value_id
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		WHERE ge.book_id=$1 AND ad.code='name' AND eav.original_value=$2 AND at.language_code=$3`,
		bookID, name, lang,
	).Scan(&value, &confidence)
	if err != nil {
		return "", "", false
	}
	return value, confidence, true
}

// seedEntityWithTranslation inserts an active entity (name attr) + a name
// translation at the given confidence — the pre-existing state the writeback
// must respect.
func seedEntityWithTranslation(t *testing.T, pool *pgxpool.Pool, bookID, name, lang, value, confidence string) {
	t.Helper()
	ctx := context.Background()
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")
	nameAttrID := bookAttrID(t, pool, bid, kindID, "name")
	var eid, avid string
	pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}')
		 RETURNING entity_id`, bid, kindID).Scan(&eid)
	pool.QueryRow(ctx,
		`INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value)
		 VALUES($1,$2,'zh',$3) RETURNING attr_value_id`, eid, nameAttrID, name).Scan(&avid)
	pool.Exec(ctx,
		`INSERT INTO attribute_translations(attr_value_id,language_code,value,confidence)
		 VALUES($1,$2,$3,$4)`, avid, lang, value, confidence)
}

func translationBody(name, lang, value string) map[string]any {
	return map[string]any{
		"source_language":   "zh",
		"default_tags":      []string{"ai-suggested"},
		"park_unknown_kinds": false,
		"entities": []map[string]any{
			{"kind_code": "character", "name": name,
				"translation": map[string]any{"language_code": lang, "value": value}},
		},
	}
}

func TestBulkExtract_WritesMachineTranslationForNewEntity(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0005-0000000e2001"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	postExtract(t, srv, token, bookID, translationBody("提拉米", "vi", "Tirami"))

	val, conf, ok := nameTranslation(t, pool, bookID, "提拉米", "vi")
	if !ok || val != "Tirami" || conf != "machine" {
		t.Errorf("want machine/Tirami, got %q/%q (found=%v)", conf, val, ok)
	}
}

func TestBulkExtract_DoesNotOverwriteVerifiedTranslation(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0005-0000000e2002"
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})
	seedEntityWithTranslation(t, pool, bookID, "阿尔德里克", "vi", "Aldric", "verified")
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	postExtract(t, srv, token, bookID, translationBody("阿尔德里克", "vi", "MachineOverwrite"))

	val, conf, _ := nameTranslation(t, pool, bookID, "阿尔德里克", "vi")
	if val != "Aldric" || conf != "verified" {
		t.Errorf("verified translation was clobbered: got %q/%q", conf, val)
	}
}

func TestBulkExtract_OverwritesNonVerifiedTranslation(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0005-0000000e2003"
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})
	seedEntityWithTranslation(t, pool, bookID, "李靖", "vi", "OldMachine", "machine")
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	resp := postExtract(t, srv, token, bookID, translationBody("李靖", "vi", "NewMachine"))

	val, conf, _ := nameTranslation(t, pool, bookID, "李靖", "vi")
	if val != "NewMachine" || conf != "machine" {
		t.Errorf("non-verified translation not overwritten: got %q/%q", conf, val)
	}
	// review-impl: a translation-ONLY change to an existing entity merges to
	// "skipped", but the translation changed → it must surface as "updated" so the
	// emit fires (VG-1 versions it = recoverable; M5c marks dependents stale).
	ents := resp["entities"].([]any)
	if st := ents[0].(map[string]any)["status"]; st != "updated" {
		t.Errorf("translation-only update must be 'updated' (emits/versioned), got %v", st)
	}
}

func TestBulkExtract_NoTranslationFieldIsBackwardCompatible(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	bookID := "00000000-0000-0000-0005-0000000e2004"
	adoptTestBook(t, pool, uuid.MustParse(bookID))
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	})
	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "zh",
		"entities":        []map[string]any{{"kind_code": "character", "name": "杨戬"}},
	})

	if _, _, ok := nameTranslation(t, pool, bookID, "杨戬", "vi"); ok {
		t.Error("a no-translation extract wrote an attribute_translations row")
	}
}
