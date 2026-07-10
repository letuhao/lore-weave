package api

import (
	"context"
	"errors"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// reparse_sweeper.go — 26 IX-3 (Build 26 Phase B, B4). The staleness healer.
//
// A background goroutine re-parses any PUBLISHED chapter whose index is stale by
// the SAME predicate the publish producer guards on
// (last_parsed_revision_id IS DISTINCT FROM published_revision_id) — the
// reconcile-by-truth-mirror-producer-predicate lesson: heal and produce can
// never disagree about what "stale" means. It re-parses the PINNED revision body
// (never the draft — IX-1) and emits the same frozen chapter.scenes_reparsed
// event. This is also the legacy backfill: on first run every already-published
// chapter (imported OR typed-only, which has zero scenes rows) is stale by
// predicate once last_parsed_revision_id ships NULL, so it gets indexed once.
//
// The draft-indexed corpus (worker imports predating IX-1's corollary, or a
// later chapter.unpublished) is OUTSIDE the editorial_status='published' gate by
// design — it is not stale, it is unpublished, and is indexed on its next
// publish through the normal IX-2 path.

// sweepTarget is one stale chapter's pinned-revision snapshot, read outside any
// transaction so the (potentially slow) /internal/parse call never holds a row
// lock. The Tx is opened per chapter afterward.
type sweepTarget struct {
	chapterID      uuid.UUID
	bookID         uuid.UUID
	publishedRev   uuid.UUID
	lang           string
	structuralPath string
	body           string
}

// RunReparseSweeper loops on `interval`, healing up to `batchSize` stale
// chapters per tick until ctx is cancelled. interval <= 0 disables it. Started
// from cmd/book-service/main.go on a shutdown-scoped context.
func (s *Server) RunReparseSweeper(ctx context.Context, interval time.Duration, batchSize int) {
	if interval <= 0 {
		slog.Info("book-service: reparse sweeper disabled (interval <= 0)")
		return
	}
	slog.Info("book-service: reparse sweeper started", "interval", interval.String(), "batch", batchSize)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			slog.Info("book-service: reparse sweeper stopping")
			return
		case <-ticker.C:
			healed, err := s.sweepStaleChapters(ctx, batchSize)
			if err != nil {
				slog.Error("book-service: reparse sweep failed", "err", err)
			} else if healed > 0 {
				slog.Info("book-service: reparse sweep healed chapters", "count", healed)
			}
		}
	}
}

// sweepStaleChapters selects a batch of stale published chapters (the IX-3
// predicate) and re-parses each. Returns the number healed. Reads the whole
// batch (including the pinned revision body) up front and closes the cursor
// before opening any per-chapter Tx.
func (s *Server) sweepStaleChapters(ctx context.Context, batchSize int) (int, error) {
	rows, err := s.pool.Query(ctx, `
SELECT c.id, c.book_id, c.published_revision_id, COALESCE(c.original_language,''),
       c.structural_path, r.body::text
FROM chapters c
JOIN chapter_revisions r ON r.id = c.published_revision_id
WHERE c.editorial_status = 'published'
  AND c.lifecycle_state  = 'active'
  AND c.published_revision_id IS NOT NULL
  AND c.last_parsed_revision_id IS DISTINCT FROM c.published_revision_id
ORDER BY c.updated_at
LIMIT $1`, batchSize)
	if err != nil {
		return 0, err
	}
	var batch []sweepTarget
	for rows.Next() {
		var t sweepTarget
		var structuralPath *string
		if scanErr := rows.Scan(&t.chapterID, &t.bookID, &t.publishedRev, &t.lang, &structuralPath, &t.body); scanErr != nil {
			slog.Error("book-service: reparse sweep row scan failed", "err", scanErr)
			continue
		}
		if structuralPath != nil {
			t.structuralPath = *structuralPath
		}
		batch = append(batch, t)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}

	healed := 0
	for _, t := range batch {
		if err := s.reparseOneChapter(ctx, t); err != nil {
			// One chapter failing (a parser hiccup, a concurrent re-publish) must
			// not abort the batch — it stays stale and the next sweep retries it.
			slog.Error("book-service: reparse sweep chapter failed", "chapter_id", t.chapterID, "err", err)
			continue
		}
		healed++
	}
	return healed, nil
}

// reparseOneChapter re-parses one stale chapter's PINNED revision body and, in a
// single Tx, upserts the scenes (IX-4), advances the freshness marker, and emits
// chapter.scenes_reparsed. The marker UPDATE is guarded on published_revision_id
// still equalling the revision we parsed: if the chapter was re-published or
// unpublished between the batch read and here, the guard matches zero rows and
// the whole Tx rolls back (no stale scenes committed, no misleading event) —
// the current revision is picked up on the next sweep.
func (s *Server) reparseOneChapter(ctx context.Context, t sweepTarget) error {
	tree, err := s.parseChapterBody(ctx, t.body, t.lang)
	if err != nil {
		return err // leave stale; next sweep retries
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	// RB-2: lock the chapters row FIRST — the SAME order the publish path takes
	// (chapters → scenes), so the two writers of this chapter can never AB-BA deadlock
	// (publish would otherwise hold chapters and block on scenes while the sweeper holds
	// scenes and blocks on chapters). This SELECT ... FOR UPDATE also IS the
	// concurrent-republish guard: if the chapter was re-published/unpublished since the
	// batch read, it matches zero rows and we discard this parse of the now-superseded
	// revision (the next sweep picks up the current one).
	var locked uuid.UUID
	err = tx.QueryRow(ctx, `
SELECT id FROM chapters
WHERE id = $1 AND published_revision_id = $2 AND editorial_status = 'published'
FOR UPDATE`, t.chapterID, t.publishedRev).Scan(&locked)
	if errors.Is(err, pgx.ErrNoRows) {
		return tx.Rollback(ctx) // superseded — skip
	}
	if err != nil {
		return err
	}

	counts, err := s.upsertChapterScenes(ctx, tx, t.bookID, t.chapterID, t.structuralPath, tree)
	if err != nil {
		return err
	}
	if _, err := tx.Exec(ctx,
		`UPDATE chapters SET last_parsed_revision_id = $2 WHERE id = $1`,
		t.chapterID, t.publishedRev); err != nil {
		return err
	}
	// RB5-1: emit only when the index changed — a no-op re-parse must not wipe the
	// book's extraction cache via the knowledge consumer.
	if counts.changed() {
		if err := emitScenesReparsed(ctx, tx, t.bookID, t.chapterID, t.publishedRev, counts.ParseVersion); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}
