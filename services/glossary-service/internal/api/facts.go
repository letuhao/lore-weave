package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"

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
//
// CALLER CONTRACT (UNENFORCED — appendFact/retractFacts do NOT self-acquire, because
// the global lock order requires ALL chain locks taken in sorted order BEFORE any write
// across chains; self-acquiring per call would reorder and deadlock). Every caller MUST
// hold acquireFactChainLock for each (entity, attr) it writes. The natural key keeps
// concurrent appends idempotent, but two unlocked writers can still interleave their
// maintain_chain valid_to rewrites. The lock is verified to serialize same-chain / free
// disjoint-chain by TestFactChainLockSerializes; F1d wiring MUST add a live two-writer
// smoke. reconcileEpisode MUST be called after the facts commit (else episodes pollute
// retrieval as permanent 'pending', the C6 trap).

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
	// Targeted ON CONFLICT on the content-addressed natural key (NOT a bare DO NOTHING),
	// so a future unique constraint on entity_facts can't be silently swallowed.
	err := q.QueryRow(ctx, `
		INSERT INTO entity_facts
		  (book_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal, cardinality, source_episode_id)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		ON CONFLICT (entity_id, fact_kind, attr_or_predicate, value_hash, valid_from_ordinal,
		             coalesce(source_episode_id, '00000000-0000-0000-0000-000000000000'::uuid))
		DO NOTHING
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

	// Same-ordinal supersede (last-write-wins) for single-valued chains. Two DIFFERENT
	// values for one single-valued attr at the SAME chapter ordinal would otherwise both
	// stay open (maintain_chain leaves the latest-valid_from facts open, and here they
	// share valid_from) → two open facts → a nondeterministic projection. The just-opened
	// fact wins: transaction-time-close (invalidate-not-delete, kept for audit) every OTHER
	// open single-valued fact on this chain at this valid_from with a DIFFERENT value. The
	// SAME value from a different episode is NOT a conflict — it coexists harmlessly.
	if p.Card == "single" {
		if _, err := q.Exec(ctx, `
			UPDATE entity_facts
			   SET invalidated_at = now(), invalidated_reason = 'superseded_same_ordinal'
			 WHERE entity_id = $1 AND fact_kind = $2 AND attr_or_predicate = $3
			   AND cardinality = 'single' AND valid_from_ordinal = $4
			   AND fact_id <> $5 AND value_hash <> md5($6)
			   AND invalidated_at IS NULL`,
			p.EntityID, p.FactKind, p.Attr, p.ValidFrom, factID, p.Value,
		); err != nil {
			return uuid.Nil, false, fmt.Errorf("append_fact: same-ordinal supersede: %w", err)
		}
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
func retractFacts(ctx context.Context, q pgxRWQuerier, bookID uuid.UUID, factIDs []uuid.UUID, reason string) ([]FactChain, error) {
	if len(factIDs) == 0 {
		return nil, nil
	}
	// book_id scopes the retract (tenancy, LOCKED) — a caller can only close THIS book's facts.
	rows, err := q.Query(ctx, `
		UPDATE entity_facts
		   SET invalidated_at = now(), invalidated_reason = $2
		 WHERE fact_id = ANY($1) AND book_id = $3 AND invalidated_at IS NULL
		RETURNING entity_id, attr_or_predicate`,
		factIDs, reason, bookID,
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
// INVARIANT (do not break): the attr_def_id resolution here MUST match loadAttrDefMap's
// (the same DISTINCT-ON universal-preferred selection). If it ever diverged, the upsert
// would target a different attr_def_id than the writeback uses and FORK a second EAV row
// for the same logical attribute. The shared selection logic is the contract.
//
// Keyed per-(entity, attr_def_id) row (§12.7.8 Probe-4). The open fact is chosen with a
// fully DETERMINISTIC order (valid_from, then created_at, then fact_id) so a same-ordinal
// tie can never make the projection nondeterministic. If the chain has no open fact (e.g.
// fully retracted) or the attr has no book_attribute definition, no upsert happens (the
// row is left as-is — the empty-chain edge is a documented repair concern).
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
		  WHERE ef.entity_id = $1 AND ef.attr_or_predicate = $2
		    AND ef.fact_kind IN ('attribute', 'name')  -- name is a first-class single fact (F1g)
		    AND ef.cardinality = 'single' AND ef.invalidated_at IS NULL AND ef.valid_to_ordinal IS NULL
		  ORDER BY ef.valid_from_ordinal DESC, ef.created_at DESC, ef.fact_id DESC
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

// emitChapterFacts is the Path-A producer (§4 step 2-4 / F1d): for each attribute the
// writeback ACTUALLY WROTE for an entity this chapter, open one append-only fact valid-from
// the chapter ordinal, citing the immutable episode. Idempotent (the content-addressed
// natural key short-circuits a re-extract → 0 new rows), ordinal-aware (maintain_chain runs
// inside appendFact), and additive — it does NOT touch the EAV the merge-strategy path wrote
// (that stays the live projection during the transition). Values mirror what the EAV stored
// (serializeValue / the name), so the fact log tracks the accepted value changes.
//
// Runs inside the per-chapter writeback tx, under the per-book advisory lock the handler
// already holds; appendFact additionally takes the per-(entity, attr) chain lock.
func (s *Server) emitChapterFacts(ctx context.Context, q pgxRWQuerier, bookID, entityID uuid.UUID, ent extractedEntity, writtenCodes []string, ordinal int64, episodeID uuid.UUID) error {
	emit := func(kind, attr, value, card string) error {
		if value == "" {
			return nil
		}
		if err := acquireFactChainLock(ctx, q, entityID, attr); err != nil {
			return err
		}
		_, _, err := appendFact(ctx, q, appendFactParams{
			BookID: bookID, EntityID: entityID, FactKind: kind, Attr: attr,
			Value: value, ValidFrom: ordinal, Card: card, SourceEpisodeID: &episodeID,
		})
		return err
	}
	for _, code := range writtenCodes {
		switch code {
		case "name":
			// name is a first-class single-valued bi-temporal fact (F1g) → as-of-name.
			if err := emit("name", "name", ent.Name, "single"); err != nil {
				return err
			}
		case "aliases":
			// aliases are multi-valued bi-temporal facts (F1g) — one per element; coexist.
			val, ok := ent.Attributes[code]
			if !ok {
				continue
			}
			for _, a := range parseListValues(serializeValue(val)) {
				if err := emit("alias", "aliases", a, "multi"); err != nil {
					return err
				}
			}
		default:
			val, ok := ent.Attributes[code]
			if !ok {
				continue
			}
			if err := emit("attribute", code, serializeValue(val), "single"); err != nil {
				return err
			}
		}
	}
	// Flag the entity's canonical for re-fold (debounced; the fold worker consumes it).
	if len(writtenCodes) > 0 {
		if err := markFoldDirty(ctx, q, entityID, false); err != nil {
			return err
		}
	}
	return nil
}

// parseListValues extracts the elements of a serializeValue() output: a JSON array →
// its string elements; anything else → the single trimmed value (or empty).
func parseListValues(serialized string) []string {
	t := strings.TrimSpace(serialized)
	if t == "" {
		return nil
	}
	if strings.HasPrefix(t, "[") {
		var arr []any
		if err := json.Unmarshal([]byte(t), &arr); err == nil {
			out := make([]string, 0, len(arr))
			for _, e := range arr {
				if s, ok := e.(string); ok {
					if s = strings.TrimSpace(s); s != "" {
						out = append(out, s)
					}
				}
			}
			return out
		}
	}
	return []string{t}
}

// nullStr returns nil for an empty string so an absent writeback_key stores SQL NULL.
func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// mergeFactChains is the fact-chain merge (§12.4.1 / A1) — NET-NEW over append-only
// history, NOT "#43 done" (that validated the flat overwrite store). It repoints ALL
// loser facts onto the winner (no `NOT IN` collision dodge — facts coexist by design,
// distinguished by their bi-temporal intervals), then reconciles each affected
// single-valued chain: a deterministic same-ordinal tiebreak (newest created_at wins,
// fact_id as final tiebreak) invalidate-not-deletes the loser of any same-valid_from
// DIFFERENT-value overlap, and maintain_chain re-derives every valid_to over the merged
// survivors. source_episode_id + valid_* are untouched (provenance + intervals preserved).
//
// Locking (§12.7.8): the caller holds the entity-pair FOR UPDATE; this additionally takes
// the per-(entity, attr) chain advisory locks for BOTH entities on the affected attrs, in
// sorted composite-key order, held through commit — so a concurrent append to either chain
// can't interleave (it would otherwise be dropped or left with a stale valid_to).
//
// Episodes are book/chapter-scoped (not entity-owned), so nothing to repoint there.
// Returns the moved fact ids + the tiebreak-invalidated fact ids for the merge journal
// (revert via revertFactChains). Returns (nil,nil,nil) when the loser has no facts.
func mergeFactChains(ctx context.Context, q pgxRWQuerier, winnerID, loserID uuid.UUID) (moved, invalidated []uuid.UUID, err error) {
	attrs, err := distinctFactAttrs(ctx, q, loserID)
	if err != nil {
		return nil, nil, err
	}
	if len(attrs) == 0 {
		return nil, nil, nil
	}
	// §12.7.8 chain locks: both entities × affected attrs, sorted composite-key order.
	type lk struct {
		entity uuid.UUID
		attr   string
	}
	locks := make([]lk, 0, len(attrs)*2)
	for _, a := range attrs {
		locks = append(locks, lk{winnerID, a}, lk{loserID, a})
	}
	sort.Slice(locks, func(i, j int) bool {
		ki := locks[i].entity.String() + ":" + locks[i].attr
		kj := locks[j].entity.String() + ":" + locks[j].attr
		return ki < kj
	})
	for _, l := range locks {
		if err := acquireFactChainLock(ctx, q, l.entity, l.attr); err != nil {
			return nil, nil, err
		}
	}

	// Repoint ALL loser facts → winner (no NOT IN dodge). RETURNING the attr too so the
	// tiebreak + maintain_chain operate on the ACTUAL moved set (MED-1): a chain added to the
	// loser after distinctFactAttrs was read is still repointed here, so deriving the set from
	// the repoint (not the pre-lock read) guarantees its valid_to is re-derived.
	movedAttrSet := map[string]struct{}{}
	rows, err := q.Query(ctx,
		`UPDATE entity_facts SET entity_id = $1 WHERE entity_id = $2 RETURNING fact_id, attr_or_predicate`,
		winnerID, loserID)
	if err != nil {
		return nil, nil, fmt.Errorf("merge facts: repoint: %w", err)
	}
	for rows.Next() {
		var id uuid.UUID
		var a string
		if err := rows.Scan(&id, &a); err != nil {
			rows.Close()
			return nil, nil, fmt.Errorf("merge facts: scan moved: %w", err)
		}
		moved = append(moved, id)
		movedAttrSet[a] = struct{}{}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, nil, fmt.Errorf("merge facts: moved rows: %w", err)
	}
	movedAttrs := make([]string, 0, len(movedAttrSet))
	for a := range movedAttrSet {
		movedAttrs = append(movedAttrs, a)
	}

	// Same-ordinal tiebreak across the affected single-valued chains: invalidate any fact
	// that has a NEWER different-value sibling at the same valid_from (keep the newest).
	irows, err := q.Query(ctx, `
		UPDATE entity_facts e
		   SET invalidated_at = now(), invalidated_reason = 'merge_tiebreak'
		 WHERE e.entity_id = $1 AND e.cardinality = 'single' AND e.invalidated_at IS NULL
		   AND e.attr_or_predicate = ANY($2)
		   AND EXISTS (
		     SELECT 1 FROM entity_facts o
		     WHERE o.entity_id = e.entity_id AND o.fact_kind = e.fact_kind
		       AND o.attr_or_predicate = e.attr_or_predicate
		       AND o.valid_from_ordinal = e.valid_from_ordinal
		       AND o.invalidated_at IS NULL AND o.value_hash <> e.value_hash
		       AND (o.created_at > e.created_at OR (o.created_at = e.created_at AND o.fact_id > e.fact_id))
		   )
		RETURNING fact_id`,
		winnerID, movedAttrs)
	if err != nil {
		return nil, nil, fmt.Errorf("merge facts: tiebreak: %w", err)
	}
	for irows.Next() {
		var id uuid.UUID
		if err := irows.Scan(&id); err != nil {
			irows.Close()
			return nil, nil, fmt.Errorf("merge facts: scan tiebreak: %w", err)
		}
		invalidated = append(invalidated, id)
	}
	irows.Close()
	if err := irows.Err(); err != nil {
		return nil, nil, fmt.Errorf("merge facts: tiebreak rows: %w", err)
	}

	for _, a := range movedAttrs {
		if err := maintainChain(ctx, q, winnerID, a); err != nil {
			return nil, nil, err
		}
	}
	return moved, invalidated, nil
}

// revertFactChains undoes mergeFactChains exactly (the reversible-merge invariant): repoint
// the moved facts back to the loser, un-invalidate the tiebreak losers, and re-derive both
// sides' affected chains. Driven by the journal's repointed_fact_ids + invalidated_fact_ids.
func revertFactChains(ctx context.Context, q pgxRWQuerier, winnerID, loserID uuid.UUID, moved, invalidated []uuid.UUID) error {
	if len(invalidated) > 0 {
		if _, err := q.Exec(ctx, `
			UPDATE entity_facts SET invalidated_at = NULL, invalidated_reason = NULL
			 WHERE fact_id = ANY($1) AND invalidated_reason = 'merge_tiebreak'`, invalidated); err != nil {
			return fmt.Errorf("revert facts: un-invalidate tiebreak: %w", err)
		}
	}
	if len(moved) > 0 {
		if _, err := q.Exec(ctx,
			`UPDATE entity_facts SET entity_id = $1 WHERE fact_id = ANY($2)`, loserID, moved); err != nil {
			return fmt.Errorf("revert facts: repoint back: %w", err)
		}
	}
	// Re-derive both sides over the union of affected attrs.
	for _, e := range []uuid.UUID{winnerID, loserID} {
		attrs, err := distinctFactAttrs(ctx, q, e)
		if err != nil {
			return err
		}
		for _, a := range attrs {
			if err := maintainChain(ctx, q, e, a); err != nil {
				return err
			}
		}
	}
	return nil
}

// splitFactsByEpisode is the fact-level core of split_entity (§12.4.2 / D2) — the inverse
// of merge, which makes a wrong (e.g. CJK-name) merge corrigible even though the store is
// append-only. Facts on `source` cited to any of `episodeIDs` are RE-ATTRIBUTED to
// `newEntity` as a NEW transaction-time event: the originals are invalidate-not-deleted
// (invalidated_reason='split', kept for audit/time-travel) and fresh open facts are opened
// on newEntity carrying the same value/valid_from/episode/cardinality. Both sides' affected
// chains are re-derived. The caller supplies an already-created newEntity (same book) and
// holds it + source under FOR UPDATE; this takes the per-(entity,attr) chain locks for both.
//
// Returns the number of facts moved. Order matters: COPY (from still-open source facts)
// before INVALIDATE, so the copy SELECT still sees them.
func splitFactsByEpisode(ctx context.Context, q pgxRWQuerier, sourceID, newEntityID uuid.UUID, episodeIDs []uuid.UUID) (int, error) {
	if len(episodeIDs) == 0 {
		return 0, nil
	}
	// Affected attrs = the source attrs cited to those episodes (open facts only).
	rows, err := q.Query(ctx, `
		SELECT DISTINCT attr_or_predicate FROM entity_facts
		WHERE entity_id = $1 AND source_episode_id = ANY($2) AND invalidated_at IS NULL`,
		sourceID, episodeIDs)
	if err != nil {
		return 0, fmt.Errorf("split: affected attrs: %w", err)
	}
	var attrs []string
	for rows.Next() {
		var a string
		if err := rows.Scan(&a); err != nil {
			rows.Close()
			return 0, fmt.Errorf("split: scan attr: %w", err)
		}
		attrs = append(attrs, a)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, fmt.Errorf("split: attr rows: %w", err)
	}
	if len(attrs) == 0 {
		return 0, nil
	}
	// §12.7.8 chain locks: both entities × affected attrs, sorted composite-key order.
	type lk struct {
		entity uuid.UUID
		attr   string
	}
	locks := make([]lk, 0, len(attrs)*2)
	for _, a := range attrs {
		locks = append(locks, lk{sourceID, a}, lk{newEntityID, a})
	}
	sort.Slice(locks, func(i, j int) bool {
		return locks[i].entity.String()+":"+locks[i].attr < locks[j].entity.String()+":"+locks[j].attr
	})
	for _, l := range locks {
		if err := acquireFactChainLock(ctx, q, l.entity, l.attr); err != nil {
			return 0, err
		}
	}

	// COPY the source's cited open facts onto newEntity (fresh fact_id/created_at/coverage_xid).
	ct, err := q.Exec(ctx, `
		INSERT INTO entity_facts
		  (book_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal, cardinality, source_episode_id)
		SELECT book_id, $1, fact_kind, attr_or_predicate, value, valid_from_ordinal, cardinality, source_episode_id
		FROM entity_facts
		WHERE entity_id = $2 AND source_episode_id = ANY($3) AND invalidated_at IS NULL
		ON CONFLICT (entity_id, fact_kind, attr_or_predicate, value_hash, valid_from_ordinal,
		             coalesce(source_episode_id, '00000000-0000-0000-0000-000000000000'::uuid))
		DO NOTHING`,
		newEntityID, sourceID, episodeIDs)
	if err != nil {
		return 0, fmt.Errorf("split: copy to new entity: %w", err)
	}
	moved := int(ct.RowsAffected())

	// INVALIDATE the originals on source (invalidate-not-delete, reason 'split'), RETURNING
	// the actual touched attrs (MED-1) — both copy + invalidate are episode-scoped, so a
	// chain added after the pre-lock read is still moved; deriving the maintain_chain set from
	// the actual invalidated rows (not the pre-read attrs) re-derives every touched chain.
	touchedSet := map[string]struct{}{}
	irows, err := q.Query(ctx, `
		UPDATE entity_facts SET invalidated_at = now(), invalidated_reason = 'split'
		WHERE entity_id = $1 AND source_episode_id = ANY($2) AND invalidated_at IS NULL
		RETURNING attr_or_predicate`,
		sourceID, episodeIDs)
	if err != nil {
		return 0, fmt.Errorf("split: invalidate originals: %w", err)
	}
	for irows.Next() {
		var a string
		if err := irows.Scan(&a); err != nil {
			irows.Close()
			return 0, fmt.Errorf("split: scan invalidated attr: %w", err)
		}
		touchedSet[a] = struct{}{}
	}
	irows.Close()
	if err := irows.Err(); err != nil {
		return 0, fmt.Errorf("split: invalidate rows: %w", err)
	}

	for _, e := range []uuid.UUID{sourceID, newEntityID} {
		for a := range touchedSet {
			if err := maintainChain(ctx, q, e, a); err != nil {
				return 0, err
			}
		}
	}
	return moved, nil
}

// distinctFactAttrs returns an entity's distinct fact attr/predicate codes (any kind).
func distinctFactAttrs(ctx context.Context, q pgxRWQuerier, entityID uuid.UUID) ([]string, error) {
	rows, err := q.Query(ctx,
		`SELECT DISTINCT attr_or_predicate FROM entity_facts WHERE entity_id = $1`, entityID)
	if err != nil {
		return nil, fmt.Errorf("distinct fact attrs: %w", err)
	}
	defer rows.Close()
	var attrs []string
	for rows.Next() {
		var a string
		if err := rows.Scan(&a); err != nil {
			return nil, fmt.Errorf("distinct fact attrs scan: %w", err)
		}
		attrs = append(attrs, a)
	}
	return attrs, rows.Err()
}
