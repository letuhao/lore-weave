package api

// F1 — system-tier attribute descriptions, end-to-end propagation. Requires
// GLOSSARY_TEST_DB_URL. Proves the sync-only (no-backfill) design works through the
// REAL adopt + sync handlers:
//   (1) a book adopted BEFORE the F1 migration clones empty descriptions, and the
//       migration's content_hash bump surfaces those attrs as update_available with
//       the authored description in `theirs`;
//   (2) take_theirs pulls the description into the book row; keep_mine preserves a
//       local edit (and silences the row);
//   (3) a book adopted AFTER the migration carries the descriptions immediately.

import (
	"context"
	"net/http"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/migrate"
)

const f1AliasesDesc = "Other names, titles, epithets, or nicknames the character is known by."

func TestF1SystemAttrDesc_PropagatesThroughAdoptAndSync(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool) // seeds system_attributes WITHOUT descriptions (F1 step not run yet)
	ctx := context.Background()
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	base := "/v1/glossary/books/" + book.String()

	// Shared-DB isolation: the F1 migration permanently fills the seeded character
	// descriptions, so on a re-used test DB the "adopt clones empty" precondition would
	// not hold. Reset the character kind's system attrs to the pristine pre-F1 state
	// (empty description + the empty-description hash the seed originally produced) so
	// the test is deterministic regardless of prior runs.
	if _, err := pool.Exec(ctx, `
		UPDATE system_attributes sa
		SET description = NULL,
		    content_hash = md5(sa.code||'|'||sa.name||'|'||''||'|'||sa.field_type||'|'||
		                       (sa.is_required)::text||'|'||COALESCE(array_to_string(sa.options,','),''))
		FROM system_kinds sk
		WHERE sa.kind_id=sk.kind_id AND sk.code='character'`); err != nil {
		t.Fatalf("reset character system descriptions: %v", err)
	}

	// Adopt the seeded character kind BEFORE the F1 migration → book_attributes carry
	// empty descriptions + the empty-description content_hash as source_hash.
	if w := ukReq(t, srv, http.MethodPost, base+"/adopt", owner.String(),
		`{"genres":["fantasy"],"kinds":["character"]}`); w.Code != http.StatusOK {
		t.Fatalf("adopt: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if up := syncAvailable(t, srv, book, owner); len(up.Updates) != 0 {
		t.Fatalf("fresh adopt: want 0 updates, got %d (%+v)", len(up.Updates), up.Updates)
	}

	charKind := bookKindID(t, pool, book, "character")
	aliasesAttrID := bookAttrID(t, pool, book, charKind, "aliases").String()
	roleAttrID := bookAttrID(t, pool, book, charKind, "role").String()

	// A local edit on the book's `role` description — keep_mine must preserve this.
	if _, err := pool.Exec(ctx, `
		UPDATE book_attributes ba SET description='LOCAL EDIT'
		FROM book_kinds bk
		WHERE ba.kind_id=bk.book_kind_id AND bk.book_id=$1 AND bk.code='character' AND ba.code='role'`,
		book); err != nil {
		t.Fatalf("local edit role description: %v", err)
	}

	// Run the F1 migration: sets System descriptions + bumps their content_hash.
	if err := migrate.UpSystemAttrDescriptions(ctx, pool); err != nil {
		t.Fatalf("UpSystemAttrDescriptions: %v", err)
	}

	// The character attrs now surface as update_available; `theirs` previews the
	// authored description (the original extraction-guidance gap, now filled).
	up := syncAvailable(t, srv, book, owner)
	aUp, ok := findUpdate(up.Updates, "attribute", "aliases")
	if !ok || aUp.Status != syncStatusUpdate || aUp.Theirs == nil || derefStr(aUp.Theirs.Description) != f1AliasesDesc {
		t.Fatalf("aliases update: got %+v (theirs=%+v)", aUp, aUp.Theirs)
	}
	rUp, ok := findUpdate(up.Updates, "attribute", "role")
	if !ok || rUp.Status != syncStatusUpdate || rUp.Theirs == nil ||
		derefStr(rUp.Theirs.Description) != "The character's narrative role (protagonist, antagonist, mentor, foil, …)." {
		t.Fatalf("role update: got %+v (theirs=%+v)", rUp, rUp.Theirs)
	}
	// The display-key `name` attr carries no description → must NOT surface as an update.
	if _, ok := findUpdate(up.Updates, "attribute", "name"); ok {
		t.Fatalf("character.name (display key) surfaced as a sync update — it should be left empty")
	}

	// Apply: take_theirs for aliases (pull the description), keep_mine for role (preserve LOCAL EDIT).
	applyBody := `{"items":[
		{"entity":"attribute","id":"` + aliasesAttrID + `","choice":"take_theirs"},
		{"entity":"attribute","id":"` + roleAttrID + `","choice":"keep_mine"}
	]}`
	aw := ukReq(t, srv, http.MethodPost, base+"/sync/apply", owner.String(), applyBody)
	if aw.Code != http.StatusOK {
		t.Fatalf("sync/apply: want 200, got %d (%s)", aw.Code, aw.Body.String())
	}

	// take_theirs pulled the authored description into the book row.
	var gotAliases string
	if err := pool.QueryRow(ctx, `SELECT description FROM book_attributes WHERE attr_id=$1`, aliasesAttrID).Scan(&gotAliases); err != nil {
		t.Fatalf("read book aliases: %v", err)
	}
	if gotAliases != f1AliasesDesc {
		t.Fatalf("aliases take_theirs: want authored description, got %q", gotAliases)
	}
	// keep_mine left the local edit intact.
	var gotRole string
	if err := pool.QueryRow(ctx, `SELECT description FROM book_attributes WHERE attr_id=$1`, roleAttrID).Scan(&gotRole); err != nil {
		t.Fatalf("read book role: %v", err)
	}
	if gotRole != "LOCAL EDIT" {
		t.Fatalf("role keep_mine: want preserved 'LOCAL EDIT', got %q", gotRole)
	}
	// The two applied rows are reconciled (take_theirs pulled, keep_mine silenced) and
	// drop out of the diff; the other 10 character attrs we left untouched still pend.
	post := syncAvailable(t, srv, book, owner)
	if _, ok := findUpdate(post.Updates, "attribute", "aliases"); ok {
		t.Fatalf("aliases still update_available after take_theirs — not reconciled")
	}
	if _, ok := findUpdate(post.Updates, "attribute", "role"); ok {
		t.Fatalf("role still update_available after keep_mine — not silenced")
	}
	if len(post.Updates) != 10 {
		t.Fatalf("post-apply: want 10 remaining (12 described char attrs − 2 applied), got %d (%+v)", len(post.Updates), post.Updates)
	}

	// New-adopt AFTER the migration: a fresh book carries descriptions immediately.
	book2 := uuid.New()
	srv2 := newAdoptServer(t, pool, book2, owner)
	if w := ukReq(t, srv2, http.MethodPost, "/v1/glossary/books/"+book2.String()+"/adopt", owner.String(),
		`{"genres":["fantasy"],"kinds":["character"]}`); w.Code != http.StatusOK {
		t.Fatalf("adopt book2: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var book2Aliases string
	if err := pool.QueryRow(ctx, `
		SELECT ba.description FROM book_attributes ba
		JOIN book_kinds bk ON bk.book_kind_id=ba.kind_id
		WHERE bk.book_id=$1 AND bk.code='character' AND ba.code='aliases'`,
		book2).Scan(&book2Aliases); err != nil {
		t.Fatalf("read book2 aliases: %v", err)
	}
	if book2Aliases != f1AliasesDesc {
		t.Fatalf("new-adopt aliases: want authored description carried at adopt, got %q", book2Aliases)
	}
}
