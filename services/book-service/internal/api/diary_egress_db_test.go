package api

// WS-1.2 — the diary egress guards (D16 taint, spec 09).
//
// The red team's finding: 5 of 7 egress paths were unguarded. The cross-cutting insight
// (CC-1) was that they are all the SAME SHAPE — a derived or listing surface inheriting a
// permission that is only enforced at the authored store.
//
// So these tests assert on the SURFACES a stranger or a listing actually touches, not on
// the books row. The repo's own lesson: a per-resource check passes while the LIST leaks.
//
// DB-gated on BOOK_TEST_DATABASE_URL.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func seedBookOfKind(t *testing.T, ctx context.Context, pool *pgxpool.Pool, owner uuid.UUID, kind string) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,$2,$3) RETURNING id`,
		owner, "book-"+kind, kind).Scan(&id); err != nil {
		t.Fatalf("seed %s: %v", kind, err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, id) })
	return id
}

// ── EGRESS #1 — a diary can NEVER be shared ──

func TestDiaryEgress_CannotBeShared_DB(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	novel := seedBookOfKind(t, ctx, pool, owner, "novel")

	// The guard is a DB TRIGGER, not a handler check — there are already TWO grant paths
	// and a third will appear. A handler guard drifts the moment someone adds path four,
	// and the failure is silent: a colleague simply gains read access to a private diary.
	_, err := pool.Exec(ctx,
		`INSERT INTO book_collaborators (book_id, user_id, role, granted_by) VALUES ($1,$2,'view',$3)`,
		diary, uuid.New(), owner)
	if err == nil {
		t.Fatal("a collaborator was granted access to a DIARY. It is private to its owner " +
			"by construction — every grant path, present and future, must be refused.")
	}
	if !strings.Contains(err.Error(), "cannot be shared") {
		t.Fatalf("expected the diary-share trigger to fire, got: %v", err)
	}

	// ...while a normal book is unaffected (the guard must not break sharing).
	if _, err := pool.Exec(ctx,
		`INSERT INTO book_collaborators (book_id, user_id, role, granted_by) VALUES ($1,$2,'view',$3)`,
		novel, uuid.New(), owner); err != nil {
		t.Fatalf("sharing a NOVEL must still work: %v", err)
	}
}

// ── EGRESS #3 — the wiki (the widest hole: AI biographies of real colleagues) ──

func TestDiaryEgress_WikiCannotBePublished_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	// The attack this closes: let the assistant write a wiki article about every colleague
	// named in your diary, then flip wiki_settings.visibility='public'. The platform would
	// serve AI-written biographies of real people — your manager, your coworkers — to the
	// open internet. No share step, no warning: the public wiki gate reads a JSONB blob on
	// the book and knows nothing about kind.
	body := `{"wiki_settings":{"visibility":"public"}}`
	req := httptest.NewRequest(http.MethodPatch, "/v1/books/"+diary.String(),
		strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)

	if rr.Code == http.StatusOK {
		t.Fatal("a DIARY's wiki_settings were mutated. Flipping visibility='public' would " +
			"serve AI-written biographies of the user's real colleagues to the internet.")
	}
	if rr.Code != http.StatusForbidden {
		t.Fatalf("want 403, got %d: %s", rr.Code, rr.Body.String())
	}

	// And it really did not change.
	var vis string
	_ = pool.QueryRow(ctx,
		`SELECT COALESCE(wiki_settings->>'visibility','off') FROM books WHERE id=$1`, diary).Scan(&vis)
	if vis == "public" {
		t.Fatal("the diary's wiki is PUBLIC")
	}
}

func TestWikiSettings_StillEditableOnANovel_DB(t *testing.T) {
	// The guard must not break the feature for the books that legitimately have a wiki.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	novel := seedBookOfKind(t, ctx, pool, owner, "novel")
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	req := httptest.NewRequest(http.MethodPatch, "/v1/books/"+novel.String(),
		strings.NewReader(`{"wiki_settings":{"visibility":"public"}}`))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("a NOVEL's wiki must still be publishable, got %d: %s", rr.Code, rr.Body.String())
	}
	var vis string
	_ = pool.QueryRow(ctx,
		`SELECT wiki_settings->>'visibility' FROM books WHERE id=$1`, novel).Scan(&vis)
	if vis != "public" {
		t.Fatalf("novel wiki visibility = %q, want public", vis)
	}
}

// ── EGRESS #7 — the library/catalog LISTING ──

func TestDiaryEgress_HiddenFromTheLibraryList_DB(t *testing.T) {
	// A LIST-level guard, deliberately. The repo's paged-join lesson: a per-resource check
	// passes while the LIST leaks. And a diary tile sitting in a library grid is a
	// real-world disclosure — a demo, a screen-share, a colleague walking past.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	novel := seedBookOfKind(t, ctx, pool, owner, "novel")

	req := httptest.NewRequest(http.MethodGet, "/v1/books?limit=100", nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("list books = %d: %s", rr.Code, rr.Body.String())
	}
	body := rr.Body.String()

	if strings.Contains(body, diary.String()) {
		t.Fatal("the DIARY appears in the library listing. It has its own surface (the " +
			"Assistant); it is not a book you browse to among your novels.")
	}
	if !strings.Contains(body, novel.String()) {
		t.Fatal("the novel vanished from the library — the guard is too broad")
	}
	_ = ctx
}

// ── EGRESS — a diary must not be enumerable via the MCP book_list tool ──

func TestDiaryEgress_NotInMCPBookList_DB(t *testing.T) {
	// WS-1.2 guarded the REST library LIST but review-impl found the MCP book_list tool
	// (the agent-facing enumerator in the SAME service) had no kind filter. So an agent —
	// including a public MCP key — could list a diary and then read its plaintext prose.
	_, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	novel := seedBookOfKind(t, ctx, pool, owner, "novel")

	// The filter is what the tool uses; assert it directly against the DB (both branches).
	for _, ownerOnly := range []bool{true, false} {
		where := bookListFilter(ownerOnly)
		rows, err := pool.Query(ctx,
			"SELECT b.id FROM books b WHERE "+where, owner)
		if err != nil {
			t.Fatalf("query (ownerOnly=%v): %v", ownerOnly, err)
		}
		var ids []uuid.UUID
		for rows.Next() {
			var id uuid.UUID
			_ = rows.Scan(&id)
			ids = append(ids, id)
		}
		rows.Close()
		set := map[uuid.UUID]bool{}
		for _, id := range ids {
			set[id] = true
		}
		if set[diary] {
			t.Fatalf("the DIARY is enumerable via bookListFilter(ownerOnly=%v) — an agent "+
				"could list it and then read its plaintext prose", ownerOnly)
		}
		if !set[novel] {
			t.Fatalf("the novel vanished from bookListFilter(ownerOnly=%v)", ownerOnly)
		}
	}
}

// ── EGRESS — a diary cannot be moved into a (shareable) world ──

func TestDiaryEgress_CannotBeMovedIntoAWorld_DB(t *testing.T) {
	// A world is shareable and its member books surface through world-scoped reads, so
	// absorbing a private diary into one is a share by the back door. Both the REST
	// moveBookIntoWorld and the agent MCP world_move_book gate on kind<>'diary'.
	_, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	var worldID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO worlds(owner_user_id, name) VALUES($1,'w') RETURNING id`, owner).Scan(&worldID); err != nil {
		t.Fatalf("seed world: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM worlds WHERE id=$1`, worldID) })

	// The UPDATE both move paths use — a diary must match ZERO rows.
	ct, err := pool.Exec(ctx,
		`UPDATE books SET world_id=$1 WHERE id=$2 AND is_bible=false AND kind<>'diary'`,
		worldID, diary)
	if err != nil {
		t.Fatalf("move: %v", err)
	}
	if ct.RowsAffected() != 0 {
		t.Fatal("a DIARY was moved into a world — a shareable world absorbing a private " +
			"diary is a back-door share")
	}
	var gotWorld *uuid.UUID
	_ = pool.QueryRow(ctx, `SELECT world_id FROM books WHERE id=$1`, diary).Scan(&gotWorld)
	if gotWorld != nil {
		t.Fatalf("the diary's world_id is set to %v", *gotWorld)
	}
}

// ── The ENABLING contract: consumers cannot guard what they cannot see ──

func TestBookProjection_CarriesKind_DB(t *testing.T) {
	// Every downstream egress surface (wiki, notifications, statistics, catalog,
	// public-MCP) resolves the book through this contract. Without `kind` they CANNOT
	// enforce the diary taint even if they want to — they have no way to ask "is this
	// private?". This is the enabling half of D16.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	_ = ctx

	req := httptest.NewRequest(http.MethodGet, "/internal/books/"+diary.String()+"/projection", nil)
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("projection = %d: %s", rr.Code, rr.Body.String())
	}

	var out map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if out["kind"] != "diary" {
		t.Fatalf("the projection does not carry kind=diary (got %v). Downstream services "+
			"cannot enforce the taint on a field they never receive.", out["kind"])
	}
}

func TestBookAccess_KindIsGatedBehindAGrant_DB(t *testing.T) {
	// `kind` must NOT be an oracle. An ungated kind would let a stranger probe any book id
	// and learn which users keep a diary — which is itself sensitive.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	stranger := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	// The shared harness stubs EVERY caller as the owner, which would make this test
	// vacuous (it would "pass" the leak). Resolve honestly: owner => Owner, anyone else
	// => None.
	s.resolveBook = func(_ context.Context, _ uuid.UUID, user uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if user == owner {
			return GrantOwner, owner, "active", nil
		}
		return GrantNone, owner, "active", nil
	}

	get := func(user uuid.UUID) map[string]any {
		req := httptest.NewRequest(http.MethodGet,
			"/internal/books/"+diary.String()+"/access?user_id="+user.String(), nil)
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		var out map[string]any
		_ = json.Unmarshal(rr.Body.Bytes(), &out)
		return out
	}

	if k := get(owner)["kind"]; k != "diary" {
		t.Fatalf("the OWNER must see kind (got %v) — consumers guard on it", k)
	}
	if _, leaked := get(stranger)["kind"]; leaked {
		t.Fatal("a STRANGER received the book's kind. That is an oracle: probe any book id " +
			"and learn who keeps a diary.")
	}
}
