# Cycle 16: Work-setup resilience (BE composition)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Make **"Set up co-writer"** survive a degraded knowledge-service. Today `POST /work` calls `knowledge.create_project` and a failure bubbles a **502**, wall-blocking the writer. This cycle makes `create_project` failure **non-fatal for greenfield (non-derivative) works**: the Work is created with a **lazy / null `project_id`**, and grounding **degrades gracefully** (packer FTS fallback, advisory empty grounding) rather than aborting setup. The writer can still draft + Generate. **Cross-service** — carries a real live-smoke (knowledge down → `POST /work` succeeds → Generate returns prose). BE composition-only.
- **Acceptance gate:** `scripts/raid/verify-cycle-16.sh` exits 0
- **Top 3 LOCKED decisions consumed:** WG-3, writer-not-hard-blocked, G2-derivative-distinction
- **DPS count:** 2
- **Estimated wall time:** 4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: none
- Files expected to exist (grep-able paths): composition-service `POST /work` setup handler + its `knowledge.create_project` call site; the packer's grounding-retrieval path (FTS fallback already present).

## Scope (IN)
- `POST /work` setup path: wrap `knowledge.create_project` so a failure (timeout / 5xx / down) does **NOT** 502. On failure, persist the Work with `project_id = NULL` (lazy creation) and a marker so a later setup retry can backfill the project.
- Grounding degradation: packer / grounding read tolerates a null `project_id` for a **non-derivative** Work → empty-but-valid grounding (FTS fallback), Generate still returns prose.
- A retry/backfill seam so `project_id` can be created later when knowledge recovers (no orphaned permanent null required, but null must be a valid runtime state).
- `scripts/raid/verify-cycle-16.sh` (acceptance gate — the runner creates it) + the live-smoke evidence artifact.

## Scope (OUT — explicitly)
- **Derivative works keep `project_id` NOT NULL (C23 GUARD).** This cycle's null is ONLY for **non-derivative greenfield** works — do NOT relax the derivative invariant (the knowledge timeline endpoint widens to ALL projects on null → cross-project grounding leak). Keep the two paths distinct.
- No FE changes — C15 already signposts empty grounding; this is pure BE resilience.
- No knowledge-service code changes — this cycle tolerates knowledge being down, it does not fix knowledge.
- No new grounding/retrieval algorithm — reuse the existing FTS fallback.
- No subgraph/graph work (C18/C19).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `scripts/raid/verify-cycle-16.sh` exits 0 — asserts (1) `POST /work` returns 2xx (NOT 502) when `knowledge.create_project` raises, (2) the resulting Work has `project_id = NULL` for a non-derivative work, (3) a **derivative** work with null `project_id` is still **rejected** (C23 guard intact), (4) packer tolerates null project_id → empty grounding, no exception.
- Lints pass: composition-service lint/format + type check.
- Integration smoke: **live-smoke (cross-service, REQUIRED)** — stack up, take knowledge-service down (or fault-inject create_project) → `POST /work` succeeds → Generate returns prose. Evidence string MUST contain `live smoke: knowledge down → POST /work 2xx → Generate returns prose`.

## DPS parallelism plan
- DPS 1: `POST /work` resilience — try/except around `knowledge.create_project`, null `project_id` persistence + backfill marker, derivative-vs-greenfield branch (return budget: 1500 tokens summary).
- DPS 2: packer/grounding null-project tolerance + the live-smoke harness (fault-inject knowledge, assert prose returns).

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Mock-only false-green:** unit pass but no real cross-service call ran — confirm the live-smoke token reflects a genuine knowledge-down → `POST /work` round-trip, not a mock.
- **Derivative leak:** any code path that now lets a **derivative** Work be created with null `project_id` — that re-opens the C23 timeline cross-project grounding leak. The relaxation must be greenfield-only.
- **Silent swallow:** catching the `create_project` error so broadly it hides genuine bugs (e.g. auth/validation 4xx) — only down/timeout/5xx should degrade; a 4xx contract error should still surface.
- **Null-deref downstream:** packer / grounding code that assumes a non-null project_id and NPEs on the new null state.
- **Orphan correctness:** a null project_id that can never be backfilled → permanently grounding-blind Work; ensure a retry/backfill seam exists.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (non-fatal create_project, null project_id for greenfield, grounding tolerance, backfill seam)
- No OUT items touched (derivative NOT-NULL invariant intact; no FE; no knowledge-service edits)
- All acceptance criteria met; `verify-cycle-16.sh` exits 0 + live-smoke token present
- Cross-cycle invariants not violated (C23 derivative project_id NOT NULL guard)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: `docs/plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md` — C16 (Work-setup resilience, WG-3) + the C23 derivative NOT-NULL guard note.
- LOCKED: `docs/plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md` — writer-not-hard-blocked; Architecture-review GUARD (derivative project_id NOT NULL).
- Spec: `docs/specs/2026-06-13-writer-core-flow-P0.md` (WG-3), `docs/specs/2026-06-13-writer-persona-use-cases-scenarios.md`.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** WG-3 → `POST /work` must NOT 502 when `knowledge.create_project` fails; persist lazy/null `project_id` and degrade grounding.
- 🔴 **Top LOCKED 2:** GUARD → null `project_id` is **greenfield-only**; derivative works stay NOT NULL (else cross-project grounding leak). Keep the branch explicit.
- 🔴 **Top LOCKED 3:** Grounding degrades gracefully (FTS fallback) — Generate still returns prose on a null/empty project.
- 🔴 **Acceptance MUST include:** live-smoke token `live smoke: knowledge down → POST /work 2xx → Generate returns prose` (cross-service rule) — mock-only is a false-green.
- 🔴 **Do NOT touch:** knowledge-service code, FE Compose (C15), C23 derivative schema/guard.
- 🔴 **Fresh session reminder:** this is a new `/raid 16` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
