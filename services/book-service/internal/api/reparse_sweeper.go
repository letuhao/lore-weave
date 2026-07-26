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
// A background goroutine re-parses any chapter whose scene index is stale by the SAME
// predicate the producers guard on — the reconcile-by-truth-mirror-producer-predicate
// lesson: heal and produce can never disagree about what "stale" means. It re-parses the
// PINNED revision body (never the live draft — IX-1) and emits the frozen
// chapter.scenes_reparsed event.
//
// ── WS-0.5: RE-KEYED from published_revision_id → kg_indexed_revision_id ──
// Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.4 (red-team P1-5).
//
// "Stale" used to mean `editorial_status='published' AND last_parsed IS DISTINCT FROM
// published_revision_id`. Publishing no longer gates the knowledge graph, so the sweeper
// now keys on the KG pointer: the revision the knowledge layer reflects, which may be a
// DRAFT revision the user explicitly indexed.
//
// ⚠️ THE WHOLE QUERY IS RE-KEYED — SELECT, JOIN, the concurrent guard, AND the stamp —
// not just the WHERE. Re-keying only the WHERE would:
//
//	(a) drop every draft-indexed chapter at the inner JOIN (which still joined on
//	    published_revision_id — NULL for a draft) — i.e. silently exclude the exact
//	    chapters this change exists to include; and
//	(b) for a chapter both published@A and draft-indexed@B, parse the PUBLISHED body and
//	    stamp last_parsed = A, which never equals kg_indexed = B → the row stays stale by
//	    predicate forever → an INFINITE RE-PARSE LOOP, re-emitting scenes_reparsed (and so
//	    re-invalidating the extraction cache, and so re-paying LLM cost) on every tick.
//
// The legacy-backfill property is preserved: the WS-0.2 migration seeds
// kg_indexed_revision_id := published_revision_id on every published chapter, so the new
// predicate selects exactly the set the old one did on today's corpus (spec §6) — no
// re-parse storm on first sweep.
//
// kg_exclude'd chapters are OUT of the sweep by design: the user asked to keep them out
// of the knowledge graph, so we must not re-parse and re-emit for them.

// sweepTarget is one stale chapter's pinned-revision snapshot, read outside any
// transaction so the (potentially slow) /internal/parse call never holds a row
// lock. The Tx is opened per chapter afterward.
type sweepTarget struct {
	chapterID uuid.UUID
	bookID    uuid.UUID
	// indexedRev is kg_indexed_revision_id — the revision the knowledge layer reflects.
	// NOT published_revision_id: for a draft-indexed chapter there is no published
	// revision at all, and for a published-AND-draft-indexed chapter the two differ.
	indexedRev     uuid.UUID
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
	// WS-0.5: the FULL query is re-keyed — the SELECT list, the JOIN, and the WHERE.
	// The JOIN is the subtle one: joining chapter_revisions on published_revision_id
	// would drop every draft-indexed chapter (NULL published_revision_id) right here,
	// silently excluding the exact rows this change exists to include.
	rows, err := s.pool.Query(ctx, `
SELECT c.id, c.book_id, c.kg_indexed_revision_id, COALESCE(c.original_language,''),
       c.structural_path, r.body::text
FROM chapters c
JOIN chapter_revisions r ON r.id = c.kg_indexed_revision_id
WHERE c.kg_indexed_revision_id IS NOT NULL
  AND c.kg_exclude       = false
  AND c.lifecycle_state  = 'active'
  AND c.last_parsed_revision_id IS DISTINCT FROM c.kg_indexed_revision_id
ORDER BY c.updated_at
LIMIT $1`, batchSize)
	if err != nil {
		return 0, err
	}
	var batch []sweepTarget
	for rows.Next() {
		var t sweepTarget
		var structuralPath *string
		if scanErr := rows.Scan(&t.chapterID, &t.bookID, &t.indexedRev, &t.lang, &structuralPath, &t.body); scanErr != nil {
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

// reparseOneChapter re-parses one stale chapter's INDEXED revision body and, in a single
// Tx, upserts the scenes (IX-4), advances the freshness marker, and emits
// chapter.scenes_reparsed.
//
// WS-0.5: the concurrent guard and the marker stamp are BOTH re-keyed onto
// kg_indexed_revision_id.
//
// The stamp is where the infinite loop hid. If the sweeper parsed the chapter's
// kg_indexed revision B but stamped `last_parsed = published_revision_id (A)`, the row
// would still satisfy `last_parsed(A) IS DISTINCT FROM kg_indexed(B)` on the NEXT tick —
// stale forever. Every tick would re-parse it and re-emit chapter.scenes_reparsed, whose
// consumer invalidates the extraction cache, so the book would re-pay LLM extraction cost
// on a loop. It must stamp the revision it actually parsed.
//
// The guard also drops `editorial_status = 'published'`: a draft-indexed chapter is, by
// definition, NOT published, so keeping that clause would make the sweeper skip every row
// it just selected. It gains `kg_exclude = false` instead, so a chapter excluded between
// the batch read and here is discarded rather than re-indexed (fail closed on the user's
// privacy choice).
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

	// RB-2: lock the chapters row FIRST — the SAME order the publish/index paths take
	// (chapters → scenes), so the two writers of this chapter can never AB-BA deadlock
	// (they would otherwise hold chapters and block on scenes while the sweeper holds
	// scenes and blocks on chapters). This SELECT ... FOR UPDATE also IS the
	// concurrent-write guard: if the chapter was re-indexed, re-published, or excluded
	// since the batch read, it matches zero rows and we discard this parse of the
	// now-superseded revision (the next sweep picks up the current one).
	var locked uuid.UUID
	err = tx.QueryRow(ctx, `
SELECT id FROM chapters
WHERE id = $1 AND kg_indexed_revision_id = $2 AND kg_exclude = false
FOR UPDATE`, t.chapterID, t.indexedRev).Scan(&locked)
	if errors.Is(err, pgx.ErrNoRows) {
		return tx.Rollback(ctx) // superseded or excluded — skip
	}
	if err != nil {
		return err
	}

	counts, err := s.upsertChapterScenes(ctx, tx, t.bookID, t.chapterID, t.structuralPath, tree)
	if err != nil {
		return err
	}
	// Stamp the revision we ACTUALLY parsed (see the infinite-loop note above).
	if _, err := tx.Exec(ctx,
		`UPDATE chapters SET last_parsed_revision_id = $2 WHERE id = $1`,
		t.chapterID, t.indexedRev); err != nil {
		return err
	}
	// RB5-1: emit only when the index changed — a no-op re-parse must not wipe the
	// chapter's extraction cache via the knowledge consumer.
	if counts.changed() {
		if err := emitScenesReparsed(ctx, tx, t.bookID, t.chapterID, t.indexedRev, counts.ParseVersion); err != nil {
			return err
		}
		// SC11-amendment Phase 0 — writer #2, 4th call site. The IX-3 sweeper HEALS a stale
		// index, and healing re-resolves every scene's anchor: the spec back-links may have
		// moved without any user action at all. If the sweeper stayed silent, a book could be
		// re-linked in the background and the mirror would never hear about it.
		if err := emitScenesLinked(ctx, tx, t.bookID, t.chapterID); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}
