package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"maps"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// insertOutboxEvent writes a transactional outbox event within the given tx.
// The outbox row lives in the same database as the mutation, ensuring atomicity.
// The worker-infra service polls/listens for new rows and relays them to Redis Streams.
func insertOutboxEvent(ctx context.Context, tx pgx.Tx, eventType string, aggregateID uuid.UUID, payload map[string]any) error {
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("outbox marshal: %w", err)
	}
	_, err = tx.Exec(ctx, `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		VALUES ('chapter', $1, $2, $3)
	`, aggregateID, eventType, payloadJSON)
	if err != nil {
		return fmt.Errorf("outbox insert: %w", err)
	}
	return nil
}

// ScenesLinkedEvent is the event_type emitted whenever this chapter's scene→spec back-links
// (`scenes.source_scene_id`) may have changed. SC11-amendment Phase 0.
//
// WHY IT CARRIES NO LINK DATA. The payload is {book_id, chapter_id} and nothing else: the
// consumer RE-READS the chapter's scenes and reconciles. An event carrying the mappings would
// let a stale or out-of-order delivery overwrite newer state — a re-read is idempotent,
// order-insensitive and self-healing. (The relay is at-least-once; design for redelivery.)
//
// WHY NOT REUSE `chapter.scenes_reparsed`. knowledge-service already consumes that one to drive
// extraction (`main.py` dispatcher.register). Emitting it from two MORE sites would silently
// change another service's event volume. A new type has exactly one consumer and zero blast
// radius.
//
// THE THREE WRITERS of `scenes.source_scene_id` — all three must emit, or a book renders as
// partly/entirely unwritten:
//  1. parse.go       — the import INSERT (guarded: only when the parser actually recovered an anchor)
//  2. reparse.go     — via its callers' `counts.changed()` guard (kg_index.go, mcp_actions.go)
//  3. worker-infra   — the IX-12 decompile write-back. THIS ONE EMITTED NOTHING before Phase 0,
//     which is precisely the write that creates the link for a decompiled book.
const ScenesLinkedEvent = "chapter.scenes_linked"

// emitScenesLinked writes `chapter.scenes_linked` into the outbox in the caller's tx (atomic with
// the link write — INV-O12: an emit that cannot be written must roll the mutation back, never be
// swallowed, or the projection silently diverges from the truth it mirrors).
func emitScenesLinked(ctx context.Context, tx pgx.Tx, bookID, chapterID uuid.UUID) error {
	return insertOutboxEvent(ctx, tx, ScenesLinkedEvent, chapterID, map[string]any{
		"book_id":    bookID,
		"chapter_id": chapterID,
	})
}

// jobServiceName is the value stored in the JobEvent payload's `service` field (and the
// jobs-service `job_projection.service` + reconcile `_RECONCILE` key). The physical owner.
const jobServiceName = "book"

// canonicalJobStatus maps a book-service-native import status to the canonical control-plane
// JobStatus. Mirrors the Python SDK's `_coerce_status` + `_STATUS_ALIASES`: an UNMAPPABLE
// status returns "" so the caller SKIPS the emit rather than poisoning the stream with a
// status the jobs-service projection can't parse (the reconcile sweep is the backstop).
var canonicalJobStatus = map[string]string{
	"pending":     "pending",
	"queued":      "pending",
	"created":     "pending",
	"running":     "running",
	"processing":  "running",
	"in_progress": "running",
	"paused":      "paused",
	"cancelling":  "cancelling",
	"completed":   "completed",
	"complete":    "completed",
	"succeeded":   "completed",
	"done":        "completed",
	"failed":      "failed",
	"error":       "failed",
	"cancelled":   "cancelled",
	"canceled":    "cancelled",
}

// importJobEventPayload maps one import_jobs row to the canonical JobEvent payload the
// jobs-service reconcile sweep upserts. Returns (payload, false) when the native status has
// no canonical mapping — the caller SKIPS it (don't ship a status the projection can't parse).
// Pure (no DB) so the reconcile transform is unit-testable without a pool mock.
func importJobEventPayload(id, ownerUserID uuid.UUID, nativeStatus string, chapters int, errMsg *string, ts time.Time) (map[string]any, bool) {
	status, ok := canonicalJobStatus[nativeStatus]
	if !ok {
		return nil, false
	}
	job := map[string]any{
		"service":       jobServiceName,
		"job_id":        id.String(),
		"owner_user_id": ownerUserID.String(),
		"kind":          "book_import",
		"status":        status,
		"parent_job_id": nil,
		"detail_status": nil,
		"progress":      map[string]any{"done": chapters},
		"title":         nil,
		"error":         nil,
		"occurred_at":   ts.UTC().Format(time.RFC3339Nano),
	}
	if status == "failed" && errMsg != nil {
		job["error"] = map[string]any{"code": "book_import_failed", "message": *errMsg}
	}
	return job, true
}

// emitJobEvent writes a Unified Job Control Plane lifecycle event into the outbox in the
// given tx (H1: atomic with the status write). aggregate_type='jobs' → the worker-infra relay
// routes it to `loreweave:events:jobs` → the jobs-service projection (D-JOBS-BOOK-IMPORT-UNWIRED).
// `nativeStatus` is canonicalized; an unmappable status SKIPS the emit (returns nil, logs) so a
// new native status can never roll back the producer's status-change tx. `extra` carries the
// optional JobEvent fields (progress, title, error, params, …); never owner/kind/status.
func emitJobEvent(ctx context.Context, tx pgx.Tx, jobID, ownerUserID uuid.UUID, kind, nativeStatus string, extra map[string]any) error {
	status, ok := canonicalJobStatus[nativeStatus]
	if !ok {
		slog.WarnContext(ctx, "emitJobEvent: skipping unmappable status", "kind", kind, "status", nativeStatus, "job_id", jobID)
		return nil
	}
	payload := map[string]any{
		"service":       jobServiceName,
		"job_id":        jobID.String(),
		"owner_user_id": ownerUserID.String(),
		"kind":          kind,
		"status":        status,
		"occurred_at":   time.Now().UTC().Format(time.RFC3339Nano),
	}
	maps.Copy(payload, extra)
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("job outbox marshal: %w", err)
	}
	_, err = tx.Exec(ctx, `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		VALUES ('jobs', $1, $2, $3)
	`, jobID, "job."+status, payloadJSON)
	if err != nil {
		return fmt.Errorf("job outbox insert: %w", err)
	}
	return nil
}
