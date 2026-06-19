package api

// D-GKA-ADOPT-USER-TIER — the adopting caller's User-tier rows shadow System by
// code at adopt (caller-scoped resolution). Requires GLOSSARY_TEST_DB_URL.
// Proves: a picked code the caller customized resolves to their user row
// (source_ref 'user:…'); a picked code they didn't customize falls back to System
// ('system:…'); and the shadow holds at all three levels (genre, kind, attribute).

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestBookAdopt_UserTierShadowsSystem(t *testing.T) {
	pool := openTestDB(t)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	book := uuid.New()
	srv := newAdoptServer(t, pool, book, owner)
	ctx := context.Background()

	// Caller's user-tier overrides: xianxia + universal genres, a character kind,
	// and a 'name' attribute on (character × universal) — each sharing a code with
	// a System standard so it must shadow at adopt.
	var ugUniversal, ukChar uuid.UUID
	mustExec := func(q string, args ...any) {
		if _, err := pool.Exec(ctx, q, args...); err != nil {
			t.Fatalf("seed user tier: %v", err)
		}
	}
	mustExec(`INSERT INTO user_genres (owner_user_id, code, name) VALUES ($1,'xianxia','My Xianxia')`, owner)
	if err := pool.QueryRow(ctx,
		`INSERT INTO user_genres (owner_user_id, code, name) VALUES ($1,'universal','My Universal') RETURNING genre_id`,
		owner).Scan(&ugUniversal); err != nil {
		t.Fatalf("seed user universal: %v", err)
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO user_kinds (owner_user_id, code, name) VALUES ($1,'character','My Character') RETURNING user_kind_id`,
		owner).Scan(&ukChar); err != nil {
		t.Fatalf("seed user character: %v", err)
	}
	// content_hash set explicitly (createUserAttribute would compute it) so we can
	// assert it propagates into book_attributes.source_hash for G5 Sync.
	const userNameHash = "usr-name-hash-001"
	mustExec(`INSERT INTO user_attributes (owner_user_id, kind_id, genre_id, code, name, content_hash) VALUES ($1,$2,$3,'name','My Name Attr',$4)`,
		owner, ukChar, ugUniversal, userNameHash)

	base := "/v1/glossary/books/" + book.String()
	aw := ukReq(t, srv, http.MethodPost, base+"/adopt", owner.String(),
		`{"genres":["xianxia","romance"],"kinds":["character"]}`)
	if aw.Code != http.StatusOK {
		t.Fatalf("adopt: want 200, got %d (%s)", aw.Code, aw.Body.String())
	}
	var ont bookOntologyResp
	if err := json.Unmarshal(aw.Body.Bytes(), &ont); err != nil {
		t.Fatalf("decode ontology: %v", err)
	}

	srcPrefix := func(ref *string) string {
		if ref == nil {
			return "<nil>"
		}
		return *ref
	}
	wantUser := func(name string, ref *string) {
		if ref == nil || !strings.HasPrefix(*ref, "user:") {
			t.Fatalf("%s: want user-sourced, got source_ref=%s", name, srcPrefix(ref))
		}
	}

	// xianxia + universal genres: caller customized both → user-sourced.
	xg, ok := bookGenreByCode(ont, "xianxia")
	if !ok {
		t.Fatal("xianxia genre missing")
	}
	wantUser("xianxia genre", xg.SourceRef)
	ug, ok := bookGenreByCode(ont, "universal")
	if !ok {
		t.Fatal("universal genre missing")
	}
	wantUser("universal genre", ug.SourceRef)

	// romance: NOT customized → falls back to System.
	rg, ok := bookGenreByCode(ont, "romance")
	if !ok {
		t.Fatal("romance genre missing")
	}
	if rg.SourceRef == nil || !strings.HasPrefix(*rg.SourceRef, "system:") {
		t.Fatalf("romance genre: want system-sourced, got %s", srcPrefix(rg.SourceRef))
	}

	// character kind: customized → user-sourced.
	ck, ok := kindByCode(ont, "character")
	if !ok {
		t.Fatal("character kind missing")
	}
	wantUser("character kind", ck.SourceRef)

	// the 'name' attribute on character × universal: user shadows the System attr,
	// and the user attr's content_hash propagates into the book's source_hash (G5 Sync).
	var found bool
	for _, a := range ont.Attributes {
		if a.KindID == ck.BookKindID && a.GenreID == ug.GenreID && a.Code == "name" {
			found = true
			wantUser("name attr", a.SourceRef)
		}
	}
	if !found {
		t.Fatal("name attribute on character×universal missing after adopt")
	}
	var bookNameHash string
	if err := pool.QueryRow(ctx,
		`SELECT source_hash FROM book_attributes
		 WHERE book_id=$1 AND kind_id=$2 AND genre_id=$3 AND code='name' AND deprecated_at IS NULL`,
		book, ck.BookKindID, ug.GenreID).Scan(&bookNameHash); err != nil {
		t.Fatalf("read book name-attr source_hash: %v", err)
	}
	if bookNameHash != userNameHash {
		t.Fatalf("user attr content_hash not propagated to source_hash: got %q want %q", bookNameHash, userNameHash)
	}

	// Re-adopt with the SAME picks is idempotent even with the user tier in play:
	// counts stable AND provenance unchanged (no system row clobbering a user one).
	countUserSourced := func(label string) (genres, kinds, attrs int) {
		q := func(sql string) int {
			var n int
			if err := pool.QueryRow(ctx, sql, book).Scan(&n); err != nil {
				t.Fatalf("%s count (%s): %v", label, sql, err)
			}
			return n
		}
		genres = q(`SELECT count(*) FROM book_genres WHERE book_id=$1 AND source_ref LIKE 'user:%'`)
		kinds = q(`SELECT count(*) FROM book_kinds WHERE book_id=$1 AND source_ref LIKE 'user:%'`)
		attrs = q(`SELECT count(*) FROM book_attributes WHERE book_id=$1 AND source_ref LIKE 'user:%'`)
		return
	}
	g1, k1, a1 := countUserSourced("pre")
	base2 := "/v1/glossary/books/" + book.String()
	if w := ukReq(t, srv, http.MethodPost, base2+"/adopt", owner.String(),
		`{"genres":["xianxia","romance"],"kinds":["character"]}`); w.Code != http.StatusOK {
		t.Fatalf("re-adopt: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	g2, k2, a2 := countUserSourced("post")
	if g1 != g2 || k1 != k2 || a1 != a2 {
		t.Fatalf("re-adopt changed user-sourced provenance: genres %d→%d kinds %d→%d attrs %d→%d", g1, g2, k1, k2, a1, a2)
	}
}
