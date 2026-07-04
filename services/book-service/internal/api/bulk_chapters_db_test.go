package api

// Chapter Browser A3/A4 — DB-gated tests for the bulk lifecycle-change and
// bulk zip-export endpoints. Real Postgres because they exercise real
// tenancy scoping (book_id-joined lookups), the per-id outcome contract
// (CB5), and an actual streamed archive/zip response. Gated on
// BOOK_TEST_DATABASE_URL like the other *_db_test.go files.

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// seedActiveChapters inserts an active book + n active chapters, returning
// the book id and the chapter ids in sort_order.
func seedActiveChapters(t *testing.T, ctx context.Context, pool *pgxpool.Pool, owner uuid.UUID, n int) (bookID uuid.UUID, chapterIDs []uuid.UUID) {
	t.Helper()
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'bulk-test') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	for i := 0; i < n; i++ {
		var chID uuid.UUID
		if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,title,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state)
VALUES($1,$2,'c.txt','en','text/plain',$3,'k','active') RETURNING id`, bookID, "Chapter "+uuid.NewString()[:8], i+1).Scan(&chID); err != nil {
			t.Fatalf("seed chapter %d: %v", i, err)
		}
		chapterIDs = append(chapterIDs, chID)
		// Give each chapter a block so exports have real text.
		if _, err := pool.Exec(ctx, `
INSERT INTO chapter_blocks(chapter_id, block_index, block_type, text_content, content_hash)
VALUES ($1, 0, 'paragraph', $2, 'h')`, chID, "content of chapter "+chID.String()); err != nil {
			t.Fatalf("seed block %d: %v", i, err)
		}
	}
	return bookID, chapterIDs
}

func bulkHTTP(t *testing.T, s *Server, caller uuid.UUID, method, path, body string) *httptest.ResponseRecorder {
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

func chapterLifecycleState(t *testing.T, ctx context.Context, pool *pgxpool.Pool, chID uuid.UUID) string {
	t.Helper()
	var st string
	if err := pool.QueryRow(ctx, `SELECT lifecycle_state FROM chapters WHERE id=$1`, chID).Scan(&st); err != nil {
		t.Fatalf("read lifecycle_state: %v", err)
	}
	return st
}

// ── A3: bulk-status ─────────────────────────────────────────────────────────

func TestBulkStatus_TrashesMultiple_PerIDOutcome_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chIDs := seedActiveChapters(t, ctx, pool, owner, 3)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	body, _ := json.Marshal(map[string]any{
		"chapter_ids":     []string{chIDs[0].String(), chIDs[1].String()},
		"lifecycle_state": "trashed",
	})
	rr := bulkHTTP(t, s, owner, http.MethodPatch, "/v1/books/"+bookID.String()+"/chapters/bulk-status", string(body))
	if rr.Code != http.StatusOK {
		t.Fatalf("bulk-status = %d, want 200\n%s", rr.Code, rr.Body.String())
	}
	var out struct {
		Results []struct {
			ChapterID string `json:"chapter_id"`
			OK        bool   `json:"ok"`
			Error     string `json:"error"`
		} `json:"results"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v — %s", err, rr.Body.String())
	}
	if len(out.Results) != 2 {
		t.Fatalf("results len = %d, want 2", len(out.Results))
	}
	for _, r := range out.Results {
		if !r.OK || r.Error != "" {
			t.Fatalf("expected ok result, got %+v", r)
		}
	}
	if got := chapterLifecycleState(t, ctx, pool, chIDs[0]); got != "trashed" {
		t.Fatalf("chapter 0 lifecycle_state = %q, want trashed", got)
	}
	if got := chapterLifecycleState(t, ctx, pool, chIDs[1]); got != "trashed" {
		t.Fatalf("chapter 1 lifecycle_state = %q, want trashed", got)
	}
	// Chapter 2 was NOT in the batch — must be untouched.
	if got := chapterLifecycleState(t, ctx, pool, chIDs[2]); got != "active" {
		t.Fatalf("chapter 2 (not requested) lifecycle_state = %q, want active (untouched)", got)
	}
}

// A partial failure (one bad id mixed with good ones) must NEVER fail the
// whole batch (CB5) — each id gets its own outcome.
func TestBulkStatus_PartialFailureIsPerID_NotGlobal_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chIDs := seedActiveChapters(t, ctx, pool, owner, 1)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	nonexistent := uuid.New().String()
	malformed := "not-a-uuid"

	body, _ := json.Marshal(map[string]any{
		"chapter_ids":     []string{chIDs[0].String(), nonexistent, malformed},
		"lifecycle_state": "trashed",
	})
	rr := bulkHTTP(t, s, owner, http.MethodPatch, "/v1/books/"+bookID.String()+"/chapters/bulk-status", string(body))
	if rr.Code != http.StatusOK {
		t.Fatalf("bulk-status = %d, want 200 (partial failure is per-id, not a global error)\n%s", rr.Code, rr.Body.String())
	}
	var out struct {
		Results []struct {
			ChapterID string `json:"chapter_id"`
			OK        bool   `json:"ok"`
			Error     string `json:"error"`
		} `json:"results"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(out.Results) != 3 {
		t.Fatalf("results len = %d, want 3", len(out.Results))
	}
	if !out.Results[0].OK {
		t.Fatalf("valid chapter_id should succeed: %+v", out.Results[0])
	}
	if out.Results[1].OK || out.Results[1].Error == "" {
		t.Fatalf("nonexistent chapter_id should fail with an error: %+v", out.Results[1])
	}
	if out.Results[2].OK || out.Results[2].Error == "" {
		t.Fatalf("malformed chapter_id should fail with an error: %+v", out.Results[2])
	}
	if got := chapterLifecycleState(t, ctx, pool, chIDs[0]); got != "trashed" {
		t.Fatalf("valid chapter should have transitioned despite siblings failing: got %q", got)
	}
}

func TestBulkStatus_CapExceeded_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedActiveChapters(t, ctx, pool, owner, 1)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	ids := make([]string, maxBulkChapterIDs+1)
	for i := range ids {
		ids[i] = uuid.NewString()
	}
	body, _ := json.Marshal(map[string]any{"chapter_ids": ids, "lifecycle_state": "trashed"})
	rr := bulkHTTP(t, s, owner, http.MethodPatch, "/v1/books/"+bookID.String()+"/chapters/bulk-status", string(body))
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("cap-exceeded bulk-status = %d, want 400\n%s", rr.Code, rr.Body.String())
	}
}

func TestBulkStatus_InvalidLifecycleState_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chIDs := seedActiveChapters(t, ctx, pool, owner, 1)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	body, _ := json.Marshal(map[string]any{"chapter_ids": []string{chIDs[0].String()}, "lifecycle_state": "bogus"})
	rr := bulkHTTP(t, s, owner, http.MethodPatch, "/v1/books/"+bookID.String()+"/chapters/bulk-status", string(body))
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("invalid lifecycle_state = %d, want 400\n%s", rr.Code, rr.Body.String())
	}
}

// A view-only collaborator must be refused (edit is required for trash/restore) —
// the SAME grant chokepoint as the single-chapter route, not loosened for bulk.
func TestBulkStatus_ViewOnlyGrantForbidden_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	viewer := uuid.New()
	bookID, chIDs := seedActiveChapters(t, ctx, pool, owner, 1)
	s.resolveBook = func(_ context.Context, _, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if userID == viewer {
			return GrantView, owner, "active", nil
		}
		return GrantOwner, owner, "active", nil
	}
	body, _ := json.Marshal(map[string]any{"chapter_ids": []string{chIDs[0].String()}, "lifecycle_state": "trashed"})
	rr := bulkHTTP(t, s, viewer, http.MethodPatch, "/v1/books/"+bookID.String()+"/chapters/bulk-status", string(body))
	if rr.Code != http.StatusForbidden {
		t.Fatalf("view-only bulk-status = %d, want 403\n%s", rr.Code, rr.Body.String())
	}
	if got := chapterLifecycleState(t, ctx, pool, chIDs[0]); got != "active" {
		t.Fatalf("chapter must be untouched after a forbidden bulk call, got %q", got)
	}
}

// ── A4: bulk zip export ──────────────────────────────────────────────────────

func TestBulkExport_ZipContainsRequestedChapters_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chIDs := seedActiveChapters(t, ctx, pool, owner, 2)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	missing := uuid.New().String()

	body, _ := json.Marshal(map[string]any{"chapter_ids": []string{chIDs[0].String(), chIDs[1].String(), missing}})
	req := httptest.NewRequest(http.MethodPost, "/v1/books/"+bookID.String()+"/chapters/export-zip", strings.NewReader(string(body)))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("bulk export = %d, want 200\n%s", rr.Code, rr.Body.String())
	}
	if ct := rr.Header().Get("Content-Type"); ct != "application/zip" {
		t.Fatalf("Content-Type = %q, want application/zip", ct)
	}
	zr, err := zip.NewReader(bytes.NewReader(rr.Body.Bytes()), int64(rr.Body.Len()))
	if err != nil {
		t.Fatalf("response is not a valid zip: %v", err)
	}
	var names []string
	var sawErrors bool
	for _, f := range zr.File {
		names = append(names, f.Name)
		if f.Name == "_errors.txt" {
			sawErrors = true
			rc, _ := f.Open()
			b, _ := io.ReadAll(rc)
			rc.Close()
			if !strings.Contains(string(b), missing) {
				t.Fatalf("_errors.txt does not mention the missing id %s: %s", missing, b)
			}
		}
	}
	if len(zr.File) != 3 { // 2 chapter .txt files + _errors.txt
		t.Fatalf("zip entries = %v, want 2 chapter files + _errors.txt", names)
	}
	if !sawErrors {
		t.Fatal("zip missing _errors.txt for the unresolvable chapter_id")
	}
}

func TestBulkExport_MalformedChapterID_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedActiveChapters(t, ctx, pool, owner, 1)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	body, _ := json.Marshal(map[string]any{"chapter_ids": []string{"not-a-uuid"}})
	rr := bulkHTTP(t, s, owner, http.MethodPost, "/v1/books/"+bookID.String()+"/chapters/export-zip", string(body))
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("malformed chapter_id export = %d, want 400\n%s", rr.Code, rr.Body.String())
	}
}

func TestBulkExport_CapExceeded_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedActiveChapters(t, ctx, pool, owner, 1)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	ids := make([]string, maxBulkChapterIDs+1)
	for i := range ids {
		ids[i] = uuid.NewString()
	}
	body, _ := json.Marshal(map[string]any{"chapter_ids": ids})
	rr := bulkHTTP(t, s, owner, http.MethodPost, "/v1/books/"+bookID.String()+"/chapters/export-zip", string(body))
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("cap-exceeded export = %d, want 400\n%s", rr.Code, rr.Body.String())
	}
}

// No grant at all (book doesn't exist / caller has no access) → 404, same as
// the single-chapter export route's existence-oracle behavior.
func TestBulkExport_NoGrant_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chIDs := seedActiveChapters(t, ctx, pool, owner, 1)
	stranger := uuid.New()
	s.resolveBook = func(_ context.Context, _, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if userID == stranger {
			return GrantNone, owner, "active", nil
		}
		return GrantOwner, owner, "active", nil
	}
	body, _ := json.Marshal(map[string]any{"chapter_ids": []string{chIDs[0].String()}})
	rr := bulkHTTP(t, s, stranger, http.MethodPost, "/v1/books/"+bookID.String()+"/chapters/export-zip", string(body))
	if rr.Code != http.StatusNotFound {
		t.Fatalf("no-grant export = %d, want 404\n%s", rr.Code, rr.Body.String())
	}
}
