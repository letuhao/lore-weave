package api

import (
	"encoding/json"
	"net/http"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/pashagolub/pgxmock/v4"
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
