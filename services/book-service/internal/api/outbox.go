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
		slog.Warn("emitJobEvent: skipping unmappable status", "kind", kind, "status", nativeStatus, "job_id", jobID)
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
