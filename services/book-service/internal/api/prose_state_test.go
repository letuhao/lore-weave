package api

// prose_state_test.go — DB-free tests for GET /internal/books/{book_id}/prose-state.
//
// These pin the WIRING (token gate, input validation, and — the one that matters —
// that a scan error propagates instead of being swallowed into a cheerful zeros/200).
// They deliberately do NOT prove the SQL: a fake querier records the statement, it
// never RUNS it, so a wrong FILTER/predicate would sail straight through. The counting
// behavior is proven against a real Postgres in prose_state_db_test.go.
//
// The fake satisfies proseStateQuerier (the same interface *pgxpool.Pool satisfies),
// so no test-only DB-driver dependency is needed.

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/book-service/internal/config"
)

// --- fake querier (implements proseStateQuerier + pgx.Row) ---

type fakeProseRow struct {
	total, withProse int
	err              error
}

func (r *fakeProseRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	if len(dest) != 2 {
		return errors.New("expected 2 scan targets")
	}
	*(dest[0].(*int)) = r.total
	*(dest[1].(*int)) = r.withProse
	return nil
}

type fakeProseQuerier struct {
	gotSQL  string
	gotArgs []any
	row     *fakeProseRow
}

func (q *fakeProseQuerier) QueryRow(_ context.Context, sql string, args ...any) pgx.Row {
	q.gotSQL, q.gotArgs = sql, args
	return q.row
}

// --- queryBookProseState ---

// The book_id must be BOUND as a parameter (not interpolated), and both counts must
// land on the right fields — a swapped scan order would report a fully-written book
// as prose-free (or vice versa) and is invisible to a smoke test.
func TestQueryBookProseState_BindsBookIDAndScansBothCounts(t *testing.T) {
	t.Parallel()
	bookID := uuid.New()
	q := &fakeProseQuerier{row: &fakeProseRow{total: 7, withProse: 3}}

	total, withProse, err := queryBookProseState(context.Background(), q, bookID)
	if err != nil {
		t.Fatalf("queryBookProseState: %v", err)
	}
	if total != 7 || withProse != 3 {
		t.Fatalf("got total=%d with_prose=%d, want 7/3 (scan order swapped?)", total, withProse)
	}
	if len(q.gotArgs) != 1 || q.gotArgs[0] != any(bookID) {
		t.Fatalf("expected the book id bound as the sole $1 arg, got %#v", q.gotArgs)
	}
	// One statement, no paging: the caller runs this per chat turn.
	if strings.Contains(strings.ToUpper(q.gotSQL), "LIMIT") ||
		strings.Contains(strings.ToUpper(q.gotSQL), "OFFSET") {
		t.Fatalf("prose-state must not paginate; SQL contains LIMIT/OFFSET:\n%s", q.gotSQL)
	}
}

// THE regression guard for the requirement "do not discard the scan error". If the
// scan error were dropped (`_ = ...Scan()`), this returns (0, 0, nil) — indistinguishable
// from a genuinely empty book — and the handler would answer 200 {"chapters":0}. An
// entire novel would silently read as empty prose.
func TestQueryBookProseState_ScanErrorPropagates(t *testing.T) {
	t.Parallel()
	boom := errors.New("connection reset")
	q := &fakeProseQuerier{row: &fakeProseRow{err: boom}}

	total, withProse, err := queryBookProseState(context.Background(), q, uuid.New())
	if !errors.Is(err, boom) {
		t.Fatalf("scan error was swallowed: err=%v (a dropped error reads as an empty book)", err)
	}
	if total != 0 || withProse != 0 {
		t.Fatalf("on error the counts must not be trusted, got %d/%d", total, withProse)
	}
}

// --- handler wiring ---

// Prove the route is INSIDE the requireInternalToken group — a refactor that moved it
// out would expose per-book chapter counts unauthenticated. 401 short-circuits before
// any pool access, so a nil pool is fine.
func TestInternalProseStateRequiresInternalToken(t *testing.T) {
	t.Parallel()
	s := &Server{cfg: &config.Config{InternalServiceToken: "secret-internal-token"}}
	req := httptest.NewRequest(http.MethodGet, "/internal/books/"+uuid.NewString()+"/prose-state", nil)
	// no X-Internal-Token
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("missing internal token: got %d want 401", rr.Code)
	}
}

// A malformed book id must 400 at the edge — before the pool is touched (nil pool here
// would panic if the handler fell through to the query).
func TestInternalProseState_InvalidBookID_400(t *testing.T) {
	t.Parallel()
	s := testServer()
	req := httptest.NewRequest(http.MethodGet, "/internal/books/not-a-uuid/prose-state", nil)
	req.Header.Set("X-Internal-Token", "itok")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("bad book id: got %d want 400", rr.Code)
	}
}
