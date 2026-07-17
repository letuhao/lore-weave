package api

// S-02 — manuscript parts (acts/volumes) DB-gated tests. Real Postgres because
// they exercise the UNIQUE(book_id, sort_order) two-phase reorder, the
// archive→un-home-chapters transaction, the id+book_id tenancy scoping, the
// cross-book move breach, and the part_id-on-chapters projection the FE navigator
// groups on. Gated on BOOK_TEST_DATABASE_URL like steering_db_test.go (skipped
// when unset).

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

// seedPartsBook inserts an active book owned by ownerID.
func seedPartsBook(t *testing.T, ctx context.Context, pool *pgxpool.Pool, ownerID uuid.UUID) uuid.UUID {
	t.Helper()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'parts') RETURNING id`, ownerID).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	return bookID
}

// seedPartsChapter inserts an active chapter in bookID at sortOrder, optionally
// homed in partID (nil = flat). Returns the chapter id.
func seedPartsChapter(t *testing.T, ctx context.Context, pool *pgxpool.Pool, bookID uuid.UUID, sortOrder int, partID *uuid.UUID) uuid.UUID {
	t.Helper()
	var chID uuid.UUID
	// Deliberately NULL title — titleless chapters are common (imports/empty), and a
	// NULL title into a non-pointer Scan destination is exactly what broke part_id in
	// listChapters (the discarded-error zero-row bug). Seeding NULL exercises the fix.
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status,part_id)
VALUES($1,'c.txt','en','text/plain',$2,$3,'active','draft',$4) RETURNING id`,
		bookID, sortOrder, "k-"+uuid.NewString(), partID).Scan(&chID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	return chID
}

func partsHTTP(t *testing.T, s *Server, caller uuid.UUID, method, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, caller))
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func decodeMap(t *testing.T, raw []byte) map[string]any {
	t.Helper()
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("decode: %v — raw %s", err, raw)
	}
	return out
}

func ownerResolver(owner uuid.UUID) func(context.Context, uuid.UUID, uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
	return func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
}

// Full CRUD round-trip as the book owner: create → list → rename → reorder →
// archive → include_trashed → restore.
func TestParts_CRUD_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx, pool, owner)
	s.resolveBook = ownerResolver(owner)
	base := "/v1/books/" + bookID.String() + "/parts"

	// create #1 — sort_order 1, path synthesized from title
	rr := partsHTTP(t, s, owner, http.MethodPost, base, `{"title":"Rising Action"}`)
	if rr.Code != http.StatusCreated {
		t.Fatalf("create #1 = %d, want 201\n%s", rr.Code, rr.Body.String())
	}
	p1 := decodeMap(t, rr.Body.Bytes())
	if p1["sort_order"].(float64) != 1 {
		t.Fatalf("first part sort_order = %v, want 1", p1["sort_order"])
	}
	if p1["path"] != "rising-action" {
		t.Fatalf("path = %v, want slugified 'rising-action'", p1["path"])
	}
	if p1["title"] != "Rising Action" || p1["lifecycle_state"] != "active" {
		t.Fatalf("part #1 wrong: %v", p1)
	}
	id1 := p1["part_id"].(string)

	// create #2 — sort_order 2
	rr = partsHTTP(t, s, owner, http.MethodPost, base, `{"title":"Climax"}`)
	if rr.Code != http.StatusCreated {
		t.Fatalf("create #2 = %d\n%s", rr.Code, rr.Body.String())
	}
	p2 := decodeMap(t, rr.Body.Bytes())
	if p2["sort_order"].(float64) != 2 {
		t.Fatalf("second part sort_order = %v, want 2", p2["sort_order"])
	}
	id2 := p2["part_id"].(string)

	// list — two active, in order
	rr = partsHTTP(t, s, owner, http.MethodGet, base, "")
	if rr.Code != http.StatusOK {
		t.Fatalf("list = %d\n%s", rr.Code, rr.Body.String())
	}
	var listed struct {
		Items []map[string]any `json:"items"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &listed)
	if len(listed.Items) != 2 || listed.Items[0]["part_id"] != id1 || listed.Items[1]["part_id"] != id2 {
		t.Fatalf("list wrong: %+v", listed.Items)
	}

	// rename #1
	rr = partsHTTP(t, s, owner, http.MethodPatch, base+"/"+id1, `{"title":"Act One"}`)
	if rr.Code != http.StatusOK {
		t.Fatalf("rename = %d\n%s", rr.Code, rr.Body.String())
	}
	if decodeMap(t, rr.Body.Bytes())["title"] != "Act One" {
		t.Fatal("rename did not stick")
	}

	// reorder → [id2, id1]
	rr = partsHTTP(t, s, owner, http.MethodPost, base+"/reorder", `{"ordered_ids":["`+id2+`","`+id1+`"]}`)
	if rr.Code != http.StatusOK {
		t.Fatalf("reorder = %d\n%s", rr.Code, rr.Body.String())
	}
	rr = partsHTTP(t, s, owner, http.MethodGet, base, "")
	_ = json.Unmarshal(rr.Body.Bytes(), &listed)
	if listed.Items[0]["part_id"] != id2 || listed.Items[1]["part_id"] != id1 {
		t.Fatalf("post-reorder order wrong: %+v", listed.Items)
	}
	if listed.Items[0]["sort_order"].(float64) != 1 || listed.Items[1]["sort_order"].(float64) != 2 {
		t.Fatalf("reorder did not produce dense 1..N: %+v", listed.Items)
	}

	// archive #1 → 204
	if rr = partsHTTP(t, s, owner, http.MethodDelete, base+"/"+id1, ""); rr.Code != http.StatusNoContent {
		t.Fatalf("archive = %d, want 204\n%s", rr.Code, rr.Body.String())
	}
	// active list now excludes it
	rr = partsHTTP(t, s, owner, http.MethodGet, base, "")
	_ = json.Unmarshal(rr.Body.Bytes(), &listed)
	if len(listed.Items) != 1 || listed.Items[0]["part_id"] != id2 {
		t.Fatalf("active list after archive wrong: %+v", listed.Items)
	}
	// include_trashed shows both
	rr = partsHTTP(t, s, owner, http.MethodGet, base+"?include_trashed=true", "")
	_ = json.Unmarshal(rr.Body.Bytes(), &listed)
	if len(listed.Items) != 2 {
		t.Fatalf("include_trashed = %d items, want 2", len(listed.Items))
	}

	// restore #1
	if rr = partsHTTP(t, s, owner, http.MethodPost, base+"/"+id1+"/restore", ""); rr.Code != http.StatusOK {
		t.Fatalf("restore = %d\n%s", rr.Code, rr.Body.String())
	}
	if decodeMap(t, rr.Body.Bytes())["lifecycle_state"] != "active" {
		t.Fatal("restore did not reactivate")
	}
}

// Archive un-homes its chapters (part_id → NULL) — they SURVIVE in the flat
// manuscript, never cascade-deleted; restore does NOT re-home them.
func TestParts_ArchiveUnhomesChaptersNotCascade_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx, pool, owner)
	s.resolveBook = ownerResolver(owner)
	base := "/v1/books/" + bookID.String() + "/parts"

	rr := partsHTTP(t, s, owner, http.MethodPost, base, `{"title":"Act I"}`)
	partID := uuid.MustParse(decodeMap(t, rr.Body.Bytes())["part_id"].(string))
	ch1 := seedPartsChapter(t, ctx, pool, bookID, 1, &partID)
	ch2 := seedPartsChapter(t, ctx, pool, bookID, 2, &partID)

	if rr = partsHTTP(t, s, owner, http.MethodDelete, base+"/"+partID.String(), ""); rr.Code != http.StatusNoContent {
		t.Fatalf("archive = %d\n%s", rr.Code, rr.Body.String())
	}

	// Both chapters SURVIVE (active) with part_id NULL.
	for _, ch := range []uuid.UUID{ch1, ch2} {
		var lifecycle string
		var pid *uuid.UUID
		if err := pool.QueryRow(ctx, `SELECT lifecycle_state, part_id FROM chapters WHERE id=$1`, ch).Scan(&lifecycle, &pid); err != nil {
			t.Fatalf("chapter %s gone after archive — cascade-deleted?! %v", ch, err)
		}
		if lifecycle != "active" {
			t.Fatalf("chapter %s lifecycle = %q, want active (un-home, not delete)", ch, lifecycle)
		}
		if pid != nil {
			t.Fatalf("chapter %s still homed (part_id=%v) after archive", ch, *pid)
		}
	}

	// Restore does NOT re-home — chapters stay flat (explicit, non-magical).
	if rr = partsHTTP(t, s, owner, http.MethodPost, base+"/"+partID.String()+"/restore", ""); rr.Code != http.StatusOK {
		t.Fatalf("restore = %d\n%s", rr.Code, rr.Body.String())
	}
	var pid *uuid.UUID
	_ = pool.QueryRow(ctx, `SELECT part_id FROM chapters WHERE id=$1`, ch1).Scan(&pid)
	if pid != nil {
		t.Fatalf("restore re-homed a chapter (part_id=%v) — should stay flat", *pid)
	}
}

// Move a chapter into / out of an act; unknown chapter → 404.
func TestParts_MoveChapter_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx, pool, owner)
	s.resolveBook = ownerResolver(owner)
	base := "/v1/books/" + bookID.String() + "/parts"

	rr := partsHTTP(t, s, owner, http.MethodPost, base, `{"title":"Act I"}`)
	partID := decodeMap(t, rr.Body.Bytes())["part_id"].(string)
	ch := seedPartsChapter(t, ctx, pool, bookID, 1, nil) // starts flat
	chPath := "/v1/books/" + bookID.String() + "/chapters/" + ch.String() + "/part"

	// move INTO the act
	rr = partsHTTP(t, s, owner, http.MethodPatch, chPath, `{"part_id":"`+partID+`"}`)
	if rr.Code != http.StatusOK {
		t.Fatalf("move-in = %d\n%s", rr.Code, rr.Body.String())
	}
	if decodeMap(t, rr.Body.Bytes())["part_id"] != partID {
		t.Fatal("move-in response did not echo part_id")
	}
	var pid *uuid.UUID
	_ = pool.QueryRow(ctx, `SELECT part_id FROM chapters WHERE id=$1`, ch).Scan(&pid)
	if pid == nil || pid.String() != partID {
		t.Fatalf("part_id not persisted: %v", pid)
	}

	// un-home (part_id: null)
	rr = partsHTTP(t, s, owner, http.MethodPatch, chPath, `{"part_id":null}`)
	if rr.Code != http.StatusOK {
		t.Fatalf("un-home = %d\n%s", rr.Code, rr.Body.String())
	}
	_ = pool.QueryRow(ctx, `SELECT part_id FROM chapters WHERE id=$1`, ch).Scan(&pid)
	if pid != nil {
		t.Fatalf("un-home did not NULL part_id: %v", *pid)
	}

	// missing field → 400 (not a silent no-op)
	if rr = partsHTTP(t, s, owner, http.MethodPatch, chPath, `{}`); rr.Code != http.StatusBadRequest {
		t.Fatalf("missing part_id = %d, want 400\n%s", rr.Code, rr.Body.String())
	}

	// unknown chapter → 404
	unknown := "/v1/books/" + bookID.String() + "/chapters/" + uuid.NewString() + "/part"
	if rr = partsHTTP(t, s, owner, http.MethodPatch, unknown, `{"part_id":null}`); rr.Code != http.StatusNotFound {
		t.Fatalf("unknown chapter = %d, want 404\n%s", rr.Code, rr.Body.String())
	}
}

// Tenancy: a chapter in book A CANNOT be moved into a part that lives in book B,
// even when the caller owns BOTH books (cross-book move = tenancy breach → 400).
func TestParts_CrossBookMoveBreach_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookA := seedPartsBook(t, ctx, pool, owner)
	bookB := seedPartsBook(t, ctx, pool, owner)
	s.resolveBook = ownerResolver(owner)

	rr := partsHTTP(t, s, owner, http.MethodPost, "/v1/books/"+bookB.String()+"/parts", `{"title":"B Act"}`)
	partB := decodeMap(t, rr.Body.Bytes())["part_id"].(string)
	chA := seedPartsChapter(t, ctx, pool, bookA, 1, nil)

	// move chA into partB via book A's path → 400 (partB is not a part of book A)
	rr = partsHTTP(t, s, owner, http.MethodPatch,
		"/v1/books/"+bookA.String()+"/chapters/"+chA.String()+"/part", `{"part_id":"`+partB+`"}`)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("cross-book move = %d, want 400\n%s", rr.Code, rr.Body.String())
	}
	// chapter unchanged (still flat)
	var pid *uuid.UUID
	_ = pool.QueryRow(ctx, `SELECT part_id FROM chapters WHERE id=$1`, chA).Scan(&pid)
	if pid != nil {
		t.Fatalf("cross-book move LANDED (part_id=%v) — tenancy breach", *pid)
	}
}

// A VIEW grantee can list parts but not write any verb (403); no row lands.
func TestParts_ViewCanReadNotWrite_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	viewer := uuid.New()
	bookID := seedPartsBook(t, ctx, pool, owner)
	// seed one active part directly so the viewer has something to read
	var partID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO parts(book_id,sort_order,title,path) VALUES($1,1,'Act I','act-i') RETURNING id`, bookID).Scan(&partID); err != nil {
		t.Fatalf("seed part: %v", err)
	}
	ch := seedPartsChapter(t, ctx, pool, bookID, 1, nil)
	s.resolveBook = func(_ context.Context, _, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if userID == viewer {
			return GrantView, owner, "active", nil
		}
		return GrantOwner, owner, "active", nil
	}
	base := "/v1/books/" + bookID.String() + "/parts"

	if rr := partsHTTP(t, s, viewer, http.MethodGet, base, ""); rr.Code != http.StatusOK {
		t.Fatalf("viewer list = %d, want 200\n%s", rr.Code, rr.Body.String())
	}
	writes := []struct {
		method, path, body string
	}{
		{http.MethodPost, base, `{"title":"x"}`},
		{http.MethodPatch, base + "/" + partID.String(), `{"title":"x"}`},
		{http.MethodPost, base + "/reorder", `{"ordered_ids":["` + partID.String() + `"]}`},
		{http.MethodDelete, base + "/" + partID.String(), ""},
		{http.MethodPost, base + "/" + partID.String() + "/restore", ""},
		{http.MethodPatch, "/v1/books/" + bookID.String() + "/chapters/" + ch.String() + "/part", `{"part_id":"` + partID.String() + `"}`},
	}
	for _, wr := range writes {
		if rr := partsHTTP(t, s, viewer, wr.method, wr.path, wr.body); rr.Code != http.StatusForbidden {
			t.Fatalf("viewer %s %s = %d, want 403\n%s", wr.method, wr.path, rr.Code, rr.Body.String())
		}
	}
	// no write landed: part still 'Act I', chapter still flat
	var title string
	_ = pool.QueryRow(ctx, `SELECT title FROM parts WHERE id=$1`, partID).Scan(&title)
	if title != "Act I" {
		t.Fatalf("viewer mutated part title to %q", title)
	}
	var n int
	_ = pool.QueryRow(ctx, `SELECT COUNT(*) FROM parts WHERE book_id=$1`, bookID).Scan(&n)
	if n != 1 {
		t.Fatalf("viewer created a part: %d rows", n)
	}
}

// Reorder validation: ordered_ids must be EXACTLY the active set — a subset,
// a foreign id, or a duplicate is 400 and no reorder lands.
func TestParts_ReorderValidation_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx, pool, owner)
	s.resolveBook = ownerResolver(owner)
	base := "/v1/books/" + bookID.String() + "/parts"

	mk := func(title string) string {
		rr := partsHTTP(t, s, owner, http.MethodPost, base, `{"title":"`+title+`"}`)
		return decodeMap(t, rr.Body.Bytes())["part_id"].(string)
	}
	a, b := mk("A"), mk("B")

	// subset (missing b) → 400
	if rr := partsHTTP(t, s, owner, http.MethodPost, base+"/reorder", `{"ordered_ids":["`+a+`"]}`); rr.Code != http.StatusBadRequest {
		t.Fatalf("subset reorder = %d, want 400\n%s", rr.Code, rr.Body.String())
	}
	// foreign id → 400
	if rr := partsHTTP(t, s, owner, http.MethodPost, base+"/reorder", `{"ordered_ids":["`+a+`","`+b+`","`+uuid.NewString()+`"]}`); rr.Code != http.StatusBadRequest {
		t.Fatalf("foreign-id reorder = %d, want 400\n%s", rr.Code, rr.Body.String())
	}
	// duplicate → 400
	if rr := partsHTTP(t, s, owner, http.MethodPost, base+"/reorder", `{"ordered_ids":["`+a+`","`+a+`"]}`); rr.Code != http.StatusBadRequest {
		t.Fatalf("duplicate reorder = %d, want 400\n%s", rr.Code, rr.Body.String())
	}
	// order unchanged after the rejected attempts
	rr := partsHTTP(t, s, owner, http.MethodGet, base, "")
	var listed struct {
		Items []map[string]any `json:"items"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &listed)
	if listed.Items[0]["part_id"] != a || listed.Items[1]["part_id"] != b {
		t.Fatalf("a rejected reorder mutated order: %+v", listed.Items)
	}
}

// The FE grouping seam: GET /chapters carries part_id — set for a homed chapter,
// null for a flat one. Without this the navigator cannot draw acts at all.
func TestParts_ChapterListExposesPartId_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx, pool, owner)
	s.resolveBook = ownerResolver(owner)

	var partID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO parts(book_id,sort_order,title,path) VALUES($1,1,'Act I','act-i') RETURNING id`, bookID).Scan(&partID); err != nil {
		t.Fatalf("seed part: %v", err)
	}
	homed := seedPartsChapter(t, ctx, pool, bookID, 1, &partID)
	flat := seedPartsChapter(t, ctx, pool, bookID, 2, nil)

	// Assert on BOTH list surfaces: the offset list AND the keyset page the navigator
	// (useManuscriptTree) actually consumes. Both must carry part_id AND a correct
	// sort_order — proving the NULL-title Scan no longer zeroes the later columns.
	for _, path := range []string{
		"/v1/books/" + bookID.String() + "/chapters",
		"/v1/books/" + bookID.String() + "/chapters/page",
	} {
		rr := partsHTTP(t, s, owner, http.MethodGet, path, "")
		if rr.Code != http.StatusOK {
			t.Fatalf("GET %s = %d\n%s", path, rr.Code, rr.Body.String())
		}
		var out struct {
			Items []map[string]any `json:"items"`
		}
		_ = json.Unmarshal(rr.Body.Bytes(), &out)
		part := map[string]any{}
		order := map[string]float64{}
		for _, it := range out.Items {
			id := it["chapter_id"].(string)
			part[id] = it["part_id"]
			order[id], _ = it["sort_order"].(float64)
		}
		if part[homed.String()] != partID.String() {
			t.Fatalf("%s: homed chapter part_id = %v, want %s", path, part[homed.String()], partID)
		}
		if part[flat.String()] != nil {
			t.Fatalf("%s: flat chapter part_id = %v, want null", path, part[flat.String()])
		}
		// sort_order must survive the NULL-title row (was zeroed by the discarded-scan bug).
		if order[homed.String()] != 1 || order[flat.String()] != 2 {
			t.Fatalf("%s: sort_order zeroed by NULL-title scan: homed=%v flat=%v",
				path, order[homed.String()], order[flat.String()])
		}
	}
}
