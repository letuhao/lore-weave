# Roadmap — Pre-merge close-out (clear ALL remaining debt + missing features before merging PR #19)

- **Date:** 2026-06-08 · **Branch:** `feat/composition-service` · **HEAD:** `7c097447`
- **PO directive (2026-06-08):** do **NOT** merge PR #19 yet — handle **all** remaining debt and missing features first, *then* close/merge the branch. Supersedes the prior "campaign done → merge" stance.
- **Method:** each item = a full 12-phase `/loom` cycle with VERIFY + `/review-impl`. Continues the cycle numbering (next is cycle 10). Cheap-but-high-value / unblocking first, then the big net-new features, then optional + cosmetic.

The branch-debt cleanup campaign (cycles 5–9) cleared the composition/LOOM branch's own ledger. This roadmap covers everything that was **excluded** or **re-scoped** there, plus the producer bugs the cycle-8 live-smoke surfaced.

### Reconciliation with the 2026-06-07 debt-payoff roadmap (063/064/K17)

The earlier [debt-payoff roadmap](2026-06-07-debt-payoff-roadmap.md) (063/064/K17) is **absorbed into this one** — it is no longer a separate plan:
- **K17** → **Cycle 12** here (entity-embedding write pipeline).
- **064** → **Cycle 15** here (already re-scouted cy5 = no clean slice; cy15 confirms + closes).
- **063** → **Cycle 17** here (added 2026-06-08 — it had fallen out of this composition close-out because it is a *lore-enrichment* debt, not a composition-branch one; PO 2026-06-08 chose to clear it pre-merge anyway so the whole platform ledger reaches zero).

---

## Phase 1 — Producer bugs (unblock the canon flywheel) — do FIRST

### Cycle 10 — DEFERRED 065: extraction status-enum — ✅ DONE 2026-06-08 (LOOM-52)
**RESOLVED — but the diagnosis below was WRONG.** Root cause was the M1 migration constraint (renamed `complete`→`completed` + dropped `paused`/`cancelled`), NOT worker-ai. Fixed by reconciling the `extraction_jobs_status_check` constraint (inline + M1 ALTER) to the full vocab `('pending','running','paused','summarizing','complete','failed','cancelled')` — a widening, NO worker-ai/state_machine/FE change. Real-PG integration regression-lock added. The full worker-ai→knowledge extraction chain smoke rides on **cycle 11** (which depends on this fix). Original (incorrect) framing kept below for the record:

> worker-ai `_mark_complete` writes `status='complete'` but the constraint allows only `'completed'` → **every finished extraction CheckViolates → marked `failed`** ([runner.py:722](../../services/worker-ai/app/runner.py#L722) + the `NOT IN ('complete',…)` guards at 724/740/767). Real platform-wide bug (completion signal broken). Fix `'complete'`→`'completed'`, add a test, **re-run the cycle-8 full-chain smoke** to confirm a job reaches `completed`. Cheap, highest leverage (also unblocks cycle 11's verification).

### Cycle 11 — DEFERRED 066: A2-S1b status_effects → :EntityStatus producer gap — ✅ DONE 2026-06-08 (LOOM-53)
**Diagnosis CORRECTED + instrumented.** The cycle-8 "canonical_id=NULL anchoring blocks the status" hypothesis was WRONG — the Pass-2 resolver keys the chapter map on `entity.id` (always set, no `≥2 links` need) and the whole producer path is statically correct. PO chose instrument-first → added `knowledge_extraction_status_effect_total{outcome}` so the silent-skip is observable; live: rebuilt knowledge-service, cycle-10 constraint swap confirmed live, metric exposed. The real-LLM death-chapter diagnostic (run one extraction, read the counter) → **DEFERRED 067** (now cheap to interpret). Original framing below:

> Depends on cycle 10. The cycle-8 smoke proved a real death-chapter extraction yields **no `:EntityStatus{gone}`** (entities had `canonical_id=NULL` — the anchor-link gap). Chase WHY: (a) does the extractor emit `status_effects` in the worker config? (b) is `event_order` threaded? (c) does anchoring (`canonical_id`/≥2 chapter_entity_links) gate the status write? Fix the producer so a published death yields `:EntityStatus`. **AC:** re-run the full-chain smoke → cypher shows `:EntityStatus{gone}` for the dead character. Cross-service live-smoke.

---

## Phase 2 — Missing features (net-new)

### Cycle 12 — K17 entity-embedding write pipeline (L/XL, cross-service)
The mui#4 semantic read path is live but nothing WRITES `embedding_{dim}`/`embedding_model` on `:Entity` (hand-stamped today). Build the producer (batch backfill + incremental dirty-signal; degrade-safe; cost-bounded) so `/glossary-semantic` returns `tier=semantic` with no hand-stamping. Full design + open questions in the [debt-payoff roadmap §K17](2026-06-07-debt-payoff-roadmap.md#item-3--k17-entity-embedding-write-pipeline-lxl). Needs its own CLARIFY (trigger point A/B/C). Cross-service live-smoke (knowledge ↔ provider-registry ↔ glossary).

### Cycle 13 — D-A3-PLANNER-FE (L/XL, [FE]) + D-A3-REPLACE-ORPHAN-ARC-NODES
The A3 decompose planner shipped BE+eval with FE deferred. Build the planner tree UI: preview the proposed arc→chapter→scene tree, edit beats/tension, commit (the BE endpoints exist: `…/outline/decompose` + `…/decompose/commit`). Clears **D-A3-REPLACE-ORPHAN-ARC-NODES** too (the FE filters/archives the childless prior arc/chapter nodes that `replace` leaves behind).

### Cycle 14 — D-COMP-DECOMPOSE-PLAN-LEDGER-DRIFT / `narrative_thread` ledger (L, Phase-B feature)
The reasoning-engine spec's Phase-B `narrative_thread` ledger (§4/§5) — track promises/intent so the decompose plan's scene beats don't drift from chapter intent (Promise/Payoff → `check` vs ledger + `compress` maintains it). Net-new. Needs CLARIFY to scope (full ledger vs a lighter intent-reinjection lever). Eval-gated.

---

## Phase 3 — Optional + cosmetic cleanup (last)

### Cycle 15 — D-GROUNDING-C-ADOPT (064) (XS–S, optional)
Re-scouted cy5: no clean slice (SDK NFKC would fold composition's `<`→`＜` delimiter defense; no `GroundingCite` consumer). Only act if a generation-side cite consumer now exists OR composition's sanitize is rebuilt. Likely stays deferred — confirm + close.

### Cycle 16 — Cosmetic LOW batch (XS–S)
Batch the tiny accepted LOWs: (a) stale comment at [works.py:138](../../services/composition-service/app/routers/works.py#L138) (cy6 fixed the race knowledge-side); (b) revise-path truncation not surfaced (cy7 `truncated` is winner-scoped — thread the canon-revise `finish_reason` if cheap); (c) `stitch`-revise `packed_prompt=""`.

### Cycle 17 — DEFERRED 063: D-GROUNDING-COMPOSE-MIGRATE (M, lore-enrichment) — added 2026-06-08
Cross-track item folded in (PO 2026-06-08): migrate lore-enrichment's grounding-COMPOSE path from the local `GroundingRef` to the SDK's `GroundingCite`, closing the last mui#3 compose-side gap. Full design + AC in the [debt-payoff roadmap §063](2026-06-07-debt-payoff-roadmap.md#item-2--063-d-grounding-compose-migrate-m). **Recommended internal-only migration** (keep `source_refs_json` byte-stable, route compose through `loreweave_grounding.compose_cites` + `from_grounding_ref`, adapt at the persistence boundary) → zero data-migration, preserves the re-cook `UUID(corpus_id)` license path. P2/P3 are gate-locked, so this is forward-guard cleanup, not a live-path fix. Single-service (lore-enrichment) — no cross-service live-smoke needed. **Note:** unrelated to the composition branch; bundled here only to reach a zero platform ledger before merge.

---

## Explicitly NOT reopening (conscious won't-fix, accepted cy5)
- `D-COMP-STITCH-PERSCENE-CEILING` — inherent property of the merge approach (chapter mode is the clean path).
- b-đúng cross-chapter prose-carry — KG lenses already carry cross-chapter state.
(If the PO wants these revisited, they become their own cycles — but they are deliberate trade-offs, not debt.)

---

## Close-out gate (when to merge PR #19)
Merge only after: cycles 10–14 done (065/066 producer bugs + K17 + planner-FE + narrative_thread); 15/16 done or consciously re-deferred; cycle 17 (063) done or re-deferred (it does **not** block the composition merge — it's a cross-track lore-enrichment item bundled for a zero platform ledger); the won't-fix items remain documented accepts. At that point the branch has **zero** open debt or missing features, and PR #19 closes the full composition V1 + Canon arc.

**Order:** 10 → 11 (flywheel unblock) → 12 (K17) → 13 (planner-FE) → 14 (narrative_thread) → 15/16 (optional+cosmetic) → 17 (063, cross-track) → MERGE. Order is flexible; 11 depends on 10, the rest are independent. 17 is independent and can run anytime (or slip to post-merge if the PO re-prioritizes — it's the only non-composition item).
