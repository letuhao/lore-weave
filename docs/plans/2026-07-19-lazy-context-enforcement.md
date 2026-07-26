# Lazy-context enforcement — index+load-on-demand for skills, frontend panels, workflow rail

**Date:** 2026-07-19 · **Branch:** feat/context-budget-law · **Size:** L (breadth-discounted from XL)
**Origin:** F7c (dogfood round-3 token re-measurement). A co-writer turn on Gemma-4 26B measured
**21.6k tokens** with MCP tools already budgeted to 7.7k. Three sources bypass the budget:

| Source | ~tokens/turn | Root cause |
|---|---|---|
| Skills (L2 bodies) | ~5–7k | `glossary`+`knowledge` (+`composition`+`co_write`) auto-injected in FULL on every book/studio turn |
| `ui_open_studio_panel` | ~2.4k | 85-panel prose description inlined in the always-advertised studio tool schema |
| `workflow_directive_block` | ~1–2k | every book workflow's full description inlined (though it already says "workflow_load first") |

## The thesis (user framing, LOCKED)

> "The platform itself already designed for this but lacks enforcement. This problem we're causing
> is lack of enforcement, not because the platform doesn't design for it."

The **index + load-on-demand + control-tool** pattern already exists and is proven for TOOLS:
`tool_list` (index) → `tool_load(name)` (pull) → schema becomes callable, bounded by
`HOT_SEED_TOKEN_BUDGET`. Skills already have the **L1 index** (`skill_metadata_block`,
~117 tok, always injected). What's missing is the **enforcement**: skills force-inject L2
regardless of turn relevance, and there is **no `load_skill` control** (the twin of `tool_load`).
This effort closes that gap and applies the same discipline to the two other un-budgeted sources.

## Capability-first guardrail (from OPTIMIZATION-EVAL-METHODOLOGY.md — non-negotiable)

> "Cutting context to save tokens can make the agent DUMBER — the worst outcome, however cheap."

The target model is the **medium** Gemma-4 26B, which cannot lazy-load as aggressively as
Cursor/Claude-Code's strong models. So every lever ships **behind a deploy-level flag** (the A/B
control mechanism, per the methodology's "one-function swap") and is enforced as the default
**only after** the A/B proves token savings **with no capability loss** on gemma-4-26b.

## The safety net that makes lazy skills viable on a medium model

Three layers keep the model from ever "not knowing" a skill exists (the failure the user feared):
1. **L1 index always on** — `skill_metadata_block` lists every surface-visible skill + one-liner.
2. **Intent→Skill Router** (`resolve_skills_to_inject_async`) — already embeds the turn text and
   unions in any skill whose description matches. Under lazy mode this becomes the **smart preload**:
   a glossary turn still gets the glossary L2 upfront; only OFF-intent turns skip it.
3. **`load_skill` control** — if the router misses and the model realizes mid-turn it needs a skill,
   it pulls the L2 body on demand (returned as a tool result → persists in history for free, no
   migration). Mirrors `tool_load`/`workflow_load` exactly.

Pins + mode-bindings (plan_forge in plan mode, co_write in write mode) still force L2 — those are
deliberate, not blanket surface defaults. **Only the unconditional surface auto-inject** (the
`else` branch of `resolve_skills_to_inject`: glossary+knowledge+composition) goes lazy.

## Milestones

- **M1 — skills lever (centerpiece).** `settings.lazy_skill_bodies` flag; `load_skill` consumer-local
  tool (def + result builder + dispatch branch, mirroring `workflow_load`); `resolve_skills_to_inject`
  gains `lazy_bodies` so its `else` surface-default branch injects nothing when lazy (pins/mode/router
  survive); L1 `skill_metadata_block` gains a "call `load_skill('<code>')`" directive when lazy.
  No DB migration (L2 body persists in message history as any tool result does).
- **M2 — frontend panel lever.** `settings.compact_studio_panel_desc` flag; a compact grouped
  description for `ui_open_studio_panel` that keeps the full `panel_id` **enum** (Frontend-Tool
  Contract: closed set stays) but replaces the ~2k per-panel prose with terse area-grouped guidance.
- **M3 — workflow rail lever.** `settings.lazy_workflow_directive` flag; when lazy, list workflow
  **slugs + short titles only** (drop full descriptions), keep the "workflow_load first" directive.
- **M4 — A/B eval.** Extend the eval harness: baseline (all flags off) vs optimized (all on) on
  gemma-4-26b, scoring (a) tokens/turn, (b) does the model still select+use the right skill/panel/
  workflow. Capability parity is the ship gate.
- **M5 — enforce winners.** Flip the proven flags' defaults; keep the flag as the documented
  kill-switch/A-B control (settings-boundary: deploy-level ceiling, the sanctioned env use). SESSION + commit.

## A/B RESULT (2026-07-19, `eval/run_lazy_context_ab_eval.py` on gemma-4-26b via lm_studio)

Deterministic token measurement used the REAL production block builders; capability ran the
REAL model through provider-registry (the production streaming path).

| Lever | Baseline→Optimized tokens | Capability (medium model) | Verdict |
|---|---|---|---|
| M1 skills (studio write turn) | 5605 → 1733 = **−3872/turn** | skill usage **3/3 = 3/3** (tools stay hot; gemma acts directly, no floundering) | ✅ ship |
| M2 ui_open_studio_panel | 2371 → 881 = **−1490/turn** | panel selection **6/6 = 6/6** | ✅ ship |
| M3 workflow directive | ~−30/workflow | slug+title + workflow_load path | ✅ ship (low-risk) |

**~5.4k tokens/turn saved on a studio co-writer turn (~25% of the measured 21.6k), NO capability
loss on gemma-4-26b.** M2's FIRST run regressed 5/6 (compact desc confused "translation coverage
matrix" → `enrichment-gaps`); per the capability-first methodology that was NOT shippable, so the
compact description was disambiguated (LANGUAGES vs ENRICH-LORE groups) and re-eval'd to 6/6 — the
iterate-the-hypothesis-and-re-measure loop the methodology prescribes.

**Enforce step:** all three flag defaults flipped to **True** (config.py). Each remains the
documented deploy-level kill-switch (env→0 reverts a lever + is how the A/B control is re-run).
**Live rollout needs a chat-service image REBUILD** — the eval proved the logic by copying the
changed modules into the running container; stream_service.py + config.py are not yet in the image.

### M4 — intent-gate the panel navigator (added 2026-07-19, user-directed)

Follow-up question: `ui_open_studio_panel` opens a panel — a click/keypress the user can do
manually — yet costs ~880 tok (compact) on EVERY studio turn. Deprecating it is wrong (the
free-string `ui_show_panel` fallback is the silent-no-op bug the enum was built to fix). So
`studio_panel_intent_gated` (default True) advertises the navigator **only on a navigation-intent
turn** — a nav VERB (open/show/view/go to/manage/import/…) **+** a panel-specific noun
(timeline/matrix/graph/glossary/wiki/what-if/…). `ui_focus_manuscript_unit` (open a chapter, part
of the writing loop) stays always-on. Deterministic, PRECISION-biased: overloaded writing words
(scene/arc/plan/chapter/character/beat) are NOT panel nouns, so "write a scene" / "plan the arc"
never fire; a missed nav phrasing just means the user clicks. Unit-tested (8 nav fire, 7 writing
don't); the tool is byte-identical to the 6/6 A/B run when it fires, so capability is unchanged.
**Effect: on a typical writing turn the panel navigator is fully omitted — combined with M2 that
is 2371 → 0 tok on most studio turns.**

## Invariants / gotchas

- `load_skill` is a **consumer-local meta-tool** (like `tool_list`/`workflow_load`), NOT a
  frontend/agent tool — no ai-gateway federation, no frontend resolver. It reads `SYSTEM_SKILLS`.
- Flags are **deploy-level A/B kill-switches** (the sanctioned env use per Settings & Config
  Boundary — NOT per-user knobs). Document each as such, mirroring `rail_driver_enabled`.
- The `plan_nudge` context-breakdown category folds mode_nudge + workflow_directive + pinned_rail —
  keep it accounting-correct (an unaccounted always-on block is what the Context Budget Law catches).
- `skill_meta_block` already hides `glossary_shaping` (internal companion) — keep that.
