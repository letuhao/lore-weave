package tasks

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// 26 IX-12 — the client parses the decompile map and forwards the internal token.
// The write-back UPDATE itself needs a live book DB (covered by the import live-smoke);
// here we pin the contract: token header, URL shape, mappings decode, graceful no-op.

func TestMaterializeClient_ParsesMappingsAndSendsToken(t *testing.T) {
	var gotToken, gotPath string
	var gotBody materializeRequest
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotToken = r.Header.Get("X-Internal-Token")
		gotPath = r.URL.Path
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"work_resolved":true,"created":2,"matched":1,"mappings":[
			{"chapter_id":"ch-1","sort_order":0,"outline_node_id":"node-a"},
			{"chapter_id":"ch-1","sort_order":1,"outline_node_id":"node-b"}]}`))
	}))
	defer srv.Close()

	c := NewMaterializeClient(srv.URL, "tok-123")
	res, err := c.Materialize(context.Background(), "book-9", "user-7")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if gotToken != "tok-123" {
		t.Errorf("internal token not forwarded: %q", gotToken)
	}
	if gotPath != "/internal/books/book-9/materialize-scenes" {
		t.Errorf("wrong path: %q", gotPath)
	}
	if gotBody.OwnerUserID != "user-7" {
		t.Errorf("owner_user_id not sent: %q", gotBody.OwnerUserID)
	}
	if !res.WorkResolved || len(res.Mappings) != 2 {
		t.Fatalf("bad decode: %+v", res)
	}
	if res.Mappings[1].OutlineNodeID != "node-b" || res.Mappings[1].SortOrder != 1 {
		t.Errorf("mapping decode wrong: %+v", res.Mappings[1])
	}
}

func TestMaterializeClient_WorkLessBookIsGracefulNoOp(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		// The composition endpoint reports a Work-less book with 200 + work_resolved=false,
		// NOT an error — the write-back must treat it as a no-op, not a failure.
		_, _ = w.Write([]byte(`{"work_resolved":false,"created":0,"matched":0,"mappings":[],"detail":"no canonical work"}`))
	}))
	defer srv.Close()

	c := NewMaterializeClient(srv.URL, "tok")
	res, err := c.Materialize(context.Background(), "book-1", "user-1")
	if err != nil {
		t.Fatalf("work-less book must not error: %v", err)
	}
	if res.WorkResolved || len(res.Mappings) != 0 {
		t.Errorf("expected graceful no-op, got %+v", res)
	}
}

func TestMaterializeClient_Non200IsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(`{"detail":"book-service scene read failed"}`))
	}))
	defer srv.Close()

	c := NewMaterializeClient(srv.URL, "tok")
	if _, err := c.Materialize(context.Background(), "b", "u"); err == nil {
		t.Fatal("expected an error on non-200")
	}
}
