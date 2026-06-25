package api

// D-BATCH-RESEARCH-JOB M2 — the in-process batch-research worker.
//
// A single background loop drains `pending` jobs one entity at a time, reusing
// researchOneEntity (the shared web-search → INV-6 neutralize → attach-evidence core).
// glossary already runs in-process background consumers (internal/events/*), so this is
// the established pattern — no proxy to knowledge.
//
// Crash-safety: every researched entity persists the cursor + counters + a heartbeat
// (updated_at) in one UPDATE, so a restarted worker resumes from cursor_entity_id and a
// crashed worker's `running` job is reclaimed once its heartbeat goes stale. The claim
// uses FOR UPDATE SKIP LOCKED so it stays correct if a second replica is ever added.
//
// Cost: max_entities caps the number of PAID searches (web search has no per-call cost
// signal — BYOK). Already-researched / anchorless entities are skipped FREE.

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"github.com/google/uuid"
)

const (
	researchWorkerTick  = 5 * time.Second
	researchJobLeaseTTL = 5 * time.Minute // a 'running' job idle past this is reclaimable (crash recovery)
)

// researchJobWork is a claimed job's mutable working state (counters + cursor) — distinct
// from the read-only researchJobView the API returns.
type researchJobWork struct {
	JobID           uuid.UUID
	BookID          uuid.UUID
	OwnerUserID     uuid.UUID
	KindID          uuid.UUID
	QueryTemplate   string
	MaxResults      int
	MaxEntities     int
	ItemsProcessed  int
	SearchesRun     int
	SourcesAttached int
	Cursor          *uuid.UUID
}

// RunResearchWorker is the background drain loop. Honours ctx for shutdown. Each tick it
// claims + fully drains every available job, then waits for the next tick.
func (s *Server) RunResearchWorker(ctx context.Context) {
	ticker := time.NewTicker(researchWorkerTick)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			for {
				job, ok := s.claimNextResearchJob(ctx)
				if !ok {
					break // nothing claimable this tick
				}
				s.drainResearchJob(ctx, job)
			}
		}
	}
}

// claimNextResearchJob atomically flips one job to 'running' and returns its working
// state. Claims a `pending` job OR a stale `running` one (a crashed worker's job, idle
// past the lease). FOR UPDATE SKIP LOCKED makes concurrent claimers pick distinct rows.
func (s *Server) claimNextResearchJob(ctx context.Context) (researchJobWork, bool) {
	var j researchJobWork
	err := s.pool.QueryRow(ctx, `
		UPDATE entity_research_jobs SET status='running', updated_at=now()
		WHERE job_id = (
			SELECT job_id FROM entity_research_jobs
			WHERE status='pending'
			   OR (status='running' AND updated_at < now() - $1::interval)
			ORDER BY created_at
			FOR UPDATE SKIP LOCKED
			LIMIT 1
		)
		RETURNING job_id, book_id, owner_user_id, kind_id, query_template, max_results,
		          max_entities, items_processed, searches_run, sources_attached, cursor_entity_id`,
		researchJobLeaseTTL.String(),
	).Scan(&j.JobID, &j.BookID, &j.OwnerUserID, &j.KindID, &j.QueryTemplate, &j.MaxResults,
		&j.MaxEntities, &j.ItemsProcessed, &j.SearchesRun, &j.SourcesAttached, &j.Cursor)
	if isNoRows(err) {
		return researchJobWork{}, false
	}
	if err != nil {
		slog.Warn("research-worker claim failed", "error", err)
		return researchJobWork{}, false
	}
	return j, true
}

// drainResearchJob visits entities of the job's kind in cursor order, researching each
// that needs it until the paid-search cap (max_entities) is hit or the kind is exhausted.
// Stops early (leaving the job's status untouched) when a pause/cancel lands between
// entities. A web-search error fails the job WITHOUT advancing the cursor, so a resume
// retries the failed entity.
func (s *Server) drainResearchJob(ctx context.Context, job researchJobWork) {
	ids, err := s.entitiesOfKindAfterCursor(ctx, job.BookID, job.KindID, job.Cursor)
	if err != nil {
		s.failResearchJob(ctx, job.JobID, "could not enumerate entities")
		return
	}
	for _, eid := range ids {
		if job.SearchesRun >= job.MaxEntities {
			break // paid-search cap reached → done
		}
		// Re-read status between entities so a pause/cancel is honoured promptly.
		switch st := s.researchJobStatus(ctx, job.JobID); st {
		case "running":
			// proceed
		default:
			return // paused_user / cancelled / vanished — stop, leave status as set
		}

		name, _ := entityNameAndAliases(ctx, s.pool, eid)
		attrValueID, hasAnchor, _ := s.entityDisplayAttrValue(ctx, eid)
		skip := !hasAnchor || strings.TrimSpace(name) == "" || s.hasReferenceEvidence(ctx, attrValueID)
		if skip {
			job.ItemsProcessed++
			cur := eid
			job.Cursor = &cur
			s.persistResearchProgress(ctx, job)
			continue
		}

		query := strings.ReplaceAll(job.QueryTemplate, "{name}", name)
		_, attached, _, rerr := s.researchOneEntity(ctx, job.OwnerUserID, eid, query, job.MaxResults)
		if rerr != nil {
			// Fail WITHOUT advancing the cursor — resume retries this entity.
			s.failResearchJob(ctx, job.JobID, "web search failed: "+rerr.Error())
			return
		}
		job.SearchesRun++
		job.SourcesAttached += attached
		job.ItemsProcessed++
		cur := eid
		job.Cursor = &cur
		s.persistResearchProgress(ctx, job)
	}
	s.completeResearchJob(ctx, job.JobID)
}

// entitiesOfKindAfterCursor lists live entity ids of the kind in a stable order, resuming
// after `cursor` (exclusive). Ordered by entity_id so the cursor is a total resume point.
func (s *Server) entitiesOfKindAfterCursor(ctx context.Context, bookID, kindID uuid.UUID, cursor *uuid.UUID) ([]uuid.UUID, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT entity_id FROM glossary_entities
		WHERE book_id=$1 AND kind_id=$2 AND deleted_at IS NULL
		  AND ($3::uuid IS NULL OR entity_id > $3)
		ORDER BY entity_id`, bookID, kindID, cursor)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]uuid.UUID, 0)
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		out = append(out, id)
	}
	return out, rows.Err()
}

// hasReferenceEvidence reports whether the entity's display attr value already carries ANY
// 'reference' evidence — the skip-already-researched idempotency signal (a re-run of a job
// over a kind only researches the entities not yet researched).
func (s *Server) hasReferenceEvidence(ctx context.Context, attrValueID uuid.UUID) bool {
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM evidences WHERE attr_value_id=$1 AND evidence_type='reference')`,
		attrValueID).Scan(&exists); err != nil {
		return false
	}
	return exists
}

// researchJobStatus reads just the status (the per-entity pause/cancel check).
func (s *Server) researchJobStatus(ctx context.Context, jobID uuid.UUID) string {
	var st string
	if err := s.pool.QueryRow(ctx, `SELECT status FROM entity_research_jobs WHERE job_id=$1`, jobID).Scan(&st); err != nil {
		return ""
	}
	return st
}

// persistResearchProgress writes the cursor + counters + heartbeat in one UPDATE, guarded
// on status='running' so a concurrent pause/cancel is never clobbered back to progress.
func (s *Server) persistResearchProgress(ctx context.Context, job researchJobWork) {
	if _, err := s.pool.Exec(ctx, `
		UPDATE entity_research_jobs
		   SET items_processed=$2, searches_run=$3, sources_attached=$4, cursor_entity_id=$5, updated_at=now()
		 WHERE job_id=$1 AND status='running'`,
		job.JobID, job.ItemsProcessed, job.SearchesRun, job.SourcesAttached, job.Cursor); err != nil {
		slog.Warn("research-worker progress persist failed", "job", job.JobID, "error", err)
	}
}

// completeResearchJob marks a fully-drained job complete (only from 'running' — a job
// paused/cancelled at the last moment is not overwritten).
func (s *Server) completeResearchJob(ctx context.Context, jobID uuid.UUID) {
	if _, err := s.pool.Exec(ctx,
		`UPDATE entity_research_jobs SET status='complete', completed_at=now(), updated_at=now()
		 WHERE job_id=$1 AND status='running'`, jobID); err != nil {
		slog.Warn("research-worker complete failed", "job", jobID, "error", err)
	}
}

// failResearchJob records a terminal failure with a message (only from 'running'). The
// cursor is left where it was so a resume retries from the failing entity.
func (s *Server) failResearchJob(ctx context.Context, jobID uuid.UUID, msg string) {
	if _, err := s.pool.Exec(ctx,
		`UPDATE entity_research_jobs SET status='failed', error_message=$2, updated_at=now()
		 WHERE job_id=$1 AND status='running'`, jobID, msg); err != nil {
		slog.Warn("research-worker fail-mark failed", "job", jobID, "error", err)
	}
}
