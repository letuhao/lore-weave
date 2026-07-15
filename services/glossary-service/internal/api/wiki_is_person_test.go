package api

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"
)

// C4 / SD-C4 (D-WIKI-PERSON-FLAG) — the wiki-gen delegate must exclude entities of a REAL-person
// kind by the STRUCTURAL is_person flag, not the literal 'colleague' code. This proves a RENAMED /
// CUSTOM person kind (is_person=true, code≠'colleague') is excluded — the leak the old literal
// filter left open — while fiction 'character' (is_person=false) still generates. Skips without
// GLOSSARY_TEST_DB_URL.
func TestResolveWikiGenEntities_ExcludesIsPersonKind(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()

	srv, _ := newEntitiesListServer(t)
	srv.pool = pool

	bookID := uuid.MustParse("00000000-0000-0000-0002-0000000c4001")
	adoptTestBook(t, pool, bookID)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
		pool.Exec(ctx, `DELETE FROM book_kinds WHERE book_id=$1 AND code='coworker'`, bookID)
	})

	// A fiction kind (is_person=false, adopted) + a CUSTOM real-person kind under a NON-'colleague'
	// code with is_person=true (what the old `code<>'colleague'` filter would have missed).
	charKind := bookKindID(t, pool, bookID, "character")
	var personKind uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO book_kinds (book_id, code, name, is_person) VALUES ($1,'coworker','Coworker',true)
		 RETURNING book_kind_id`, bookID).Scan(&personKind); err != nil {
		t.Fatalf("insert coworker kind: %v", err)
	}

	seed := func(kind uuid.UUID) uuid.UUID {
		var id uuid.UUID
		if err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}')
			 RETURNING entity_id`, bookID, kind).Scan(&id); err != nil {
			t.Fatalf("seed entity: %v", err)
		}
		return id
	}
	charA := seed(charKind)
	charB := seed(charKind)
	personE := seed(personKind) // a real coworker — must NEVER be wiki-gen'd

	ids, total, err := srv.resolveWikiGenEntities(ctx, bookID, nil, 100)
	if err != nil {
		t.Fatalf("resolveWikiGenEntities: %v", err)
	}
	got := map[string]bool{}
	for _, id := range ids {
		got[id] = true
	}
	if !got[charA.String()] || !got[charB.String()] {
		t.Errorf("fiction character entities must be included in wiki-gen; got %v", ids)
	}
	if got[personE.String()] {
		t.Error("a REAL-person (is_person) entity under a custom code leaked into wiki-gen — the exact PP-4 hole")
	}
	if total != 2 {
		t.Errorf("total_matched should be 2 (the two characters only), got %d", total)
	}
}

// C4/SD-C4 (cold-review MED-2) — PP-4 protects the THIRD PARTY, not owner preference: the book-kind
// update tool must NOT let an owner CLEAR is_person on a SYSTEM-adopted person kind (re-enabling AI
// biographies of a real, non-consenting colleague). A CUSTOM (user-authored) kind stays togglable.
func TestBookKindPatch_CannotClearIsPersonOnSystemKind(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()
	srv, _ := newEntitiesListServer(t)
	srv.pool = pool

	bookID := uuid.MustParse("00000000-0000-0000-0002-0000000c4002")
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM book_kinds WHERE book_id=$1`, bookID) })

	if _, err := pool.Exec(ctx,
		`INSERT INTO book_kinds (book_id, code, name, is_person, source_ref) VALUES ($1,'colleague','Colleague',true,'system:abc')`,
		bookID); err != nil {
		t.Fatalf("seed system colleague kind: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO book_kinds (book_id, code, name, is_person) VALUES ($1,'client','Client',true)`,
		bookID); err != nil {
		t.Fatalf("seed custom person kind: %v", err)
	}

	f := false
	// clearing on the SYSTEM-adopted colleague → refused.
	if _, _, _, _, perr := srv.resolveBookPatch(ctx, bookID, bookLevelKind,
		bookPatchToolIn{BookID: bookID.String(), Code: "colleague", IsPerson: &f}); !errors.Is(perr, errCannotClearSystemPersonFlag) {
		t.Fatalf("clearing is_person on a system person kind must be refused, got %v", perr)
	}
	// clearing on the CUSTOM kind → allowed (the user-settable case).
	if _, _, _, _, perr := srv.resolveBookPatch(ctx, bookID, bookLevelKind,
		bookPatchToolIn{BookID: bookID.String(), Code: "client", IsPerson: &f}); perr != nil {
		t.Fatalf("clearing is_person on a CUSTOM kind must be allowed, got %v", perr)
	}
}

// C4/SD-C4 (cold-review LOW-4) — the adopt clone must CARRY is_person from the system kind into the
// book tier (the tier the PP-4 guards read); if it dropped the flag, an adopted real-person kind
// would be is_person=false in the book and leak into AI wiki-gen.
func TestAdopt_CarriesIsPersonFromSystemKind(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	ctx := context.Background()
	srv, _ := newEntitiesListServer(t)
	srv.pool = pool

	userID := uuid.New()
	bookID := uuid.MustParse("00000000-0000-0000-0002-0000000c4003")
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM book_kinds WHERE book_id=$1`, bookID)
		pool.Exec(ctx, `DELETE FROM system_kinds WHERE code='c4testperson'`)
	})

	if _, err := pool.Exec(ctx,
		`INSERT INTO system_kinds (code, name, is_default, is_person) VALUES ('c4testperson','Test Person',false,true)
		 ON CONFLICT (code) DO UPDATE SET is_person=true`); err != nil {
		t.Fatalf("seed system person kind: %v", err)
	}
	if err := srv.adoptBookOntologyCore(ctx, bookID, userID, nil, []string{"c4testperson"}); err != nil {
		t.Fatalf("adopt: %v", err)
	}
	var isPerson bool
	if err := pool.QueryRow(ctx,
		`SELECT is_person FROM book_kinds WHERE book_id=$1 AND code='c4testperson'`, bookID).Scan(&isPerson); err != nil {
		t.Fatalf("read adopted kind: %v", err)
	}
	if !isPerson {
		t.Fatal("adopt DROPPED is_person — an adopted real-person kind would leak into AI wiki-gen")
	}
}
