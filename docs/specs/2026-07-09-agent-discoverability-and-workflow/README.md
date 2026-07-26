# Agent Discoverability & Workflow — design folder

This folder splits the discoverability/workflow rework into **independent, fan-out-ready** design
artifacts. Each parallel session picks ONE file, designs it fully, and (crucially) **live-tests it on
the chat GUI with `gemma-4-26b-a4b-qat`** — a mid-tier local model. The whole point of the effort is:
*can a mid-tier model actually do the job through our MCP / skills / workflows, or does it stall in a
`find_tools` loop?* Every scenario is written **expectation-first** (define the pass/fail BEFORE
building), so the live test is a real acceptance gate, not a vibe check.

## ⬛ The black-box rule (non-negotiable)

**A user scenario is written entirely from the chair of someone who does NOT know this platform** — no
tool names, no "workflow", no "kind/attribute/entity", no modes, no mechanism. It contains only: what
the user *wants*, what the user *does* (types/clicks), and what the user can *see and verify*.
Success/failure is judged on the **observable outcome**, never on which internal tool fired.

Why: the platform's core failure is that it was *designed* assuming the caller knows the internals. A
**white-box** test (one that asserts "the assistant should call `X`") re-encodes that exact assumption
— it passes while real users fail, and it can't catch a broken-but-matching path or credit a valid
different one. We keep failing because we test white-box. So: the internal happy-path is demoted to a
**non-binding "Builder hint"** section that is *not* the acceptance test.

**Two distinct artifact types — do not conflate:**
- **Black-box user scenarios** (`S01`…`S12`) — judge the *user's* outcome. Written per `_TEMPLATE.md`.
- **⚙️ Mechanism / developer tests** (`S00a`…`S00e`) — white-box *by design*, because they verify a
  primitive (`tool_list`, `tool_load`, the step-runner) directly. They name tools because the tool *is*
  the subject. Their user-observable payoff is proven by the black-box scenarios, never asserted here.

## Files

| File | What it is |
|---|---|
| [`2026-07-09-agent-discoverability-and-workflow-architecture.md`](2026-07-09-agent-discoverability-and-workflow-architecture.md) | **The overall spec** (umbrella). Root cause, target architecture (deterministic list/load triad + Workflow primitive), the 6-phase roadmap, the W1–W12 catalog. Do not fragment it — the per-task docs link back to it. |
| [`scenarios/_TEMPLATE.md`](scenarios/_TEMPLATE.md) | The expectation-first live-test scenario template. **Copy it to author each new scenario.** |
| [`scenarios/_INDEX.md`](scenarios/_INDEX.md) | The scenario backlog + fan-out status board (claim a row before you start). |
| [`scenarios/S06-flagship-idea-to-arc.md`](scenarios/S06-flagship-idea-to-arc.md) | ★ **THE FLAGSHIP — the front door we ship.** One long session where a user speaks pure story-vision and a real book foundation appears (world structure → cast → connections → arc plan → drafted chapter) without ever naming a tool. Synthesized from 4 perspectives (story-craft, UX, platform-mechanics, mid-tier-model failure modes). S01–S05 are its *servants*. Read this to understand what "working" means. |
| `scenarios/S**-*.md` | One live-testable scenario per file. |

## How a scenario relates to the umbrella

The umbrella says *what to build* (mechanism: `tool_list`/`tool_load`/`workflow_load`, the Workflow
object, mode-binding). A **scenario** says *what a real user does and what the model must do in
response* — the acceptance transcript for one job (e.g. W1 glossary bootstrap). Scenarios are the
**test-first** face of the umbrella's workflows: `S0x` ↔ `W0x`. Build order is driven by which scenarios
must pass.

## The core failure we are designing against

> "I try to real use but almost every time the model gets stuck at tool search — it calls a lot of
> tool searches and stops at nothing."

Every scenario captures this as an explicit **Baseline (current behavior)** section — run the job
against the *current* system with gemma first, record the loop (how many `find_tools`/`invoke_tool`
calls, where it stalls) — and a **Target** section — the deterministic transcript the fixed system must
produce. The delta is the work.

## Live-test conventions (shared by every scenario)

- **Model:** `gemma-4-26b-a4b-qat` (local lm_studio, $0). Resolve its `model_ref` live — it is the
  `user_model_id` UUID, not the alias:
  `SELECT user_model_id, alias, capability_flags FROM user_models WHERE owner_user_id='019d5e3c-7cc5-7e6a-8b27-1344e148bf7c' AND is_active;`
  (`user_default_models` is empty for the test account — always pass an explicit `model_ref`).
  lm_studio must be up; if it wedges mid-stream, `lms` reload (see the queue-wedge lesson).
- **Account:** `claude-test@loreweave.dev` / `Claude@Test2026` (auth id `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`).
- **Surface:** the real chat GUI. FE `:5174` is the **baked** nginx prod build (rebuild image for FE
  changes; a host `vite dev` can shadow it) — for a robust smoke use a built image on a free port or
  `vite dev` `:5199`. FE talks to the gateway via relative `/v1`.
- **Fixture book:** Mị Đế (the book the external feedback was generated against) unless a scenario says
  otherwise — it exercises the exact glossary/KG surface the feedback covers.
- **Automation:** drive the GUI with Playwright MCP; dockview refs go stale — target `data-testid` +
  `evaluate` (see the live-dockview automation recipe).
- **Record everything:** save the raw transcript + a short findings report per run under
  `docs/eval/discoverability/YYYY-MM-DD-<scenario>-<model>.md` (persist reports to dated files; do not
  leave results only in chat). Capture: # of `find_tools`/`invoke_tool` calls, wall-clock, whether the
  job completed, and the exact stall point if it failed.
- **Permission mode:** state it per scenario (`ask` for read-only journeys, `write` for mutating ones).

## Fan-out protocol

1. Open [`scenarios/_INDEX.md`](scenarios/_INDEX.md), claim an unclaimed row (put your session/branch in
   the Owner column).
2. Copy `_TEMPLATE.md` → `scenarios/S0x-<slug>.md`; fill §1–§6 (the black-box user view + observable
   acceptance) **before** touching code. Internal tool/workflow detail goes **only** in §8 Builder hint
   (non-binding). If you wrote a tool name in §1–§6, you slipped into white-box — move it to §8.
3. Run the **Baseline** live test with gemma; record it under `docs/eval/discoverability/`.
4. The scenario's "Gap → required capability" section maps to a phase in the umbrella — that's the
   build. (Mechanism phases 0–3 unblock the scenarios; scenario authoring can proceed in parallel.)
5. Re-run the live test against the fix; scenario passes when the Target transcript reproduces with
   gemma.

Scenarios are **disjoint files** — safe to author in parallel worktrees/sessions. The *mechanism* they
depend on (Phase 0–3) is shared, so sequence the builds via the umbrella roadmap even while the
scenario docs are written concurrently.
