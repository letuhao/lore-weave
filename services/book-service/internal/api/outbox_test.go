package api

import (
	"testing"
	"time"

	"github.com/google/uuid"
)

// Unified Job Control Plane (D-JOBS-BOOK-IMPORT-UNWIRED) — the status canonicalization +
// reconcile row→JobEvent mapping are the load-bearing transforms; the DB-touching emit /
// reconcile-query e2e is covered by live-smoke (B3).

func TestCanonicalJobStatusMapsNativeImportStatuses(t *testing.T) {
	cases := map[string]string{
		"pending":    "pending",
		"processing": "running", // the worker's native mid-import status
		"completed":  "completed",
		"failed":     "failed",
	}
	for native, want := range cases {
		if got := canonicalJobStatus[native]; got != want {
			t.Errorf("canonicalJobStatus[%q] = %q, want %q", native, got, want)
		}
	}
}

func TestCanonicalJobStatusUnmappableIsSkipped(t *testing.T) {
	// An unknown native status must NOT map → the emit/reconcile skips it (never ships a
	// status the jobs-service projection can't parse, and never rolls back the producer tx).
	if _, ok := canonicalJobStatus["weird_unmapped"]; ok {
		t.Fatal("expected an unmappable status to be absent from canonicalJobStatus")
	}
}

func TestImportJobEventPayloadShape(t *testing.T) {
	id, owner := uuid.New(), uuid.New()
	ts := time.Date(2026, 6, 17, 12, 0, 0, 0, time.UTC)
	job, ok := importJobEventPayload(id, owner, "processing", 3, nil, ts)
	if !ok {
		t.Fatal("expected processing to map")
	}
	if job["service"] != "book" || job["kind"] != "book_import" {
		t.Errorf("service/kind = %v/%v, want book/book_import", job["service"], job["kind"])
	}
	if job["status"] != "running" { // processing → running
		t.Errorf("status = %v, want running", job["status"])
	}
	if job["job_id"] != id.String() || job["owner_user_id"] != owner.String() {
		t.Errorf("job_id/owner mismatch")
	}
	if p, _ := job["progress"].(map[string]any); p == nil || p["done"] != 3 {
		t.Errorf("progress = %v, want {done:3}", job["progress"])
	}
	if job["error"] != nil {
		t.Errorf("non-failed job must carry no error, got %v", job["error"])
	}
	if job["occurred_at"] != "2026-06-17T12:00:00Z" {
		t.Errorf("occurred_at = %v", job["occurred_at"])
	}
}

func TestImportJobEventPayloadFailedCarriesError(t *testing.T) {
	msg := "pandoc blew up"
	job, ok := importJobEventPayload(uuid.New(), uuid.New(), "failed", 0, &msg, time.Now().UTC())
	if !ok {
		t.Fatal("expected failed to map")
	}
	if job["status"] != "failed" {
		t.Errorf("status = %v, want failed", job["status"])
	}
	e, _ := job["error"].(map[string]any)
	if e == nil || e["code"] != "book_import_failed" || e["message"] != msg {
		t.Errorf("error = %v, want {code:book_import_failed, message:%q}", job["error"], msg)
	}
}

func TestImportJobEventPayloadUnmappableSkipped(t *testing.T) {
	job, ok := importJobEventPayload(uuid.New(), uuid.New(), "weird_unmapped", 0, nil, time.Now().UTC())
	if ok || job != nil {
		t.Errorf("unmappable status must return (nil,false), got (%v,%v)", job, ok)
	}
}
