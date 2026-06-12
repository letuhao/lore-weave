# Cycle 10: Glossary Gap Report (BE-thin + FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Wire knowledge-service's existing **`find_gap_candidates()`** as `GET /projects/{id}/gaps?min_mentions=&limit=` — **entity gaps** (high-mention discovered entity with **no** glossary entry). This is **distinct** from lore-enrichment's attribute-dimension `detect-gaps` (entity missing a `history` field) — different query, do NOT merge. FE: gap summary cards + a `min_mentions` threshold control + **bulk-promote** (sequential, **reuses the C9 single-promote** — no batch endpoint) with a progress indicator. Rendered inside the C6 project-detail shell scoped by route (G6).
- **Acceptance gate:** `scripts/raid/verify-cycle-10.sh` exits 0
- **Top 3 LOCKED decisions consumed:** C10-gap-report, Two-distinct-gap-concepts, G6
- **DPS count:** 2
- **Estimated wall time:** 4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C9
- Files expected to exist (grep-able paths): knowledge-service `find_gap_candidates()` (already ready per the lock); the C9 single-promote orchestration (glossary draft-create → link-to-glossary) — bulk-promote reuses it; the C6 project-detail shell.

## Scope (IN)
- **BE (thin)** — wire `GET /projects/{id}/gaps?min_mentions=&limit=` over the existing `find_gap_candidates()` (entity gaps: high-mention, no glossary entry). Pass-through params; no new gap engine.
- **FE** — gap-report **summary cards** + a `min_mentions` **threshold** control + a `limit` control.
- **FE bulk-promote** — **sequential** calls that **reuse the C9 single-promote** flow (draft-create → link-to-glossary), with a **progress indicator**. NO batch endpoint.
- Rendered inside the **C6 project-detail shell** scoped by route (G6).
- `scripts/raid/verify-cycle-10.sh` (acceptance gate, runner creates it).

## Scope (OUT — explicitly)
- **NO merge with lore-enrichment `detect-gaps`** — that is attribute-dimension gaps (missing `history`); this is **entity** gaps. Different query; keep separate.
- **NO new gap engine / scoring** — reuse `find_gap_candidates()` as-is.
- **NO batch-promote endpoint** — bulk-promote is sequential C9 calls.
- No proposals inbox aggregation (C11); no semantic-layer changes (C8); no promote-flow changes (C9, only reuse).
- No timeline / build-wizard work.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `GET /projects/{id}/gaps` returns high-mention/no-glossary candidates; `min_mentions` + `limit` params honored; bulk-promote invokes the C9 single-promote sequentially and reports progress.
- Lints pass: provider-gate green.
- Integration smoke: **verify (FE)** — the report lists high-value entity gaps; bulk-promote moves them to glossary **drafts** (via C9). Evidence = a **Playwright screenshot** of the gap report + a post-bulk-promote state showing the selected gaps became glossary drafts. (Not flagged cross-service in the decomposition; thin-BE + FE — Playwright screenshot smoke.)

## DPS parallelism plan
- DPS 1: BE (thin) — wire `GET /projects/{id}/gaps?min_mentions=&limit=` over `find_gap_candidates()` + a route test (return budget: 1500 tokens summary).
- DPS 2: FE — summary cards + threshold/limit controls + bulk-promote (sequential, reuses C9) + progress indicator, route-scoped in the C6 shell.
- Serial tail (Raid Leader): Playwright screenshot smoke + `verify-cycle-10.sh`.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Gap-concept conflation:** any code that routes this through lore-enrichment `detect-gaps` (attribute gaps) instead of `find_gap_candidates()` (entity gaps) — a LOCKED violation; the two must stay separate queries.
- **Bulk-promote NOT reusing C9:** a re-implemented promote (or a new batch endpoint) instead of sequential C9 single-promote calls — duplicates logic + risks divergence.
- **No progress / partial-failure handling:** bulk-promote over N gaps must show progress and survive one failed item without aborting the rest (or clearly report which failed).
- **Threshold not wired:** `min_mentions` control that doesn't actually pass through to the BE query.
- **Route-scoping:** must use the route `projectId` (G6), not a project select-box.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (gaps endpoint over find_gap_candidates, summary cards, threshold, sequential bulk-promote reusing C9).
- No OUT items touched (no detect-gaps merge, no new gap engine, no batch endpoint).
- All acceptance criteria met incl. Playwright screenshot.
- Cross-cycle invariants not violated: two-distinct-gap-concepts kept separate, bulk-promote reuses C9, G6 route-scoping.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — C10 row (Glossary Gap Report) + the "two-distinct-gap-concepts" note.
- OPEN_QUESTIONS_LOCKED.md — **C10 Gap Report** lock, **Two distinct "gap" concepts — keep separate**, **G6**.
- `docs/specs/2026-06-13-knowledge-design-vs-impl-gap.md` — Gap Report gap (design §4).
- `docs/specs/2026-06-13-knowledge-service-standalone-ux-review.md` — gap-report UX (summary cards, bulk-promote).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **C10 Gap Report LOCKED:** wire `GET /projects/{id}/gaps?min_mentions=&limit=` over **`find_gap_candidates()`** (entity gaps: high-mention, **no** glossary entry).
- 🔴 **Two distinct gap concepts — KEEP SEPARATE:** this is NOT lore-enrichment's attribute-dimension `detect-gaps` (missing `history`). Different query; do not merge.
- 🔴 **Bulk-promote = sequential C9 calls** (reuse the single-promote) with a progress indicator — NO batch endpoint, no re-implemented promote.
- 🔴 **Acceptance MUST include:** a Playwright screenshot of the gap report + post-bulk-promote glossary-draft state (thin-BE + FE smoke).
- 🔴 **Do NOT touch:** proposals inbox (C11), semantic layer (C8), promote flow internals (C9 — reuse only), timeline (C14).
- 🔴 **Fresh session reminder:** this is a new `/raid 10` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
