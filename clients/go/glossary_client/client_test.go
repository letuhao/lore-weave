package glossary_client

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func staticSVID(token string) SVIDProvider {
	return func(context.Context) (string, error) { return token, nil }
}

func newTestClient(t *testing.T, srv *httptest.Server) *Client {
	t.Helper()
	c, err := New(ClientConfig{
		BaseURL:  srv.URL,
		SVID:     staticSVID("test-svid"),
		ClientID: "test-cycle25",
	})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return c
}

func TestNew_RejectsEmptyBaseURL(t *testing.T) {
	_, err := New(ClientConfig{SVID: staticSVID("x")})
	if err == nil {
		t.Fatal("expected error for empty BaseURL")
	}
}

func TestNew_RejectsMissingSVID(t *testing.T) {
	_, err := New(ClientConfig{BaseURL: "http://x"})
	if err == nil {
		t.Fatal("expected error for missing SVID")
	}
}

func TestGetCanonEntry_HappyPath(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Q-L5-4 HTTP/JSON V1.
		if r.Method != http.MethodGet {
			t.Errorf("method=%s want GET", r.Method)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer test-svid" {
			t.Errorf("Authorization=%q", got)
		}
		if got := r.Header.Get("X-Client-ID"); got != "test-cycle25" {
			t.Errorf("X-Client-ID=%q", got)
		}
		if !strings.Contains(r.URL.Path, "/v1/canon/book-1/world.climate") {
			t.Errorf("path=%s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(CanonEntry{
			CanonEntryID:  "ce-1",
			BookID:        "book-1",
			AttributePath: "world.climate",
			Value:         json.RawMessage(`"arid"`),
			CanonLayer:    "L1_axiom",
			LockLevel:     "hard",
			LastSyncedAt:  time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC),
		})
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	got, err := c.GetCanonEntry(context.Background(), "book-1", "world.climate", "")
	if err != nil {
		t.Fatalf("GetCanonEntry: %v", err)
	}
	if got.CanonLayer != "L1_axiom" {
		t.Fatalf("Q-L5-3 canon_layer drift: %s", got.CanonLayer)
	}
	if string(got.Value) != `"arid"` {
		t.Fatalf("value drift: %s", got.Value)
	}
}

func TestGetCanonEntry_WithRealityID(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.URL.Query().Get("reality_id"); got != "reality-A" {
			t.Errorf("reality_id query=%q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		realityID := "reality-A"
		overrideID := "l3-evt-99"
		_ = json.NewEncoder(w).Encode(CanonEntry{
			CanonEntryID:          "ce-1",
			BookID:                "book-1",
			AttributePath:         "world.climate",
			Value:                 json.RawMessage(`"tropical"`),
			CanonLayer:            "L2_seeded",
			LockLevel:             "soft",
			RealityID:             &realityID,
			OverriddenByL3EventID: &overrideID,
			LastSyncedAt:          time.Now().UTC(),
		})
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	got, err := c.GetCanonEntry(context.Background(), "book-1", "world.climate", "reality-A")
	if err != nil {
		t.Fatalf("GetCanonEntry: %v", err)
	}
	if got.RealityID == nil || *got.RealityID != "reality-A" {
		t.Fatalf("reality_id not echoed")
	}
	if got.OverriddenByL3EventID == nil {
		t.Fatal("per-reality response should carry overridden_by_l3_event_id signal")
	}
}

func TestGetCanonEntry_NotFound(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()
	c := newTestClient(t, srv)
	_, err := c.GetCanonEntry(context.Background(), "book-x", "world.climate", "")
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("expected ErrNotFound, got %v", err)
	}
}

func TestGetCanonEntry_Forbidden_ACL(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer srv.Close()
	c := newTestClient(t, srv)
	_, err := c.GetCanonEntry(context.Background(), "book-x", "world.climate", "")
	if !errors.Is(err, ErrForbidden) {
		t.Fatalf("expected ErrForbidden, got %v", err)
	}
}

func TestListCanonEntries_SincePagination(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.URL.Query().Get("since"); got == "" {
			t.Error("since= missing")
		}
		if got := r.URL.Query().Get("limit"); got != "50" {
			t.Errorf("limit=%s", got)
		}
		next := "cursor-N"
		_ = json.NewEncoder(w).Encode(CanonEntryPage{
			Entries:    []CanonEntry{{CanonEntryID: "ce-1", BookID: "b1", AttributePath: "world.climate", CanonLayer: "L2_seeded", LockLevel: "soft"}},
			NextCursor: &next,
		})
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	since := time.Date(2026, 5, 28, 0, 0, 0, 0, time.UTC)
	page, err := c.ListCanonEntries(context.Background(), "b1", &since, 50, "")
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(page.Entries) != 1 {
		t.Fatalf("entries len=%d want 1", len(page.Entries))
	}
	if page.NextCursor == nil || *page.NextCursor != "cursor-N" {
		t.Fatal("next_cursor missing")
	}
}

func TestWriteCanonEntry_HappyPath(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("method=%s want POST", r.Method)
		}
		var req CanonWriteRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("decode req: %v", err)
		}
		if req.CanonLayer != "L2_seeded" {
			t.Errorf("Q-L5-3 canon_layer=%s", req.CanonLayer)
		}
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(CanonWriteResponse{
			CanonEntryID: "ce-new",
			WrittenAt:    time.Now().UTC(),
			CanonLayer:   req.CanonLayer,
		})
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	resp, err := c.WriteCanonEntry(context.Background(), CanonWriteRequest{
		BookID:        "b1",
		AttributePath: "world.climate",
		Value:         json.RawMessage(`"arid"`),
		CanonLayer:    "L2_seeded",
	})
	if err != nil {
		t.Fatalf("Write: %v", err)
	}
	if resp.CanonEntryID != "ce-new" {
		t.Fatalf("canon_entry_id drift")
	}
}

func TestWriteCanonEntry_GuardrailRejected_Q_L5_5(t *testing.T) {
	// Q-L5-5: server returns 409 with GuardrailViolation; client must
	// surface as *GuardrailRejectedError.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusConflict)
		_, _ = fmt.Fprintf(w, `{
			"code": "canon_guardrail_l1_conflict",
			"axiom": {
				"book_id": "b1",
				"attribute_path": "world.climate",
				"canon_layer": "L1_axiom",
				"value": "\"arid\""
			},
			"proposed_value": "\"tropical\"",
			"reason": "world.climate is L1 axiom = arid; cannot override"
		}`)
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	_, err := c.WriteCanonEntry(context.Background(), CanonWriteRequest{
		BookID:        "b1",
		AttributePath: "world.climate",
		Value:         json.RawMessage(`"tropical"`),
		CanonLayer:    "L2_seeded",
	})
	if err == nil {
		t.Fatal("expected guardrail rejection")
	}
	var gv *GuardrailRejectedError
	if !errors.As(err, &gv) {
		t.Fatalf("expected *GuardrailRejectedError, got %T", err)
	}
	if gv.Code != "canon_guardrail_l1_conflict" {
		t.Fatalf("Q-L5-5 violation code drift: %s", gv.Code)
	}
	if gv.Axiom.CanonLayer != "L1_axiom" {
		t.Fatalf("axiom must always be L1_axiom for guardrail rejects, got %s", gv.Axiom.CanonLayer)
	}
}

func TestExportCanonForSeed_StreamsNDJSON(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/x-ndjson")
		// 2 entries + envelope.
		entries := []CanonEntry{
			{CanonEntryID: "ce-1", BookID: "b1", AttributePath: "world.climate", CanonLayer: "L1_axiom", LockLevel: "hard"},
			{CanonEntryID: "ce-2", BookID: "b1", AttributePath: "faction.banner", CanonLayer: "L2_seeded", LockLevel: "soft"},
		}
		for _, e := range entries {
			b, _ := json.Marshal(e)
			_, _ = w.Write(b)
			_, _ = w.Write([]byte("\n"))
		}
		env := SeedExportEnvelope{
			Envelope:   "seed_export_complete",
			SnapshotAt: time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC),
			EntryCount: 2,
		}
		b, _ := json.Marshal(env)
		_, _ = w.Write(b)
		_, _ = w.Write([]byte("\n"))
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	got := []string{}
	env, err := c.ExportCanonForSeed(context.Background(), "b1", func(e CanonEntry) error {
		got = append(got, e.AttributePath)
		return nil
	})
	if err != nil {
		t.Fatalf("Export: %v", err)
	}
	if env.EntryCount != 2 {
		t.Fatalf("envelope entry_count=%d want 2", env.EntryCount)
	}
	if len(got) != 2 {
		t.Fatalf("visited %d entries, want 2", len(got))
	}
	if got[0] != "world.climate" || got[1] != "faction.banner" {
		t.Fatalf("entry order drift: %v", got)
	}
}

func TestClient_SVIDFailurePropagates(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {}))
	defer srv.Close()
	c, _ := New(ClientConfig{
		BaseURL: srv.URL,
		SVID:    func(context.Context) (string, error) { return "", errors.New("workload api down") },
	})
	_, err := c.GetCanonEntry(context.Background(), "b1", "world.climate", "")
	if err == nil {
		t.Fatal("expected SVID error to propagate")
	}
	if !strings.Contains(err.Error(), "workload api down") {
		t.Fatalf("SVID error not wrapped: %v", err)
	}
}

func TestClient_RetriesFreeByDesign(t *testing.T) {
	// Per package doc: the client is RETRY-FREE. A 503 propagates as
	// HTTPError; the caller wraps with cycle-18 resilience.WithRetry.
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls++
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = io.WriteString(w, `{"code":"upstream_down","message":"flake"}`)
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	_, err := c.GetCanonEntry(context.Background(), "b1", "world.climate", "")
	if err == nil {
		t.Fatal("expected error")
	}
	var he *HTTPError
	if !errors.As(err, &he) {
		t.Fatalf("expected *HTTPError, got %T", err)
	}
	if he.StatusCode != 503 {
		t.Fatalf("status=%d", he.StatusCode)
	}
	if calls != 1 {
		t.Fatalf("client retried (calls=%d); should be retry-free", calls)
	}
}
