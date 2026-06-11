package grantclient

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"
)

// --- Pure grant logic (security-critical; no I/O) ---

func TestGrantLevelString(t *testing.T) {
	t.Parallel()
	cases := map[GrantLevel]string{
		GrantNone: "none", GrantView: "view", GrantEdit: "edit", GrantManage: "manage", GrantOwner: "owner",
	}
	for lvl, want := range cases {
		if got := lvl.String(); got != want {
			t.Errorf("GrantLevel(%d).String()=%q want %q", lvl, got, want)
		}
	}
}

func TestParseGrantLevel_RoundTripAndDefaultDeny(t *testing.T) {
	t.Parallel()
	// Exact round-trip with book-service's wire strings.
	for _, lvl := range []GrantLevel{GrantNone, GrantView, GrantEdit, GrantManage, GrantOwner} {
		if got := ParseGrantLevel(lvl.String()); got != lvl {
			t.Errorf("round-trip %q: got %v want %v", lvl.String(), got, lvl)
		}
	}
	// Unknown/empty/cased/future → none (default-deny).
	for _, s := range []string{"", "admin", "VIEW", "Owner", "superuser"} {
		if got := ParseGrantLevel(s); got != GrantNone {
			t.Errorf("ParseGrantLevel(%q)=%v want none (default-deny)", s, got)
		}
	}
}

func TestAtLeast(t *testing.T) {
	t.Parallel()
	if !GrantEdit.AtLeast(GrantView) || !GrantEdit.AtLeast(GrantEdit) {
		t.Error("edit must satisfy view and edit")
	}
	if GrantEdit.AtLeast(GrantManage) || GrantView.AtLeast(GrantEdit) {
		t.Error("a lower grant must NOT satisfy a higher need")
	}
	if !GrantOwner.AtLeast(GrantManage) {
		t.Error("owner must satisfy manage")
	}
}

func TestNewClient_Validation(t *testing.T) {
	t.Parallel()
	if _, err := NewClient(Options{InternalToken: "x"}); err == nil {
		t.Error("missing BaseURL must error")
	}
	if _, err := NewClient(Options{BaseURL: "http://b"}); err == nil {
		t.Error("missing InternalToken must error")
	}
	c, err := NewClient(Options{BaseURL: "http://b/", InternalToken: "x"})
	if err != nil {
		t.Fatalf("valid opts: %v", err)
	}
	if c.ttl != DefaultCacheTTL {
		t.Errorf("default ttl=%v want %v", c.ttl, DefaultCacheTTL)
	}
}

// --- HTTP-backed resolution (httptest authority) ---

// stubAuthority returns a book-service /access stub that always replies with
// `level` and counts how many times it was actually hit.
func stubAuthority(t *testing.T, level string) (*httptest.Server, *int64) {
	t.Helper()
	var hits int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt64(&hits, 1)
		if r.Header.Get("X-Internal-Token") != "itok" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"grant_level":"` + level + `"}`))
	}))
	t.Cleanup(srv.Close)
	return srv, &hits
}

func testClient(t *testing.T, baseURL string) *Client {
	t.Helper()
	c, err := NewClient(Options{BaseURL: baseURL, InternalToken: "itok"})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	return c
}

func TestResolveGrant_AllLevels(t *testing.T) {
	t.Parallel()
	for _, want := range []GrantLevel{GrantNone, GrantView, GrantEdit, GrantManage, GrantOwner} {
		srv, _ := stubAuthority(t, want.String())
		c := testClient(t, srv.URL)
		got, err := c.ResolveGrant(context.Background(), uuid.New(), uuid.New())
		if err != nil {
			t.Fatalf("level %v: %v", want, err)
		}
		if got != want {
			t.Errorf("ResolveGrant=%v want %v", got, want)
		}
	}
}

func TestResolveGrant_SendsInternalToken(t *testing.T) {
	t.Parallel()
	srv, _ := stubAuthority(t, "edit")
	c := testClient(t, srv.URL)
	// Wrong token would make the stub 401 → ErrUnavailable; correct token = edit.
	if _, err := c.ResolveGrant(context.Background(), uuid.New(), uuid.New()); err != nil {
		t.Fatalf("expected token accepted, got %v", err)
	}
	bad := testClient(t, srv.URL)
	bad.internalToken = "wrong"
	if _, err := bad.ResolveGrant(context.Background(), uuid.New(), uuid.New()); err != ErrUnavailable {
		t.Errorf("bad token: got %v want ErrUnavailable", err)
	}
}

func TestResolveGrant_PositiveCached(t *testing.T) {
	t.Parallel()
	srv, hits := stubAuthority(t, "edit")
	c := testClient(t, srv.URL)
	book, user := uuid.New(), uuid.New()
	for i := 0; i < 3; i++ {
		if _, err := c.ResolveGrant(context.Background(), book, user); err != nil {
			t.Fatal(err)
		}
	}
	if got := atomic.LoadInt64(hits); got != 1 {
		t.Errorf("positive grant hit authority %d times, want 1 (cached)", got)
	}
}

func TestResolveGrant_NoneNeverCached(t *testing.T) {
	t.Parallel()
	srv, hits := stubAuthority(t, "none")
	c := testClient(t, srv.URL)
	book, user := uuid.New(), uuid.New()
	// A `none` result must re-check every call — else a freshly granted user
	// stays denied for the whole TTL window.
	for i := 0; i < 3; i++ {
		lvl, err := c.ResolveGrant(context.Background(), book, user)
		if err != nil || lvl != GrantNone {
			t.Fatalf("got (%v,%v)", lvl, err)
		}
	}
	if got := atomic.LoadInt64(hits); got != 3 {
		t.Errorf("none hit authority %d times, want 3 (never cached)", got)
	}
}

func TestResolveGrant_PositiveExpires(t *testing.T) {
	t.Parallel()
	srv, hits := stubAuthority(t, "manage")
	c := testClient(t, srv.URL)
	base := time.Unix(1_700_000_000, 0)
	c.now = func() time.Time { return base }
	book, user := uuid.New(), uuid.New()

	if _, err := c.ResolveGrant(context.Background(), book, user); err != nil { // miss → store exp=base+60s
		t.Fatal(err)
	}
	c.now = func() time.Time { return base.Add(59 * time.Second) } // still valid
	if _, err := c.ResolveGrant(context.Background(), book, user); err != nil {
		t.Fatal(err)
	}
	if got := atomic.LoadInt64(hits); got != 1 {
		t.Fatalf("within TTL hit %d times, want 1", got)
	}
	c.now = func() time.Time { return base.Add(61 * time.Second) } // expired
	if _, err := c.ResolveGrant(context.Background(), book, user); err != nil {
		t.Fatal(err)
	}
	if got := atomic.LoadInt64(hits); got != 2 {
		t.Errorf("after TTL hit %d times, want 2 (re-fetched on expiry)", got)
	}
}

func TestResolveGrant_FailClosed(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	t.Cleanup(srv.Close)
	c := testClient(t, srv.URL)
	lvl, err := c.ResolveGrant(context.Background(), uuid.New(), uuid.New())
	if lvl != GrantNone || err != ErrUnavailable {
		t.Errorf("authority 503: got (%v,%v) want (none, ErrUnavailable)", lvl, err)
	}
}

func TestRequireGrant(t *testing.T) {
	t.Parallel()
	srv, _ := stubAuthority(t, "edit")
	c := testClient(t, srv.URL)
	book, user := uuid.New(), uuid.New()
	// edit satisfies view+edit...
	for _, need := range []GrantLevel{GrantView, GrantEdit} {
		if err := c.RequireGrant(context.Background(), book, user, need); err != nil {
			t.Errorf("edit should satisfy %v, got %v", need, err)
		}
	}
	// ...but not manage/owner.
	for _, need := range []GrantLevel{GrantManage, GrantOwner} {
		if err := c.RequireGrant(context.Background(), book, user, need); err != ErrForbidden {
			t.Errorf("edit must NOT satisfy %v: got %v want ErrForbidden", need, err)
		}
	}
}

func TestRequireGrant_UnavailableFailsClosed(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	t.Cleanup(srv.Close)
	c := testClient(t, srv.URL)
	if err := c.RequireGrant(context.Background(), uuid.New(), uuid.New(), GrantView); err != ErrUnavailable {
		t.Errorf("unreachable authority: got %v want ErrUnavailable", err)
	}
}
