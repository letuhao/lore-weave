package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/config"
)

// newActionFixtureNoAdopt is newActionFixture without the pre-adopt — for the adopt
// round-trip (so the new-vs-present counts are non-zero and the ontology visibly grows).
func newActionFixtureNoAdopt(t *testing.T, pool *pgxpool.Pool) *actionFixture {
	t.Helper()
	runK2aMigrations(t, pool)
	owner, book := uuid.New(), uuid.New()
	ts := httptest.NewServer(projection(book, owner))
	t.Cleanup(ts.Close)
	srv := NewServer(pool, &config.Config{JWTSecret: versionTestSecret, BookServiceURL: ts.URL, InternalServiceToken: "tok"})
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject: owner.String(), ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(versionTestSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return &actionFixture{srv: srv, jwt: signed, ownerID: owner, bookID: book}
}

// adopt (C) round-trip: propose → preview (new counts) → confirm → ontology grows.
func TestBookTool_AdoptRoundTrip(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixtureNoAdopt(t, pool)
	ctx := context.Background()

	_, card, err := f.srv.toolAdoptStandards(ctxWithUser(f.ownerID), nil,
		adoptToolIn{BookID: f.bookID.String(), Genres: []string{"xianxia"}, Kinds: []string{"character"}})
	if err != nil {
		t.Fatalf("propose adopt: %v", err)
	}
	if card.Descriptor != descAdopt || card.Destructive {
		t.Fatalf("bad adopt card: %+v", card)
	}

	// preview enumerates new-vs-present (book is empty → xianxia+universal & character+unknown are new)
	if w := f.preview(t, card.ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("preview: want 200, got %d (%s)", w.Code, w.Body.String())
	} else {
		var pv actionPreview
		json.Unmarshal(w.Body.Bytes(), &pv)
		if pv.Descriptor != descAdopt || len(pv.PreviewRows) == 0 {
			t.Errorf("adopt preview should enumerate counts: %+v", pv)
		}
	}
	// confirm → adopt copy-down
	if w := f.confirm(t, card.ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("confirm adopt: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	// universal + xianxia present; character + unknown present
	for _, code := range []string{"universal", "xianxia"} {
		var n int
		pool.QueryRow(ctx, `SELECT count(*) FROM book_genres WHERE book_id=$1 AND code=$2`, f.bookID, code).Scan(&n)
		if n != 1 {
			t.Errorf("genre %q not adopted: count=%d", code, n)
		}
	}
	for _, code := range []string{"character", "unknown"} {
		var n int
		pool.QueryRow(ctx, `SELECT count(*) FROM book_kinds WHERE book_id=$1 AND code=$2`, f.bookID, code).Scan(&n)
		if n != 1 {
			t.Errorf("kind %q not adopted: count=%d", code, n)
		}
	}
	// replay the adopt confirm → single-use 422
	if w := f.confirm(t, card.ConfirmToken); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("replay adopt: want 422 single-use, got %d", w.Code)
	}
}

// create (W) — all three levels via the MCP tool, code-addressed.
func TestBookTool_CreateAllLevels(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool) // pre-adopted
	octx := ctxWithUser(f.ownerID)

	_, g, err := f.srv.toolBookCreate(octx, nil, bookCreateToolIn{BookID: f.bookID.String(), Level: "genre", Name: "Faction", Code: "t1_faction"})
	if err != nil || g.Code != "t1_faction" {
		t.Fatalf("create genre: %v %+v", err, g)
	}
	_, k, err := f.srv.toolBookCreate(octx, nil, bookCreateToolIn{BookID: f.bookID.String(), Level: "kind", Name: "Sect", Code: "t1_sect"})
	if err != nil || k.Code != "t1_sect" {
		t.Fatalf("create kind: %v %+v", err, k)
	}
	// attribute on character×universal (both adopted)
	_, a, err := f.srv.toolBookCreate(octx, nil, bookCreateToolIn{
		BookID: f.bookID.String(), Level: "attribute", Name: "Bloodline", Code: "t1_bloodline",
		KindCode: "character", GenreCode: "universal",
	})
	if err != nil || a.Code != "t1_bloodline" {
		t.Fatalf("create attr: %v %+v", err, a)
	}
	// attribute against a non-live kind_code → friendly error (not a panic/500)
	if _, _, err := f.srv.toolBookCreate(octx, nil, bookCreateToolIn{
		BookID: f.bookID.String(), Level: "attribute", Name: "X", Code: "x", KindCode: "nope", GenreCode: "universal",
	}); err == nil || !strings.Contains(err.Error(), "no live kind") {
		t.Fatalf("attr with bad kind_code: want friendly error, got %v", err)
	}
}

// patch (W) — base-version 409 on stale, success on match/opt-out.
func TestBookTool_PatchBaseVersion409(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	_, k, err := f.srv.toolBookCreate(octx, nil, bookCreateToolIn{BookID: f.bookID.String(), Level: "kind", Name: "Realm", Code: "t1_realm"})
	if err != nil {
		t.Fatalf("seed kind: %v", err)
	}

	// stale base_version → 409-style error
	nm := "Realm v2"
	if _, _, err := f.srv.toolBookPatch(octx, nil, bookPatchToolIn{
		BookID: f.bookID.String(), Level: "kind", Code: "t1_realm",
		BaseVersion: "2000-01-01T00:00:00Z", Name: &nm,
	}); err == nil || !strings.Contains(err.Error(), "changed since") {
		t.Fatalf("stale base_version: want 409, got %v", err)
	}

	// opt-out (empty base_version) → patches
	_, out, err := f.srv.toolBookPatch(octx, nil, bookPatchToolIn{
		BookID: f.bookID.String(), Level: "kind", Code: "t1_realm", Name: &nm,
	})
	if err != nil || out.Status != "patched" || out.Version == "" {
		t.Fatalf("opt-out patch: %v %+v", err, out)
	}
	var got string
	pool.QueryRow(context.Background(), `SELECT name FROM book_kinds WHERE book_id=$1 AND code='t1_realm'`, f.bookID).Scan(&got)
	if got != nm {
		t.Errorf("patch did not apply: name=%q", got)
	}
	_ = k
}

// set-active-genres delta — remove then add a genre code; no silent full-set drop.
func TestBookTool_SetActiveGenresDelta(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool) // all genres active
	octx := ctxWithUser(f.ownerID)

	_, out, err := f.srv.toolBookSetActiveGenres(octx, nil, setActiveGenresToolIn{BookID: f.bookID.String(), Remove: []string{"xianxia"}})
	if err != nil {
		t.Fatalf("remove active: %v", err)
	}
	if contains(out.ActiveCodes, "xianxia") {
		t.Errorf("xianxia should be inactive after remove: %v", out.ActiveCodes)
	}
	_, out2, err := f.srv.toolBookSetActiveGenres(octx, nil, setActiveGenresToolIn{BookID: f.bookID.String(), Add: []string{"xianxia"}})
	if err != nil {
		t.Fatalf("add active: %v", err)
	}
	if !contains(out2.ActiveCodes, "xianxia") {
		t.Errorf("xianxia should be active after add: %v", out2.ActiveCodes)
	}
	// a bogus code → friendly tenancy error, no silent skip
	if _, _, err := f.srv.toolBookSetActiveGenres(octx, nil, setActiveGenresToolIn{BookID: f.bookID.String(), Add: []string{"not_a_genre"}}); err == nil {
		t.Errorf("bogus genre code must error")
	}
}

// set-kind-genres delta + entity-genres set/get with tenancy.
func TestBookTool_KindGenresAndEntityGenres(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)
	ctx := context.Background()

	// link xianxia to the character kind
	_, kg, err := f.srv.toolBookSetKindGenres(octx, nil, setKindGenresToolIn{BookID: f.bookID.String(), KindCode: "character", Add: []string{"xianxia"}})
	if err != nil {
		t.Fatalf("set kind-genres: %v", err)
	}
	if !contains(kg.GenreCodes, "xianxia") {
		t.Errorf("xianxia not linked to character: %v", kg.GenreCodes)
	}

	// seed an entity in the character kind, set its genre override
	charKind := bookKindID(t, pool, f.bookID, "character")
	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'t1 entity') RETURNING entity_id`,
		f.bookID, charKind).Scan(&entityID); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM glossary_entities WHERE entity_id=$1`, entityID) })

	_, set, err := f.srv.toolEntitySetGenres(octx, nil, entityGenresSetToolIn{BookID: f.bookID.String(), EntityID: entityID.String(), GenreCodes: []string{"xianxia"}})
	if err != nil {
		t.Fatalf("set entity genres: %v", err)
	}
	if set.UsesBookDefault || len(set.GenreIDs) < 2 { // xianxia + universal auto-included
		t.Errorf("entity override should hold xianxia+universal: %+v", set)
	}
	_, get, err := f.srv.toolEntityGetGenres(octx, nil, entityGenresGetToolIn{BookID: f.bookID.String(), EntityID: entityID.String()})
	if err != nil || get.UsesBookDefault {
		t.Fatalf("get entity genres: %v %+v", err, get)
	}
	// clear → back to book default
	_, cleared, err := f.srv.toolEntitySetGenres(octx, nil, entityGenresSetToolIn{BookID: f.bookID.String(), EntityID: entityID.String()})
	if err != nil || !cleared.UsesBookDefault {
		t.Fatalf("clear entity genres: %v %+v", err, cleared)
	}

	// a different (non-grantee) user cannot read this book's entity genres → not accessible
	if _, _, err := f.srv.toolEntityGetGenres(ctxWithUser(uuid.New()), nil, entityGenresGetToolIn{BookID: f.bookID.String(), EntityID: entityID.String()}); err == nil {
		t.Errorf("non-grantee read must be denied")
	}
}

// patch at the attribute level exercises the 3-arg (kind_code, genre_code, code)
// resolver + base-version on book_attributes (content the kind/genre tests skip).
func TestBookTool_PatchAttributeLevel(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	if _, _, err := f.srv.toolBookCreate(octx, nil, bookCreateToolIn{
		BookID: f.bookID.String(), Level: "attribute", Name: "Title", Code: "t1_title",
		KindCode: "character", GenreCode: "universal",
	}); err != nil {
		t.Fatalf("seed attr: %v", err)
	}
	// stale base_version → 409
	nm := "Title v2"
	if _, _, err := f.srv.toolBookPatch(octx, nil, bookPatchToolIn{
		BookID: f.bookID.String(), Level: "attribute", Code: "t1_title", KindCode: "character", GenreCode: "universal",
		BaseVersion: "2000-01-01T00:00:00Z", Name: &nm,
	}); err == nil || !strings.Contains(err.Error(), "changed since") {
		t.Fatalf("stale attr patch: want 409, got %v", err)
	}
	// opt-out → patches the right (kind×genre×code) row
	if _, out, err := f.srv.toolBookPatch(octx, nil, bookPatchToolIn{
		BookID: f.bookID.String(), Level: "attribute", Code: "t1_title", KindCode: "character", GenreCode: "universal", Name: &nm,
	}); err != nil || out.Status != "patched" {
		t.Fatalf("attr patch: %v %+v", err, out)
	}
	var got string
	pool.QueryRow(context.Background(),
		`SELECT a.name FROM book_attributes a JOIN book_kinds k ON k.book_kind_id=a.kind_id
		 WHERE a.book_id=$1 AND k.code='character' AND a.code='t1_title'`, f.bookID).Scan(&got)
	if got != nm {
		t.Errorf("attr patch did not apply: name=%q", got)
	}
}

// field_type is validated on the new W tools (no DB CHECK backstops it) — a hallucinated
// type is rejected on both create and patch, on the core (so HTTP is hardened too).
func TestBookTool_AttrFieldTypeValidated(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)

	if _, _, err := f.srv.toolBookCreate(octx, nil, bookCreateToolIn{
		BookID: f.bookID.String(), Level: "attribute", Name: "Bad", Code: "t1_bad",
		KindCode: "character", GenreCode: "universal", FieldType: "dropdown",
	}); err == nil || !strings.Contains(err.Error(), "field_type") {
		t.Fatalf("create with bad field_type: want rejection, got %v", err)
	}
	// seed a valid attr, then patch its field_type to garbage → rejected
	if _, _, err := f.srv.toolBookCreate(octx, nil, bookCreateToolIn{
		BookID: f.bookID.String(), Level: "attribute", Name: "Good", Code: "t1_good",
		KindCode: "character", GenreCode: "universal", FieldType: "select", Options: []string{"a"},
	}); err != nil {
		t.Fatalf("seed valid attr: %v", err)
	}
	bad := "nonsense"
	if _, _, err := f.srv.toolBookPatch(octx, nil, bookPatchToolIn{
		BookID: f.bookID.String(), Level: "attribute", Code: "t1_good", KindCode: "character", GenreCode: "universal",
		FieldType: &bad,
	}); err == nil || !strings.Contains(err.Error(), "field_type") {
		t.Fatalf("patch to bad field_type: want rejection, got %v", err)
	}
}

// a non-grantee cannot drive any W tool — the grant gate is enforced before the write.
func TestBookTool_NonGranteeWriteDenied(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	stranger := ctxWithUser(uuid.New()) // not the book owner/grantee

	if _, _, err := f.srv.toolBookCreate(stranger, nil, bookCreateToolIn{BookID: f.bookID.String(), Level: "genre", Name: "X", Code: "x"}); err == nil {
		t.Error("non-grantee create must be denied")
	}
	if _, _, err := f.srv.toolBookSetActiveGenres(stranger, nil, setActiveGenresToolIn{BookID: f.bookID.String(), Add: []string{"xianxia"}}); err == nil {
		t.Error("non-grantee set-active-genres must be denied")
	}
	if _, _, err := f.srv.toolAdoptStandards(stranger, nil, adoptToolIn{BookID: f.bookID.String(), Genres: []string{"xianxia"}}); err == nil {
		t.Error("non-grantee adopt must be denied")
	}
}

func contains(xs []string, v string) bool {
	for _, x := range xs {
		if x == v {
			return true
		}
	}
	return false
}
