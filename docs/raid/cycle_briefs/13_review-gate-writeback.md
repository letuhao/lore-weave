# Cycle 13: Review gate + write-back (H0)

> Proposal review API + the H0 write-back boundary: enriched proposals enter the
> KG **quarantined** (`source_type='enriched'`, NOT canon); only the author's
> explicit PROMOTE canonizes them, keeping a permanent origin marker. Retraction
> rides the glossary recycle-bin. This is the cycle where H0 is enforced for real.

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Build the proposal review API on `lore-enrichment-service` — list / `approve` / `reject` / `edit` plus the author-only `promote` endpoint, mirroring knowledge-service `pending_facts` (confirm/reject + injection-defense + confidence/quarantine). Write-back goes **through the glossary SSOT** (`POST /books/{id}/extract-entities` + wiki via D4-03), entering the KG as `source_type='enriched'` + `pending_validation=true` + `confidence<1.0` (quarantined). PROMOTE flips it to canon while **retaining** `origin='enrichment'` + `promoted_from_proposal_id/by/at` + `original_technique`. Retraction routes through the glossary recycle-bin (M6).
- **Acceptance gate:** `scripts/raid/verify-cycle-13.sh` exits 0 (this runner creates that script).
- **Top 3 LOCKED decisions consumed:** H0, Q1, Q2.
- **DPS count:** 3
- **Estimated wall time:** 5–7 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C4, C5, C12
- Files expected to exist (grep-able paths):
  - `services/lore-enrichment-service/app/clients/` (KG-read + glossary write port, C1)
  - `services/lore-enrichment-service/migrations/` with `enrichment_proposal` + H0 columns `origin`, `review_status`, `promoted_entity_id/by/at` (C2)
  - `contracts/api/lore-enrichment/` OpenAPI incl. promote endpoint stub (C3)
  - glossary `glossary.entity_updated` event + knowledge-service `glossary_sync`→Neo4j consumer (C4)
  - D4-03 wiki-from-KG body renderer carrying `source_type` (C5)
  - canon-verify + injection-defense at proposal creation (C12)

## Scope (IN)
- Review API on `lore-enrichment-service`: `GET /proposals` (filter by `review_status`, scope), `POST /proposals/{id}/approve`, `/reject`, `/edit` (author edits before promote), `/promote`.
- Lifecycle state machine wiring: `proposed → author_reviewing → approved → promoted | rejected`. Only `approved` is promotable; illegal transitions rejected.
- **Author authorization:** only the book/project owner may `promote` (demo principal = `claude-test@loreweave.dev`); enforce via book-service ownership read, not a self-asserted claim.
- **Write-back (quarantine):** on approve/promote-stage, write entity+facts through glossary SSOT (`extract-entities` bulk + wiki). Tag every fact `source_type='enriched'` (or `enriched:<technique>`), `pending_validation=true`, `confidence<1.0`. C4 sync carries it to Neo4j as quarantined.
- **Promotion (canonization):** PROMOTE flips `source_type`→`glossary`, `confidence`→1.0, `pending_validation`→false BUT persists permanent origin marker (`origin='enrichment'`, `promoted_from_proposal_id`, `promoted_by`, `promoted_at`, `original_technique`).
- **Retraction (M6):** retract path routes the promoted/quarantined entity to the glossary recycle-bin (soft-delete), reversible; proposal `review_status` updated to reflect retraction.
- Idempotency on promote/write-back (re-call with same proposal_id is a no-op, not a duplicate canon entity).
- `scripts/raid/verify-cycle-13.sh` (live-smoke driver) + service tests.

## Scope (OUT — explicitly)
- NO job orchestration / Redis-Streams runner (that is C14).
- NO eval framework or quality gate (C15); do not touch `tests/quality/` judge files or `eval/` climate/geo suites.
- NO direct Neo4j canonical writes — write only through glossary SSOT (Q2). Enrichment never mutates Neo4j content directly.
- NO new generation/strategy logic (C9–C11); consume existing proposals only.
- NO edits to `world-service` / `game-server` / `tilemap` / `infra/existing-prod/`.
- NO hardcoded model names — any LLM/embedding use resolves via provider-registry.
- NO auto-promotion / auto-admit thresholds (default = always human-gate).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `services/lore-enrichment-service/tests/` review-gate + lifecycle + authz + idempotency suite (incl. illegal-transition + non-owner-promote-denied + origin-marker-persists-after-promote).
- Lints pass: service lint/typecheck; OpenAPI spec for the 5 review routes lints clean.
- **Live-smoke token (REQUIRED — cross-service, CLAUDE.md VERIFY rule):** `live smoke: propose → enriched-in-KG (quarantined, source_type=enriched) → author promote → canon (source_type=glossary, origin marker intact) → retract → recycle-bin` against a running glossary + knowledge-service + book-service stack. If full stack not bootable: `LIVE-SMOKE deferred to D-C13-LIVE-SMOKE` or `live infra unavailable: <reason>`.
- H0 negative gate: a non-promoted proposal NEVER appears as `source_type='glossary'`/confidence=1.0 in glossary or Neo4j.

## DPS parallelism plan
- DPS 1: Review API + lifecycle state machine + authz (handlers, state transitions, owner-check via book-service read). Files: `app/api/proposals*`, `app/services/review*`, tests. (return budget: 1500 tokens summary)
- DPS 2: Write-back + promotion adapters — glossary SSOT calls (extract-entities + wiki/D4-03), source_type/confidence tagging, origin-marker persistence, idempotency. Files: `app/services/writeback*`, `app/clients/glossary*`, tests. (return budget: 1500 tokens summary)
- DPS 3: Retraction (M6 recycle-bin) + `scripts/raid/verify-cycle-13.sh` live-smoke driver + cross-service smoke fixtures. (return budget: 1500 tokens summary)

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **H0 leak (PRIMARY):** can any code path write enriched content as `source_type='glossary'` / confidence=1.0 / `pending_validation=false` WITHOUT an explicit author promote? Check approve vs promote separation; check default column values on write-back.
- **Permanent origin marker:** does promotion REALLY retain `origin='enrichment'` + `promoted_from_proposal_id/by/at` + `original_technique`, or is it only in audit/change-history (locked: must be on the entity for lifetime traceability)?
- **Authz bypass:** is owner-check sourced from book-service truth, or trusting a client-supplied user_id? Can a non-owner promote? Per-user/per-project scoping (Q3) enforced on list/edit too?
- **Mock-only false-green:** are the cross-service calls (glossary extract-entities, C4 sync→Neo4j, C5 wiki) exercised against a real stack in the live-smoke, or only mocked? Mock-only repeatedly hid cross-service contract bugs.
- **Idempotency / dup canon:** does re-calling promote create a second entity or double-write to Neo4j?
- **Injection-defense:** is the C12 injection neutralization preserved at write-back time (untrusted enriched text never executed as instructions to glossary/LLM)?
- **Retraction reversibility:** does recycle-bin retraction actually soft-delete (reversible) and propagate via C4 sync, not hard-delete canon?
- **Hardcoded model names:** any model id literal in write-back/wiki rendering instead of provider-registry resolution?

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All 5 review routes (list/approve/reject/edit/promote) + retraction present; lifecycle state machine enforced.
- No OUT items touched (no Neo4j direct write, no C14 orchestration, no eval/climate files, no prod-isolation breach).
- H0 invariant intact: enriched enters quarantined; only author-promote canonizes; origin marker persists.
- Live-smoke token present in VERIFY evidence (or explicit deferral row).
- Cross-cycle invariants (Q1 mirror-pending_facts, Q2 glossary-SSOT-only, Q3 scoping) not violated.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle decomposition (C13 row + H0 invariant note): [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)
- Locked decisions (full list): [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md) — H0, Q1, Q2, Q3, Q6, posture (promotion authority).
- Plan + clarify ground truth: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md) · [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- LOCKED decisions consumed (full list): H0, Q1, Q2, Q3, Q6, Q-R1, promotion-authority posture, retrieval/eval isolation.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **H0 (CORE):** enriched ≠ canon. Write-back enters KG `source_type='enriched'` + `pending_validation=true` + `confidence<1.0` (quarantined). ONLY author PROMOTE canonizes → `source_type='glossary'`, confidence=1.0, BUT permanent origin marker (`origin='enrichment'` + `promoted_from_proposal_id/by/at` + `original_technique`) MUST remain.
- 🔴 **Q2:** write through glossary SSOT only (`extract-entities` + wiki); `glossary_sync` (C4) propagates to Neo4j. NEVER write Neo4j canonical content directly.
- 🔴 **Promotion authority + Q1:** only the book/project owner (demo = `claude-test@loreweave.dev`) may promote; verify via book-service ownership, not a client claim. Mirror pending_facts (confirm/reject + injection-defense + quarantine).
- 🔴 **Acceptance MUST include:** the cross-service live-smoke token `live smoke: propose → enriched-quarantined → promote → canon → retract`. Unit-green alone fails VERIFY; mock-only hides contract bugs.
- 🔴 **Do NOT touch:** Neo4j direct writes, C14 orchestration, `tests/quality/` + `eval/` climate/geo files, `world-service`/`game-server`/`infra/existing-prod/`; no hardcoded model names.
- 🔴 **Fresh session reminder:** this is a new `/raid 13` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
