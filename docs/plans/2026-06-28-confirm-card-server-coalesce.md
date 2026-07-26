# Plan — Confirm-card server coalesce (bugs #27 / #29 / #30 / #18)

**Date:** 2026-06-28 · **Branch:** `fix/critical-ux-bugs` · **Size:** XL (load-bearing — touches the
agent run lifecycle + the human-gate / injection-damage boundary).

## Problem (verified in code)

The chat run lifecycle honours **exactly one confirm card per turn**:
- `chat_suspended_runs` stores a single `pending_tool_call`, PK = `run_id` (`db/suspended_runs.py`).
- the tool loop `break`s on the **first** frontend confirm call, silently dropping any tail calls
  (`stream_service.py` ~613-619).
- the first confirm **deletes the run row** (`delete_suspended_run(run_id)` on resume) → sibling
  cards can never resume → they 422 as "expired" (#27/#29).

The system is *designed* for one batched card (`ConfirmActionCard.tsx:21-24`), and the
**Plan/Action kit already is the coalesce engine**: `execute_plan` → `effectExecutePlan` runs a typed
`Plan{Ops}` through the deterministic tier-ordered executor with per-op `applied/skipped/failed`
outcomes + per-op destructive gating (`plan_confirm.go`, `plan_ops.go`, `sdks/go/loreweave_mcp`).
The only gap is behavioural: a weak local model **loops** single-propose tools instead of producing
one batch, and the server tolerates the broken multi-card turn (#30/#18). The skill rules that say
"batch" are **soft prose** the model ignores.

## Decision (user)

**Full server coalesce** — the server merges the N proposals a turn produces into **one** confirm
card that commits all rows. Chosen over prompt-only and over server-enforced-error-feedback.

## Design

Two layers; the run-loop layer is the robustness guarantee, the batch tool is the clean path.

### L1 — `glossary_propose_batch` MCP tool (deterministic, no planner LLM)  ·  glossary-service
A new class-C propose tool that accepts an explicit `ops[]` (the **same** op vocabulary the planner
emits) → `planRegistry().ValidatePlan` → `mintGrantActionCard(descExecutePlan, plan)`. It is
`toolPlan` minus the planner model: zero extra LLM cost, fully deterministic, reuses the entire
`execute_plan` executor + preview + FE card. Gives the agent a single call that turns "many writes"
into ONE card. (≈ one new handler + tool registration + a schema for the ops list.)

### L2 — per-turn token coalesce (the server-merges-strays guarantee)  ·  chat-service + glossary
The run loop already executes every propose tool and sees each result's minted `confirm_token`.
Change:
1. **Accumulate** every class-C `confirm_token` minted in the turn (from propose-tool results).
2. At the suspend point (first frontend `confirm_action`/`glossary_confirm_action`), if **>1** token
   was accumulated this turn, **bundle them**: suspend on ONE synthetic `confirm_action` with a
   `glossary.batch` descriptor whose args carry the child tokens — the individual cards never render.
   Exactly one token → today's single-card behaviour, unchanged.
3. **glossary-service**: `POST /v1/glossary/actions/confirm-batch` (+ `/preview-batch`) accepting
   `{child_tokens:[…], enabled_ops?:[…]}`. For each token: `verifyActionToken` → claim jti
   (single-use, unchanged ledger) → dispatch to the **existing** per-descriptor effect → collect a
   per-token outcome. Aggregate into one `{applied, skipped, failed}` summary. Preview loops the
   existing per-token preview and concatenates rows. **No effect handler is rewritten** — the batch
   path is a loop over the same single-confirm effects.
4. **FE** `ConfirmActionCard`: route the `glossary.batch` descriptor to the batch preview/confirm
   endpoints; batch row rendering already exists (server `preview_rows` + `items[]`). On confirm,
   `submitToolResult` resumes the run with the aggregated summary.

### L3 — skill hardening (cheap reinforcement)  ·  chat-service
`glossary_skill.py`: soft → hard — "for MORE THAN ONE write, you MUST use a single batch
(`glossary_propose_batch` or `glossary_plan`); NEVER emit individual propose cards in a loop." Plus
the #18 hard-stop: "MUST NOT call `glossary_plan` more than once per turn."

## Security review (must hold)
- The human gate (INV-1) is **preserved**: the bundle is still ONE human confirm; every child effect
  still re-validates against current state at confirm (§13.5). No write happens without the click.
- Single-use is **preserved**: each child jti is claimed in the same `consumed_tokens` ledger; a
  replayed batch re-claims → those children skip, not double-apply.
- Injection-damage bound (H7 Tier-A caps): bundling does not raise the cap — the batch is still
  gated by ONE human review listing every row. Destructive children stay per-op opt-in (enabled_ops).
- Ownership: every child token is grant-authority bound to (user, book); the batch endpoint
  re-checks each, and rejects a mixed-book batch (all children must share the suspended run's book).

## Phasing
- **P1:** L1 batch tool + L3 skill (additive, low-risk, immediately useful). Tests.
- **P2:** L2 run-loop coalesce + glossary batch endpoints (load-bearing). Tests + live smoke.
- VERIFY: cross-service live smoke (chat-service ↔ glossary-service) — drive a real 3-kind batch.

## Out of scope (tracked separately)
- #19 (planner model-ref after stop) — needs a live model_ref capture; separate row.
- #28 (KG schema inspector) — FE feature, separate.
