package api

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// facts.go — the append-only bi-temporal FACT core (spec
// docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md §12).
// entity_facts is the single source of truth (INV-FACTS §12.0); the EAV table
// (entity_attribute_values) is a DERIVED "current" projection (§12.2.1). These
// helpers are the only place that writes facts.
//
// TRANSITIONAL MODEL (migration §6C — projection, not big-bang): facts are
// populated as an ADDITIVE parallel SSOT alongside the existing merge-strategy EAV
// write, which stays the live "current" projection during the transition. The
// fact→EAV projection (refreshEAVProjection) is therefore NOT a live double-writer
// here (that would clash with the EAV merge strategies overwrite/append/fill/
// summarize). It is the self-contained REPAIR / CUTOVER path: the rebuild-from-facts
// backstop (INV-FACTS) and the eventual authoritative writer once consumers migrate
// onto the KAL. The "synchronous-in-tx projection" invariant (§12.2.1) binds at that
// cutover; until then a fact append and the EAV write already share the per-chapter
// writeback tx, so no skew is introduced.
//
// Locking (§12.7.8): a fact write takes a per-(entity, attr) advisory xact lock,
// NOT the per-book lock — disjoint chains run in parallel. The idempotent natural
// key (§12.2.2) + the ordinal-aware maintain_chain (§12.3.3) make disjoint appends
// safe without book-global serialization. Acquire chain locks in sorted composite
// (entity_id, attr) order to stay deadlock-free (§12.7.8 global lock order).

// factChainLockNS namespaces the per-(entity, attr) advisory xact lock around a
// fact-chain write (§12.7.8). Distinct from extractionWritebackLockNS so the two
// lock domains never collide. Value is the ASCII bytes of "FACT".
const factChainLockNS int32 = 0x46414354

// acquireFactChainLock takes pg_advisory_xact_lock(FACT_CHAIN_NS,
// hashtext(entity||':'||attr)) — the single canonical fact-write lock key (§12.7.8)
// so Path A and Path B don't take non-conflicting locks and serialize nothing.
// Released at tx end.
func acquireFactChainLock(ctx context.Context, q pgxRWQuerier, entityID uuid.UUID, attr string) error {
	key := entityID.String() + ":" + attr
	if _, err := q.Exec(ctx, `SELECT pg_advisory_xact_lock($1, hashtext($2))`, factChainLockNS, key); err != nil {
		return fmt.Errorf("acquire fact-chain lock (%s): %w", key, err)
	}
	return nil
}

// ingestEpisode mints (or resumes) the immutable episode for a chapter revision
// (§12.2.5). UNIQUE(chapter_id, content_hash) makes a re-run with the same text
// RESUME the existing episode rather than re-mint (C6); a text edit (new hash) mints
// a new revision. Returns the episode id and whether it was newly minted. Seals as
// 'pending'; the caller flips it to 'reconciled' after the facts land.
func ingestEpisode(ctx context.Context, q pgxRWQuerier, bookID, chapterID uuid.UUID, chapterOrdinal int64, contentHash, writebackKey string) (uuid.UUID, bool, error) {
	var episodeID uuid.UUID
	minted := true
	err := q.QueryRow(ctx, `
		INSERT INTO episodes (book_id, chapter_id, chapter_ordinal, content_hash, status, writeback_key)
		VALUES ($1, $2, $3, $4, 'pending', $5)
		ON CONFLICT (chapter_id, content_hash) DO NOTHING
		RETURNING episode_id`,
		bookID, chapterID, chapterOrdinal, contentHash, nullStr(writebackKey),
	).Scan(&episodeID)
	if errors.Is(err, pgx.ErrNoRows) {
		minted = false
		if err = q.QueryRow(ctx,
			`SELECT episode_id FROM episodes WHERE chapter_id = $1 AND content_hash = $2`,
			chapterID, contentHash,
		).Scan(&episodeID); err != nil {
			return uuid.Nil, false, fmt.Errorf("ingest_episode: refetch: %w", err)
		}
	} else if err != nil {
		return uuid.Nil, false, fmt.Errorf("ingest_episode: insert: %w", err)
	}
	return episodeID, minted, nil
}

// reconcileEpisode flips a sealed 'pending' episode to 'reconciled' once its facts
// have committed (the tx-2 step of §12.2.5).
func reconcileEpisode(ctx context.Context, q pgxRWQuerier, episodeID uuid.UUID) error {
	_, err := q.Exec(ctx,
		`UPDATE episodes SET status = 'reconciled', reconciled_at = now()
		 WHERE episode_id = $1 AND status = 'pending'`, episodeID)
	if err != nil {
		return fmt.Errorf("reconcile_episode(%s): %w", episodeID, err)
	}
	return nil
}

// appendFactParams is one bi-temporal fact to OPEN (Path A, §4 step 4 / §12.2.2).
type appendFactParams struct {
	BookID    uuid.UUID
	EntityID  uuid.UUID
	FactKind  string // attribute | relation | event | name | alias
	Attr      string // attribute code or relation predicate
	Value     string
	ValidFrom int64  // chapter ordinal — the lower bound of the half-open interval
	Card      string // single | multi  (default single)

	// SourceEpisodeID cites the immutable episode (anti-hallucination, §3.2).
	// nil for cold-start/migration facts.
	SourceEpisodeID *uuid.UUID
}

// appendFact opens a fact (Path A), idempotently:
//  1. INSERT … ON CONFLICT DO NOTHING on the content-addressed natural key (§12.2.2)
//     — a re-run for the same chapter appends ZERO new rows (C2);
//  2. maintain_chain (§12.3.3) — the ordinal-aware interval-split derives every
//     valid_to in the (entity, attr) chain, correct under out-of-order/backfill.
//
// The caller must already hold the per-(entity, attr) chain lock. Returns the fact
// id and whether a new row was inserted (false = idempotent no-op).
func appendFact(ctx context.Context, q pgxRWQuerier, p appendFactParams) (uuid.UUID, bool, error) {
	if p.Card == "" {
		p.Card = "single"
	}
	var factID uuid.UUID
	inserted := true
	err := q.QueryRow(ctx, `
		INSERT INTO entity_facts
		  (book_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal, cardinality, source_episode_id)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		ON CONFLICT DO NOTHING
		RETURNING fact_id`,
		p.BookID, p.EntityID, p.FactKind, p.Attr, p.Value, p.ValidFrom, p.Card, p.SourceEpisodeID,
	).Scan(&factID)
	if errors.Is(err, pgx.ErrNoRows) {
		inserted = false
		ep := uuid.Nil
		if p.SourceEpisodeID != nil {
			ep = *p.SourceEpisodeID
		}
		if err = q.QueryRow(ctx, `
			SELECT fact_id FROM entity_facts
			WHERE entity_id = $1 AND fact_kind = $2 AND attr_or_predicate = $3
			  AND value_hash = md5($4) AND valid_from_ordinal = $5
			  AND coalesce(source_episode_id, '00000000-0000-0000-0000-000000000000'::uuid) = $6`,
			p.EntityID, p.FactKind, p.Attr, p.Value, p.ValidFrom, ep,
		).Scan(&factID); err != nil {
			return uuid.Nil, false, fmt.Errorf("append_fact: refetch on conflict: %w", err)
		}
	} else if err != nil {
		return uuid.Nil, false, fmt.Errorf("append_fact: insert: %w", err)
	}

	if err := maintainChain(ctx, q, p.EntityID, p.Attr); err != nil {
		return uuid.Nil, false, err
	}
	return factID, inserted, nil
}

// maintainChain invokes the single valid_to writer (migration 0045, §12.3.3).
func maintainChain(ctx context.Context, q pgxRWQuerier, entityID uuid.UUID, attr string) error {
	if _, err := q.Exec(ctx, `SELECT maintain_chain($1, $2)`, entityID, attr); err != nil {
		return fmt.Errorf("maintain_chain(%s, %s): %w", entityID, attr, err)
	}
	return nil
}

// retractFacts is Path B's transaction-time close (§12.3.3 / A3): mark the dropped
// facts invalidated (invalidate-not-delete — kept for audit/time-travel), then
// re-run maintain_chain over each affected (entity, attr) chain so the predecessor
// auto-re-extends across the retracted interval (the chain re-stitch). The caller
// holds the affected chain locks. reason is recorded on invalidated_reason
// ('retract' for a Path-B text-edit drop, 'split' for split_entity, 'merge_tiebreak'
// for a merge overlap loser). Returns the affected chains so a caller on the cutover
// path can refresh their EAV projections (refreshEAVProjection).
func retractFacts(ctx context.Context, q pgxRWQuerier, factIDs []uuid.UUID, reason string) ([]FactChain, error) {
	if len(factIDs) == 0 {
		return nil, nil
	}
	rows, err := q.Query(ctx, `
		UPDATE entity_facts
		   SET invalidated_at = now(), invalidated_reason = $2
		 WHERE fact_id = ANY($1) AND invalidated_at IS NULL
		RETURNING entity_id, attr_or_predicate`,
		factIDs, reason,
	)
	if err != nil {
		return nil, fmt.Errorf("retract: close facts: %w", err)
	}
	seen := map[FactChain]struct{}{}
	var order []FactChain
	for rows.Next() {
		var c FactChain
		if err := rows.Scan(&c.EntityID, &c.Attr); err != nil {
			rows.Close()
			return nil, fmt.Errorf("retract: scan chain: %w", err)
		}
		if _, ok := seen[c]; !ok {
			seen[c] = struct{}{}
			order = append(order, c)
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("retract: rows: %w", err)
	}
	for _, c := range order {
		if err := maintainChain(ctx, q, c.EntityID, c.Attr); err != nil {
			return nil, err
		}
	}
	return order, nil
}

// FactChain identifies one supersession chain.
type FactChain struct {
	EntityID uuid.UUID
	Attr     string
}

// refreshEAVProjection writes the CURRENT value of a single-valued attribute into
// the EAV "current" projection from the latest-valid fact (§12.2.1). Self-contained:
// it resolves attr_def_id the same way the writeback's loadAttrDefMap does
// (book_attributes, universal-genre preferred) so no caller need pass it. This is the
// REPAIR / CUTOVER writer — used by the rebuild-from-facts backstop and (post-cutover)
// after every append/retract; it is NOT wired as a live double-writer during the
// additive-SSOT transition (it would clash with the EAV merge strategies).
//
// Keyed per-(entity, attr_def_id) row (§12.7.8 Probe-4). If the chain has no open
// fact (e.g. fully retracted) or the attr has no book_attribute definition, no upsert
// happens (the row is left as-is — the empty-chain edge is a documented repair concern).
func refreshEAVProjection(ctx context.Context, q pgxRWQuerier, entityID uuid.UUID, attr string) error {
	_, err := q.Exec(ctx, `
		WITH target AS (
		  SELECT ge.entity_id, ba.attr_id AS attr_def_id
		  FROM glossary_entities ge
		  JOIN book_attributes ba ON ba.book_id = ge.book_id AND ba.kind_id = ge.kind_id
		                          AND ba.code = $2 AND ba.deprecated_at IS NULL
		  JOIN book_genres g ON g.genre_id = ba.genre_id
		  WHERE ge.entity_id = $1
		  ORDER BY (g.code = 'universal') DESC, ba.sort_order
		  LIMIT 1
		),
		cur AS (
		  SELECT ef.value
		  FROM entity_facts ef
		  WHERE ef.entity_id = $1 AND ef.attr_or_predicate = $2 AND ef.fact_kind = 'attribute'
		    AND ef.cardinality = 'single' AND ef.invalidated_at IS NULL AND ef.valid_to_ordinal IS NULL
		  ORDER BY ef.valid_from_ordinal DESC
		  LIMIT 1
		)
		INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
		SELECT t.entity_id, t.attr_def_id, 'zh', c.value
		FROM target t CROSS JOIN cur c
		ON CONFLICT (entity_id, attr_def_id)
		DO UPDATE SET original_value = EXCLUDED.original_value`,
		entityID, attr,
	)
	if err != nil {
		return fmt.Errorf("refresh EAV projection (%s/%s): %w", entityID, attr, err)
	}
	return nil
}

// rebuildProjectionForEntity is the INV-FACTS backstop (§12.2.1): re-derive the EAV
// projection for every single-valued attribute chain of an entity from its facts.
// Used after merge/split/migration, never on the hot path.
func rebuildProjectionForEntity(ctx context.Context, q pgxRWQuerier, entityID uuid.UUID) error {
	rows, err := q.Query(ctx, `
		SELECT DISTINCT attr_or_predicate FROM entity_facts
		WHERE entity_id = $1 AND fact_kind = 'attribute' AND cardinality = 'single'`, entityID)
	if err != nil {
		return fmt.Errorf("rebuild projection: list attrs: %w", err)
	}
	var attrs []string
	for rows.Next() {
		var a string
		if err := rows.Scan(&a); err != nil {
			rows.Close()
			return fmt.Errorf("rebuild projection: scan attr: %w", err)
		}
		attrs = append(attrs, a)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("rebuild projection: rows: %w", err)
	}
	for _, a := range attrs {
		if err := refreshEAVProjection(ctx, q, entityID, a); err != nil {
			return err
		}
	}
	return nil
}

// nullStr returns nil for an empty string so an absent writeback_key stores SQL NULL.
func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}
