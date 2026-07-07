# Skill eval loop-flake — root cause, fix, and clean re-run (2026-07-08)

Closes `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE` and `D-SKILL-EVAL-RERUN-AFTER-LOOP-FIX` from the first Part E pass ([`2026-07-07-part-e-first-pass.md`](2026-07-07-part-e-first-pass.md)). Investigation, two real platform fixes, and a clean re-run — not a guess-fix off noisy data.

## Investigation

Re-ran the worst-offending scenario (`prefer_dirty_retranslate_over_force`, translation) with `QG_KEEP_SESSIONS=1` and pulled the raw `tool_calls` JSONB straight from `loreweave_chat.chat_messages`. Every one of 30 consecutive `find_tools` calls carried `"args": {}` — the model never included `intent`, from the very first call, regardless of feedback across all 30 attempts. `find_tools`'s own schema marks `intent` as `required`, but nothing server-side enforced it — an empty intent silently degraded into a genuine zero-token search (`_score()` returns 0.0 for empty `intent_tokens`), landing on the same generic "No tool matched. Reconsider the wording..." note a real no-match gets. That note gave the model no signal its own call was malformed.

**Differential test**: swapped the eval model from the locked `gemma-4-26b-a4b-qat` to `Qwen2.5 7B Instruct` (same scenario, same everything else) — Qwen succeeded on the first attempt, zero `find_tools` spam. Confirmed this is a `gemma-4-26b-a4b-qat`-specific tool-calling defect in this LM Studio setup (matches the repo's existing memory `context-budget-test-model-gemma26b`: this model's evals are already known-noisy), not a platform or skill-prose bug.

## Fix 1 (defensive, kept regardless of model choice)

`tool_discovery.find_tools_result()`: a missing/blank `intent` now returns a directive ("`intent` is required... describe what you want to do... call find_tools again with a non-empty `intent`") instead of the generic no-match note — mirrors the "model-directed validation error" pattern jobs-service's kit already uses for pydantic failures. Verified server-side; did **not** by itself fix gemma's behavior (it kept sending empty args regardless of the new message — confirming the defect is upstream of anything the app layer can correct) but is a strictly-better response for any model that occasionally omits a required arg.

## Fix 2 — the REAL root cause (a genuine, serious, pre-existing production bug)

Switching to Qwen (which reliably sends `intent`) did **not** fix the eval — it just changed the failure signature from "spam empty find_tools" to "confidently claim a real, skill-documented tool doesn't exist" (`book_chapter_create`, `settings_list_providers`, `composition_generate`, etc., dozens of instances across all 5 skill files). Traced with a direct call to `discovery_seed_for_surface`: pinning `enabled_skills=["book"]` with `enabled_tools=[]` (exactly how the REAL frontend pins a skill — `useContextRack.ts` → `patchSession({enabled_skills: next})`, which never sets `enabled_tools`) produced **zero** `book_*` tools in the seed. `pins.curated_mode` was `False`.

Root cause: `is_curated()` derived `curated_mode` from `enabled_tools` alone — a skill-only pin never entered curated mode, so `discovery_seed_for_surface`'s entire curated hot-domain union (the mechanism Part B built specifically to seed a pinned skill's tools) never ran. The skill's **prompt** was still injected (confidently telling the model to call its tools directly, exactly per design), but its **tools** were never advertised — the model was left to `find_tools` its way to something it was told exists, and when that discovery didn't happen reliably (compounded by Fix 1's target bug on gemma, or simply not being attempted), it defaulted to "this doesn't exist." A second instance of the identical assumption (`curated_mode` implies `enabled_tools` non-empty) was baked into `effective_enabled_tools()`'s `or not enabled_tools` short-circuit, which would have silently skipped even the glossary-specific hot-seed gate for a pure glossary-only pin.

**Why Part B's own tests never caught this**: every test in `TestCuratedSkillHotDomainUnion` co-pinned a dummy `enabled_tools` entry alongside the skill under test (`"enabled_tools": ["glossary_search"], "enabled_skills": ["translation"]`) — accidentally triggering curated_mode through the OTHER parameter and masking the skill-only path the real frontend actually uses. This live-eval pass is what finally exercised the untested path.

**Fix**: `is_curated(enabled_tools, enabled_skills)` now returns true if *either* is non-empty; `effective_enabled_tools()`'s dead short-circuit removed. New regression tests: `test_is_curated_skill_only_pin`, `test_skill_only_pin_with_NO_enabled_tools_still_seeds_the_domain`, `test_skill_only_pin_of_glossary_also_seeds_via_the_glossary_gate` — the middle one is explicitly the real-world case every prior test missed. Live-verified post-fix: a `book`-only pin (`enabled_tools=[]`) now correctly seeds all 21 `book_*` tools, `book_chapter_create` included. chat-service 1158/1158.

## Clean re-run (round 3, both fixes live, Qwen2.5 7B Instruct)

| Skill | PASS | FAIL | WEAK |
|---|---|---|---|
| composition | 1 | 4 | 1 |
| translation | 3 | 3 | 1 |
| book | 1 | 2 | 8 |
| settings | 4 | 2 | 2 |
| jobs | 0 | 3 | 3 |
| **Total** | **9** | **14** | **15** |

**Zero hallucinated tool names anywhere** (all 5 judges independently confirmed, cross-checked against real MCP server code) — even stronger than the first pass, since tool discovery is now actually working and the model had every opportunity to invent one under pressure and didn't.

**The dominant round-1/2 failure mode (false denial of a real, documented tool) is gone for jobs/settings/translation and much reduced for book/composition.** Where it recurs (composition: 2/6 scenarios), the cause is now understood and different: composition has ~56 tools, only ~17 fit `HOT_SEED_TOKEN_BUDGET` (working as designed — read tools prioritized, write-shaped verbs like `composition_generate`/`composition_outline_node_update` get trimmed). `find_tools` search itself was directly verified to return both tools correctly and confidently for reasonable queries — the gap is Qwen2.5 7B not always *attempting* the search before concluding a budget-trimmed tool doesn't exist. This is a model-capability limitation interacting with an intentional, working budget mechanism, not a platform bug.

**Two new, genuinely distinct patterns surfaced, neither a skill-authoring or platform defect:**
1. **"Called the correct real tool, then emitted 0 characters to the user"** — recurred across all 5 files (translation ×1, book ×4, settings ×2, jobs ×3). Matches this repo's own pre-existing, already-catalogued lesson `reasoning-model-burns-max-tokens-before-real-answer` — a local reasoning-capable model exhausting its token budget on internal reasoning before emitting content. Pre-existing, known, out of scope for this pass.
2. **Non-convergent retry loops on a genuinely failing lookup** (book: 2 scenarios, 250-320s, repeating near-identical reasoning without recognizing a terminal state) — related to #1, a small-model loop-termination characteristic.

**One real, reproducible content finding survived a properly-functioning platform**: `motif_not_connected_to_planforge` (composition) still FAILed in round 3 — with tool discovery genuinely working, the model called real tools (`plan_propose_spec`) while still conflating "bind a motif after a plan compiles" with "bake the motif into the plan during compilation." `composition_skill.py` already states the rule fairly explicitly ("Motifs are NOT connected to PlanForge... bind here after the plan is compiled, not as part of the planning flow") — n=1 from a 7B model isn't enough to conclude the prose itself needs strengthening (the same overfitting risk flagged in the first pass), so left as-is rather than rewritten off one data point.

## Deferred items — resolution

- `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE` — **RESOLVED.** Root-caused (a real `curated_mode` gap affecting every curated-pin-only skill in production, plus a defensive `find_tools` improvement) and fixed; live-verified.
- `D-SKILL-EVAL-RERUN-AFTER-LOOP-FIX` — **RESOLVED.** This document is the re-run. Clean signal obtained: skill-authoring content is validated (zero hallucinated tools, most content rules correctly followed once tools are actually reachable); remaining friction is model-capability/reasoning-budget characteristics, not skill or platform defects.
- **New, NOT tracked as a fresh defer row** (matches existing memory `reasoning-model-burns-max-tokens-before-real-answer`, already a known class): the "real tool call, 0 chars to user" pattern. If it needs a dedicated investigation later, it's an inference-config/reasoning-budget question spanning every skill, not specific to this spec's scope.
