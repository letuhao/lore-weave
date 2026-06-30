package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpEntityFacts — chain step 0044. The append-only bi-temporal FACT store that
// becomes the single source of truth for entity knowledge (spec
// docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md §12.0
// INV-FACTS). Everything else — the EAV "current" projection, the canonical
// snapshot, episode/segment summaries, translations, the KG edge view — is a
// DERIVED, REBUILDABLE cache. No truth lives outside entity_facts.
//
// This step lays the SSOT substrate only (schema). The interval-maintenance
// routine (maintain_chain), the synchronous-in-tx EAV projection upsert, Path A
// append / Path B retract, the tiered locking model, and fact-chain merge/split
// are application code in later slices; the cold-start seed is step 0046.
//
// Three objects + one extension:
//
//   - episodes — the immutable, content-hash-revisioned ingest unit (§12.2.5).
//     UNIQUE(chapter_id, content_hash) so a re-run with the same text RESUMES,
//     never re-mints (C6). status pending→reconciled: seal+writeback_key reserved
//     in tx-1 as 'pending'; facts written + flip to 'reconciled' in tx-2 (the LLM
//     call sits BETWEEN the two txs, never inside a DB transaction). A crash after
//     tx-1 leaves a resumable 'pending' episode, not a phantom sealed-empty one.
//
//   - entity_facts — the atomic unit of knowledge (§3.2 / §12.2.2 / §12.3.1).
//     Bi-temporal: VALID (story) time = [valid_from_ordinal, valid_to_ordinal)
//     half-open chapter-ordinal interval (open fact => valid_to_ordinal NULL =
//     +inf); TRANSACTION (system) time = created_at / invalidated_at
//     (invalidate-not-delete). value_hash is a STORED generated md5(value) so the
//     content-addressed natural key is consistent by construction. valid_to_eff is
//     a STORED generated coalesce(valid_to_ordinal, INT64_MAX) — the same
//     null-sink sentinel the KG uses (events.py _NULL_ORDER_SENTINEL) — so the
//     as-of range query is index-served. coverage_xid (xid8, non-wrapping) is the
//     staleness key the canonical cache compares against (§12.1 fact_coverage_txid).
//
//     The natural key UNIQUE(entity_id, fact_kind, attr_or_predicate, value_hash,
//     valid_from_ordinal, coalesce(source_episode_id, NIL)) makes Path-A re-runs
//     idempotent (ON CONFLICT DO NOTHING, C2). valid_from_ordinal IN THE KEY is
//     what makes oscillation work (A4): ch.100 宗门 and ch.300 宗门 are two rows /
//     two intervals, with [200,300)=秘境 intact between them — NOT a content-hash
//     collision. (coalesce(source_episode_id, NIL) so cold-start/migration facts
//     with no episode still dedup deterministically.)
//
//   - merge_journal extension — repointed_fact_ids / invalidated_fact_ids /
//     repointed_episode_ids so fact-chain merge (§12.4.1 step 5) and split_entity
//     (§12.4.2) stay exactly revertible; the existing fixed child-table list omits
//     these tables.
//
// All statements idempotent (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS), routed
// through execGuarded (the migration advisory lock) like every chain step.
// Forward-only; no data rewrite (the cold-start seed is the separate step 0046).
func UpEntityFacts(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-facts", `
		-- ── Episodes: immutable, content-hash-revisioned ingest unit ──────────────
		CREATE TABLE IF NOT EXISTS episodes (
		  episode_id      UUID PRIMARY KEY DEFAULT uuidv7(),
		  book_id         UUID NOT NULL,
		  chapter_id      UUID NOT NULL,
		  chapter_ordinal BIGINT NOT NULL,
		  char_start      INT,
		  char_end        INT,
		  token_count     INT,
		  content_hash    TEXT NOT NULL,
		  status          TEXT NOT NULL DEFAULT 'pending',
		  writeback_key   TEXT,
		  ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
		  reconciled_at   TIMESTAMPTZ,
		  CONSTRAINT episodes_status_chk CHECK (status IN ('pending','reconciled'))
		);
		CREATE UNIQUE INDEX IF NOT EXISTS uq_episode_chapter_hash
		  ON episodes (chapter_id, content_hash);
		CREATE INDEX IF NOT EXISTS idx_episode_book_ordinal
		  ON episodes (book_id, chapter_ordinal);

		-- ── entity_facts: append-only bi-temporal SSOT ───────────────────────────
		CREATE TABLE IF NOT EXISTS entity_facts (
		  fact_id            UUID PRIMARY KEY DEFAULT uuidv7(),
		  book_id            UUID NOT NULL,
		  entity_id          UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
		  fact_kind          TEXT NOT NULL,
		  attr_or_predicate  TEXT NOT NULL,
		  value              TEXT NOT NULL DEFAULT '',
		  value_hash         TEXT GENERATED ALWAYS AS (md5(value)) STORED,
		  valid_from_ordinal BIGINT NOT NULL,
		  valid_to_ordinal   BIGINT,
		  valid_to_eff       BIGINT GENERATED ALWAYS AS
		                       (coalesce(valid_to_ordinal, 9223372036854775807)) STORED,
		  cardinality        TEXT NOT NULL DEFAULT 'single',
		  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
		  coverage_xid       xid8 NOT NULL DEFAULT pg_current_xact_id(),
		  invalidated_at     TIMESTAMPTZ,
		  invalidated_reason TEXT,
		  source_episode_id  UUID REFERENCES episodes(episode_id) ON DELETE SET NULL,
		  CONSTRAINT entity_facts_cardinality_chk CHECK (cardinality IN ('single','multi')),
		  CONSTRAINT entity_facts_kind_chk
		    CHECK (fact_kind IN ('attribute','relation','event','name','alias')),
		  CONSTRAINT entity_facts_interval_chk
		    CHECK (valid_to_ordinal IS NULL OR valid_to_ordinal > valid_from_ordinal)
		);

		-- Content-addressed natural key (§12.2.2). source_episode_id coalesced to the
		-- nil UUID so migration/cold-start facts (no episode) still dedup deterministically.
		CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_facts_natural
		  ON entity_facts (
		    entity_id, fact_kind, attr_or_predicate, value_hash, valid_from_ordinal,
		    coalesce(source_episode_id, '00000000-0000-0000-0000-000000000000'::uuid)
		  );

		-- As-of range query, index-served (§12.3.1). Partial on current belief
		-- (invalidated_at IS NULL) — the latest-valid projection + every as-of read.
		CREATE INDEX IF NOT EXISTS idx_entity_facts_asof
		  ON entity_facts (entity_id, attr_or_predicate, valid_from_ordinal, valid_to_eff)
		  WHERE invalidated_at IS NULL;

		-- Canonical-cache staleness probe (§12.1): newest coverage_xid per entity.
		CREATE INDEX IF NOT EXISTS idx_entity_facts_coverage
		  ON entity_facts (entity_id, coverage_xid);

		-- Episode-scoped fact lookup (Path-B diff/retract + split_entity by provenance).
		CREATE INDEX IF NOT EXISTS idx_entity_facts_episode
		  ON entity_facts (source_episode_id) WHERE source_episode_id IS NOT NULL;

		-- Book-scoped repair (rebuild-projection-from-facts backstop, §12.2.1).
		CREATE INDEX IF NOT EXISTS idx_entity_facts_book ON entity_facts (book_id);

		-- ── merge_journal extension: fact/episode moves for exact revert (§12.4.1) ─
		ALTER TABLE merge_journal
		  ADD COLUMN IF NOT EXISTS repointed_fact_ids   UUID[] NOT NULL DEFAULT '{}';
		ALTER TABLE merge_journal
		  ADD COLUMN IF NOT EXISTS invalidated_fact_ids UUID[] NOT NULL DEFAULT '{}';
		ALTER TABLE merge_journal
		  ADD COLUMN IF NOT EXISTS repointed_episode_ids UUID[] NOT NULL DEFAULT '{}';`)
}
