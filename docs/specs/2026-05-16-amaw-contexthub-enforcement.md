# Spec — Improve AMAW's ContextHub integration: hook-based enforcement

> **Status:** DESIGN 2026-05-16. Default v2.2 (12-phase human-in-loop — NOT `/amaw`;
> using AMAW to modify AMAW's own machinery is circular, per DEFERRED #006). Size **L**.
> Branch `mmo-rpg/zone-map-amaw`.
> **Motivation:** the human-in-loop review found AMAW's ContextHub integration is
> mechanically real (the bridge fires, `add_lesson` works) but **functionally inert on
> the read/enforce side** — across a full XL `/amaw` task, every `search_lessons
> --type guardrail` returned `(none)` and every `check_guardrails` returned
> `pass:true`; no AMAW decision was changed by a ContextHub read. The write side works;
> the loop is not closed.

## 1. Problem

Three concrete defects keep the read/enforce side dormant:

1. **Discretion, not determinism** — the Adversary/Scope-Guard *choose* to run
   `search_lessons` at "Step 0"; the result is advisory. Agent-driven lookup over a
   young corpus returns nothing useful → ignored.
2. **Trigger ↔ query mismatch** — guardrails are seeded by *action* (`git push`,
   force-push, migration) but AMAW queries `check_guardrails` with phrases
   (`"ready-to-commit"`, `"git commit"`) that match no trigger → always `pass:true`.
3. **No harness-level gate beyond `git commit`** — the one `PreToolUse` hook
   (`.claude/settings.json`) only intercepts `git commit`. `git push`, force-push,
   destructive file ops, and migrations are not gated against guardrails at all.

## 2. Scope

All 4 fixes (PO decision):
1. **D1** — extend the `PreToolUse` Bash hook into a real risky-action guardrail gate.
2. **D2** — a `SessionStart` hook that injects the active guardrail set into context.
3. **D3** — bake task-relevant lessons into sub-agent prompts at spawn (deterministic
   injection) instead of instructing the sub-agent to go search.
4. **D4** — align guardrail triggers with a canonical action-query vocabulary.

Out: changing ContextHub itself; the `/review-impl` flow; the v2.2 phase gate
(`workflow-gate.sh pre-commit`) — that stays as-is, this spec only adds the guardrail
layer beside it.

## 3. Design decisions

### D1 — `PreToolUse` risky-action guardrail gate

New `scripts/amaw-guardrail-gate.py` (Python — cross-platform; the current inline
`bash -c '... grep ...'` is fragile on Windows). Wired as a `PreToolUse` hook with
`matcher: "Bash"`. The script:

1. Reads the PreToolUse JSON from stdin; extracts the Bash command string.
2. **Cheap local pre-check first** — match the command against a risky-action pattern
   table (see below). No match → emit allow immediately (zero ContextHub cost — most
   Bash calls take this path).
3. On a risky-pattern match → `mcp-query.py check_guardrails "<canonical action>"`
   (the action label is from the D4 vocabulary).
4. **Fail-OPEN** — ContextHub unreachable / `mcp-query` error / timeout (cap ~8 s) →
   emit *allow* + a stderr warning. **A guardrail infra outage must NEVER block a
   tool call** — fail-closed would brick the session on a transient blip (one was
   observed during Phase 0b retro).
5. A definite guardrail violation → emit
   `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision":
   "deny", "permissionDecisionReason": "<guardrail title + requirement>"}}`.

**Always-on (PO decision)** — the gate fires for every session in the clone, not only
when `amaw_enabled`. Guardrails are unconditional policy.

Risky-action pattern table (initial): `git push`, `git push --force` / `-f` /
`--force-with-lease`, `git reset --hard`, `rm -rf`, `*.sql` migration runners,
`docker compose down -v`. Extensible — a constant table at the top of the script.

The existing `git commit` → `workflow-gate.sh pre-commit && amaw-pre-commit` chain is
preserved (it is the v2.2 phase gate — a separate concern); the settings.json hook
runs both: the commit-gate AND the new risky-action gate.

### D2 — `SessionStart` context-injection hook

New `scripts/amaw-context-inject.py`, wired as a `SessionStart` hook. It queries
ContextHub for the active guardrail set + the most recent high-signal lessons and
emits them as `additionalContext` (text added to the session's context). Result: the
guardrails are **always in front of the agent** — the Kiro-steering pattern — not
search-on-demand. Fail-open: ContextHub down → emit nothing (the session proceeds
without the injected block; the D1 hook is the hard backstop). `SessionStart` (once
per session) over `UserPromptSubmit` (every prompt) — guardrails are stable enough
that once-per-session injection is sufficient and far cheaper in tokens.

### D3 — bake lessons into sub-agent prompts at spawn

Change the AMAW workflow so the **orchestrator (main session)**, before spawning an
Adversary / Scope Guard, runs `mcp-query.py search_lessons <topic>` itself and
**embeds the results verbatim** into the sub-agent's prompt under a
`## Captured rules relevant to this review` heading. The sub-agent prompt's "Step 0:
go run search_lessons" instruction is **replaced** by "the captured rules below were
pre-loaded for you — your findings must be informed by them." Determinism replaces
discretion; the sub-agent no longer needs MCP access for that step.

Files: `docs/amaw-workflow.md` (the Adversary + Scope-Guard prompt templates + the
spawn instructions), `.claude/commands/amaw.md` **and**
`agentic-workflow/.claude/commands/amaw.md` (the live copy + the installable source —
both must change in lockstep), and `agentic-workflow/AMAW.md` if it carries the
template prose. The `Step 0` MCP-call instruction in each is rewritten.

### D4 — canonical action-query vocabulary + guardrail trigger alignment

Define a fixed vocabulary of action labels the hook + AMAW use when calling
`check_guardrails` — e.g. `git push`, `git push --force`, `git reset --hard`,
`destructive file op`, `db migration`, `ready-to-commit`. `docs/amaw-workflow.md`
documents this vocabulary as the contract. Guardrails are then (re-)seeded so each
guardrail's `guardrail-trigger` matches one of these labels exactly (or a regex over
them). A `scripts/seed-amaw-guardrails.py` script creates/updates the canonical
guardrail set idempotently so the corpus is reproducible (and so a fresh ContextHub
can be re-seeded). Without D4, D1 and D2 stay no-ops — this is the keystone fix.

## 4. Acceptance criteria

- AC-1: `amaw-guardrail-gate.py`, fed a PreToolUse JSON for a benign Bash command,
  emits *allow* and makes **no** ContextHub call (cheap-pre-check path).
- AC-2: fed a risky command (`git push --force ...`) with a matching seeded guardrail,
  it emits `permissionDecision: "deny"` with the guardrail reason.
- AC-3: with ContextHub unreachable, the gate **fails open** (allow + warning) for
  every input — verified by pointing `mcp-query` at a dead endpoint.
- AC-4: `amaw-context-inject.py` emits the guardrail set as context when ContextHub is
  up, and emits nothing (no error) when it is down.
- AC-5: `seed-amaw-guardrails.py` run twice is idempotent; afterwards
  `check_guardrails "git push --force"` returns a non-empty violation set.
- AC-6: the AMAW prompt templates (all copies) no longer instruct the sub-agent to run
  `search_lessons`; they carry a pre-loaded captured-rules block instead. The two
  `amaw.md` copies are byte-identical in the changed region.
- AC-7: the existing `git commit` v2.2 phase gate still fires (regression check).
- AC-8: hook scripts are unit-tested standalone (fixture stdin JSON) **before** being
  wired into `settings.json`.

## 5. Risks

- **R-A (HIGH) — a broken `PreToolUse` hook bricks every session in the clone.**
  Mitigation: hook scripts are developed + tested **standalone** (AC-8) with fixture
  JSON; only wired into `settings.json` once green; fail-open is unconditional; the
  hook has a hard timeout. VERIFY must include a real end-to-end "benign command still
  runs" check after wiring.
- R-B — the two `amaw.md` copies drift. Mitigation: edit both, AC-6 byte-compares.
- R-C — ContextHub availability. Mitigation: fail-open everywhere (D1, D2).
- R-D — per-Bash-call latency. Mitigation: D1's cheap local pre-check — ContextHub is
  only contacted for commands that already matched a risky pattern.

## 6. Note on enforcement ceiling

Hooks enforce **process** (was a risky action gated? were guardrails in context?) —
they cannot enforce **judgment** (did the Adversary review well?). This spec raises
the floor; it does not fix author-blindness. The independent-review-after-AMAW
practice (`/review-impl` / human review) remains necessary regardless.
