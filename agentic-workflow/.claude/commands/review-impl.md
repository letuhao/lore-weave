---
description: On-demand adversarial implementation review. Invoke when POST-REVIEW needs a deeper look or after COMMIT when something feels off.
---

# /review-impl — Adversarial implementation review

Perform a deep adversarial review of the most recent implementation work. This is the **separate mental mode** that POST-REVIEW deliberately does NOT do (see Phase 9 note in `WORKFLOW.md`).

## Scope

Review whatever the user is currently focused on. If `$ARGUMENTS` names a task or ticket (e.g. `K17.9`, `PROJ-421`), scope to that task's files. Otherwise scope to the changes in the latest commit (`git show --stat HEAD`).

## How this differs from the REVIEW-CODE phase (Phase 7)

| Phase 7 REVIEW-CODE | `/review-impl` |
|---|---|
| "Does the code implement the design? Are the patterns clean?" | "What does the test coverage **miss**? What could break that nothing currently guards against?" |
| Focus on the code as written | Focus on the *surface area the code leaves exposed* |
| 2-stage: spec compliance + code quality | 1-stage: coverage gaps + drift risk + adjacent correctness |

## Mental mode — required before starting

Before reading any file, list in your head:
1. **Every field on every input model** — which ones does the implementation actually persist/act on, and which are silently dropped?
2. **Every normalization step upstream** — does any of them make a downstream defense moot? (e.g., a whitespace-stripping normalizer that runs *before* a whitespace-sensitive sanitizer)
3. **Every invariant the implementation claims** — idempotence, ordering, dedup keys — and whether a future change could break them without a test catching it
4. **Every boundary between this code and its callers/callees** — what contract is assumed, and what happens if that contract drifts?
5. **Every cross-cutting standard the change touches** — see the Standards gate below. The author may have built without the relevant standard loaded; this review is the catch-net.

## Standards gate — MANDATORY, do this before the coverage pass

**Why this exists:** the author of the code under review may not have had the relevant standard in context (fresh session, sub-agent with a narrow prompt, or simply forgot). `/review-impl` is where a drift against a *repo-wide rule* gets caught — a passing unit test never catches "this violated the provider-gateway invariant" or "this new table has no scope key." **Do NOT trust that the author knew the rules; verify against the index.**

**Step 1 — load the index.** Read [`docs/standards/README.md`](../../docs/standards/README.md) (the single entry point to every rule/law/invariant/machine-contract). Use its **Quick-nav by concern** table to map *what the change actually is* → *which standards govern it*. The index links out; open the authoritative doc for any standard the change plausibly touches. Do not rely on memory of the rules — they drift and get amended (e.g. the language rule, the tenancy tiers).

**Step 2 — run the change through the always-on ENFORCED/LOCKED rules.** These are non-negotiable; a violation is a HIGH finding, not a nit:
- **Provider-gateway invariant** — no direct provider SDK import / provider API call; every LLM/embed/**rerank**/image/audio/STT call goes through `provider-registry-service`. Local backends (ollama/lm_studio/local-rerank/stt/tts) are BYOK creds, **never** a per-service `*_URL`/`*_MODEL`/`*_TOKEN` env var.
- **No hardcoded model names / pricing** — resolve from provider-registry, never a literal in runtime code.
- **User Boundaries & Tenancy** — every user-facing table declares a scope tier (System/Per-user/Per-book) + carries a scope key; no regular-user write to a shared/global row; `UNIQUE(code)` on a shared table is the tenancy-bug smell (want `UNIQUE(owner_user_id|book_id, code)`). Self-hosted ≠ single-user.
- **Language rule (I3)** — Rust=kernel-derived · Go=domain/meta · Python=AI/LLM · TS=gateway/realtime, per `contracts/language-rule.yaml`.
- **MCP-first invariant** — new AI *agent* logic is an MCP tool-call through `ai-gateway`, not a bespoke HTTP endpoint over a raw prompt.
- **Frontend-Tool Contract** — closed-set arg ⇒ `enum`; resolver never silently no-ops; one name for one concept; both sides machine-checked.
- **No hardcoded secrets** — all secrets via env; a dedicated payload/encryption key is never `JWT_SECRET`.
- **Gateway invariant (I1)** — external traffic through `api-gateway-bff` (sole exception: PRR-20 game-server WS).
- **Destructive data ops (data-loss class) — two failure modes, both HIGH:**
  - **(a) In tests** — an unscoped `DELETE`/`TRUNCATE`/`DROP` in a test file; a `*_TEST_*_URL` (or a fixture that *falls back* to a production `*_DB_URL`) pointing at a real service DB; or a DB-gated fixture that runs destructive setup/cleanup **without first refusing a non-throwaway DSN** (Go `testsafe.EnsureThrowawayDB(current_database())`, Python `_guard_throwaway(dsn)`, called *before* the first destructive statement). A test that *can* wipe a real database is a HIGH finding — an unscoped `DELETE FROM books` against the real `loreweave_book` already hard-deleted every user's books once. Enforced by `scripts/db-safety-gate.py`; verify the change added **no un-exempted finding** and **no bogus `db-safety-gate: ok` pragma sitting over a REAL execution** (a pragma is only for a mock / SQL-string assertion / already-guarded fixture).
  - **(b) In production** — a raw hard `DELETE FROM <table>` (or `TRUNCATE`/cascade) of user-important data that should be a **soft delete** (trash + a *guarded* purge: must be trashed first → retention window → background purge). Important data is soft-delete by default; an unscoped, un-tiered, or trash-bypassing production hard-delete is a HIGH finding. (See CLAUDE.md › "Destructive DB ops in tests" + "User Boundaries & Tenancy".)

**Step 3 — check the machine-contract SoT + gate for the change's domain.** If the change touches a concept with a SoT file (events, errors, cache keys, service ACL, frontend-tools, dependency matrix, entity-status, language rule — §B of the index), verify the change updated the SoT **and** any polyglot mirrors move together, and that the guarding lint/drift-test would still pass. A schema changed in one language but not its mirror is a HIGH finding (the classic weak-model-silently-drops-an-arg bug).

**Step 4 — confirm enforcement exists, don't just assert conformance.** For any standard the change relies on, name the **gate or test** that would go red if a future edit broke it. If none exists and the standard is ENFORCED/LOCKED, that missing test is itself a finding (LOW→MED). "It conforms today" without a guard is drift waiting to happen — this repo's whole meta-pattern is *rule + SoT + gate + test*.

If the change touches **none** of the standards, say so explicitly with the one-line reason (e.g. "pure internal refactor, no new I/O surface, no provider/model/table/tool/secret touched") — same anti-rubber-stamp bar as the coverage pass.

## Process

1. **Read the task's plan row or ticket** to recover the acceptance criteria in their original form.
2. **Re-read all changed files from disk** — `git show HEAD` for the latest commit, or files matching the task.
3. **Run the Standards gate above** — index → applicable standards → ENFORCED/LOCKED rules → SoT+mirror → enforcement-exists. Do this before the coverage pass; a standards violation outranks a coverage nit.
4. **Read all callers and callees one hop out** — the implementation is at a boundary; the boundary partners can hide bugs.
5. **For each input-model field:** is it persisted, transformed, or dropped? If dropped, is that intentional?
6. **For each defensive operation** (sanitize, validate, dedup): does an upstream step make it moot? Is there a test that would catch if it became moot?
7. **For each test added:** does it prove the invariant, or does it merely exercise the happy path?

## Output format

Return findings as a numbered list, **ordered by severity**: HIGH (production bug **or a violation of an ENFORCED/LOCKED standard**), MED (real risk but not exploitable today, **or a SoT/mirror drift a gate would eventually catch**), LOW (coverage/drift/documentation, **or a missing enforcement test for a standard the change relies on**), COSMETIC (test-quality smell).

Tag any standards finding with the standard's name + its source (e.g. `[Provider-gateway invariant]`, `[User Boundaries & Tenancy]`) so the author can jump to the rule.

For each finding:
- One-line title with severity tag
- `file:line` reference
- What's actually wrong (1–3 sentences)
- Suggested fix or "accept and document"

**If you find nothing, say why convincingly** — list the specific coverage checks you made and what you verified they pass. Do NOT output "0 issues found" without that evidence; that's the rubber-stamp we're trying to avoid.

## When to suggest follow-up work vs. fix now

- HIGH → fix now, loop back to VERIFY
- MED → the user decides: fix-now or deferred item in session notes
- LOW + COSMETIC → default to deferred item unless batching with HIGH/MED fixes

Never silently accept a HIGH finding.
