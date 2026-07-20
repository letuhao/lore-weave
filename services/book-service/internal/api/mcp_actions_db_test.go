package api

// S-BOOK Tier-W DB-gated tests (/review-impl HIGH + H8 follow-ups). These need a
// real Postgres because they exercise the single-use confirm-token ledger
// (book_consumed_tokens) and the chapter_drafts optimistic-concurrency path —
// behavior the nil-pool unit tests in mcp_server_test.go deliberately cannot cover.
//
// Gating: set BOOK_TEST_DATABASE_URL to a throwaway Postgres (PG18; the schema
// uses uuidv7()/JSON_TABLE). When unset the whole file is SKIPPED, so `go test`
// stays green on a machine with no DB. Each test seeds its own book/chapter and
// runs migrate.Up() to install the schema (idempotent).

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/loreweave/book-service/internal/migrate"
	"github.com/loreweave/book-service/internal/testsafe"
	lwmcp "github.com/loreweave/loreweave_mcp"
)

// dbTestServer spins a Server bound to a real pool (BOOK_TEST_DATABASE_URL) with
// the schema migrated and a stubbed owner-grant resolver. Skips if the env var is
// unset. The confirm secret is the DISTINCT mcpConfirmSecret (key-split).
func dbTestServer(t *testing.T) (*Server, *pgxpool.Pool) {
	t.Helper()
	dsn := os.Getenv("BOOK_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("BOOK_TEST_DATABASE_URL not set — DB-gated test skipped")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("pgxpool.New: %v", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		t.Skipf("BOOK_TEST_DATABASE_URL unreachable (%v) — skipping", err)
	}
	// SAFETY GUARD — DB-gated tests in this package run destructive setup/cleanup.
	// Refuse anything but a throwaway DB so BOOK_TEST_DATABASE_URL can never wipe a
	// real service database (see internal/testsafe — the loreweave_book wipe).
	var dbName string
	if err := pool.QueryRow(ctx, `SELECT current_database()`).Scan(&dbName); err != nil {
		pool.Close()
		t.Fatalf("current_database: %v", err)
	}
	if err := testsafe.EnsureThrowawayDB(dbName); err != nil {
		pool.Close()
		t.Fatal(err)
	}
	if err := migrate.Up(ctx, pool); err != nil {
		pool.Close()
		t.Fatalf("migrate.Up: %v", err)
	}
	s := mcpTestServer(GrantOwner)
	s.pool = pool
	t.Cleanup(pool.Close)
	return s, pool
}

// seedChapter inserts an active book + chapter + draft (version 1) owned by
// ownerID, returning their ids. The draft has prose so publish passes the
// non-empty check.
func seedChapter(t *testing.T, ctx context.Context, pool *pgxpool.Pool, ownerID uuid.UUID) (bookID, chID uuid.UUID) {
	t.Helper()
	body := json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","_text":"hello world"}]}`)
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'t') RETURNING id`, ownerID).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status)
VALUES($1,'c.txt','en','text/plain',1,'k','active','draft') RETURNING id`, bookID).Scan(&chID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_version) VALUES($1,$2,'json',1)`, chID, body); err != nil {
		t.Fatalf("seed draft: %v", err)
	}
	return bookID, chID
}

func confirmReq(t *testing.T, s *Server, userID uuid.UUID, tok string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]string{"confirm_token": tok})
	req := httptest.NewRequest(http.MethodPost, "/v1/book/actions/confirm", strings.NewReader(string(body)))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, userID))
	rr := httptest.NewRecorder()
	s.confirmBookAction(rr, req)
	return rr
}

// confirmReqViaInternalEnvelope drives confirmBookAction exactly the way
// auth-service's public-MCP confirm-replay does (mcp_approvals.go::replayConfirm):
// query-param token, nil body, X-Internal-Token+X-User-Id, NO Authorization
// header — the shape that 401'd unconditionally before resolveConfirmCaller.
func confirmReqViaInternalEnvelope(s *Server, internalTok, userID, tok string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, "/v1/book/actions/confirm?token="+tok, nil)
	if internalTok != "" {
		req.Header.Set("X-Internal-Token", internalTok)
	}
	if userID != "" {
		req.Header.Set("X-User-Id", userID)
	}
	rr := httptest.NewRecorder()
	s.confirmBookAction(rr, req)
	return rr
}

// /review-impl HIGH — single-use confirm-token ledger. A REPLAY of a VALID,
// unexpired publish token must be refused on the 2nd confirm: the 1st publishes
// (200, inserts ONE chapter_revisions row + ONE chapter.published outbox event),
// the 2nd returns the used/!ok error (422) and does NOT re-run the effect.
func TestMCP_ConfirmToken_SingleUse_RefusesReplay_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	tok, err := lwmcp.MintConfirmToken(mcpConfirmSecret, owner, bookID, descBookPublish,
		actionPayload{Op: "publish", ChapterID: chID.String()}, actionTokenTTL)
	if err != nil {
		t.Fatalf("mint: %v", err)
	}

	// 1st confirm → publishes.
	rr1 := confirmReq(t, s, owner, tok)
	if rr1.Code != http.StatusOK {
		t.Fatalf("1st confirm = %d, want 200; body=%s", rr1.Code, rr1.Body.String())
	}

	// 2nd confirm (same still-valid token) → refused, single-use.
	rr2 := confirmReq(t, s, owner, tok)
	if rr2.Code != http.StatusUnprocessableEntity {
		t.Fatalf("replay confirm = %d, want 422; body=%s", rr2.Code, rr2.Body.String())
	}
	if !strings.Contains(rr2.Body.String(), "already confirmed") {
		t.Errorf("replay body = %s, want 'already confirmed'", rr2.Body.String())
	}

	// Effect ran EXACTLY once: one publish revision, one chapter.published event.
	var revCount, evtCount int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM chapter_revisions WHERE chapter_id=$1 AND message='publish'`, chID).Scan(&revCount); err != nil {
		t.Fatalf("count revisions: %v", err)
	}
	if revCount != 1 {
		t.Errorf("publish revisions = %d, want 1 (replay must NOT re-insert)", revCount)
	}
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='chapter.published'`, chID).Scan(&evtCount); err != nil {
		t.Fatalf("count events: %v", err)
	}
	if evtCount != 1 {
		t.Errorf("chapter.published events = %d, want 1 (replay must NOT re-emit)", evtCount)
	}
	// The hash was recorded in the ledger.
	var ledgered int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM book_consumed_tokens WHERE token_hash=$1`, actionTokenHash(tok)).Scan(&ledgered)
	if ledgered != 1 {
		t.Errorf("ledger rows = %d, want 1", ledgered)
	}
}

// Internal confirm-replay envelope (D-PMCP-WORKER-CARRIER retrofit). Found live
// 2026-07-08: auth-service's public-MCP confirm-replay (self-confirm AND
// human-approve, mcp_approvals.go::replayConfirm) sends a query-param token +
// nil body + X-Internal-Token/X-User-Id (never a Bearer JWT, since it's a
// trusted internal caller, not the browser) — confirmBookAction 401'd that
// shape unconditionally before resolveConfirmCaller.
func TestMCP_ConfirmToken_InternalReplayEnvelope_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tok, err := lwmcp.MintConfirmToken(mcpConfirmSecret, owner, bookID, descBookPublish,
		actionPayload{Op: "publish", ChapterID: chID.String()}, actionTokenTTL)
	if err != nil {
		t.Fatalf("mint: %v", err)
	}

	// Exactly the shape auth-service's replayConfirm sends.
	rr := confirmReqViaInternalEnvelope(s, mcpTestToken, owner.String(), tok)
	if rr.Code != http.StatusOK {
		t.Fatalf("internal-envelope confirm-replay = %d, want 200; body=%s", rr.Code, rr.Body.String())
	}
	var revCount int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM chapter_revisions WHERE chapter_id=$1 AND message='publish'`, chID).Scan(&revCount); err != nil {
		t.Fatalf("count revisions: %v", err)
	}
	if revCount != 1 {
		t.Errorf("publish revisions = %d, want 1", revCount)
	}

	// Wrong internal token → 401, never falls through.
	tok2, _ := lwmcp.MintConfirmToken(mcpConfirmSecret, owner, bookID, descBookPublish,
		actionPayload{Op: "publish", ChapterID: chID.String()}, actionTokenTTL)
	if rr := confirmReqViaInternalEnvelope(s, "wrong-token", owner.String(), tok2); rr.Code != http.StatusUnauthorized {
		t.Errorf("wrong internal token = %d, want 401; body=%s", rr.Code, rr.Body.String())
	}
	// Correct internal token, no X-User-Id → 401 (fail closed).
	if rr := confirmReqViaInternalEnvelope(s, mcpTestToken, "", tok2); rr.Code != http.StatusUnauthorized {
		t.Errorf("internal token with no X-User-Id = %d, want 401; body=%s", rr.Code, rr.Body.String())
	}
	// Correct internal token, malformed X-User-Id → 401.
	if rr := confirmReqViaInternalEnvelope(s, mcpTestToken, "not-a-uuid", tok2); rr.Code != http.StatusUnauthorized {
		t.Errorf("internal token with malformed X-User-Id = %d, want 401; body=%s", rr.Code, rr.Body.String())
	}
	// Correct internal token, SYNTACTICALLY-valid X-User-Id naming a DIFFERENT user
	// than the token's bound proposer → still 403: resolveConfirmCaller resolves the
	// (wrong) caller successfully via the envelope path, but decodeActionToken's
	// claims.UserID != userID check fires identically regardless of which auth path
	// produced userID. tok2 is never actually consumed by any of the negative cases
	// above (they all fail before decodeActionToken's consume step), so it is still
	// cryptographically valid here — mirrors glossary's
	// TestConfirmAction_InternalReplayEnvelope_WrongOrMissingCredsRejected.
	if rr := confirmReqViaInternalEnvelope(s, mcpTestToken, uuid.New().String(), tok2); rr.Code != http.StatusForbidden {
		t.Errorf("internal envelope naming a different user than the proposer = %d, want 403; body=%s", rr.Code, rr.Body.String())
	}
}

// The priced-media confirm round-trip (mint→verify→user-bind→consume→open_ui).
// Moved here from the nil-pool unit suite because the single-use claim now hits
// the DB before the open_ui outcome.
func TestMCP_ConfirmToken_RoundTrip_Media_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedChapter(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tok, err := lwmcp.MintConfirmToken(mcpConfirmSecret, owner, bookID, descBookMedia,
		actionPayload{Op: "set_cover", EstimateUSD: "~0.04"}, actionTokenTTL)
	if err != nil {
		t.Fatalf("mint: %v", err)
	}
	rr := confirmReq(t, s, owner, tok)
	if rr.Code != http.StatusOK {
		t.Fatalf("confirm status = %d, want 200; body=%s", rr.Code, rr.Body.String())
	}
	var out map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	if out["outcome"] != "open_ui" {
		t.Fatalf("outcome = %v, want open_ui", out["outcome"])
	}
}

// H8 — a POSITIVE-but-STALE base_version (≠ current draft_version) returns
// ErrStaleDraftVersion and does NOT overwrite the draft. The existing nil-pool
// tests only cover base_version<=0 (rejected before any DB access); this proves
// the optimistic-concurrency stop on a real version mismatch.
func TestMCP_SaveDraft_StaleBaseVersion_StopsNoOverwrite_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner) // draft_version = 1
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tctx := identityCtxForTest(t, owner)

	// base_version = 5 is positive but stale (current is 1) → 409 stop.
	in := saveDraftIn{
		BookID:      bookID.String(),
		ChapterID:   chID.String(),
		BaseVersion: 5,
		Body:        "OVERWRITE",
	}
	_, _, err := s.toolChapterSaveDraft(tctx, nil, in)
	if err != ErrStaleDraftVersion {
		t.Fatalf("err = %v, want ErrStaleDraftVersion", err)
	}

	// The draft was NOT overwritten: version still 1 and body unchanged.
	var ver int64
	var body string
	if err := pool.QueryRow(ctx, `SELECT draft_version, body::text FROM chapter_drafts WHERE chapter_id=$1`, chID).Scan(&ver, &body); err != nil {
		t.Fatalf("read draft: %v", err)
	}
	if ver != 1 {
		t.Errorf("draft_version = %d, want 1 (stale save must not bump)", ver)
	}
	if strings.Contains(body, "OVERWRITE") {
		t.Errorf("draft body was overwritten by a stale save: %s", body)
	}
}

// D-MCP-BOOK-CREATE-QUOTA — book_create must enforce a per-user active-book
// ceiling. Seed N active books at a temporarily-lowered cap, then assert the
// (N+1)th book_create is refused with the limit error and inserts NO new row.
func TestMCP_BookCreate_PerUserCeiling_Refuses_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	// Lower the cap so we only need to seed a few rows; restore after the test.
	const cap = 3
	prev := maxBooksPerUser
	maxBooksPerUser = cap
	t.Cleanup(func() { maxBooksPerUser = prev })

	// Seed exactly `cap` active, non-bible books owned by the caller.
	for i := 0; i < cap; i++ {
		if _, err := pool.Exec(ctx,
			`INSERT INTO books(owner_user_id,title,is_bible,lifecycle_state) VALUES($1,'at-cap',false,'active')`,
			owner); err != nil {
			t.Fatalf("seed book %d: %v", i, err)
		}
	}

	// Sanity: the count helper sees exactly `cap` active books.
	if got, err := s.countActiveBooks(ctx, owner); err != nil || got != cap {
		t.Fatalf("countActiveBooks = %d, err=%v; want %d", got, err, cap)
	}

	tctx := identityCtxForTest(t, owner)
	_, _, err := s.toolBookCreate(tctx, nil, bookCreateIn{Title: "one too many"})
	if err == nil {
		t.Fatalf("book_create at cap = nil error, want refusal")
	}
	if !strings.Contains(err.Error(), "book limit reached") {
		t.Errorf("err = %v, want 'book limit reached'", err)
	}

	// No new row was inserted — count is still exactly `cap`.
	var n int
	if err := pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM books WHERE owner_user_id=$1 AND is_bible=false AND lifecycle_state='active'`,
		owner).Scan(&n); err != nil {
		t.Fatalf("recount: %v", err)
	}
	if n != cap {
		t.Errorf("active book count = %d, want %d (refused create must NOT insert)", n, cap)
	}
}

// headerRoundTripper injects the kit identity envelope (X-Internal-Token +
// X-User-Id) onto every outgoing MCP request so the in-process httptest server's
// IdentityMiddleware authenticates the caller — the same headers the gateway
// stamps on a real /mcp call.
type headerRoundTripper struct {
	rt     http.RoundTripper
	userID string
}

func (h headerRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	req.Header.Set(lwmcp.HeaderInternalToken, mcpTestToken)
	req.Header.Set(lwmcp.HeaderUserID, h.userID)
	return h.rt.RoundTrip(req)
}

// TestMCP_BookList_OutputValidates_DB is the regression guard for the go-sdk
// output-schema bug: a UUID OUTPUT field reflected to JSON type "array" (from
// [16]byte) but marshaled as a string, so the SERVER rejected its own output
// ("validating tool output: .../book_id: <uuid> has type \"string\", want
// \"array\""). The empty-list COMPOSE-B smoke could not catch it (no items → no
// item validation). Here we seed a book owned by the caller, call book_list
// THROUGH the real /mcp handler (identity middleware + stateless StreamableHTTP +
// the go-sdk's output validator), and assert the call returns a NON-error result
// whose book_id is the seeded id rendered as a STRING.
func TestMCP_BookList_OutputValidates_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedChapter(t, ctx, pool, owner) // book owned by `owner`, active, not a bible

	// Stand up the genuine /mcp handler (X-Internal-Token gate + envelope→ctx +
	// the stateless StreamableHTTP transport that runs the output-schema validator).
	srv := httptest.NewServer(s.mcpHandler())
	t.Cleanup(srv.Close)

	transport := &mcp.StreamableClientTransport{
		Endpoint: srv.URL,
		HTTPClient: &http.Client{
			Transport: headerRoundTripper{rt: http.DefaultTransport, userID: owner.String()},
		},
		DisableStandaloneSSE: true, // request/response only (JSONResponse:true server)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "0.0.1"}, nil)
	cs, err := client.Connect(ctx, transport, nil)
	if err != nil {
		t.Fatalf("connect /mcp: %v", err)
	}
	t.Cleanup(func() { _ = cs.Close() })

	res, err := cs.CallTool(ctx, &mcp.CallToolParams{Name: "book_list"})
	if err != nil {
		// A protocol-level error here is the output-validation failure surfacing
		// (the server refuses to emit output that violates its own schema).
		t.Fatalf("book_list call failed (the output-schema bug regressed?): %v", err)
	}
	if res.IsError {
		t.Fatalf("book_list returned isError=true (output validation failed): %+v", res.Content)
	}

	// The structured result must carry the seeded book_id as a STRING.
	raw, err := json.Marshal(res.StructuredContent)
	if err != nil {
		t.Fatalf("marshal structured content: %v", err)
	}
	var out bookListOut
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("unmarshal book_list output: %v; raw=%s", err, raw)
	}
	if out.Total < 1 || len(out.Books) < 1 {
		t.Fatalf("book_list returned no books for the owner; out=%s", raw)
	}
	var found bool
	for _, b := range out.Books {
		if b.BookID == bookID.String() {
			found = true
		}
	}
	if !found {
		t.Errorf("seeded book_id %s (as string) not in book_list output; raw=%s", bookID, raw)
	}
}
