package api

// G4 test helpers — SQL-level adopt (no HTTP/grant) + book-tier id lookups, used
// by retargeted tests that previously read system_kinds / system_kind_attributes.
//
// After the G4 cutover glossary_entities.kind_id → book_kinds and
// entity_attribute_values.attr_def_id → book_attributes, so a book MUST be adopted
// before any entity can be created in it. adoptTestBook mirrors the copy-down in
// book_adopt_handler.go's adoptBookOntology, but adopts ALL system kinds + genres
// (not a picked subset) so any kind a test references already exists in the book.
// Idempotent (ON CONFLICT DO NOTHING) so repeated calls on a shared DB are safe.

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// adoptTestBook copies the System standards into the book tier for bookID:
// every system genre (incl. 'universal'), all of them activated, every system
// kind, the system kind↔genre links, and every system attribute (remapped to the
// book ids by code). Pure SQL — no grant check, no HTTP. Idempotent.
func adoptTestBook(t *testing.T, pool *pgxpool.Pool, bookID uuid.UUID) {
	t.Helper()
	ctx := context.Background()

	// 1) genres (all system genres, incl. universal).
	if _, err := pool.Exec(ctx, `
		INSERT INTO book_genres (book_id, code, name, icon, color, sort_order, source_ref, source_hash)
		SELECT $1, sg.code, sg.name, sg.icon, sg.color, sg.sort_order, 'system:'||sg.genre_id::text, sg.content_hash
		FROM system_genres sg
		ON CONFLICT (book_id, code) DO NOTHING`, bookID); err != nil {
		t.Fatalf("adoptTestBook genres: %v", err)
	}
	// 2) activate every adopted genre.
	if _, err := pool.Exec(ctx, `
		INSERT INTO book_active_genres (book_id, genre_id)
		SELECT $1, bg.genre_id FROM book_genres bg WHERE bg.book_id=$1
		ON CONFLICT DO NOTHING`, bookID); err != nil {
		t.Fatalf("adoptTestBook active-genres: %v", err)
	}
	// 3) kinds (all system kinds).
	if _, err := pool.Exec(ctx, `
		INSERT INTO book_kinds (book_id, code, name, description, icon, color, sort_order, is_hidden, source_ref, source_hash)
		SELECT $1, sk.code, sk.name, sk.description, sk.icon, sk.color, sk.sort_order, sk.is_hidden,
		       'system:'||sk.kind_id::text, md5(sk.code||'|'||sk.name||'|'||coalesce(sk.description,''))
		FROM system_kinds sk
		ON CONFLICT (book_id, code) DO NOTHING`, bookID); err != nil {
		t.Fatalf("adoptTestBook kinds: %v", err)
	}
	// 4) kind↔genre links, remapped to book ids by code.
	if _, err := pool.Exec(ctx, `
		INSERT INTO book_kind_genres (book_id, kind_id, genre_id)
		SELECT $1, bk.book_kind_id, bg.genre_id
		FROM system_kind_genres skg
		JOIN system_kinds  sk ON sk.kind_id  = skg.kind_id
		JOIN system_genres sg ON sg.genre_id = skg.genre_id
		JOIN book_kinds  bk ON bk.book_id=$1 AND bk.code = sk.code
		JOIN book_genres bg ON bg.book_id=$1 AND bg.code = sg.code
		ON CONFLICT DO NOTHING`, bookID); err != nil {
		t.Fatalf("adoptTestBook kind-genres: %v", err)
	}
	// 5) attributes, remapped to book ids by (kind, genre) code.
	if _, err := pool.Exec(ctx, `
		INSERT INTO book_attributes
		  (book_id, kind_id, genre_id, code, name, description, field_type, is_required,
		   sort_order, options, auto_fill_prompt, translation_hint, source_ref, source_hash)
		SELECT $1, bk.book_kind_id, bg.genre_id, sa.code, sa.name, sa.description, sa.field_type, sa.is_required,
		       sa.sort_order, sa.options, sa.auto_fill_prompt, sa.translation_hint,
		       'system:'||sa.attr_id::text, sa.content_hash
		FROM system_attributes sa
		JOIN system_kinds  sk ON sk.kind_id  = sa.kind_id
		JOIN system_genres sg ON sg.genre_id = sa.genre_id
		JOIN book_kinds  bk ON bk.book_id=$1 AND bk.code = sk.code
		JOIN book_genres bg ON bg.book_id=$1 AND bg.code = sg.code
		ON CONFLICT (book_id, kind_id, genre_id, code) DO NOTHING`, bookID); err != nil {
		t.Fatalf("adoptTestBook attributes: %v", err)
	}
}

// bookKindID returns the book_kinds.book_kind_id for (bookID, code). Fails the test
// if absent (the book wasn't adopted, or the code doesn't exist as a system kind).
func bookKindID(t *testing.T, pool *pgxpool.Pool, bookID uuid.UUID, code string) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := pool.QueryRow(context.Background(),
		`SELECT book_kind_id FROM book_kinds WHERE book_id=$1 AND code=$2`,
		bookID, code).Scan(&id); err != nil {
		t.Fatalf("bookKindID(%s): %v", code, err)
	}
	return id
}

// bookAttrID returns the book_attributes.attr_id for (bookID, bookKindID, code),
// preferring the universal-genre row when multiple genres carry the same code (the
// seed lifts every kind's attrs into (kind, universal), so the universal row is the
// extraction/entity attribute). Fails the test if absent.
func bookAttrID(t *testing.T, pool *pgxpool.Pool, bookID, bookKindID uuid.UUID, code string) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := pool.QueryRow(context.Background(), `
		SELECT ba.attr_id
		FROM book_attributes ba
		JOIN book_genres g ON g.genre_id = ba.genre_id
		WHERE ba.book_id=$1 AND ba.kind_id=$2 AND ba.code=$3
		ORDER BY (g.code = 'universal') DESC, ba.sort_order, ba.attr_id
		LIMIT 1`, bookID, bookKindID, code).Scan(&id); err != nil {
		t.Fatalf("bookAttrID(%s): %v", code, err)
	}
	return id
}
