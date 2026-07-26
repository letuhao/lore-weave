# Deep arc-conformance SUCCESSION — motif-tag + causal-edge extractors

**Date:** 2026-06-28 · **Track:** Narrative Motif Library (W10 deep arc-conformance) ·
**Branch:** `feat/narrative-pattern-library`

## Why

Deep arc-conformance currently realizes two of three §14.4 dims from prose (pacing-drift +
thread-progression). The third — **legal succession** ("did the realized prose follow the arc's
legal-succession order, and do each motif's realized *effects* satisfy the next's *preconditions*?")
— was mislabeled "blocked on the F-1 causal graph". It is **not blocked**; it is two buildable
extractors that compose. This doc designs + plans both.

The §14.4 succession question decomposes into:
1. **Realized motif ORDER** — which motif each realized scene actually delivers, in reading order.
   → needs a **motif-tag classifier** (Feature 1). Reuses the proven thread-tag recipe.
2. **Legal-succession check** — does that realized order respect the `precedes` graph?
   → reuses the EXISTING `precedes_pairs` / `successors_by_ids` (already built). Structural.
3. **Causal verification** — is each legal transition actually *caused* in the prose (A's effect
   enables B), not just adjacent? → needs **`(:Event)-[:CAUSES]->(:Event)` edges** (Feature 2).

Feature 1 delivers a real **structural** deep-succession (1+2). Feature 2 upgrades it to
**causally-verified** (3). `causal_verified` flips per-transition only where a causal edge backs it.

## Feature 1 — motif-tag classifier → structural deep succession

Mirrors `D-W10-ARC-CONFORMANCE-THREAD-TAG` exactly (see [[thread-tag-classifier-pattern]]).

**knowledge-service**
- NEW `app/extraction/motif_tag.py` — classify each `:Event` (title+summary+participants) → which
  of the arc's **placement `motif_code`s** it realizes (vocab = `[{code, name, summary}]` from the
  arc's placements' motifs), or `"none"`. Pure `build_messages` / `parse_assignments` + advisory
  batched `classify_event_motifs`. NEVER raises.
- `Event += realized_motif_code: str | None`; `set_realized_motifs(user_id, {event_id: code})`
  (tenant-scoped Cypher SET, mirror `set_narrative_threads`).
- `POST /internal/extraction/tag-motifs` (X-Internal-Token), body `{user_id, book_id, motifs:
  [{code,name,summary}], model_source, model_ref}` → `{tagged, events_seen, motifs_assigned}`.
- `motif_beat` step += `realized_motif_code` (additive, "" until tagged). Orthogonal to
  `thread`/`narrative_thread`.

**composition-service**
- `knowledge_client.tag_motifs(...)` (advisory degrade).
- Deep conformance: when `deep&model_ref`, ALSO call `tag_motifs` with the arc's placement-motif
  vocab; pass the resolved `precedes_pairs` (already computed) into `build_deep_report`.
- `build_deep_report.succession` becomes **available**: per thread (or globally) order the realized
  `realized_motif_code`s by chapter, dedupe consecutive, check each pair against `precedes_pairs`
  → `legal` / `reversed` (a precedes edge the wrong way = violation) / `unrelated`. Shape mirrors the
  coarse succession (`{available, causal_verified:false, threads:[{transitions, legal, unrelated,
  violations}]}`). `causal_verified:false` until Feature 2.

**FE** — `ArcConformancePanel` deep section renders succession (legal/violations per thread) when
available; honest "needs tagging" when not.

## Feature 2 — causal-edge extractor → causally-verified succession

**knowledge-service**
- NEW `app/extraction/causal_edges.py` — over the `event_order`-ordered timeline, an LLM infers, for
  each event, which *recent prior* events directly CAUSE/ENABLE it (a bounded look-back window, not
  all pairs — cost). Pure `build_messages` (a window of events + ask "which earlier ids cause this
  one") / `parse_edges` (validate ids ∈ window, drop self/forward) + advisory batched
  `infer_causal_edges`. NEVER raises.
- `merge_causal_edges(user_id, [(from_id, to_id)])` — Cypher `MERGE (a)-[:CAUSES]->(b)` (tenant-
  scoped on both nodes; idempotent). NEW relationship type; no schema migration (Neo4j is schemaless).
- `POST /internal/extraction/causal-edges` (book-scoped) → `{edges_written, events_seen}`.
- Reader `get_causal_pairs(user_id, book_id) -> list[[from_id, to_id]]` for composition.

**composition-service**
- `knowledge_client.causal_pairs(...)` (advisory degrade → `[]`).
- Deep conformance: read causal pairs; pass to `build_deep_report`. The succession dim upgrades a
  transition's `causal_verified:true` IFF the two motif-tagged events (the realized motifs in the
  pair) are connected by a causal edge in the prose. Report `causal_verified` true when ≥1 transition
  is causally backed; per-transition `caused: bool`.

**FE** — succession rows show a "caused" marker where a causal edge backs the legal transition.

## What stays a refinement (honest tail)

The deepest form — verifying motif A's *textual effects* literally satisfy motif B's *textual
preconditions* (an NLP entailment judge over `motif.effects`/`motif.preconditions` JSONB) — is a
further LLM-judge layer (calibration territory, like the conformance gold-set). Feature 2's causal
edges are the *structural causal* signal; the entailment judge is the *semantic* refinement. Tracked
as `D-SUCCESSION-ENTAILMENT-JUDGE`, NOT built here. Both extractors here ship advisory/uncalibrated
(a calibration gold-set is the trust follow-up, mirroring the conformance judge).

## Plan (milestones — commit at each)

- **F1-M1** knowledge: `motif_tag.py` + `Event.realized_motif_code` + `set_realized_motifs` +
  `/tag-motifs` + `motif_beat` field. Tests: pure build/parse + classify degrade + route mount/auth
  + motif_beat orthogonal-fields.
- **F1-M2** composition+FE: `tag_motifs` client + deep `build_deep_report.succession` (structural) +
  route tags-motifs-then-reports + FE render. Tests: pure succession (legal/reversed/unrelated) +
  route + FE.
- **F2-M3** knowledge: `causal_edges.py` + `merge_causal_edges` + `/causal-edges` + `get_causal_pairs`.
  Tests: pure window-build/parse-edges (drop self/forward/out-of-window) + infer degrade + route.
- **F2-M4** composition+FE: `causal_pairs` client + `causal_verified` upgrade in succession + FE
  "caused" marker. Tests: pure causal-verify + route + FE.

Live smokes (need Neo4j corpus + a chat model) deferred per-feature. Provider-gateway invariant holds
(both extractors call `submit_and_wait(operation="chat")` with a passed `model_ref`; no provider SDK).
