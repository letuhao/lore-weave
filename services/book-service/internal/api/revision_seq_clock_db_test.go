package api

// #287 — revision LIST order must survive a wall-clock step-back. The dev VM's clock
// steps back ~1.39s every ~30s; `created_at DESC` then lists a LATER save as older,
// and Revision Compare's "newest two" default diffs the wrong pair. This test drives
// the REAL handlers (patchDraft → listRevisions), then shifts the FIRST revision's
// created_at into the future — a deterministic stand-in for the clock stepping back
// between the two writes. The LAST write must still be listed first.
//
// Pristine-compatible on purpose: this file compiles and runs against unfixed
// upstream/main, where it FAILS (the skewed first revision sorts newest by wall
// clock) — that red run is the issue's reproduction.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

func revisionClockTestServerCalls(t *testing.T, s *Server, bookID, chID, owner uuid.UUID, commit string) {
	t.Helper()
	body := map[string]any{
		"body":          map[string]any{"type": "doc", "content": []map[string]any{{"type": "paragraph", "_text": "draft for " + commit}}},
		"body_format":   "json",
		"commit_message": commit,
	}
	raw, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal patch body: %v", err)
	}
	req := httptest.NewRequest(http.MethodPatch,
		"/v1/books/"+bookID.String()+"/chapters/"+chID.String()+"/draft", bytes.NewReader(raw))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("book_id", bookID.String())
	rctx.URLParams.Add("chapter_id", chID.String())
	req = req.WithContext(addChi(req, rctx))
	w := httptest.NewRecorder()
	s.patchDraft(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("patchDraft (%q): want 200, got %d body=%s", commit, w.Code, w.Body.String())
	}
}

func revisionClockListMessages(t *testing.T, s *Server, bookID, chID, owner uuid.UUID) []string {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet,
		"/v1/books/"+bookID.String()+"/chapters/"+chID.String()+"/revisions", nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("book_id", bookID.String())
	rctx.URLParams.Add("chapter_id", chID.String())
	req = req.WithContext(addChi(req, rctx))
	w := httptest.NewRecorder()
	s.listRevisions(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("listRevisions: want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var out struct {
		Items []struct {
			RevisionID string  `json:"revision_id"`
			Message    *string `json:"message"`
		} `json:"items"`
	}
	if err := json.NewDecoder(w.Body).Decode(&out); err != nil {
		t.Fatalf("decode list: %v", err)
	}
	msgs := make([]string, 0, len(out.Items))
	for _, it := range out.Items {
		if it.Message != nil {
			msgs = append(msgs, *it.Message)
		} else {
			msgs = append(msgs, "")
		}
	}
	return msgs
}

func TestRevisionListOrderSurvivesClockStepBack(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)

	revisionClockTestServerCalls(t, s, bookID, chID, owner, "save one")
	revisionClockTestServerCalls(t, s, bookID, chID, owner, "save two")

	// The clock STEPS BACK between the writes (the dev VM does this every ~30s).
	// Stand-in: shove the FIRST write's created_at into the future — after the step
	// back, the earlier-inserted row carries the LATER wall-clock timestamp.
	if _, err := pool.Exec(ctx,
		`UPDATE chapter_revisions SET created_at = created_at + interval '1 hour'
		 WHERE chapter_id=$1 AND message='save one'`, chID); err != nil {
		t.Fatalf("skew created_at: %v", err)
	}

	msgs := revisionClockListMessages(t, s, bookID, chID, owner)
	if len(msgs) < 2 {
		t.Fatalf("expected 2 revisions, got %d (%v)", len(msgs), msgs)
	}
	if got := msgs[0]; got != "save two" {
		t.Fatalf("newest-first listed %q first after a clock step-back — the wall-clock order is the defect (#281/#287: a LATER save listed as older)", got)
	}
	if !strings.Contains(strings.Join(msgs, ","), "save two") {
		t.Fatalf("save two missing from the list entirely: %v", msgs)
	}
}
