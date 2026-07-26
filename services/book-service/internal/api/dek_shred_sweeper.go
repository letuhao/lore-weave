package api

import (
	"context"
	"log/slog"
	"time"

	"github.com/google/uuid"
)

// P4 (D-DIARY-SHRED-OUTBOX-RETRY) — the durable diary-DEK crypto-shred sweeper. eraseDiaryBook writes a
// pending_dek_shreds row atomically with the content delete and attempts the shred inline; when that inline
// attempt fails (a transient auth blip), this background loop retries the shred until it CONVERGES — so a
// blip can no longer leave the DEK alive with a still-decryptable backup.
//
// THE REUSE-GUARD (why this is not a blind retry): the per-user DEK is shared. After an erase, if the user
// re-provisions a diary and writes NEW content ("erase & start fresh" — the E14 flow) BEFORE the shred lands,
// that new content is encrypted under the still-live DEK. Blind-shredding it then would DESTROY the new
// content — silent data loss. So before every retry the sweeper checks for post-erase diary content; if any
// exists it does NOT shred (it resolves the row + alerts loudly — the old-backup risk is now a conscious
// situation, strictly no worse than today's failed-inline-shred, and never worse than data loss).

// RunDekShredSweeper loops on `interval`, converging up to `batchSize` owed shreds per tick until ctx is
// cancelled. interval <= 0 (or crypto disabled) disables it. Started from cmd/book-service/main.go.
func (s *Server) RunDekShredSweeper(ctx context.Context, interval time.Duration, batchSize int) {
	if interval <= 0 || !s.diaryCrypto.Enabled() {
		slog.Info("book-service: dek-shred sweeper disabled (interval <= 0 or crypto off)")
		return
	}
	slog.Info("book-service: dek-shred sweeper started", "interval", interval.String(), "batch", batchSize)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			slog.Info("book-service: dek-shred sweeper stopping")
			return
		case <-ticker.C:
			converged, skipped, err := s.sweepPendingShreds(ctx, batchSize)
			if err != nil {
				slog.Error("book-service: dek-shred sweep failed", "err", err)
			} else if converged > 0 || skipped > 0 {
				slog.Info("book-service: dek-shred sweep", "converged", converged, "skipped_reuse", skipped)
			}
		}
	}
}

// ownerHasDiaryContent reports whether the owner still has ANY diary chapter. The per-user DEK is
// SHARED across ALL the owner's diary books — an active diary and a trashed "start-fresh" one can
// coexist, and a re-provision mints another under the SAME key — so a crypto-shred is SAFE only when NO
// diary content remains; otherwise it would destroy content it still protects (cold-review HIGH-1/MED-2).
// The inline erase path AND the sweeper both gate every shred on this. Residual (documented): erasing
// ONE of several diaries does NOT crypto-shred, so that diary's backup ciphertext stays decryptable
// until ALL diary content is erased — the safe choice (no data loss) pending per-book DEKs.
func (s *Server) ownerHasDiaryContent(ctx context.Context, owner uuid.UUID) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM chapters c JOIN books b ON b.id=c.book_id
		               WHERE b.owner_user_id=$1 AND b.kind='diary')`, owner).Scan(&exists)
	return exists, err
}

type pendingShred struct {
	owner       uuid.UUID
	bookID      uuid.UUID
	requestedAt time.Time
	attempts    int
}

// sweepPendingShreds converges a batch of owed shreds. Returns (converged, skipped-for-reuse, err).
func (s *Server) sweepPendingShreds(ctx context.Context, batchSize int) (int, int, error) {
	// Round-robin by last attempt (unattempted first) so a stuck poison row can't STARVE newer owed
	// shreds at the head of the batch (cold-review LOW-3); requested_at breaks ties.
	rows, err := s.pool.Query(ctx,
		`SELECT owner_user_id, book_id, requested_at, attempts FROM pending_dek_shreds
		 ORDER BY last_attempt_at ASC NULLS FIRST, requested_at ASC LIMIT $1`, batchSize)
	if err != nil {
		return 0, 0, err
	}
	var batch []pendingShred
	for rows.Next() {
		var p pendingShred
		if err := rows.Scan(&p.owner, &p.bookID, &p.requestedAt, &p.attempts); err != nil {
			rows.Close()
			return 0, 0, err
		}
		batch = append(batch, p)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, 0, err
	}

	converged, skipped := 0, 0
	for _, p := range batch {
		// REUSE-GUARD (cold-review HIGH-1/MED-2) — does the owner still have ANY diary content under the
		// shared DEK (a re-provisioned "start-fresh" diary, OR a coexisting trashed one)? If so the DEK
		// still protects live content; shredding it would be data loss. Resolve the row WITHOUT shredding
		// + alert (the old-backup residual is a conscious tradeoff, never worse than today, never data loss).
		hasContent, err := s.ownerHasDiaryContent(ctx, p.owner)
		if err != nil {
			slog.Error("dek-shred sweep: content-guard query failed; leaving the row for next tick", "user_id", p.owner, "err", err)
			continue
		}
		if hasContent {
			slog.Warn("dek-shred sweep: owner still has diary content under the shared DEK — NOT shredding (data-loss avoided); old backup ciphertext may remain until all diary content is erased",
				"user_id", p.owner)
			_, _ = s.pool.Exec(ctx, `DELETE FROM pending_dek_shreds WHERE owner_user_id=$1`, p.owner)
			skipped++
			continue
		}

		// Safe to converge — no diary content remains under the DEK. Retry the idempotent shred.
		if err := s.diaryCrypto.destroyUserDEK(ctx, p.owner); err != nil {
			_, _ = s.pool.Exec(ctx,
				`UPDATE pending_dek_shreds SET attempts=attempts+1, last_error=$2, last_attempt_at=now()
				 WHERE owner_user_id=$1`, p.owner, err.Error())
			slog.Warn("dek-shred sweep: shred still failing; will retry", "user_id", p.owner, "attempts", p.attempts+1, "err", err)
			continue
		}
		if _, err := s.pool.Exec(ctx, `DELETE FROM pending_dek_shreds WHERE owner_user_id=$1`, p.owner); err != nil {
			slog.Warn("dek-shred sweep: shred converged but clearing the row failed (idempotent — next tick no-ops)", "user_id", p.owner, "err", err)
			continue
		}
		converged++
	}
	return converged, skipped, nil
}
