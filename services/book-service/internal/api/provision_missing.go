package api

import (
	"context"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/google/uuid"
)

// provisionMissingConcurrency bounds the calls in flight for one owner. composition's POST /work
// creates a knowledge project per book, and a sign-in must not turn into a burst against it.
const provisionMissingConcurrency = 4

// provisionMissingDeadline bounds the whole sweep. The frontend fires this without waiting, so the
// bound protects the services, not the user; books it does not reach are picked up next sign-in
// or when opened.
const provisionMissingDeadline = 90 * time.Second

type provisionMissingResult struct {
	Checked     int `json:"checked"`
	Ready       int `json:"ready"`
	Provisioned int `json:"provisioned"`
	Failed      int `json:"failed"`
}

// provisionMissing — POST /v1/books/provision-missing — the sign-in backfill (plan 2026-09-18, Q4).
//
// Books created before provisioning moved to creation time get their knowledge project only when
// someone opens them. On sign-in the frontend calls this once, and it asks composition for the Work
// of every book the CALLER OWNS that does not have a ready one yet.
//
// OQ-1 holds by construction:
//   - the book list is `owner_user_id = caller` — never a shared, collaborated or anyone else's book;
//   - the only identity sent downstream is the caller's own bearer, taken from this request;
//   - nothing is minted, and there is no internal-token path here.
//
// The same scope as the library's book count: active, not the bible, never a diary (kind='diary' is
// the privacy lock, and a diary never gets a knowledge project from here).
func (s *Server) provisionMissing(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bearer := r.Header.Get("Authorization")
	// Detached from the client: the frontend fires this and does not wait, so the browser (or the
	// BFF proxying it) may drop the connection long before the sweep ends. The deadline, not the
	// client, bounds it.
	ctx, cancel := context.WithTimeout(context.WithoutCancel(r.Context()), provisionMissingDeadline)
	defer cancel()
	start := time.Now()

	rows, err := s.pool.Query(ctx, `
SELECT id FROM books
WHERE owner_user_id=$1 AND is_bible=false AND kind<>'diary' AND lifecycle_state='active'
ORDER BY created_at`, ownerID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list books")
		return
	}
	var ids []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err == nil {
			ids = append(ids, id)
		}
	}
	rows.Close()

	out := s.provisionBooks(ctx, ids, bearer)
	slog.InfoContext(ctx, "book.provision_missing", "user_id", ownerID, "checked", out.Checked,
		"ready", out.Ready, "provisioned", out.Provisioned, "failed", out.Failed,
		"ms", time.Since(start).Milliseconds())
	writeJSON(w, http.StatusOK, out)
}

// provisionBooks checks each book's Work (a cheap GET) and asks for one only when it is missing or
// still pending its knowledge project. Bounded concurrency; stops starting new books at the deadline.
func (s *Server) provisionBooks(ctx context.Context, ids []uuid.UUID, bearer string) provisionMissingResult {
	var (
		mu  sync.Mutex
		out provisionMissingResult
		wg  sync.WaitGroup
		sem = make(chan struct{}, provisionMissingConcurrency)
	)
	for _, id := range ids {
		if ctx.Err() != nil {
			break
		}
		sem <- struct{}{}
		wg.Add(1)
		go func(bookID string) {
			defer wg.Done()
			defer func() { <-sem }()
			work, ok := s.fetchStructureWork(ctx, bookID, bearer)
			if ok && work.ProjectID != nil {
				mu.Lock()
				out.Checked++
				out.Ready++
				mu.Unlock()
				return
			}
			_, err := s.provisionCompositionWork(ctx, bookID, bearer)
			mu.Lock()
			out.Checked++
			if err != nil {
				out.Failed++
			} else {
				out.Provisioned++
			}
			mu.Unlock()
		}(id.String())
	}
	wg.Wait()
	return out
}
