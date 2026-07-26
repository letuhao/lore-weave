# Plan: Intent→Skill Router (Part F)

**Date:** 2026-07-07 · **Branch:** `feat/context-budget-law` · **Origin:**
[`docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md`](../specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md)
§12-15 (Part F, CLARIFY complete, decisions §13.1-13.4 all RESOLVED 2026-07-07). **Size: XL** — new
chat-service subsystem (skill-vector cache + per-turn routing), first consumer of the embedding
client being built in the sibling tactical plan (below). User's explicit choice: build the full
dedicated router (embedding-based skill selection), not the narrower "patch the one orphaned
coverage gap and stop" option.

**Cross-plan dependency (read before starting BUILD):** this plan's F2 slice needs a working
chat-service embedding client + shared cosine-similarity helper — those are built by
[`docs/plans/2026-07-07-mcp-discovery-and-reliability-hardening.md`](2026-07-07-mcp-discovery-and-reliability-hardening.md)'s
Group B (B1: `sdks/python` cosine helper, B3: `app/clients/embedding_client.py`), **not rebuilt here**.
F2 is sequenced to start only after that plan's B1+B3 land — see "Fan-out execution slices" below for
exactly how the two plans' slices interleave in one combined fan-out round.

## Problem (see spec §12 for full grounding — summary only)

`resolve_skills_to_inject()` (`skill_registry.py:258-269`) selects skills from surface flags only
(`editor`/`book_scoped`/`studio`/`admin`/`permission_mode`) — zero intent/query-text input, per its
own docstring (`skill_registry.py:4`: "filters by session pins + surface flags"). Concretely:
`glossary_web_search`/`glossary_deep_research` (general web research, no book needed) live only
inside `glossary_skill`, whose `surfaces={"book","editor"}` excludes `"chat"` — so a universal-surface
web-research ask has NO skill to route to, not even at the cheap L1-menu tier. This is the traced root
cause of the 4 failed sessions in the sibling tactical plan, independently corroborated by Part E's
eval (`D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE`, same failure signature across 37 scenarios / 5 skills).

## Design (per spec §14)

- **F0 — orphaned-capability fix (no embedding dependency, ships independently):** give
  `glossary_web_search`/`glossary_deep_research` an actual skill-home visible on `chat`. Decide at
  BUILD time between (a) extend `universal_skill`'s prompt to explicitly own general web-research +
  name the two tools with a calling example, or (b) a small new skill (`surfaces` including `"chat"`)
  — pick whichever reads more coherently against `universal_skill`'s existing scope once both are
  drafted side-by-side.
- **F2 — skill-vector cache + per-turn routing (depends on the sibling plan's embedding client):**
  precompute one embedding per `SkillDef` (its `description` + an author-supplied synonym/keyword
  hint, mirroring `tool_meta().synonyms`) at `SYSTEM_SKILLS` load — a static ~11-15-vector set,
  refreshed only when a skill changes. Per turn: embed the user's current message once (the SAME
  embedding call the sibling plan's `search_catalog()` upgrade already pays for — one call, two
  consumers), cosine-rank against the skill-vector cache, filtered to skills whose `surfaces` already
  include the active surface (the router narrows WITHIN the structurally-eligible set — `surfaces`
  keeps encoding "does this even apply here," untouched). Skills scoring above the single global
  confidence threshold (§13.2, tuned via Part E's harness) are UNIONED into
  `resolve_skills_to_inject()`'s output — additive only, never removing what the static path already
  guarantees (e.g. `knowledge` auto-injecting everywhere per the shipped Part D). Verified against the
  SAME shared `HOT_SEED_TOKEN_BUDGET` ceiling other skill-injection paths already respect — no
  separate carve-out.
- **Fallback discipline (mandatory, same defense-in-depth posture as the sibling plan's Layer A):** an
  embedding-call failure, timeout, or empty result set falls back to EXACTLY today's
  `resolve_skills_to_inject()` behavior — the router can only make selection better or identical to
  today, never worse or blocking.
- **F3 — accuracy verification:** reuse Part E's `run_skill_gate.py` harness + existing scenario files
  (`scripts/eval/skill_scenarios/*.json`) to score whether the router's additions match each
  scenario's expected skill — direct reuse of infrastructure already built for skill-content quality,
  now also proving router accuracy. This also serves as the re-run tracked as
  `D-SKILL-EVAL-RERUN-AFTER-LOOP-FIX` once the sibling plan's loop-fix has landed.

## Touch list
- **chat-service (Py):** `app/services/skill_registry.py` (`resolve_skills_to_inject()` — add the
  additive router union; `SkillDef` — add an optional synonym/keyword hint field, mirroring
  `tool_meta().synonyms`), `app/services/universal_skill.py` (F0, if extending universal rather than
  a new skill file), possibly a NEW `app/services/research_skill.py` (F0, if a dedicated skill reads
  more coherently), NEW skill-vector cache module (small, likely inside `skill_registry.py` or a
  sibling `skill_router.py`), tests: `test_skill_registry.py` (routing additive-union behavior,
  fallback-on-embed-failure, budget-ceiling respected).
- **scripts/eval:** reuse `run_skill_gate.py` + existing `skill_scenarios/*.json` for F3 — no new
  scenario authoring needed unless F0's new/extended skill needs its own scenario file (small,
  mirrors existing per-skill scenario shape).

## Fan-out execution slices (combined with the sibling tactical plan's fan-out round)

- **F0** — Group-A-style: fully independent of everything else in either plan (no embedding
  dependency, touches `universal_skill.py`/a new skill file only). Safe to run in parallel with
  EVERY slice in both plans, including the sibling plan's Group A and Group B.
- **F2** — sequenced AFTER the sibling plan's B1 (`sdks/python` cosine helper) AND B3
  (`embedding_client.py` + `tool_discovery.py` embeddings integration) land. Do not start F2 in
  parallel with B3 on the assumption they're unrelated — F2's per-turn routing call is designed to
  literally reuse the same embedding client instance/call B3 builds, not a separate one.
- **F3** — sequenced after F2 (needs the router live to measure it) AND after the sibling plan's
  Layer A retry-cap/loop fix lands (Part E's control-run signature was dominated by the loop bug,
  not routing — re-running F3 before that fix would still measure the old noise floor, not the
  router's real accuracy).

**Practical ordering for one combined fan-out round:** kick off F0 + sibling-plan Group A + sibling-plan
B1/B2 all in parallel immediately; sibling-plan B3 follows B1; this plan's F2 follows B3; F3 follows
both F2 and the sibling plan's stream_service.py fix (B2) being verified.

## Verify
- Unit: additive-union behavior (router never removes a static default), fallback-on-failure (embed
  timeout/error → identical output to pre-router behavior), budget-ceiling respected with the
  router's additions in play.
- **Live, via Part E's harness (mandatory — this is an accuracy claim, not just a doesn't-crash
  claim):** re-run `run_skill_gate.py` against the existing 37 scenarios (+ any new F0 scenario) with
  the router live; compare routing-accuracy signal against the pre-router baseline already recorded
  in `docs/eval/skill-authoring/2026-07-07-part-e-first-pass.md`.
- Cross-plan live-smoke: re-run the original 4-session repro (Vietnamese general web-search query, no
  book context) — confirm the router now surfaces the F0 skill on the `chat` surface and the turn
  resolves with a real answer, not a loop or a false "I can't do this."

## Out of scope (this pass)
- Per-surface confidence-threshold tuning (§13.2 RESOLVED: one global constant to start).
- Gating router rollout on full Part B skill-coverage completion (§13.4 RESOLVED: ship incrementally).
- A dedicated LLM-classifier router (Option A) or pure L1-directory-only router (Option B) — Option C
  (embedding-similarity) is the chosen mechanism; the other two are not built as fallback mechanisms,
  only as the ALREADY-EXISTING L1-directory (Option B's shape) staying in place underneath the router,
  per §13.1's "belt-and-suspenders" design note.
