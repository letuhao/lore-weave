package api

// W10-M1 world MCP tools + world→bible internal route. Validation/owner-scoping
// guards run always; the DB-backed create/get/list/move happy paths require
// BOOK_TEST_DATABASE_URL (dbTestServer), matching the other *_db_test.go files.

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/book-service/internal/config"
)

// ── validation (no DB) ───────────────────────────────────────────────────────

func TestToolWorldCreate_RequiresName(t *testing.T) {
	t.Parallel()
	s := &Server{} // name check short-circuits before any pool access
	ctx := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: "   "}); err == nil {
		t.Fatal("expected an error for an empty/whitespace name")
	}
}

func TestToolWorldGet_RejectsBadUUID(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ctx := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldGet(ctx, nil, worldGetIn{WorldID: "not-a-uuid"}); err == nil {
		t.Fatal("expected an error for a non-UUID world_id")
	}
}

// The world→bible internal route's pre-pool guards: world_id parse + the user_id
// parent-scope vector (a bad/missing user_id must NOT reach the ownership query).
func TestGetInternalWorldBible_InvalidWorldID(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodGet, "/internal/worlds/not-a-uuid/bible?user_id="+uuid.New().String(), "", "", map[string]string{"world_id": "not-a-uuid"})
	s.getInternalWorldBible(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid world_id, got %d", rr.Code)
	}
}

func TestGetInternalWorldBible_MissingUserID(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	wid := uuid.New()
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodGet, "/internal/worlds/"+wid.String()+"/bible", "", "", map[string]string{"world_id": wid.String()})
	s.getInternalWorldBible(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for missing user_id, got %d", rr.Code)
	}
}

func TestGetInternalWorldBible_RequiresInternalToken(t *testing.T) {
	t.Parallel()
	s := &Server{cfg: &config.Config{InternalServiceToken: "secret-internal-token"}}
	srv := httptest.NewServer(s.Router())
	defer srv.Close()
	resp, err := http.Get(srv.URL + "/internal/worlds/" + uuid.New().String() + "/bible?user_id=" + uuid.New().String())
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 without internal token, got %d", resp.StatusCode)
	}
}

// ── DB-backed happy paths + owner-scoping ────────────────────────────────────

func TestToolWorldCreateGetList(t *testing.T) {
	s, _ := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	_, out, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: "Aethelmoor", Description: "a realm"})
	if err != nil {
		t.Fatalf("world_create: %v", err)
	}
	if out.World.WorldID == "" || out.World.BibleBookID == nil || out.World.BibleChapterID == nil {
		t.Fatalf("world_create must provision a world + bible book + bible chapter: %+v", out.World)
	}

	_, gout, err := s.toolWorldGet(ctx, nil, worldGetIn{WorldID: out.World.WorldID})
	if err != nil {
		t.Fatalf("world_get: %v", err)
	}
	if gout.World.Name != "Aethelmoor" || gout.World.BibleBookID == nil {
		t.Fatalf("world_get lost data: %+v", gout.World)
	}

	_, lout, err := s.toolWorldList(ctx, nil, worldListIn{})
	if err != nil {
		t.Fatalf("world_list: %v", err)
	}
	found := false
	for _, wd := range lout.Worlds {
		if wd.WorldID == out.World.WorldID {
			found = true
		}
	}
	if !found {
		t.Fatalf("world_list must include the created world; got %d worlds", len(lout.Worlds))
	}
}

// A world is OWNER-scoped: user B cannot read user A's world (no existence oracle).
func TestToolWorldGet_OwnerScoped(t *testing.T) {
	s, _ := dbTestServer(t)
	ownerA, ownerB := uuid.New(), uuid.New()

	_, out, err := s.toolWorldCreate(identityCtxForTest(t, ownerA), nil, worldCreateIn{Name: "A-only"})
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	if _, _, err := s.toolWorldGet(identityCtxForTest(t, ownerB), nil, worldGetIn{WorldID: out.World.WorldID}); err == nil {
		t.Fatal("owner B must NOT be able to read owner A's world")
	}
}

// The world→bible internal route resolves the same bible handle world_create returns.
func TestGetInternalWorldBible_ResolvesBible(t *testing.T) {
	s, _ := dbTestServer(t)
	owner := uuid.New()
	_, out, err := s.toolWorldCreate(identityCtxForTest(t, owner), nil, worldCreateIn{Name: "BibleResolve"})
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodGet,
		"/internal/worlds/"+out.World.WorldID+"/bible?user_id="+owner.String(),
		"", "", map[string]string{"world_id": out.World.WorldID})
	s.getInternalWorldBible(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["bible_book_id"] == nil || body["bible_chapter_id"] == nil {
		t.Fatalf("bible resolution must return the book+chapter: %+v", body)
	}
	if body["bible_book_id"] != *out.World.BibleBookID {
		t.Fatalf("bible_book_id mismatch: route=%v tool=%v", body["bible_book_id"], *out.World.BibleBookID)
	}
}
