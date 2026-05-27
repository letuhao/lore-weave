# Plan — Improve AMAW's ContextHub integration: hook-based enforcement

> **Spec:** [docs/specs/2026-05-16-amaw-contexthub-enforcement.md](../specs/2026-05-16-amaw-contexthub-enforcement.md)
> **Size:** L, default v2.2. Branch `mmo-rpg/zone-map-amaw`.
> **Safety rule (R-A):** hook scripts are built + tested **standalone** before being
> wired into `.claude/settings.json`. A broken `PreToolUse` hook bricks every session.

## Build order (5 steps — D4 first; it is the keystone)

### Step 1 — D4: canonical action vocabulary + guardrail re-seed
- Define the fixed action-label vocabulary (`git push`, `git push --force`,
  `git reset --hard`, `destructive file op`, `db migration`, `ready-to-commit`).
- `scripts/seed-amaw-guardrails.py` — idempotent create/update of the canonical
  guardrail set in ContextHub, each with a `guardrail-trigger` matching a label.
- Document the vocabulary in `docs/amaw-workflow.md` as the `check_guardrails` contract.
- Verify: run the seed script twice (idempotent); `check_guardrails "git push --force"`
  returns a non-empty violation set (AC-5).

### Step 2 — D1: PreToolUse risky-action gate
- `scripts/amaw-guardrail-gate.py` — stdin PreToolUse JSON → cheap risky-pattern
  pre-check → on match `check_guardrails` → fail-open → allow / deny JSON.
- **Unit-test standalone** (AC-1/2/3): feed fixture JSON for benign / risky /
  ContextHub-down cases; assert output. NO settings.json wiring yet.
- Only once green: wire into `.claude/settings.json` `PreToolUse` Bash hook (alongside
  the existing `git commit` chain). Then end-to-end verify a benign Bash command still
  runs and a risky one is gated (AC-7 regression: `git commit` gate still fires).

### Step 3 — D2: SessionStart context-injection hook
- `scripts/amaw-context-inject.py` — query ContextHub for the guardrail set + recent
  high-signal lessons → emit as `additionalContext`; fail-open (down → emit nothing).
- Test standalone (AC-4), then wire as a `SessionStart` hook in `settings.json`.

### Step 4 — D3: bake lessons into sub-agent prompts
- `docs/amaw-workflow.md` — rewrite the Adversary + Scope-Guard prompt templates:
  replace "Step 0: run search_lessons" with a pre-loaded `## Captured rules` block;
  rewrite the spawn instructions so the orchestrator fetches + embeds lessons.
- `.claude/commands/amaw.md` + `agentic-workflow/.claude/commands/amaw.md` — same
  rewrite, in lockstep (AC-6 byte-compares the changed region).
- `agentic-workflow/AMAW.md` — update if it carries the template prose.

### Step 5 — VERIFY
- AC-1..AC-8 each checked. The load-bearing checks: AC-3 (fail-open with a dead
  ContextHub endpoint), AC-8 (hooks tested standalone before wiring), AC-7 (the
  existing `git commit` gate still fires), and a real end-to-end "benign command runs
  / risky command gated" run after the settings.json wiring.

## VERIFY gate

Hook scripts: standalone fixture tests green. settings.json wired + a live session
sanity check (benign Bash runs; `git commit` gate intact; a risky command hits the
guardrail). Seed script idempotent. Prompt-template copies byte-consistent.

## Risk-driven sequencing note

D4 before D1/D2 — without aligned triggers the gates are no-ops, so seeding first
lets the D1/D2 verification actually exercise a real deny. D1 wired only after its
standalone tests pass (R-A). D3 is pure doc edits — lowest risk, last.
