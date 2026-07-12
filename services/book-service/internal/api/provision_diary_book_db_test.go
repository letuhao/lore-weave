package api

// WS-1.4 (step 1) — POST /v1/books/diary, the diary get-or-create the provisioner calls.
//
// The properties that matter: it is the ONLY kind='diary' write path; it is IDEMPOTENT (a
// re-open returns the same diary, never a second one); it is race-safe; the owner is the JWT
// principal; and a TRASHED diary is surfaced, not silently forked or resurrected (E14).
//
// DB-gated on BOOK_TEST_DATABASE_URL.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"
)

func provisionDiary(t *testing.T, s *Server, caller uuid.UUID, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/books/diary", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, caller))
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func diaryBookID(t *testing.T, rr *httptest.ResponseRecorder) string {
	t.Helper()
	var out struct {
		BookID string `json:"book_id"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v (body=%s)", err, rr.Body.String())
	}
	return out.BookID
}

func TestProvisionDiary_CreatesThenReturnsTheSameOne_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	owner := uuid.New()
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE owner_user_id=$1`, owner) })

	// First call CREATES the diary.
	rr1 := provisionDiary(t, s, owner, "")
	if rr1.Code != http.StatusCreated {
		t.Fatalf("first provision = %d, want 201. body=%s", rr1.Code, rr1.Body.String())
	}
	id1 := diaryBookID(t, rr1)
	if id1 == "" {
		t.Fatalf("first provision returned no book_id. body=%s", rr1.Body.String())
	}
	// The created book really is a diary (kind is not in the projection; check the DB).
	var kind string
	if err := pool.QueryRow(context.Background(), `SELECT kind FROM books WHERE id=$1`, id1).Scan(&kind); err != nil {
		t.Fatalf("read kind: %v", err)
	}
	if kind != "diary" {
		t.Fatalf("provisioned book kind = %q, want diary", kind)
	}

	// Second call RETURNS THE SAME one (idempotent) — never a second diary.
	rr2 := provisionDiary(t, s, owner, "")
	if rr2.Code != http.StatusOK {
		t.Fatalf("second provision = %d, want 200 (idempotent get). body=%s", rr2.Code, rr2.Body.String())
	}
	id2 := diaryBookID(t, rr2)
	if id2 != id1 {
		t.Fatalf("a second provision returned a DIFFERENT diary (%s -> %s). The assistant's "+
			"memory would split across two diaries.", id1, id2)
	}

	var n int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM books WHERE owner_user_id=$1 AND kind='diary' AND lifecycle_state='active'`,
		owner).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 1 {
		t.Fatalf("active diaries = %d, want exactly 1", n)
	}
}

func TestProvisionDiary_IsRaceSafe_DB(t *testing.T) {
	// Two devices open /assistant at the same instant. Exactly one diary must exist and both
	// callers must receive it — the ON CONFLICT + partial unique is what makes that true.
	s, pool := dbTestServer(t)
	owner := uuid.New()
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE owner_user_id=$1`, owner) })

	const n = 8
	var wg sync.WaitGroup
	ids := make([]string, n)
	codes := make([]int, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			rr := provisionDiary(t, s, owner, "")
			codes[i] = rr.Code
			if rr.Code == http.StatusOK || rr.Code == http.StatusCreated {
				ids[i] = diaryBookID(t, rr)
			}
		}(i)
	}
	wg.Wait()

	first := ids[0]
	for i, id := range ids {
		if codes[i] != http.StatusOK && codes[i] != http.StatusCreated {
			t.Fatalf("caller %d got %d, want 200/201", i, codes[i])
		}
		if id == "" || id != first {
			t.Fatalf("concurrent provision produced DIFFERENT diaries (caller %d: %q vs %q). "+
				"The assistant's memory would be split across two.", i, id, first)
		}
	}
	var rows int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM books WHERE owner_user_id=$1 AND kind='diary' AND lifecycle_state='active'`,
		owner).Scan(&rows); err != nil {
		t.Fatalf("count: %v", err)
	}
	if rows != 1 {
		t.Fatalf("active diary rows = %d, want exactly 1", rows)
	}
}

func TestProvisionDiary_OwnerIsTheJWTPrincipal_DB(t *testing.T) {
	// The owner is the authenticated principal. A body-supplied owner (a cross-user write
	// attempt) must NOT change whose diary is created; the body only carries an optional title.
	s, pool := dbTestServer(t)
	owner := uuid.New()
	attacker := uuid.New()
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE owner_user_id=ANY($1)`,
			[]uuid.UUID{owner, attacker})
	})

	body, _ := json.Marshal(map[string]any{"owner_user_id": attacker.String(), "title": "mine"})
	rr := provisionDiary(t, s, owner, string(body))
	if rr.Code != http.StatusCreated {
		t.Fatalf("provision = %d, want 201. body=%s", rr.Code, rr.Body.String())
	}

	// The diary belongs to the JWT principal, not the body-supplied id.
	var ownerRows, attackerRows int
	ctx := context.Background()
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM books WHERE owner_user_id=$1 AND kind='diary'`, owner).Scan(&ownerRows)
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM books WHERE owner_user_id=$1 AND kind='diary'`, attacker).Scan(&attackerRows)
	if ownerRows != 1 || attackerRows != 0 {
		t.Fatalf("owner diaries=%d attacker diaries=%d, want 1/0 — a body-supplied owner must be ignored",
			ownerRows, attackerRows)
	}
}

func TestProvisionDiary_TrashedDiaryIsSurfaced_DB(t *testing.T) {
	// E14: a trashed diary must NOT be silently forked (stranding the old KG anchors) or
	// silently resurrected. The endpoint refuses with 409 BOOK_DIARY_TRASHED so the caller
	// can offer restore-vs-start-fresh.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE owner_user_id=$1`, owner) })

	// Provision then trash the diary.
	if rr := provisionDiary(t, s, owner, ""); rr.Code != http.StatusCreated {
		t.Fatalf("seed provision: %d", rr.Code)
	}
	if _, err := pool.Exec(ctx,
		`UPDATE books SET lifecycle_state='trashed' WHERE owner_user_id=$1 AND kind='diary'`, owner); err != nil {
		t.Fatalf("trash: %v", err)
	}

	rr := provisionDiary(t, s, owner, "")
	if rr.Code != http.StatusConflict {
		t.Fatalf("provision with a trashed diary = %d, want 409 (surface it, don't fork). body=%s",
			rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "BOOK_DIARY_TRASHED") {
		t.Fatalf("expected BOOK_DIARY_TRASHED, got %s", rr.Body.String())
	}
	// It must NOT have silently created a fresh active diary.
	var active int
	_ = pool.QueryRow(ctx,
		`SELECT count(*) FROM books WHERE owner_user_id=$1 AND kind='diary' AND lifecycle_state='active'`,
		owner).Scan(&active)
	if active != 0 {
		t.Fatalf("a fresh diary was silently forked despite a trashed one existing (active=%d)", active)
	}
}

func TestProvisionDiary_DoesNotCountAgainstTheNovelCeiling_DB(t *testing.T) {
	// review-impl M1 — the diary is hidden from the library and must ALSO be invisible to the
	// per-user novel ceiling (like is_bible). Otherwise provisioning an assistant silently
	// steals a novel slot and the user hits BOOK_LIMIT_REACHED one novel early.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE owner_user_id=$1`, owner) })

	for i := 0; i < 2; i++ {
		if _, err := pool.Exec(ctx,
			`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'n','novel')`, owner); err != nil {
			t.Fatalf("seed novel: %v", err)
		}
	}
	if rr := provisionDiary(t, s, owner, ""); rr.Code != http.StatusCreated {
		t.Fatalf("provision diary: %d", rr.Code)
	}

	n, err := s.countActiveBooks(ctx, owner)
	if err != nil {
		t.Fatalf("countActiveBooks: %v", err)
	}
	if n != 2 {
		t.Fatalf("countActiveBooks = %d, want 2 — the diary must not count toward the novel ceiling", n)
	}
}

func TestProvisionDiary_PurgePendingDiaryCreatesFresh_DB(t *testing.T) {
	// review-impl L2 — a purge_pending diary is on its way to deletion and CANNOT be restored,
	// so provisioning must create a FRESH diary rather than 409 an impossible restore.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE owner_user_id=$1`, owner) })

	if rr := provisionDiary(t, s, owner, ""); rr.Code != http.StatusCreated {
		t.Fatalf("seed: %d", rr.Code)
	}
	if _, err := pool.Exec(ctx,
		`UPDATE books SET lifecycle_state='purge_pending' WHERE owner_user_id=$1 AND kind='diary'`,
		owner); err != nil {
		t.Fatalf("purge_pending: %v", err)
	}

	rr := provisionDiary(t, s, owner, "")
	if rr.Code != http.StatusCreated {
		t.Fatalf("provision with a purge_pending diary = %d, want 201 (create fresh, not a dead-end "+
			"409). body=%s", rr.Code, rr.Body.String())
	}
}
