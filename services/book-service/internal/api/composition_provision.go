package api

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

// provisionTimeout bounds one POST /work. The call runs OFF the request path (see
// provisionCompositionWorkAsync), so it never adds latency to book creation; the bound exists so a
// hung composition or knowledge service cannot pile up goroutines.
const provisionTimeout = 10 * time.Second

// provisionClient is its own client, never http.DefaultClient: the default has no timeout, and a
// best-effort side call must not be able to wait forever.
var provisionClient = &http.Client{Timeout: provisionTimeout}

// provisionCompositionWork asks composition for the book's Work — POST
// /v1/composition/books/{id}/work — which creates the knowledge project when there is none.
//
// It forwards the CALLER'S OWN bearer and nothing else. That is the whole OQ-1 contract
// (composition-service works.py): knowledge auto-provision stays owner-only, and no owner-identity
// token is ever minted. It is the same call the Studio makes when the owner opens the book
// (useEnsureWork), made earlier. /work is idempotent, so a later open returns the same Work.
//
// Best-effort: it returns the status for callers that count outcomes (the sign-in backfill), and
// logs every failure, but a failure never changes what the caller already did.
func (s *Server) provisionCompositionWork(ctx context.Context, bookID, bearer string) (int, error) {
	base := strings.TrimRight(s.cfg.CompositionServiceURL, "/")
	if base == "" || bearer == "" {
		slog.DebugContext(ctx, "book.provision skipped", "book_id", bookID,
			"has_base", base != "", "has_bearer", bearer != "")
		return 0, fmt.Errorf("provision skipped: no composition URL or no bearer")
	}
	start := time.Now()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, base+"/v1/composition/books/"+bookID+"/work", nil)
	if err != nil {
		return 0, err
	}
	req.Header.Set("Authorization", bearer)
	resp, err := provisionClient.Do(req)
	if err != nil {
		slog.WarnContext(ctx, "book.provision failed", "book_id", bookID, "err", err,
			"ms", time.Since(start).Milliseconds())
		return 0, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		slog.WarnContext(ctx, "book.provision failed", "book_id", bookID, "status", resp.StatusCode,
			"ms", time.Since(start).Milliseconds())
		return resp.StatusCode, fmt.Errorf("composition POST /work → %d", resp.StatusCode)
	}
	slog.InfoContext(ctx, "book.provision ok", "book_id", bookID, "status", resp.StatusCode,
		"ms", time.Since(start).Milliseconds())
	return resp.StatusCode, nil
}

// provisionCompositionWorkAsync runs provisionCompositionWork after the response is on its way,
// so book creation never waits on composition or knowledge. The request context is detached from
// cancellation (the client may hang up the moment it has its 201) but keeps its values, so logs
// stay correlated.
func (s *Server) provisionCompositionWorkAsync(ctx context.Context, bookID, bearer string) {
	detached := context.WithoutCancel(ctx)
	go func() {
		_, _ = s.provisionCompositionWork(detached, bookID, bearer)
	}()
}
