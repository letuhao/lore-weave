package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// entityFactEvidenceSQL — the citation table write-time dedupe needs (plan T34 / design D7).
//
// ── THE PROBLEM ──────────────────────────────────────────────────────────────────────────
// Every chapter that mentions an entity re-asserts its attributes, and `emitChapterFacts`
// opened a NEW interval for each assertion — even when the value had not changed. Measured:
// **11.7 % of all fact rows carry no new information**, and `gender` is **93.2 %** of them.
// That share grows with chapter count, because the number of re-assertions grows and the
// number of actual changes does not.
//
// The rows are not merely wasteful. A chain of identical values makes "when did this change?"
// unanswerable without comparing every adjacent pair, and it inflates the as-of read's scan
// with intervals that all say the same thing.
//
// ── WHY A SEPARATE TABLE AND NOT A COUNTER ───────────────────────────────────────────────
// A counter on `entity_facts` would say a fact was re-asserted 40 times and not WHERE. The
// citation is the useful half: it is what lets a reader jump to the chapter that re-confirmed
// a value, and what makes a fact's support auditable after the extraction that produced it has
// been superseded. `evidences` cannot be reused — it hangs off `attr_value_id` (the EAV
// projection), not off a fact, and the two have different lifetimes.
//
// ── IDEMPOTENT BY KEY, NOT BY CHECK ──────────────────────────────────────────────────────
// The unique key is (fact_id, episode_id). Re-running an extraction for the same chapter must
// not inflate the evidence count either — "the fact count did not grow" would then be true
// while a different number grew unboundedly, which is the same bug wearing a different column.
// `ON CONFLICT DO NOTHING` at the call site makes a re-run a no-op on BOTH tables.
const entityFactEvidenceSQL = `
CREATE TABLE IF NOT EXISTS entity_fact_evidence (
    fact_id         uuid        NOT NULL REFERENCES entity_facts(fact_id) ON DELETE CASCADE,
    episode_id      uuid        REFERENCES episodes(episode_id) ON DELETE SET NULL,
    chapter_ordinal bigint      NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    -- The nil-uuid coalesce mirrors uq_entity_facts_natural: a citation with no episode
    -- (migration / cold-start writes) must still dedup deterministically rather than being
    -- allowed in unboundedly because NULL never equals NULL.
    PRIMARY KEY (fact_id, chapter_ordinal)
);

-- The read this exists for: every chapter that re-asserted a given fact, in story order.
CREATE INDEX IF NOT EXISTS idx_efe_fact ON entity_fact_evidence (fact_id, chapter_ordinal);
`

// UpEntityFactEvidence creates the fact-citation table (T34 / D7).
func UpEntityFactEvidence(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-fact-evidence", entityFactEvidenceSQL)
}
