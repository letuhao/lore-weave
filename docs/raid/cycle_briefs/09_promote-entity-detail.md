# Cycle 9: Promote + entity detail (BE+FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Wire the **promote flow** + the **entity-detail** panel. Promote a *discovered* entity → FE orchestrates two calls: (1) create a glossary **draft** entity (`status=draft`, tag `ai-suggested`) from the discovered entity's name/kind/aliases via glossary's extract-entities/create; (2) knowledge `POST /entities/{id}/link-to-glossary` to **anchor** (`anchor_score=1.0`). Promote creates a **draft**, NOT active — the human reviews it in glossary. Entity detail shows a **facts list** (existing endpoint) + relations + an **unpin** toggle (`is_pinned_for_context`) + the promote action. Provenance MVP = facts list + `source_chapter`; full passage-trail deferred.
- **Acceptance gate:** `scripts/raid/verify-cycle-9.sh` exits 0
- **Top 3 LOCKED decisions consumed:** C9-promote-flow, Curation-flywheel-integrate, G6
- **DPS count:** 3
- **Estimated wall time:** 5h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C8
- Files expected to exist (grep-able paths): knowledge-service entities route with the C8 `status` derivation + semantic layer; the C6 project-detail shell; the existing knowledge `POST /entities/{id}/link-to-glossary` route (wire it); the existing entity facts endpoint; glossary's extract-entities/create draft path.

## Scope (IN)
- **FE promote flow** — orchestrate two calls in order: (1) create glossary **draft** entity (`status=draft`, tag `ai-suggested`) from the discovered entity (name/kind/aliases); (2) knowledge `POST /entities/{id}/link-to-glossary` → anchor `anchor_score=1.0`. Surface success → entity now reads `canonical`.
- **BE** — ensure `POST /entities/{id}/link-to-glossary` is wired/usable (anchor: set `glossary_entity_id` + `anchor_score=1.0`).
- **FE entity detail** — **facts list** (existing endpoint) + `source_chapter` provenance + relations + **unpin** toggle (`is_pinned_for_context`) + the promote button (only for `discovered`).
- Rendered inside the **C6 project-detail shell** scoped by route (G6).
- `scripts/raid/verify-cycle-9.sh` (acceptance gate, runner creates it).

## Scope (OUT — explicitly)
- **NO new in-knowledge review system** — promote creates a glossary **draft** the human reviews IN glossary (integrate, don't duplicate).
- **NO bulk-promote / gap report** — that is C10 (which *reuses* this single-promote).
- **NO proposals inbox** aggregation — that is C11.
- **NO full passage-trail provenance** — MVP is facts list + `source_chapter` only (deferred).
- Do not make promote create an **active** glossary entity — it MUST be a draft.
- No relationship/event override work (dị bản, C25+).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: promote-orchestration test (draft-create then link-to-glossary, in order); link-to-glossary anchors (`glossary_entity_id` set + `anchor_score=1.0`); unpin toggles `is_pinned_for_context`; entity-detail renders facts + relations.
- Lints pass: provider-gate green; no hardcoded model.
- Integration smoke: **live smoke (cross-service, REQUIRED)** — promote a discovered entity → a glossary **draft** is created (tag `ai-suggested`) AND the knowledge entity becomes **anchored/canonical**. Evidence string contains `live smoke: promote discovered entity -> glossary draft created + entity anchored`. Plus a **Playwright screenshot** of the entity-detail panel (facts + promote + unpin) and the post-promote canonical state.

## DPS parallelism plan
- DPS 1: BE — verify/wire `POST /entities/{id}/link-to-glossary` anchoring (`glossary_entity_id` + `anchor_score=1.0`) (return budget: 1500 tokens summary).
- DPS 2: FE — promote orchestration (glossary draft-create → link-to-glossary) + success/canonical refresh.
- DPS 3: FE — entity-detail panel (facts list + `source_chapter` + relations + unpin toggle + promote button gating).
- Serial tail (Raid Leader): cross-service live-smoke (real promote → draft + anchor) + Playwright screenshot + `verify-cycle-9.sh`.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Promote creates ACTIVE instead of draft** — the lock requires a **draft** (`status=draft`, tag `ai-suggested`); active is a violation.
- **Call ordering / partial failure:** draft created but link-to-glossary fails (or vice-versa) → orphaned draft or unanchored entity. Confirm error handling + idempotency / no double-draft on retry.
- **Mock-only false-green:** promote "works" but no real glossary draft was created on a stacked-up service — confirm the live-smoke token reflects a real cross-service round-trip.
- **Duplicate review surface:** any new in-knowledge approval UI duplicates the glossary review queue — violates integrate-don't-duplicate.
- **Unpin wired to wrong field:** must toggle `is_pinned_for_context`, not delete/archive.
- **Over-scoped provenance:** building a full passage-trail (deferred) instead of facts + `source_chapter`.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (two-call promote, draft+anchor, entity detail facts/relations/unpin/promote).
- No OUT items touched (no bulk-promote, no gap report, no proposals, no new review system, no active-entity promote).
- All acceptance criteria met incl. live-smoke token + Playwright shot.
- Cross-cycle invariants not violated: promote = draft, integrate-don't-duplicate, G6 route-scoping.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — C9 row (Promote + entity detail) + cross-service live-smoke note.
- OPEN_QUESTIONS_LOCKED.md — **C9 promote flow** lock, **Curation flywheel = INTEGRATE, don't duplicate**, **G6**.
- `docs/specs/2026-06-13-knowledge-design-vs-impl-gap.md` — promote/anchor + entity-detail gap (design entity-detail).
- `docs/specs/2026-06-13-knowledge-service-standalone-ux-review.md` — entity-detail UX (facts, unpin, promote).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **C9 promote LOCKED:** promote = (1) create glossary **DRAFT** (`status=draft`, tag `ai-suggested`) then (2) `POST /entities/{id}/link-to-glossary` to anchor (`anchor_score=1.0`). Draft, **never active** — human reviews in glossary.
- 🔴 **Integrate, don't duplicate:** NO new in-knowledge review system — promote feeds the existing glossary review queue.
- 🔴 **Unpin = `is_pinned_for_context` toggle**; provenance MVP = facts list + `source_chapter` (full passage-trail deferred).
- 🔴 **Acceptance MUST include:** the cross-service live-smoke token `live smoke: promote discovered entity -> glossary draft created + entity anchored` (real call) + a Playwright screenshot.
- 🔴 **Do NOT touch:** bulk-promote/gap report (C10), proposals inbox (C11), build wizard (C12/C13), timeline (C14).
- 🔴 **Fresh session reminder:** this is a new `/raid 9` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
