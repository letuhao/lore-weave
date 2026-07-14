package api

// PP-4 (spec 08 R6) — DB integration: entity-level guard on the enrichment surface. Requires
// GLOSSARY_TEST_DB_URL (openTestDB skips otherwise).

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// seedEntityOfKind inserts a book_kind with `code` (if absent) + an entity of that kind, and returns
// the entity id. Reuses adoptTestBook for the base tier.
func seedEntityOfKind(t *testing.T, pool *pgxpool.Pool, bookID uuid.UUID, code string) string {
	t.Helper()
	ctx := context.Background()
	adoptTestBook(t, pool, bookID)
	var kindID uuid.UUID
	_ = pool.QueryRow(ctx,
		`INSERT INTO book_kinds(book_id, code, name) VALUES($1,$2,$2)
		 ON CONFLICT DO NOTHING RETURNING book_kind_id`, bookID, code).Scan(&kindID)
	if kindID == uuid.Nil {
		_ = pool.QueryRow(ctx,
			`SELECT book_kind_id FROM book_kinds WHERE book_id=$1 AND code=$2`, bookID, code).Scan(&kindID)
	}
	var eid string
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}')
		 RETURNING entity_id`, bookID, kindID).Scan(&eid); err != nil {
		t.Fatalf("seed entity of kind %q: %v", code, err)
	}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_enrichments WHERE entity_id=$1`, eid)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE entity_id=$1`, eid)
	})
	return eid
}

func TestEnrichments_RefusesAColleagueEntity_PP4(t *testing.T) {
	pool := openTestDB(t)
	runEnrichmentMigrations(t, pool)
	book := uuid.MustParse("00000000-0000-0000-0004-0000000000c1")
	srv, token := newCanonContentServer(t)
	srv.pool = pool

	body := func() string {
		b, _ := json.Marshal(map[string]any{
			"proposal_id": "00000000-0000-0000-0004-0000000000a1", "technique": "retrieval",
			"facts": []map[string]any{{"dimension": "trait", "content": "always pushes back", "confidence": 0.3}},
		})
		return string(b)
	}()

	// A 'colleague' entity (a real person) → enrichment REFUSED (PP-4).
	colleague := seedEntityOfKind(t, pool, book, "colleague")
	w := postEnrichments(t, srv, token, book.String(), colleague, body)
	if w.Code != http.StatusForbidden {
		t.Fatalf("PP-4 BREACH: enriching a colleague = %d, want 403. body=%s", w.Code, w.Body.String())
	}
	var resp struct {
		Code string `json:"code"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Code != "GLOSS_NO_ENRICH_PERSON" {
		t.Fatalf("want GLOSS_NO_ENRICH_PERSON, got %q", resp.Code)
	}

	// A non-person entity (e.g. 'org') is NOT refused by PP-4 (200 OK).
	org := seedEntityOfKind(t, pool, book, "org")
	w2 := postEnrichments(t, srv, token, book.String(), org, body)
	if w2.Code != http.StatusOK {
		t.Fatalf("enriching a non-person 'org' entity = %d, want 200 (PP-4 must not over-block). body=%s",
			w2.Code, w2.Body.String())
	}
}

// PP-4 / review H1 — the LLM wiki-gen DELEGATE (the AI-biography path) must ALSO exclude a colleague.
// Both the by-kind resolver and the explicit single-entity "Regenerate" path drop 'colleague' entities.
func TestWikiGenDelegate_ExcludesColleague_PP4(t *testing.T) {
	pool := openTestDB(t)
	runEnrichmentMigrations(t, pool)
	book := uuid.MustParse("00000000-0000-0000-0004-0000000000c2")
	srv, _ := newCanonContentServer(t)
	srv.pool = pool
	ctx := context.Background()

	colleague := seedEntityOfKind(t, pool, book, "colleague")
	org := seedEntityOfKind(t, pool, book, "org")

	// by-kind resolver (no kind filter → all kinds) must OMIT the colleague, KEEP the org.
	ids, _, err := srv.resolveWikiGenEntities(ctx, book, nil, 100)
	if err != nil {
		t.Fatalf("resolveWikiGenEntities: %v", err)
	}
	got := map[string]bool{}
	for _, id := range ids {
		got[id] = true
	}
	if got[colleague] {
		t.Fatal("H1 BREACH: the LLM wiki-gen delegate would biography a colleague (by-kind path)")
	}
	if !got[org] {
		t.Fatal("the delegate must still generate a non-person 'org' page")
	}

	// explicit single-entity "Regenerate" path must also drop the colleague.
	ex, _, err := srv.resolveDelegateEntityIDs(ctx, book, []string{colleague}, nil, 100)
	if err != nil {
		t.Fatalf("resolveDelegateEntityIDs: %v", err)
	}
	if len(ex) != 0 {
		t.Fatalf("H1 BREACH: explicit Regenerate of a colleague resolved %d ids, want 0", len(ex))
	}
}
