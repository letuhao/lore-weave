package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

// ── schema_migrations ledger ────────────────────────────────────────────────
//
// Historically the glossary chain was LEDGER-FREE: cmd/glossary-service ran every
// idempotent migrate func on EVERY boot, and execGuarded has no applied-record. That
// replays all DDL/seeds/backfills each startup — most visibly it CREATE+seeds the
// legacy system_kind_attributes table only for the G4e step to DROP it again, every
// boot (harmless whole-table recycle, no pg_attribute slot leak, but pure churn —
// D-GKA-G4-SEED-CLEANUP).
//
// This ledger records which steps have run so each runs EXACTLY ONCE. Adoption is safe
// precisely because every step is already idempotent: the first post-ledger boot of an
// EXISTING (un-ledgered) DB runs each step one final idempotent pass (the ledger is
// empty), records it, then quiesces — DDL no-ops on present tables, the cutover's own
// internal FK-existence guard keeps its TRUNCATE from firing on an already-cutover DB
// (NO data loss), and the legacy create/drop happens one last time before `0001_schema`
// stops replaying. Fresh DBs run each step once. From the second boot on, applied steps
// are skipped, system_kind_attributes is never recreated, and startup does no DDL work.
//
// IMPORTANT — seed semantics changed. Seed/SeedKindAliases/SeedGenreKindAttr are now
// ledgered (run once), NOT re-asserted every boot. New seed data (e.g. a kind added to
// domain.DefaultKinds) therefore needs a NEW chain entry, not auto-pickup on deploy —
// standard migration discipline. The seeds remain idempotent (ON CONFLICT) so a manual
// re-run after clearing a ledger row is still safe.

// Step pairs a stable ledger name with the migration func it guards. The Name is the
// permanent identity in schema_migrations — never rename one once shipped (a rename
// re-runs the step on every existing DB).
type Step struct {
	Name string
	Fn   func(context.Context, *pgxpool.Pool) error
}

// chain is the ordered glossary migration sequence. Order is load-bearing (FK targets,
// the G4 cutover→cache→drop ordering) and MUST match the historical main.go call order
// exactly — that order is what every already-migrated DB ran. Append new steps to the
// END with the next ordinal; never reorder or renumber existing entries.
var chain = []Step{
	{"0001_schema", Up},
	{"0002_seed", Seed},
	{"0003_seed_kind_aliases", SeedKindAliases},
	{"0004_snapshot", UpSnapshot},
	{"0005_backfill_snapshots", BackfillSnapshots},
	{"0006_soft_delete", UpSoftDelete},
	{"0007_genre_groups", UpGenreGroups},
	{"0008_wiki", UpWiki},
	{"0009_wiki_suggestions", UpWikiSuggestions},
	{"0010_extraction", UpExtraction},
	{"0011_evidence_chapter_index", UpEvidenceChapterIndex},
	{"0012_outbox", UpOutbox},
	{"0013_knowledge_memory", UpKnowledgeMemory},
	{"0014_backfill_knowledge_memory", BackfillKnowledgeMemory},
	{"0015_short_desc_auto", UpShortDescAuto},
	{"0016_short_desc_constraints", UpShortDescConstraints},
	{"0017_entity_enrichments", UpEntityEnrichments},
	{"0018_entity_merge", UpEntityMerge},
	{"0019_merge_candidates", UpMergeCandidates},
	{"0020_entity_revisions", UpEntityRevisions},
	{"0021_glossary_search", UpGlossarySearch},
	{"0022_entity_counts", UpEntityCounts},
	{"0023_user_kinds", UpUserKinds},
	{"0024_genre_kind_attr", UpGenreKindAttr},
	{"0025_seed_genre_kind_attr", SeedGenreKindAttr},
	{"0026_glossary_cutover_g4", UpGlossaryCutoverG4},
	{"0027_merge_candidates_g4", UpMergeCandidatesG4},
	{"0028_glossary_cutover_g4_cache", UpGlossaryCutoverG4Cache},
	{"0029_glossary_drop_legacy_g4", UpGlossaryDropLegacyG4},
	{"0030_consumed_tokens", UpConsumedTokens},
	{"0031_system_soft_delete", UpSystemSoftDelete},
	{"0032_extraction_concurrency", UpExtractionConcurrency},
	{"0033_evidence_provenance", UpEvidenceProvenance},
	{"0034_merge_policy", UpMergePolicy},
	{"0035_multirow_attr_values", UpMultirowAttrValues},
	// Merge: this branch's 0035 collided with main's 0035_multirow_attr_values; renumbered
	// to 0036 (idempotent migration, so a DB that already ran it under the old key re-runs cleanly).
	{"0036_system_attr_descriptions", UpSystemAttrDescriptions},
	// KG-ML M5 (C4 / DD4) — name_i18n on the kind tiers + System vi seed.
	{"0037_kind_name_i18n", UpKindNameI18n},
	// D-BATCH-RESEARCH-JOB M1 — async batch entity-research job table.
	{"0038_entity_research_jobs", UpEntityResearchJobs},
	// D-EXTRACT-ATTR-MERGE-DEFAULTS M1 — re-seed merge_strategy by type heuristic
	// (tags→append, state→overwrite, identity→fill) so re-extraction accumulates.
	{"0039_merge_strategy_heuristic", UpMergeStrategyHeuristic},
	// D-GLOSSARY-ST-DEDUP M3a — normalized_name GENERATED→app-maintained so the
	// dedup-key backstop folds CJK simplified/traditional + full-width + casefold
	// via the shared loreweave_extraction SDK (the same fold the resolver uses).
	{"0040_st_dedup_app_maintained", UpStDedupAppMaintained},
	// M7 (D-T5.2-WINDOWED-MENTIONS) — per-chapter mention_count on chapter_entity_links
	// so the FE mention heatmap can window per-chapter frequencies ≤ a cutoff.
	{"0041_chapter_link_mention_count", UpChapterLinkMentionCount},
	// #38/#39 — (book_id, normalized_name) lookup index for cross-kind entity dedup
	// (findEntityCrossKind), so a name resolves across kinds without a per-book scan.
	{"0042_cross_kind_dedup_index", UpCrossKindDedupIndex},
	// #26/#7 — the `summarize` merge-rewrite mode's canonical layer on the EAV
	// (canonical_value + canonical_dirty + canonical_synced_at).
	{"0043_canonical_summary", UpCanonicalSummary},
	// Temporal-knowledge F1a — the append-only bi-temporal fact SSOT (entity_facts
	// + episodes) + merge_journal fact/episode-move columns. Spec
	// docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md §12.0/§12.2/§12.3.
	{"0044_entity_facts", UpEntityFacts},
	// Temporal-knowledge F1b — maintain_chain(entity, attr): the single writer of
	// entity_facts.valid_to_ordinal (ordinal-aware interval-split + retract restitch
	// + merge reconcile, one routine). Spec §12.3.3 (LOCKED).
	{"0045_maintain_chain", UpMaintainChain},
	// Temporal-knowledge F1h — cold-start seed: every flat EAV value becomes one open
	// bi-temporal fact so the derived projection is byte-identical to the pre-migration
	// flat store on day one. Spec §12.5.4 / dec-5.
	{"0046_facts_cold_start", UpFactsColdStart},
	// Temporal-knowledge F2 — the canonical as a lazy, versioned, regenerable CACHE
	// (canonical_snapshot rows + per-entity canonical_fold_state). Spec §12.1 (B0 LOCKED).
	{"0047_canonical_snapshot", UpCanonicalSnapshot},
	// Temporal-knowledge F1g — name/aliases as first-class bi-temporal fact kinds
	// (name single, alias multi); reconciles the cold-start/F1d attribute representation.
	// Spec §12.4.3.
	{"0048_bitemporal_names", UpBitemporalNames},
	// Temporal-knowledge close_fact — explicit valid-time close: `valid_to_pinned` column +
	// pin-aware maintain_chain (the manual close is an authored input the single deriver
	// respects, never overwrites). Spec §12.3.2.
	{"0049_fact_close_pin", UpFactClosePin},
	// Per-episode translation surface — on-demand, immutable canonical translation cache
	// (mirror of KG-TL M3 event_text_translations); the LLM runs in translation-service via
	// provider-registry, glossary only stores + single-flights the fill. Spec §6B/§7.6.
	{"0050_canonical_snapshot_translations", UpCanonicalSnapshotTranslations},
	// D-GLOSSARY-ENTITY-SCOPE — optional author-set scope_label disambiguator +
	// widened dedup key (book_id, kind_id, normalized_name, scope_label). Real
	// feedback, 2026-07-08: two same-named entities in different "worlds" within
	// one multi-world book were indistinguishable to the dedup/merge resolver.
	{"0051_entity_scope_label", UpEntityScopeLabel},
	// WS-1.5 (spec 05 §Q2) — the System-tier WORK ontology (colleague·project·meeting·
	// decision·task·jargon·org), seeded HIDDEN so it never shows in a novelist's picker;
	// provisioning clones it into the diary's book tier. A NEW ledger entry, per the
	// "new seed data needs a new chain entry" rule (editing DefaultKinds would no-op on
	// already-migrated DBs).
	{"0052_seed_work_kinds", SeedWorkKinds},
	// WS-1.6 (spec 05 §Q5) — glossary_entities.is_self + one-self-per-book unique. The
	// user's OWN identity entity in their diary, so capture + the detectors exclude it.
	{"0053_entity_is_self", UpEntityIsSelf},
	// C4 / SD-C4 (D-WIKI-PERSON-FLAG) — a structural is_person flag on every kind tier (backfills
	// the seeded 'colleague'); the wiki-gen/enrichment PP-4 guards filter on it instead of the
	// literal 'colleague' code, so a renamed/custom REAL-person kind can't leak an AI biography.
	{"0054_kind_is_person", UpKindIsPerson},
}

// EnsureLedger creates the schema_migrations bookkeeping table. Idempotent; must run
// before any ApplyOnce. Routed through execGuarded (the migration advisory lock) — a
// bare CREATE TABLE IF NOT EXISTS is NOT concurrency-safe in Postgres (concurrent runs
// can raise a duplicate pg_type/pg_class unique violation rather than no-op'ing), and
// concurrent startup is an acknowledged scenario here (parallel test binaries / multiple
// replicas — see execGuarded). Serializing it on the same key as the rest of the chain
// closes that race.
func EnsureLedger(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "ensure-schema-migrations", `
		CREATE TABLE IF NOT EXISTS schema_migrations (
		  name       TEXT PRIMARY KEY,
		  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)`)
}

// migrationApplied reports whether a step name is recorded in the ledger.
func migrationApplied(ctx context.Context, pool *pgxpool.Pool, name string) (bool, error) {
	var exists bool
	if err := pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE name = $1)`, name,
	).Scan(&exists); err != nil {
		return false, fmt.Errorf("ledger lookup %s: %w", name, err)
	}
	return exists, nil
}

// ApplyOnce runs fn iff name is not yet recorded, then records it. fn runs with its own
// transaction/advisory-lock (unchanged) — we do NOT hold a lock across it, so a fn that
// takes the migration advisory lock internally can't self-deadlock.
//
// Crash-safety: if the process dies between fn succeeding and the ledger INSERT, the
// next boot finds name still unrecorded and re-runs fn — harmless because every step is
// idempotent. Concurrent startups: both may run fn (serialized by fn's own advisory
// lock, so no DDL conflict) and race to INSERT; the PK + ON CONFLICT DO NOTHING dedups.
func ApplyOnce(ctx context.Context, pool *pgxpool.Pool, name string, fn func(context.Context, *pgxpool.Pool) error) error {
	applied, err := migrationApplied(ctx, pool, name)
	if err != nil {
		return err
	}
	if applied {
		return nil
	}
	if err := fn(ctx, pool); err != nil {
		return fmt.Errorf("migrate %s: %w", name, err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO schema_migrations(name) VALUES($1) ON CONFLICT DO NOTHING`, name,
	); err != nil {
		return fmt.Errorf("record migration %s: %w", name, err)
	}
	return nil
}

// RunChain ensures the ledger exists then applies every chain step once, in order. This
// replaces the historical sequence of unconditional migrate calls in main.go. The two
// async background backfills (BackfillShortDescription, BackfillEntityRevisions) are NOT
// in the chain — they stay as non-blocking goroutines in main.go (self-limiting to
// unprocessed rows).
func RunChain(ctx context.Context, pool *pgxpool.Pool) error {
	if err := EnsureLedger(ctx, pool); err != nil {
		return err
	}
	for _, s := range chain {
		if err := ApplyOnce(ctx, pool, s.Name, s.Fn); err != nil {
			return err
		}
	}
	return nil
}
