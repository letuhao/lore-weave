# Cycle 5: Build-graph gates unblock (FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Unblock the knowledge graph-build flow in `BuildGraphDialog`. Two FE gates: (1) when the project has **no embedding model** (or no app/LLM model) resolved, show an in-flow **`AddModelCta`** (from C0) that deep-links to model registration and returns to the dialog instead of a dead-end; (2) promote the **golden-set benchmark** from a hidden/implicit precondition to a **visible inline gate** — an unbenchmarked project shows a "Run benchmark" step, and only a passing benchmark enables the Confirm/Build button. This is the real build-graph blocker per the LOCKED diagnosis (embedding + benchmark, NOT rerank). No backend change — wire to existing model-resolution + benchmark endpoints.
- **Acceptance gate:** `scripts/raid/verify-cycle-5.sh` exits 0
- **Top 3 LOCKED decisions consumed:** Diagnosis-correction (build blocker = embedding+benchmark), KN-1/BL-16, no-hardcoded-model-names
- **DPS count:** 2
- **Estimated wall time:** 3h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0
- Files expected to exist (grep-able paths): `frontend/src/features/knowledge/components/BuildGraphDialog.tsx` (the build dialog); the reusable `AddModelCta` component shipped by C0 (grep `AddModelCta`)

## Scope (IN)
- `BuildGraphDialog`: detect empty embedding-model / empty chat-LLM-model state → render the C0 `AddModelCta` **inline in the dialog flow** (deep-link out to register a model, return to the dialog with the selection applied). No raw "go to settings" dead-end.
- Promote **golden-set benchmark** to a **visible inline gate**: surface benchmark status; when unbenchmarked, show a "Run benchmark" action; Confirm/Build stays disabled until a passing benchmark exists.
- Disabled-state messaging that names the missing precondition (no embedding model / not benchmarked) so the user knows exactly what to do.
- `scripts/raid/verify-cycle-5.sh` (acceptance gate) + a Playwright MCP screenshot of the no-embedding CTA and the post-benchmark enabled Confirm.

## Scope (OUT — explicitly)
- **NO backend changes** — embedding resolution + benchmark endpoints already exist; this cycle only wires the FE gates.
- **NOT rerank** — rerank is C1–C3 grounding-quality, explicitly NOT a build-graph precondition (LOCKED diagnosis).
- NOT the project-detail shell / browser IA (that is C6/C7); NOT the entities/timeline tabs (C8/C14).
- No new model-registration UI — reuse C0's `AddModelCta` round-trip; do not duplicate the register form.
- No changes to `BuildGraphDialog`'s actual extraction-start contract (targets/concurrency/pinning are C12/C13).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `frontend` unit tests for `BuildGraphDialog` gate logic — no-embedding ⇒ CTA shown + Build disabled; unbenchmarked ⇒ Build disabled; benchmark-pass ⇒ Build enabled.
- Lints pass: `npm run lint` (frontend) clean on touched files.
- Integration smoke: Playwright MCP — open BuildGraphDialog on a project with no embedding model ⇒ `AddModelCta` visible; run benchmark ⇒ Confirm enables. Screenshot filed with this brief.

## DPS parallelism plan
- DPS 1: embedding/LLM empty-state detection + inline `AddModelCta` wiring + disabled messaging (worktree: `BuildGraphDialog.tsx`, its hook). (return budget: 1500 tokens summary)
- DPS 2: benchmark inline gate — status surfacing, "Run benchmark" action, Confirm-enable predicate (same dialog; coordinate on the shared disabled-state predicate, integrate last).

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Wrong blocker:** any gate that treats **rerank** as a build precondition — violates the LOCKED diagnosis. Only embedding + benchmark gate the build.
- **Dead-end CTA:** an `AddModelCta` that navigates away without a return path / without applying the newly-registered model back into the dialog.
- **Hardcoded model name:** any literal embedding/LLM model string baked into the dialog instead of resolved from provider-registry state.
- **Enable-too-early:** Confirm enabled while benchmark is unrun/failing, or while embedding is still empty.
- **Duplicated register UI:** re-implementing model registration instead of reusing C0's `AddModelCta`.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (inline CTA on empty-model, visible benchmark gate, Confirm-enable predicate)
- No OUT items touched (no BE change, no rerank gate, no shell/browser IA, no extraction-contract change)
- All acceptance criteria met (`verify-cycle-5.sh` exits 0; Playwright screenshot filed)
- Cross-cycle invariants not violated (no hardcoded model names; AddModelCta reused not duplicated)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — **C5** row (Build-graph gates unblock; verify: no-embedding → CTA; unbenchmarked → run-benchmark → Confirm enables).
- OPEN_QUESTIONS_LOCKED.md — Diagnosis-correction lock (build blocker = embedding + golden-set benchmark, not rerank).
- `docs/specs/2026-06-13-knowledge-service-standalone-ux-review.md` — KN-1.
- `docs/specs/2026-06-13-knowledge-design-vs-impl-gap.md` — build-wizard precondition gaps (BL-16).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** Diagnosis-correction → the build-graph blocker is **embedding model + golden-set benchmark**, NOT rerank. Gate ONLY on those two.
- 🔴 **Top LOCKED 2:** KN-1/BL-16 → empty-model must offer an in-flow `AddModelCta` round-trip, not a dead-end; benchmark must be a **visible inline gate**.
- 🔴 **Top LOCKED 3:** No hardcoded model names → resolve embedding/LLM identity from provider-registry state, never a literal string in the dialog.
- 🔴 **Acceptance MUST include:** Playwright MCP screenshot of (no-embedding → CTA) AND (run-benchmark → Confirm enabled); `verify-cycle-5.sh` exits 0.
- 🔴 **Do NOT touch:** rerank as a precondition; the C6 detail shell / C7 browser IA; the extraction start contract (targets/concurrency/pinning = C12/C13); backend.
- 🔴 **Fresh session reminder:** this is a new `/raid 5` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
