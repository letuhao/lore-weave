# Plan — Enrichment GUI gap-closure (draft ↔ impl)

> **Created:** 2026-06-04 · **Branch:** `lore-enrichment/foundation` · **Status:** READY TO BUILD
> **Origin:** 8-agent draft-vs-impl audit (workflow `wf_48eeef8c-006`). Matrix: **80 implemented / 8 partial / 7 missing / 17 diverged (mostly accepted) / 5 na.**
> **Decision (PO, 2026-06-04):** plan + close ALL real gaps FIRST; **do NOT run deep e2e yet** — e2e against an incomplete GUI is wasted effort. Deep e2e (Step 2) runs only AFTER the slices below land.

## Principle

The enrichment **engine and high-traffic flows are ship-quality** (all 5 compose modes, async job spine, proposal triage→promote/reject/retract, gap detect/enrich, source register/ingest/ground, de-bias profile — all wired to real, owner-gated, non-stub backends; several flows EXCEED the drafts). The remaining work is **author-control + observability surfacing + cosmetic parity**. Close them so the GUI is genuinely feature-complete vs the drafts, then e2e.

Accepted divergences (NO action — conscious team decisions, kept out of scope): tab-not-sidebar; top-N numeric input; mode E web-search DROPPED (copyright); verify-clean collapsed line (per-flag rows still render on FAILURE); Profile/Settings + glossary unknown-review being newer than the drafts; cost-cap in USD.

---

## Slices (build order)

Each slice is its own BUILD→VERIFY→REVIEW→COMMIT cycle (per CLAUDE.md). FE = `frontend/src/features/enrichment/`; BE = `services/lore-enrichment-service/app/`.

### Slice 1 — Compose author controls (HIGH #1, #2 + MED #6) · size **M-L** (FS)
The two load-bearing Step-3 author controls from the draft + the gate advisory.

- **#2 Technique selector (P1/P2/P3)** — `ComposeConfig.tsx`: a technique `<select>` (retrieval / fabrication / recook; draft-expand stays mode-D-implicit). BE **already accepts** `ComposeBody.technique` (compose.py) → mostly FE wiring + pass-through; default per mode unchanged when unset. Gate-locked techniques (P2/P3) still enforced server-side.
- **#6 eval-gate warning** — when the author picks P2/P3, show the draft's "⚠ P2/P3 cần eval-gate pass" advisory (read-only hint; gate enforced server-side regardless). Pairs with #2.
- **#1 Dimension picker chips** — let the author choose WHICH dimensions to enrich (today entirely server-derived: pipeline enriches `missing_dimensions` = full − `present_dimensions`).
  - **BE:** add a read endpoint `GET /v1/lore-enrichment/projects/{id}/dimensions?book_id=&kind=` → `resolve_dimensions(profile, kind)` (the effective base+override list) so the FE can render the chips; add an optional `requested_dimensions` to `ComposeTargetInput` → when set, the handler sets `missing_dimensions = requested` (and present = the complement) instead of deriving. Keep "auto" (omit) = current behavior.
  - **FE:** `ComposeConfig`/`ComposePanel` render the kind's dimensions as toggle chips + an "auto" default; thread the selected subset into the run body.
- i18n ×4; vitest for the selector + picker + gate-warning; BE pytest for `requested_dimensions` → missing mapping + the dimensions endpoint. **Op:** rebuild service to ship the endpoint.

### Slice 2 — Profile override full editor (HIGH #3) · size **M** (FE)
`DimensionOverrideEditor.tsx` currently authors only `add`. BE (`book_profile.validate_dimension_overrides`) already validates all 4 ops (add/remove/relabel/reweight).
- Add UI to **remove** a seeded dimension, **relabel** it, **reweight** it (per-kind), round-trip through the existing full-replace PUT (`useBookProfile`).
- FE-only. vitest covering each op + the full-replace round-trip (don't wipe untouched ops). i18n ×4.

### Slice 3 — Jobs observability (MED #4, #5) · size **S** (FE)
Data already in the `/jobs` payload — just render it.
- **#4** `JobsPanel.tsx`: show a failed job's `error_message` (e.g. "refused: gate-locked") under the failed badge.
- **#5** show **spent-vs-cap** (`actual_cost_usd` / `max_spend_usd`) + `estimated_cost` — cost-cap-pause is the panel's whole point.
- Verify the list endpoint returns these fields (add to the serializer if absent — small BE). vitest + i18n ×4.

### Slice 4 — Compose "Save to corpus" (MED #7) · size **S-M** (FS)
Today modes C/F always ingest as `compose_ephemeral` (TTL-reaped). Add an opt-in to persist as a **curated** Source.
- **BE:** `compose.py` `_ingest_context` — accept a `persist_corpus` flag; when true, DON'T tag ephemeral (the corpus becomes a normal `/sources` entry surfaced in Sources). (Mirror of the reaper tag.)
- **FE:** a "Lưu vào nguồn / Save to corpus" checkbox in `ComposeContextForm` + `ComposeFilesForm`; thread to the body.
- pytest (tagged vs untagged) + vitest + i18n ×4.

### Slice 5 — Proposal flag preview + Source embed status (MED #8, #9) · size **M** (FS)
- **#8 (FE)** `ProposalCard.tsx`: show advisory-flag KIND + short evidence inline (e.g. "regurgitation 逐字重合 14 字"), not just a count. Data is in the proposal/verify payload. vitest.
- **#9 (FS)** `SourceCard.tsx`: an explicit "embedded ✓ / processing" status pill. Needs a BE status signal — today `chunk_count>0` is the de-facto proxy. Add an `embed_status` (or surface `chunks_embedded` vs `chunks_total`) on the `/sources` list; FE renders the pill. pytest + vitest.

### Slice 6 — Cosmetic parity + dead-path cleanup (LOW #10–18 + #19) · size **M** (mostly FE)
Batch the no-behavior-loss parity items; each is small. Skip any the team decides isn't worth it.
- #10 per-mode © risk badges on `ModeSelector` cards · #11 mode-C "② Trừu tượng →" preview chip · #12 ①②③④ safety strip as 4 chips · #13 dim/source NAMES on `ProposalCard` · #14 `ProposalDetail` subtitle (kind · entity · book) · #15 (accepted — no action) · #16 completed-gap "✓ 5/5 re-enrich" row in `GapsPanel` (+ BE: surface fully-covered entities from detect-gaps) · #17 Sources in-grid dashed "add corpus" tile · #18 `ProfileForm` profile_source chip refresh after Suggest.
- **#19 dead path:** `listKindAliases` GET has a real BE handler + FE api wrapper but no consumer — either surface an existing-alias table in the glossary unknown-review GUI, OR drop the unused wrapper. Decide at build time (lean: surface a small read-only alias list in `ResolveKindModal`, else delete).
- i18n ×4 for any new strings; vitest per touched component.

---

## After the slices — Step 2: deep e2e (separate session)
Only once Slices 1–6 land:
1. **Rebuild** `lore-enrichment-service` (Tesseract jpn/vie + extract + migrate ordering + new endpoints) + `lore-enrichment-worker` (reaper).
2. **Live-smoke the reaper** end-to-end (stale upload → failed; orphan object delete; ephemeral corpus reaped) on the running stack.
3. **Browser e2e** (Playwright, this worktree's vite dev) of the full author journeys: compose each mode → proposal → promote/reject/retract; profile authoring incl. the new override ops; jobs cost/error surfacing; glossary unknown-review triage.

## Tracking
- These gaps are logged as a single planned epic; per-slice deferral rows are unnecessary while this plan is the live tracker.
- E2e (Step 2) is the explicit follow-on — do not start it before Slices 1–6.
