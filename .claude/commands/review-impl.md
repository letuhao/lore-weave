---
description: On-demand adversarial implementation review. Invoke when POST-REVIEW needs a deeper look or after COMMIT when something feels off.
argument-hint: "[task-id | commit | empty] [+check]"
---

# /review-impl — Adversarial implementation review

Perform a deep adversarial review of the most recent implementation work. This is the **separate mental mode** that POST-REVIEW deliberately does NOT do (see Phase 9 note in `AGENTS.md`).

## Arguments

Strip standalone flag tokens from `$ARGUMENTS` first, then route the remainder as scope.

- **`+check`** — run the findings validator (below) before rendering anything to the user. Default OFF.
  May appear before or after the scope (`/review-impl +check`, `/review-impl K17.9 +check`).
  An unknown `+`-prefixed token is passed through as part of the scope rather than silently eaten.

## Scope

Review whatever the user is currently focused on. If the remaining `$ARGUMENTS` names a task or ticket (e.g. `K17.9`, `PROJ-421`), scope to that task's files. Otherwise scope to the changes in the latest commit (`git show --stat HEAD`).

Capture the reviewed diff verbatim — `git show HEAD` for the latest commit, `git diff --cached` if reviewing staged work, `gh pr diff <N>` for a PR. **Keep it**: the validator judges findings against that exact text, not against a re-read of disk.

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
  - **(b) In production** — a raw hard `DELETE FROM <table>` (or `TRUNCATE`/cascade) of user-important data that should be a **soft delete** (trash + a *guarded* purge: must be trashed first → retention window → background purge). Important data is soft-delete by default; an unscoped, un-tiered, or trash-bypassing production hard-delete is a HIGH finding. (See AGENTS.md › "Destructive DB ops in tests" + "User Boundaries & Tenancy".)

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

## `+check` — the findings validator

Adapted from AI Factory's `aif-review` `+check` (`.claude/skills/aif-review/references/CHECK-MODE.md`), which is the better-engineered half of that skill. It exists because the instruction *"say why convincingly"* asks the same model that wrote the findings to grade them — and a fresh context is a mechanism where an instruction is only a hope.

**Run it after the full review is produced internally but BEFORE anything is rendered.** It only changes which findings reach the user and what the result block reports. If `+check` is not set, skip this section entirely and emit no validator lines.

### Procedure

1. **Collect** every finding into a numbered list, in display order, each under a heading
   `### Item N (severity: HIGH|MED|LOW|COSMETIC)`. If the list is empty, skip to step 5 with
   `hidden=0, adjusted=0, reclassified=0` — do not dispatch a validator to judge nothing.
2. **Build the validator prompt** with four blocks:
   - **Reviewed diff** — the verbatim diff captured in *Scope*. This is the validator's primary
     source of truth. Never make it reconstruct the change from disk: on a PR the branch is not
     checked out, and it would judge the wrong version.
   - **Items** — the list from step 1.
   - **Severity rules** — the four levels as defined in *Output format* above, inlined verbatim.
     Do **not** hand it `aif-review`'s `SEVERITY.md`: that file defines two levels
     (critical/suggestion) and mapping four onto two silently destroys the MED/LOW distinction
     this repo's deferral gate depends on.
   - **Standards context — the adaptation that matters.** For every finding tagged with a
     standard, inline the **actual rule text** from `docs/standards/**` (or `AGENTS.md`) next to
     it. A generic validator has no idea that `UNIQUE(code)` on a shared table is a tenancy hole
     or that a per-service `*_MODEL` env var breaks the provider-gateway invariant, so it reads
     a correct standards finding as *"generic what-if speculation with no concrete trigger"* and
     drops it. **That failure mode would delete exactly the findings this command exists to
     produce.** Give it the rule, or do not let it vote on the item.
3. **Dispatch one** `Task(subagent_type: general-purpose)` with that prompt. Fresh context, read-only
   by instruction (it may `Read`/`Glob`/`Grep` to check interaction with unchanged surrounding code,
   never write, never run commands, never invent findings that were not in the input).
4. **Parse by `### Item N`.** Each item carries a `Verdict` and an optional `Severity`:
   - `keep` — text stays. `adjusted` unchanged.
   - `modify` — replace the text with `Modified-text:`; increment `adjusted`.
   - `drop` — remove it; increment `hidden`. `Severity` is ignored.
   - `Severity: HIGH|MED|LOW|COSMETIC` moves the item between levels; increment `reclassified`
     and append ` [+check: promoted from LOW]` / ` [+check: demoted from HIGH]` so the move is
     visible rather than silent. Omitted or `unchanged` ⇒ stays put.
   - **A HIGH finding tagged with an ENFORCED/LOCKED standard may be `modify`d but never
     `drop`ped or demoted below MED.** The validator can correct a wrong file, line, or wording;
     it cannot overrule the standard itself. If it votes `drop` on one, keep the item and append
     `WARN [+check]: validator voted drop on a LOCKED-standard finding — kept, verify by hand`.
5. **Fail open, loudly.** A validator that dies must never silently shrink a review:
   - *Per-item malformed* (missing heading, no `Verdict`, unknown token, `modify` without
     `Modified-text`) → treat as `keep`, and emit
     `WARN [+check]: validator response for item N was malformed, kept as-is`.
   - *Whole dispatch failed* (empty, exception, timeout, refusal) → treat **all** items as `keep`
     and emit `WARN [+check]: validator failed (<reason>), all items kept as-is`. In this case build
     the result block from the **unfiltered** list — do not recompute anything from a run that did
     not happen.
   All `WARN` lines go directly above the result block, which stays last.
6. **Report the arithmetic**, so a shrinking review is never mistaken for a clean one:
   `+check: N items in, M rendered (hidden: X, adjusted: Y, reclassified: Z)`.

## Machine-readable result

End the output with one fenced `aif-gate-result` block — the shared contract (`scripts/gate_result.py`,
`.claude/skills/aif-review/references/GATE-RESULT-CONTRACT.md`) so a CI leg or an orchestrator reads
this review the same way it reads every other gate here.

- `gate` is `"review"`. `status` is `fail` when any HIGH survives, `warn` when the worst is MED, else `pass`.
- `blockers` carries the HIGH findings only (`severity: "error"`), each with a stable `id`, its `file`, and a one-line `summary`. MED/LOW/COSMETIC stay in the human section and out of `blockers`.
- `affected_files` lists what the review actually read, not just what it complained about.
- `suggested_next` is `/aif-fix` when blockers remain, else `null`.

The human-readable findings come first and stay the point; the JSON is for whatever runs after you.

## When to suggest follow-up work vs. fix now

- HIGH → fix now, loop back to VERIFY
- MED → the user decides: fix-now or deferred item in session notes
- LOW + COSMETIC → default to deferred item unless batching with HIGH/MED fixes

Never silently accept a HIGH finding.
