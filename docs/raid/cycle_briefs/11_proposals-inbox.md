# Cycle 11: Pending Proposals inbox (FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** A **Pending Proposals** inbox that **aggregates exactly 3 existing sources** read-only + deep-links to each one's own review UI: (1) glossary **ai-suggested drafts** (`?status=draft&tags=ai-suggested`), (2) **AI wiki stubs**, (3) **lore-enrichment proposals** (`/proposals?review_status=proposed|author_reviewing`). **INTEGRATE, do not duplicate** — NO new in-knowledge review system; each row deep-links to the source's existing review surface. Rendered inside the C6 project-detail shell scoped by route (G6).
- **Acceptance gate:** `scripts/raid/verify-cycle-11.sh` exits 0
- **Top 3 LOCKED decisions consumed:** C11-proposals-inbox, Curation-flywheel-integrate, G6
- **DPS count:** 2
- **Estimated wall time:** 4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C8
- Files expected to exist (grep-able paths): glossary drafts list endpoint (`?status=draft&tags=ai-suggested`); the AI wiki stubs source; lore-enrichment `/proposals?review_status=...` endpoint; the C6 project-detail shell + its Proposals sub-tab slot; each source's existing review UI route (deep-link targets).

## Scope (IN)
- **FE aggregation** — fetch + unify the 3 sources into a single Proposals inbox list (read-only): glossary ai-suggested drafts · AI wiki stubs · lore-enrichment proposals (`review_status=proposed|author_reviewing`).
- **FE deep-links** — each row links out to that source's **existing** review UI (glossary draft review · wiki review · lore-enrichment proposal review). No in-place approve/reject.
- Source labels / counts per origin so the user knows which queue a row belongs to.
- Rendered inside the **C6 project-detail shell** Proposals sub-tab, scoped by route (G6).
- `scripts/raid/verify-cycle-11.sh` (acceptance gate, runner creates it).

## Scope (OUT — explicitly)
- **NO new review/approve system in knowledge-service** — read-only aggregation + deep-link ONLY (integrate, don't duplicate).
- **NO 4th source** — exactly the 3 named sources.
- **NO new BE proposal store / schema** — consume existing endpoints.
- No gap-report logic (C10); no promote-flow changes (C9); no semantic-layer changes (C8).
- No in-row mutation (approve/reject/edit) — that happens in each source's own UI.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: the inbox merges all 3 sources into one list; each row carries its origin + a correct deep-link URL; empty-source handling (one source returns nothing) degrades gracefully.
- Lints pass: provider-gate green; no new BE write surface.
- Integration smoke: **verify (FE)** — the inbox unifies the 3 sources and each row deep-links to its existing review UI. Evidence = a **Playwright screenshot** of the unified inbox (rows from ≥2 sources visible) + a deep-link landing on a source review UI. (Not flagged cross-service; FE-only — Playwright screenshot smoke.)

## DPS parallelism plan
- DPS 1: FE — the 3 source-fetch adapters (glossary ai-suggested drafts · wiki stubs · lore-enrichment proposals) + a normalized row model with origin + deep-link URL (return budget: 1500 tokens summary).
- DPS 2: FE — the inbox list UI (unified rows, origin labels/counts, empty-state, deep-link navigation), route-scoped in the C6 shell.
- Serial tail (Raid Leader): Playwright screenshot smoke (≥2 sources + a deep-link landing) + `verify-cycle-11.sh`.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Duplication:** any in-knowledge approve/reject/edit control — violates integrate-don't-duplicate; the inbox is read-only + deep-link.
- **Wrong source query:** glossary must filter `status=draft&tags=ai-suggested`; lore-enrichment must filter `review_status=proposed|author_reviewing` — a too-broad query pulls non-proposal rows.
- **Broken / wrong deep-links:** a row that links to the wrong review UI or a dead route — the deep-link is the whole value.
- **One-source-down breaks the inbox:** a failing source must degrade gracefully (show the others), not blank the whole list.
- **New BE store:** any new proposal table/endpoint in knowledge-service — must consume existing sources only.
- **Route-scoping:** uses the route `projectId` (G6), not a project select-box.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (3-source aggregation, origin labels, deep-links, read-only, route-scoped).
- No OUT items touched (no new review system, no 4th source, no new BE schema, no in-row mutation).
- All acceptance criteria met incl. Playwright screenshot.
- Cross-cycle invariants not violated: integrate-don't-duplicate, exactly-3-sources, G6 route-scoping.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — C11 row (Pending Proposals inbox) + the "Curation flywheel = INTEGRATE, don't duplicate" note.
- OPEN_QUESTIONS_LOCKED.md — **C11 Proposals inbox** lock, **Curation flywheel = INTEGRATE, don't duplicate**, **G6**.
- `docs/specs/2026-06-13-knowledge-design-vs-impl-gap.md` — proposals-inbox gap (design §4).
- `docs/specs/2026-06-13-knowledge-service-standalone-ux-review.md` — proposals-inbox UX (3 sources + deep-link).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **C11 LOCKED:** aggregate **exactly 3 sources** (glossary ai-suggested drafts · AI wiki stubs · lore-enrichment proposals) **read-only + deep-link** — no in-knowledge review system.
- 🔴 **INTEGRATE, do not duplicate:** each row deep-links to its source's **existing** review UI; NO approve/reject/edit in the inbox, NO new BE proposal store.
- 🔴 **Source filters:** glossary `status=draft&tags=ai-suggested`; lore-enrichment `review_status=proposed|author_reviewing`. Graceful degrade if one source is down.
- 🔴 **Acceptance MUST include:** a Playwright screenshot of the unified inbox (≥2 sources) + a deep-link landing on a source review UI (FE-only smoke).
- 🔴 **Do NOT touch:** gap report (C10), promote flow (C9), semantic layer (C8); no 4th source.
- 🔴 **Fresh session reminder:** this is a new `/raid 11` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
