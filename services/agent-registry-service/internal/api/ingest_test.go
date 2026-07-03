package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"regexp"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/pashagolub/pgxmock/v4"

	"github.com/loreweave/agent-registry-service/internal/config"
)

const adminSub = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
const testIngestID = "019d6000-0000-7000-8000-000000000001"

func TestNormTransport(t *testing.T) {
	cases := map[string]string{
		"streamable-http": "streamable-http",
		"streamable_http": "streamable-http",
		"STREAMABLE-HTTP": "streamable-http",
		" sse ":           "sse",
	}
	for in, want := range cases {
		if got := normTransport(in, ""); got != want {
			t.Errorf("normTransport(%q) = %q, want %q", in, got, want)
		}
	}
	// falls back to transport_type when type is empty
	if got := normTransport("", "streamable_http"); got != "streamable-http" {
		t.Errorf("fallback to transport_type failed: %q", got)
	}
}

func TestMapUpstreamEntry(t *testing.T) {
	t.Run("flat shape, streamable-http remote", func(t *testing.T) {
		raw := json.RawMessage(`{
			"name":"io.github.acme/lore",
			"description":"lore tools",
			"version":"1.2.0",
			"remotes":[{"type":"streamable-http","url":"https://mcp.acme.dev/v1"}]
		}`)
		m, reason := mapUpstreamEntry(raw)
		if reason != "" {
			t.Fatalf("reason = %q, want ok", reason)
		}
		if m.Name != "io.github.acme/lore" || m.Endpoint != "https://mcp.acme.dev/v1" || m.Version != "1.2.0" {
			t.Errorf("bad map: %+v", m)
		}
		if m.RegistryID != "io.github.acme/lore" { // id absent → reverse-DNS name is stable
			t.Errorf("registry_id = %q, want the name", m.RegistryID)
		}
	})

	t.Run("nested server shape + version_detail + transport_type variant", func(t *testing.T) {
		raw := json.RawMessage(`{
			"server":{
				"id":"srv-123",
				"name":"io.github.acme/wiki",
				"version_detail":{"version":"0.9.1"},
				"remotes":[{"transport_type":"streamable_http","url":"https://wiki.acme.dev/mcp"}]
			}
		}`)
		m, reason := mapUpstreamEntry(raw)
		if reason != "" {
			t.Fatalf("reason = %q, want ok", reason)
		}
		if m.RegistryID != "srv-123" || m.Endpoint != "https://wiki.acme.dev/mcp" || m.Version != "0.9.1" {
			t.Errorf("bad nested map: %+v", m)
		}
	})

	t.Run("no usable remote → skip (counted)", func(t *testing.T) {
		// only a non-streamable (sse) remote and a local package — no streamable-http.
		raw := json.RawMessage(`{
			"name":"io.github.acme/sse-only",
			"remotes":[{"type":"sse","url":"https://x/sse"}],
			"packages":[{"registry_type":"npm"}]
		}`)
		_, reason := mapUpstreamEntry(raw)
		if reason != "no_remote" {
			t.Errorf("reason = %q, want no_remote", reason)
		}
	})

	t.Run("no name → invalid", func(t *testing.T) {
		raw := json.RawMessage(`{"description":"x","remotes":[{"type":"streamable-http","url":"https://x"}]}`)
		_, reason := mapUpstreamEntry(raw)
		if reason != "invalid" {
			t.Errorf("reason = %q, want invalid", reason)
		}
	})

	t.Run("first streamable-http wins, empty-url skipped", func(t *testing.T) {
		raw := json.RawMessage(`{
			"name":"io.x/multi",
			"remotes":[
				{"type":"streamable-http","url":""},
				{"type":"sse","url":"https://x/sse"},
				{"type":"streamable-http","url":"https://x/real"}
			]
		}`)
		m, reason := mapUpstreamEntry(raw)
		if reason != "" || m.Endpoint != "https://x/real" {
			t.Errorf("want https://x/real ok, got %q reason=%q", m.Endpoint, reason)
		}
	})
}

// The ingest routes are admin-only: a non-admin JWT is rejected BEFORE any DB op,
// so the mock needs no expectations.
func TestIngestRoutes_AdminOnly(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	user := mintJWT(t, "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c", "user")

	endpoints := []struct{ method, path string }{
		{http.MethodPost, "/v1/agent-registry/admin/ingest/pull"},
		{http.MethodGet, "/v1/agent-registry/admin/ingest/queue"},
		{http.MethodPost, "/v1/agent-registry/admin/ingest/queue/019d5e3c-7cc5-7e6a-8b27-1344e148bf7c/approve"},
		{http.MethodPost, "/v1/agent-registry/admin/ingest/queue/019d5e3c-7cc5-7e6a-8b27-1344e148bf7c/reject"},
	}
	for _, e := range endpoints {
		// non-admin → 403
		rec := doJSON(s, e.method, e.path, user, `{}`)
		if rec.Code != http.StatusForbidden {
			t.Errorf("%s %s (user) → want 403, got %d", e.method, e.path, rec.Code)
		}
		// unauthenticated → 401
		rec = doJSON(s, e.method, e.path, "", `{}`)
		if rec.Code != http.StatusUnauthorized {
			t.Errorf("%s %s (anon) → want 401, got %d", e.method, e.path, rec.Code)
		}
	}
}

// approve loads the queue row, then runs the P3 guard BEFORE any write — so a
// model-capability or SSRF endpoint is rejected with the row untouched. testCfg has
// AllowInternalMcpTargets=false, so an internal target is genuinely blocked.
func approvePath() string {
	return "/v1/agent-registry/admin/ingest/queue/" + testIngestID + "/approve"
}

// anyArgs returns n pgxmock.AnyArg() matchers — pgxmock requires the arg COUNT to
// match the query's bound params (a query with $1..$n rejects a WithArgs of the wrong
// arity, and omitting WithArgs asserts ZERO args).
func anyArgs(n int) []any {
	a := make([]any, n)
	for i := range a {
		a[i] = pgxmock.AnyArg()
	}
	return a
}

func expectQueueRow(mock pgxmock.PgxPoolIface, name, endpoint, status string) {
	mock.ExpectQuery("SELECT name, endpoint_url, status FROM registry_ingest_queue").
		WithArgs(pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows([]string{"name", "endpoint_url", "status"}).AddRow(name, endpoint, status))
}

func TestApproveIngest_ModelCapRejected(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	expectQueueRow(mock, "openai", "https://api.openai.com/v1/chat/completions", "pending")
	rec := doJSON(s, http.MethodPost, approvePath(), mintJWT(t, adminSub, "admin"), `{}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("model endpoint → want 400, got %d (%s)", rec.Code, rec.Body.String())
	}
	var e errorBody
	_ = json.Unmarshal(rec.Body.Bytes(), &e)
	if e.Code != "MODEL_CAPABILITY_NOT_ALLOWED" {
		t.Errorf("code = %q, want MODEL_CAPABILITY_NOT_ALLOWED", e.Code)
	}
}

func TestApproveIngest_SsrfRejected(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	// link-local cloud-metadata IP — blocked by isBlockedIP with no DNS needed.
	expectQueueRow(mock, "evil", "http://169.254.169.254/mcp", "pending")
	rec := doJSON(s, http.MethodPost, approvePath(), mintJWT(t, adminSub, "admin"), `{}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("internal endpoint → want 400, got %d (%s)", rec.Code, rec.Body.String())
	}
	var e errorBody
	_ = json.Unmarshal(rec.Body.Bytes(), &e)
	if e.Code != "SSRF_BLOCKED" {
		t.Errorf("code = %q, want SSRF_BLOCKED", e.Code)
	}
}

func TestApproveIngest_AlreadyReviewed(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	expectQueueRow(mock, "x", "https://mcp.ok.dev/v1", "approved")
	rec := doJSON(s, http.MethodPost, approvePath(), mintJWT(t, adminSub, "admin"), `{}`)
	if rec.Code != http.StatusConflict {
		t.Fatalf("already-approved → want 409, got %d", rec.Code)
	}
}

func TestApproveIngest_NotFound(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	mock.ExpectQuery("SELECT name, endpoint_url, status FROM registry_ingest_queue").
		WithArgs(pgxmock.AnyArg()).
		WillReturnError(pgx.ErrNoRows)
	rec := doJSON(s, http.MethodPost, approvePath(), mintJWT(t, adminSub, "admin"), `{}`)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("unknown id → want 404, got %d", rec.Code)
	}
}

// The INSERT-race recovery branch (§7b#3): if a concurrent approve wins the endpoint
// between our dedup-SELECT and INSERT, the unique index makes our INSERT 23505 → we
// re-SELECT the winner and LINK to it (never a 500, never a duplicate). 8.8.8.8 is a
// public literal IP so classifyRegistrationURL needs no DNS.
func TestApproveIngest_UniqueViolationRaceLinks(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	existing := uuid.MustParse("019d6000-0000-7000-8000-0000000000ee")
	expectQueueRow(mock, "racer", "http://8.8.8.8/mcp", "pending")
	// dedup pre-check finds nothing (the winner hasn't committed yet from our view)
	mock.ExpectQuery("SELECT mcp_server_id FROM mcp_server_registrations WHERE tier='system'").
		WithArgs(anyArgs(1)...).WillReturnError(pgx.ErrNoRows)
	// our INSERT loses the race → 23505
	mock.ExpectQuery("INSERT INTO mcp_server_registrations").
		WithArgs(anyArgs(4)...).WillReturnError(&pgconn.PgError{Code: "23505"})
	// recovery re-SELECT finds the winner
	mock.ExpectQuery("SELECT mcp_server_id FROM mcp_server_registrations WHERE tier='system'").
		WithArgs(anyArgs(1)...).WillReturnRows(pgxmock.NewRows([]string{"mcp_server_id"}).AddRow(existing))
	// finishApprove: queue UPDATE + audit INSERT
	mock.ExpectExec("UPDATE registry_ingest_queue SET status='approved'").
		WithArgs(anyArgs(3)...).WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	mock.ExpectExec("INSERT INTO registry_audit").
		WithArgs(anyArgs(8)...).WillReturnResult(pgxmock.NewResult("INSERT", 1))

	rec := doJSON(s, http.MethodPost, approvePath(), mintJWT(t, adminSub, "admin"), `{}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("race-link → want 200, got %d (%s)", rec.Code, rec.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &body)
	if body["linked_existing"] != true || body["mcp_server_id"] != existing.String() {
		t.Errorf("want linked_existing to the winner %s, got %+v", existing, body)
	}
}

func TestSystemToolPrefix(t *testing.T) {
	p := systemToolPrefix("https://mcp.acme.dev/v1")
	if !regexp.MustCompile(`^s_[0-9a-f]{8}_$`).MatchString(p) {
		t.Errorf("systemToolPrefix = %q, want s_<hash8>_", p)
	}
	// stable + endpoint-keyed (dedup relies on this)
	if p != systemToolPrefix("https://mcp.acme.dev/v1") {
		t.Errorf("systemToolPrefix must be deterministic")
	}
	if p == systemToolPrefix("https://other.dev/v1") {
		t.Errorf("different endpoints must get different prefixes")
	}
}

func TestClampStr(t *testing.T) {
	if clampStr("short", 512) != "short" {
		t.Errorf("under-cap changed")
	}
	long := make([]byte, 600)
	for i := range long {
		long[i] = 'a'
	}
	if got := clampStr(string(long), 512); len(got) != 512 {
		t.Errorf("over-cap len = %d, want 512", len(got))
	}
	// rune-safe: a 2-byte rune ('é') straddling the cut must not be split.
	s := "aaa" + string(rune('é')) // é is 2 bytes; cut at 4 lands mid-rune
	got := clampStr(s, 4)
	if !json.Valid([]byte(`"`+got+`"`)) { // valid UTF-8 → valid JSON string content
		t.Errorf("clampStr split a multi-byte rune: %q", got)
	}
}

// Real HTTP pagination + the truncated flag: page 0 returns one server + a next_cursor,
// the cursor page 500s → the pull is partial and MUST flag Truncated (a denylist-sync
// must not treat a partial pull as a complete snapshot).
func TestPullOfficialRegistry_TruncatedOnMidPullError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("cursor") == "" {
			_, _ = w.Write([]byte(`{"servers":[{"name":"io.x/a","remotes":[{"type":"streamable-http","url":"https://a.dev/mcp"}]}],"metadata":{"next_cursor":"p2"}}`))
			return
		}
		w.WriteHeader(http.StatusInternalServerError) // page 2 fails mid-pull
	}))
	defer srv.Close()

	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	s := NewServer(mock, &config.Config{
		JWTSecret: testCfg().JWTSecret, VaultKey: testCfg().VaultKey,
		OfficialRegistryURL:     srv.URL,
		AllowInternalMcpTargets: true, // httptest is 127.0.0.1 — allow the loopback dial
	})
	mock.ExpectQuery("INSERT INTO registry_ingest_queue").
		WithArgs(anyArgs(6)...).WillReturnRows(pgxmock.NewRows([]string{"inserted"}).AddRow(true))

	counts, err := s.pullOfficialRegistry(context.Background())
	if err != nil {
		t.Fatalf("pull err: %v", err)
	}
	if counts.Fetched != 1 || counts.New != 1 {
		t.Errorf("want fetched=1 new=1, got %+v", counts)
	}
	if !counts.Truncated {
		t.Errorf("mid-pull 500 must flag Truncated; got %+v", counts)
	}
}
