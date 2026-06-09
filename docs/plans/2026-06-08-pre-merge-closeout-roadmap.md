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

### Cycle 12 — K17 entity-embedding write pipeline (L/XL, cross-service) — ✅ DONE 2026-06-08 (LOOM-54 foundation + LOOM-55 wiring/smoke)
**COMPLETE.** Foundation (S1+S2) + the backfill route (S3) + a cross-service live smoke (S4) that embedded 22/22 anchored demo entities via real provider-registry and returned `tier=semantic` from `/glossary-semantic` on the auto-embedded vectors — retiring the DEFERRED 061 hand-stamp. Optional non-blocking follow-up: auto-incremental hook + auto-backfill-on-model-change (both call the same route). Detail below (foundation) + DEFERRED ~~068~~.

**Reshaped by raw-search:** the just-merged passage-embedding pipeline (`passage_ingester` + `upsert_passage`) is the template — K17 REUSES the mechanics, not design-from-scratch. Trigger = batch-backfill + incremental (B), since an entity is cross-chapter (unlike chapter-scoped passages). **Foundation shipped (S1+S2):** `set_entity_embedding` + `find_entities_needing_embedding` (entities.py) + `embed_project_entities` (entity_embedder.py, degrade-safe, glossary-fallback, dim-validated, drain-cap), 7 unit tests; /review-impl MED fixed (no `updated_at` bump on the derived embedding write). **Cycle 12b (DEFERRED 068):** S3 wire a caller (internal backfill route + incremental post-extraction hook) + S4 cross-service live full-chain smoke (retire the DEFERRED 061 hand-stamp). Original framing below:

> The mui#4 semantic read path is live but nothing WRITES `embedding_{dim}`/`embedding_model` on `:Entity` (hand-stamped today). Build the producer (batch backfill + incremental dirty-signal; degrade-safe; cost-bounded) so `/glossary-semantic` returns `tier=semantic` with no hand-stamping. Full design + open questions in the [debt-payoff roadmap §K17](2026-06-07-debt-payoff-roadmap.md#item-3--k17-entity-embedding-write-pipeline-lxl). Needs its own CLARIFY (trigger point A/B/C). Cross-service live-smoke (knowledge ↔ provider-registry ↔ glossary).

### Cycle 13 — D-A3-PLANNER-FE (L/XL, [FE]) + D-A3-REPLACE-ORPHAN-ARC-NODES — ✅ DONE 2026-06-08 (LOOM-56 design + LOOM-57 build)
**D-A3-PLANNER-FE CLEARED.** Built the Planner sub-tab: api+types + `usePlanner` + `PlannerView`/`PlannerTree`/`PlannerSceneRow`, always-mounted CSS-hidden in CompositionPanel; flow template+premise+model → preview arc→chapter→scene tree → inline edit (title/synopsis/tension + chapter intent + add/remove scene) → commit (409→named-chapters replace-confirm). tsc clean + composition vitest 76 (incl. the no-unmount round-trip lock + edit→commit-payload non-default regression). i18n×4. /review-impl: 1 fix (no-unmount test), 3 LOW accepted (beat_role editable, model hint, both follow-ups). **D-A3-REPLACE-ORPHAN-ARC-NODES → DEFERRED 069** (precisely diagnosed: a BE fix in `commit_decomposed_tree`, not FE — archive the prior arc/chapter on replace). Design-checkpoint detail below.

DESIGN+PLAN locked in [docs/plans/2026-06-08-a3-planner-fe.md](2026-06-08-a3-planner-fe.md) (no code, per XL discipline): Planner sub-tab in CompositionPanel (CSS-hidden), flow template+premise+model → preview tree → inline edit → commit (409→replace-confirm); MVC usePlanner+PlannerView+PlannerTree+PlannerSceneRow + locked api/types; 4 slices (S1 api+types · S2 preview+hook+tab · S3 edit+commit/replace · S4 orphan-handling+i18n+a11y). /review-impl on the design folded (preview-step 400 surfacing; unmount + 409-replace mitigations). **BUILD = cycle 13-BUILD** (a focused session inherits the locked interfaces). Original framing below:

> The A3 decompose planner shipped BE+eval with FE deferred. Build the planner tree UI: preview the proposed arc→chapter→scene tree, edit beats/tension, commit (the BE endpoints exist: `…/outline/decompose` + `…/decompose/commit`). Clears **D-A3-REPLACE-ORPHAN-ARC-NODES** too (the FE filters/archives the childless prior arc/chapter nodes that `replace` leaves behind).

### Cycle 14 — D-COMP-DECOMPOSE-PLAN-LEDGER-DRIFT / `narrative_thread` ledger (L, Phase-B feature) — 🟡 S1 FOUNDATION DONE (LOOM-58)
The reasoning-engine spec's Phase-B `narrative_thread` ledger (§4/§5/§10.2) — track promises/intent so the decompose plan's scene beats don't drift from chapter intent (Promise/Payoff → `check` vs ledger + `compress` maintains it). **PO chose the FULL ledger §10.2** (over a lighter intent-reinjection lever). ✅ **S1 foundation built:** the `narrative_thread` table (kind promise/foreshadow/question/mice_thread · status open→progressing→paid|dropped · `opened_at_node`/`payoff_node` **FK → outline_node ON DELETE SET NULL** · priority · the `payoff-only-when-paid` CHECK) + `generation_job.state` JSONB ([migrate.py](../../services/composition-service/app/db/migrate.py)); `NarrativeThread` model; `NarrativeThreadRepo` (open_thread / update_status / **list_open** = the F2 re-injection set, priority DESC + created_at ASC / list_for_project); **4 real-PG integration tests** (lifecycle, payoff-only-when-paid, list_open ordering, node-delete SET-NULL). /review-impl: MED (missing FK) fixed + ordering/delete tests added; 2 LOW accepted. **The ledger is INERT** — no producer/consumer/eval yet. **S2 OPEN-detection + S3 re-injection/compress + S4 DEBT-check + eval → DEFERRED 070** (build when long-form promise-drift is the measured pain; ADVISORY per spec D4). Foundation is enough to unblock the merge gate (schema + repo locked; the producer is additive, no migration).

---

## Phase 3 — Optional + cosmetic cleanup (last)

### Cycle 15 — D-GROUNDING-C-ADOPT (064) (XS, optional) — ✅ DONE (LOOM-59)
Re-scouted cy5: no clean slice (SDK NFKC would fold composition's `<`→`＜` delimiter defense; no `GroundingCite` consumer). Only act if a generation-side cite consumer now exists OR composition's sanitize is rebuilt. ✅ **Re-CONFIRMED against HEAD 6492f0fa (code-verified, not assumed):** both blockers still hold — [sanitize.py:40](../../services/composition-service/app/packer/sanitize.py#L40) fullwidth-escapes `<`→`＜` + `⟦…⟧` directives, and the SDK `prenormalize` NFKC-folds it back ([sdks/.../sanitize.py:110-114](../../sdks/python/loreweave_grounding/sanitize.py#L110-L114)); grep = ZERO `GroundingCite`/`compose_cites`/`loreweave_grounding` in composition. **PO 2026-06-09: keep deferred (re-confirmed), NOT won't-fix** — genuine future trigger (a cite consumer appears OR sanitize is rebuilt). DEFERRED 064 stamped with the re-confirmation + trigger. Docs-only cycle, no production code.

### Cycle 16 — Cosmetic LOW batch (M) — ✅ DONE (LOOM-60)
Batch the tiny accepted LOWs: (a) stale comment at [works.py:138](../../services/composition-service/app/routers/works.py#L138) (cy6 fixed the race knowledge-side); (b) revise-path truncation not surfaced (cy7 `truncated` is winner-scoped — thread the canon-revise `finish_reason` if cheap); (c) `stitch`-revise `packed_prompt=""`. ✅ **All three done (PO chose all):** (a) comment rewritten to state D-COMP-POST-WORK-RACE was resolved cy6/LOOM-48 knowledge-side (`create_or_get` + advisory lock); (b) new `ReflectResult.revise_finish_reason` ([canon_check.py](../../services/composition-service/app/engine/canon_check.py)) — `run_canon_reflect` captures the last text-producing revise pass's stop reason ([canon_reflect.py](../../services/composition-service/app/engine/canon_reflect.py)), and all 3 engine sites (auto/scene, chapter, stitch) OR `=="length"` into the job's `truncated` flag (a cut-off repair is no longer a silent green); (c) [engine.py:759](../../services/composition-service/app/routers/engine.py#L759) `packed_prompt="" → chapter_intent` (stitch repair now has the chapter goal to steer by). Carried the signal on `ReflectResult` (field, default None) not a 4th return value → zero churn to 5 test sites + 3 callers. **Verify:** 361 composition unit incl a new truncating-revise test + a non-default contrast (clean revise asserts `revise_finish_reason is None`). Single-service.

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
