# Spec: Skill-Authoring Contract + MCP Exposure Posture Standard

**Status (2026-07-07):** Parts A, B (Phase 1+2), C, D, and E's first pass are ALL SHIPPED — every part of this spec's original scope is now built. Part A (lint), Part B Phase 1+2 (all 5 domain skills, adversarially fact-checked), Part C (scope-size-adaptive exposure, threshold=20), Part D (hot-domain generic derivation, closes `D-SKILL-HOTDOMAIN-RUNTIME-WIRING`), Part E (live judge-gate eval, first pass run + report). See build notes below for each. **Part F (NEW, added same day, §12-15) — CLARIFY complete, decisions §13.1-13.4 all RESOLVED, ready for its own PLAN, not yet built:** an Intent→Skill Router — the deeper fix behind a same-day discussion (`docs/specs/2026-07-07-mcp-discovery-and-reliability-hardening.md` §0.5) concluding `find_tools`-style tool search is defense-in-depth, not a fix for "the agent has no procedure to follow for an ambiguous ask" — that lives one tier up, at skill selection. **Size:** XL (cross-service standard, touched every future domain skill); Part F alone is its own XL (first embedding call site in chat-service).

**Part A build note (2026-07-07):** building the lint (§4) immediately found 3 more real, live instances of the bug this spec exists to prevent — evidence the problem is broader than the single plan_forge case §1 originally scoped from:
1. **`knowledge_skill`'s audit entry in §1(B) was WRONG.** It claimed direct availability of `kg_*`/`memory_*` tools ("Use `kg_graph_query`... for Y") exactly like `plan_forge` claimed `plan_*` — not a softer "search first" pattern as originally assessed. Its `hot_domains` is now honestly declared `{"knowledge"}`; the runtime doesn't fulfill that yet (neither `_BOOK_SCOPED_HOT_DOMAINS`/`_STUDIO_HOT_DOMAINS` include it, and it can't be a small permission_mode-style patch — `knowledge` auto-injects on the universal chat surface too, which hot-seeds nothing by design) — **tracked as Part D's job, not fixed in Part A.**
2. **`glossary_skill.py` referenced 7 tools already `_meta.visibility:"legacy"`-tagged** by the 2026-07-06 CRUD-consolidation spec (`glossary_book_create/patch/delete`, `glossary_user_create/patch/delete`, `glossary_propose_new_entity`) — the skill prose was never updated when those tools were superseded. Fixed: swapped to `glossary_ontology_upsert`/`glossary_ontology_delete`/`glossary_propose_entities`. This is the CAT-4 lockstep gap (2026-07-06 spec §8.12) manifesting one layer up, at the skill layer instead of the discovery layer — the new legacy-reference lint (§4) now guards this permanently.
3. **`GROUP_DIRECTORY`'s `"knowledge"` domain matched NOTHING in `find_tools(group="knowledge")` or any hot-domain set** — its real tools carry literal prefixes `kg_`/`memory_`, never `knowledge_`, and the group/hot-domain filters compared the literal prefix against the domain name directly. Fixed with a small `_DOMAIN_ALIASES`/`_domain_of()` resolution layer (`tool_discovery.py` + `find-tools.ts`, kept in lockstep) — the third instance this session of the "GROUP_DIRECTORY description says X, the matching mechanism doesn't actually reach X" bug class (after the "story"/"composition" text fixes earlier the same day).

All fixes verified: chat-service 1134/1134, ai-gateway 142/142.

**Part B build note (2026-07-07):** shipped `composition_skill.py` + `translation_skill.py` (56-tool and 12-tool inventories researched from the real MCP server registrations, not guessed — every tool name verified by the skill-claims lint, zero hallucinated/stale names). Building it surfaced two more structural gaps beyond what §1/§4 anticipated:
1. **A pure-studio turn (studio_context set, editor_context/book_context absent) fell through to the generic "chat" surface in the SKILL system** (`_surface_key`/`resolve_skills_to_inject` had no `studio` concept at all), even though `surface_hot_domains` already treated studio as independent and hot-seeded glossary+composition+story there. Fixed: `studio: bool` threaded through both, additive to editor/book_scoped (not exclusive) — this ALSO retroactively fixed glossary_skill's visibility on pure-studio turns, not just unblocked composition_skill.
2. **The curated-mode hot-domain union (`tool_surface.py`) only had two hand-authored branches (glossary's gate, plan's carve-out)** — pinning `translation` (never hot on any surface) or `composition` on a non-studio surface would have re-hit the exact plan_forge seeding gap. Generalized into one loop over `pins.effective_skills` unioning each pinned skill's `hot_domains`, with explicit `covered_domains` tracking so no domain is ever double-budgeted (the review-impl HIGH bug class, guarded against by construction this time). `translation_skill` and `composition`-off-studio are curated-pin-only (never auto-injected) — no change to any surface's DEFAULT behavior.

Also found + fixed in the same pass (both real, pre-existing staleness, found because the lint made them visible): `workflow_skill.py` referenced `chapter_publish`/`chapter_save_draft` — missing their `book_` prefix, the real tools are `book_chapter_publish`/`book_chapter_save_draft` — and its translate step, now redundant with `translation_skill`'s detail, trimmed to a one-clause pointer (§8b.6).

All fixes verified: chat-service 1142/1142.

**`/review-impl` (2026-07-07) — 8 findings, all fixed:** a cold-start adversarial pass (2 sub-agents fact-checking every falsifiable claim in `composition_skill.py`/`translation_skill.py` against the real Python MCP server code, `services/composition-service/app/mcp/server.py` + `services/translation-service/app/mcp/server.py`) found the lint passing does NOT mean the prose is factually accurate — it only checks a named tool exists in the right domain, never what the tool actually does. Content fixes: (1) `composition_motif_archive` was taught as having "no restore" — wrong, `composition_motif_patch(status="active")` un-archives it (canon rules genuinely have no restore; motifs are different, the skill wrongly generalized from one to the other). (2) `translation_coverage` was taught as reporting glossary-staleness — it doesn't; only `translation_segment_status` does. (3) `translation_list_versions` was taught as returning a version's full body at `detail="full"` — it never returns body text at ANY detail level (metadata-only; there is no MCP tool that reads a translation's body). (4) `translation_job_control`'s `cancel`/`pause` were both taught as "reversible-in-effect" — only `pause` is (`undo_hint→resume`); `cancel` is terminal (`undo_hint: {"available": false}`). (5) `translation_start_extraction`'s reasoning_effort clamp was taught as something the agent should "report back... if clamped" — the tool's response never surfaces the clamped value in plaintext (only inside the opaque `confirm_token`); the instruction asked the model to do something impossible. Architecture fix: (6) the curated hot-domain union (`tool_surface.py`) gave each newly-pinned skill its OWN separate `HOT_SEED_TOKEN_BUDGET`-sized call — pinning 2 skills could seed ~2x the intended size, contradicting §9's own "one shared ceiling" invariant; fixed to collect every uncovered domain from every pinned skill FIRST, then ONE shared budgeted call (regression test: 2 skills pinned together stay within ~1 budget). Cosmetic: (7) `catalog.py`'s FE tool-picker `domain` field used the raw un-aliased prefix, showing `"kg"`/`"memory"` instead of `"knowledge"` — fixed to use `_domain_of()`. Doc-gap: (8) the lint's live-catalog "did-you-mean" check (§8b.2) was marked RESOLVED/deferred only in inline code comments, never a tracked SESSION_HANDOFF item — added as `D-SKILL-LINT-LIVE-CATALOG`.

All fixes verified: chat-service 1144/1144, ai-gateway 142/142 (re-confirmed independently, not just re-trusted).

**Part B Phase 2 build note (2026-07-07):** shipped `book_skill.py` (21 tools), `settings_skill.py` (12 tools), `jobs_skill.py` (5 tools) — the three domains named in §5's Phase 2 list, built via 2 parallel research+draft agents (book, settings) + one written directly (jobs, already fully read while scoping the fanout) against each domain's real MCP server source, mirroring Phase 1's process. All three are **curated-pin-only** (never in any auto-inject branch, matching translation's rollout posture) — none of `book`/`settings`/`jobs` was previously in any hot-domain constant, so this is strictly additive: zero default-turn behavior changes for any existing surface. Surfaces: `book` gets `{book, editor, studio}` (needs a book in context, like composition); `settings`/`jobs` get `{book, editor, studio, chat}` (account-level/cross-service, meaningful with no book open).

The skill-claims lint caught 2 real cross-domain mentions on first run (both legitimate contrastive references, not "call this directly" claims — added to `_ALLOWED_CONTRASTIVE_MENTIONS`, same pattern as translation's `jobs_get` entry): `book_skill.py` naming `story_search` to explain where it's catalogued (moot in practice — `story` is already unconditionally hot on every surface `book_skill` is visible on, via `_BOOK_SCOPED_HOT_DOMAINS`/`_STUDIO_HOT_DOMAINS`), and `jobs_skill.py` naming `translation_job_control`/`translation_job_status` to explain the "a domain may have its own separate job view" distinction. Also bumped `test_metadata_is_compact`'s line-count ceiling (6→9) — a real, expected consequence of 3 more genuinely-invested skills becoming visible on the book/editor surface's L1 catalog, not a smell.

Research turned up two facts worth flagging as their own evidence the fanout-then-fact-check process earns its cost: (1) book-service's three priced propose tools (`book_set_cover`/`book_media_generate`/`book_audio_generate`) do **not** execute generation on confirm — `confirm_action` returns `outcome: "open_ui"` and the human must trigger the actual run from the Studio app, unlike composition/translation's priced confirms which execute inline; a naive skill draft would very plausibly have gotten this backwards by pattern-matching the other two domains. (2) `settings_model_delete`, if the model being deleted is the caller's current per-capability default, silently clears that default via `ON DELETE CASCADE` (no refusal, no separate warning) — a real footgun the skill now warns the agent to flag to the user before confirming.

New regression tests: `TestPhase2Skills` (registration/hot_domains/catalog visibility/surface-split — book excluded from plain chat, settings+jobs included) and `test_curated_pin_of_phase2_skills_seeds_book_settings_jobs_domains` (proves the existing generic curated hot-domain union, already proven for composition/translation, covers these three with zero new per-skill wiring).

Verified: chat-service 1150/1150 (105 targeted skill/surface/catalog tests + full suite). ai-gateway untouched by this Phase (skills are chat-service-only per §8b.4) — no rerun needed, no files changed there.

**Adversarial fact-check (2026-07-07) — 3 parallel cold-start agents, one per skill, each independently re-deriving tool behavior from source before comparing to the prose (same process as Phase 1's 5-bug catch):**

- `jobs_skill.py` — **clean.** 8 load-bearing claims verified line-by-line (default `detail`, the identical anti-oracle shape across `jobs_get`/`_control`, no `jobs_resume`/`jobs_retry` tool exists, `_control` only ever forwards `cancel`/`pause`, pause-requires-multi-unit-kind is REAL enforced logic in `derive_control_caps` not just a docstring claim, `parent` campaign filtering, the `translation_job_control` cross-reference, `ui_watch_job` exists). No fixes needed.
- `settings_skill.py` — **clean.** 6 load-bearing claims verified against Go source + the `user_default_models` migration SQL (secret-redaction across all 12 tools, the 4-capability defaults whitelist + planner-validates-against-chat quirk, `provider_inventory` vs `list_providers` distinction, favorite/active independence, the delete-cascades-default FK behavior, `model_update`'s field whitelist excluding credential/secret). No fixes needed. Side-note: `settings_get_defaults`'s own Go tool *description* string is itself stale ("rerank or embedding" only, missing chat/planner) — the skill correctly followed the real capability-validation code instead of propagating that staleness; flagged here as a tiny pre-existing doc-drift in provider-registry-service, not a skill bug (not fixed this pass — cosmetic, own-service docstring, no functional effect).
- `book_skill.py` — **1 WRONG + 2 IMPRECISE, all fixed.** (1) WRONG: the file claimed `book_get_chapter` returns a `draft_version` an agent could read before its first `book_chapter_save_draft` — it doesn't; no `book_*` read tool ever exposes the live draft version (only a prior save/restore's own response does), and a stale-version 409 doesn't reveal the correct value either — a genuine dead end via chat tools for any chapter not freshly created this turn. Fixed: the skill now states this plainly, gives the one safe deterministic case (a chapter just created via `book_chapter_create` always starts at `base_version=1`), and instructs telling the user to open the editor once rather than guessing for any other chapter. (2) IMPRECISE: "trash is recoverable" didn't mention that recovery itself has no MCP tool (Studio-UI/REST-only) — fixed, added as a 3rd "what you cannot do" item and softened the trash-section wording. (3) IMPRECISE: bulk-create's filename-dedup only scans ACTIVE chapters, not trashed ones (a trashed-then-recreated same-named chapter isn't deduped) — fixed, one added sentence, no behavior implication beyond accuracy.

Re-verified after fixes: chat-service 1150/1150 (unchanged pass count — the fixes are prose-only, no new tool-name tokens, no lint/test impact).

**§3.3 measurement (2026-07-07, informational — see Part C):** queried `loreweave_auth.mcp_api_keys` (dev DB) for real scope-size data ahead of picking Option 4's threshold. 5 active keys, bimodal: 3 keys (`lazy-load-smoke*`) hold `{read, domain:book}` → resolves to 5 tools (book reads only); 2 keys (`opus-client`, `opus-mi-de` — almost certainly the external agent that filed the original bug report) hold ALL 4 tiers + all 8 domains → resolves to the full 161-tool `TOOL_POLICY` allowlist. No key in between was observed. With only 2 clusters this far apart, any threshold in the wide range ~6–160 classifies all 5 real keys identically — the data doesn't yet discriminate a precise number, but it does answer the qualitative question: real usage today is "tiny read-only smoke key" or "give the external agent everything," and the second case is exactly where lazy-hiding (and the already-shipped `invoke_tool` fix) earns its keep. PO picked **threshold = 20**.

**Part C build note (2026-07-07):** shipped `scopeToolCount(scopes)` + `DIRECT_LIST_TOOL_THRESHOLD=20` in `mcp-public-gateway/src/scope/tool-policy.ts`; wired into `public-mcp.controller.ts`'s `tools/list` branch as `directList = !wildcard && scopeToolCount(resolved.scopes) < 20`, passing `activated: undefined` to `filterListResponseText` on that path (a small-scope key skips the Redis/activation-store read entirely, not just the collapse). Key discovery: `filterListResponseText`'s existing `activated` param WAS ALREADY the collapse switch — without it, the function already just returns `filterTools(tools, scopes)`, the exact plain scope-filtered list the spec asks for — so no new list-filtering code was needed, only the branch condition. Confirmed (via `gateRequestBody`/`isToolAllowed`) that a directly-listed tool is immediately callable via a raw `tools/call` with zero further change — `requiresActivation` only gates the `invoke_tool`-unwrap path, never a raw call. Wildcard stays its own earlier branch per §8b.7 (never routed through `scopeToolCount`). `invoke_tool` stays advertised unconditionally on both branches (harmless if unused; a minor pre-existing description-string staleness — "calling the tool's name directly will not work," false on the new direct-list path — flagged as a followup nit, not fixed this pass). Verified: mcp-public-gateway 230/230 (7 new tests), `tsc --noEmit` clean on both `src` and spec configs.

**Part D build note (2026-07-07):** implemented the generic hot-domain derivation `surface_hot_domains()`'s design text promised in §4 (formalized as its own edge case in §8b.9) — replaced the 3 hand-authored constants (`_BOOK_SCOPED_HOT_DOMAINS`, `_STUDIO_HOT_DOMAINS`, `PLAN_HOT_DOMAINS`) with a single derivation: union the `hot_domains` of whichever skills `resolve_skills_to_inject` would inject BY DEFAULT (empty `enabled_skills`) on a surface, plus `story` (the one surface-level, not-skill-owned exception, kept as its own explicit constant with its original Dracula-eval justification comment preserved). **Deliberate, sign-off'd behavior change**: `knowledge_skill` already auto-injects on every non-admin surface and already honestly declared `hot_domains={"knowledge"}` (Part A) — that declaration is now HONORED, so "knowledge" is hot everywhere `knowledge_skill` is injected, including the universal/chat surface, which previously hot-seeded nothing. This closes `D-SKILL-HOTDOMAIN-RUNTIME-WIRING`. `tool_surface.py`'s curated-mode plan carve-out also now derives from `SYSTEM_SKILLS["plan_forge"].hot_domains` instead of the standalone `PLAN_HOT_DOMAINS` constant (one source of truth, removing the two-constants-must-agree drift risk the standalone constant carried — `PLAN_HOT_DOMAINS` deleted). Full regression pass per §8b.9: 4 tests in `test_tool_discovery.py` + 1 in `test_stream_service.py` needed updating (all 5 are the SAME expected "knowledge now hot" flip, documented inline with a shared docstring explaining why) — every other domain (glossary/composition/story/plan) is byte-for-byte unchanged from the old hand-authored constants, confirmed by the same tests. Added a token-budget regression test (`test_studio_seed_stays_bounded_with_knowledge_added`) proving the shared `HOT_SEED_TOKEN_BUDGET` ceiling still holds with a 4th domain competing for it (same `budget_names_by_tokens` mechanism, no new call site — it truncates the wider candidate set, it doesn't grow the cap). Verified: chat-service 1152/1152.

**Part E build note (2026-07-07) — first live pass, see full report [`docs/eval/skill-authoring/2026-07-07-part-e-first-pass.md`](../eval/skill-authoring/2026-07-07-part-e-first-pass.md):** built `scripts/eval/run_skill_gate.py` (a sibling of `run_quality_gate.py` — reuses its proven SSE-driving pattern, adds per-turn `book_context`/`editor_context`/`studio_context`/`enabled_skills` so a scenario can force the right surface+curated-pin, which the context-budget driver never needed). Authored 37 scenarios across 5 files (`scripts/eval/skill_scenarios/{composition,translation,book,settings,jobs}.json`, via 5 parallel fan-out agents each researching their own skill file, zero invented tool names — cross-checked). Rebuilt+ran the real chat-service stack against local `gemma-4-26b-a4b-qat`, then 5 independent judge Agents scored every scenario against its own self-contained `ground_truth` (absolute scoring, not A/B — there is no prior baseline for a brand-new capability). **Headline: zero hallucinated tool names across all 37 scenarios** — the failure mode this whole effort exists to prevent never occurred. A cross-cutting `find_tools`-loop-then-give-up pattern accounted for most of the FAIL/WEAK scores; a control run against the untouched, previously-shipped `glossary_skill` reproduced the identical signature, confirming it's a pre-existing model/infra characteristic, not a defect in this session's new skill prose — tracked as `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE` rather than chased or silently absorbed into a rushed prose edit. Two FAILs were a different, more interesting shape (the agent reached a conclusion that contradicted a rule the skill states) — flagged as suggestive, not conclusive on n=1 from a known-noisy local model, re-run tracked as `D-SKILL-EVAL-RERUN-AFTER-LOOP-FIX`.

**Part E follow-up (2026-07-08) — both deferred items RESOLVED, full report [`docs/eval/skill-authoring/2026-07-08-loop-flake-rootcause-and-rerun.md`](../eval/skill-authoring/2026-07-08-loop-flake-rootcause-and-rerun.md):** root-caused the loop-flake to TWO real, fixed bugs, not model noise alone. (1) `find_tools` silently degraded a missing/blank `intent` into a genuine zero-token search instead of a directive error — fixed (`find_tools_result()`). (2) The actual dominant cause: `is_curated()` derived curated-mode ONLY from `enabled_tools`, so the REAL frontend's skill-only pin path (`useContextRack.ts` → `enabled_skills` alone, `enabled_tools` always `[]`) never entered curated mode — a pinned skill's PROMPT was injected (confidently telling the model to call its tools) but its TOOLS were never hot-seeded, live-observed causing the model to falsely deny real, skill-documented tools exist across all 5 skill files. Part B's own tests never caught this because every one of them co-pinned a dummy `enabled_tools` entry alongside the tested skill, accidentally masking the exact path production uses — fixed (`is_curated()` now OR's `enabled_skills`; a second identical short-circuit in `effective_enabled_tools()` removed too). Clean re-run (Qwen2.5 7B, both fixes live): zero hallucinated tool names (even stronger than the first pass), the dominant false-tool-denial pattern gone for 3/5 skills and much reduced for the other 2 (residual cause: composition's ~56-tool domain genuinely exceeds the hot-seed token budget by design — `find_tools` search itself verified correct, the gap is the small model not always retrying via search before giving up). Two new patterns surfaced that are NOT skill/platform defects — a "real tool call then 0 chars to the user" pattern (matches this repo's pre-existing `reasoning-model-burns-max-tokens-before-real-answer` lesson) and non-convergent retry loops on a failing lookup — both model-capability/reasoning-budget characteristics, not tracked as new spec-scoped defer rows. chat-service 1158/1158.

**Origin:** `docs/plans/2026-06-29-public-mcp-lazy-tool-loading.md`'s 2026-07-07 amendment (the `invoke_tool` fix) + the same day's Plan/Ask-mode tool-seeding bugfix, both root-caused to the same underlying gap: **a skill's prose can promise a tool the seeding/exposure layer never actually delivers, and nothing catches that until a live agent (or an external bug report) hits it.** User's framing: tool count will keep growing, skills are currently "làm cho có" (built to exist, not truly invested), and skills should ship as **workflow definitions + tool-use guides**, not bare "here's MCP, go find_tools yourself."
**Related:** `docs/specs/2026-07-06-tool-catalog-simplification.md` (Part A group-directory + CAT-4 legacy-visibility — SHIPPED, this spec builds on it, does not redo it), `docs/standards/mcp-tool-io.md`, `docs/plans/2026-06-29-public-mcp-lazy-tool-loading.md`, [[mcp-lazy-toolload-needs-invoke-facade]]

---

## 1. Problem (grounded)

Three concrete, evidence-backed gaps, found in one session (2026-07-07):

**(A) A skill's claims are not mechanically checked against what's actually seeded.** `plan_forge_skill.py` instructed the model to call `plan_propose_spec` as literal step 1 ("Act — do NOT narrate... emit the tool call in the SAME turn"), but `tool_discovery.py`'s hot-domain sets never included a `"plan"` domain — the skill and the seeding layer drifted apart with **no test connecting them**. This is a *general* failure mode, not a one-off: any skill's prose can name a tool whose domain isn't (or stops being) hot-seeded, and nothing in the repo would catch it before a live agent — or an external user — hits the dead end. `docs/specs/2026-07-06-tool-catalog-simplification.md` §8.12 already names the sibling risk ("GROUP_DIRECTORY drift... silently has no discovery pointer") and proposes a lint for *that* layer; this spec extends the same discipline to the **skill layer**, which that spec didn't touch.

**(B) Skill coverage is narrow and uneven relative to tool-domain count and complexity.** Of 11 tool-name-prefix domains in `GROUP_DIRECTORY` (`glossary, story, composition, knowledge, translation, book, jobs, catalog, registry, settings, plan`), only **3** have a dedicated skill with an explicit tool-use guide + workflow definition (`glossary_skill`, `knowledge_skill`, `plan_forge_skill` — all genuinely well-invested: concrete rules, ordering, error-recovery, trust-boundary). The rest fall back to `universal_skill`'s generic "call find_tools, then figure it out" plus, for a handful of cross-cutting concerns, `workflow_skill.py`'s short ordering fragment (book→translate→glossary→wiki, draft→publish, async "started not done"). Concretely:

| Domain | Tool count (approx, per 2026-07-06 spec + TOOL_POLICY) | Dedicated skill? | Current guidance |
|---|---|---|---|
| glossary | 47 | ✅ `glossary_skill` | Deep — ontology shaping, batch-vs-single, confirm flow, trust boundary |
| knowledge | 30 | ✅ `knowledge_skill` | Deep — memory-vs-graph split, temporal reads, triage, confirm flow |
| plan (PlanForge) | 8 | ✅ `plan_forge_skill` | Deep — propose→refine→validate→compile, outcome honesty |
| **composition** (non-plan: outline/scene/canon/motif) | **~35+** | ❌ none | Generic `universal_skill` + `find_tools` only — the SECOND-largest domain by tool count has zero dedicated guidance |
| translation | 12 | ❌ none | One ordering sentence in `workflow_skill.py`; nothing on versions, coverage, retranslate-dirty, segment status |
| book | ~12 | ❌ none | Two thin sentences (draft→publish) in `workflow_skill.py`; nothing on chapter revisions, bulk create |
| jobs | 5 | ❌ none | One sentence ("say started, call ui_watch_job") — no jobs_cancel/pause guidance |
| settings | ~8 | ❌ none | Nothing — BYOK provider/model registration has real footguns (default model, favorites) untaught |
| story | 1 (hot-seeded) | ❌ none | Never explicitly taught even though it's HOT on every book-scoped surface |
| catalog | 2 | ❌ none | Nothing (low-complexity, likely acceptable) |
| registry | small | ❌ none | Nothing (admin-facing, likely acceptable) |

As tool count grows (the user's explicit concern), this gap widens — every new domain defaults to the weakest tier (bare discovery) unless someone deliberately invests, and there is no process that flags "this domain crossed a complexity threshold, it needs a skill now."

**(C) The external MCP edge's progressive-disclosure design fights the modern client's own native mechanism.** Researched 2026-07-07 (see prior turn's sourced summary): Anthropic's **Tool Search Tool** (`defer_loading: true` + `tool_search_tool_regex/bm25`) is the sanctioned client-side answer to "too many tools," and it is **enabled by default in Claude Code** — including for tools sourced from an MCP server, via the MCP connector's `default_config.defer_loading`. That mechanism expects the **server to expose its real tool list**; it does its own thinning on top. `mcp-public-gateway`'s design instead hides almost everything server-side (`find_tools`+`confirm_action` only, everything else gated behind session-scoped "activation") — for a Claude-based external agent (the exact client that filed the bug report that started this investigation), this is redundant with, and until the `invoke_tool` fix, actively incompatible with, functionality the client already provides. `notifications/tools/list_changed` — the mechanism the original design leaned on — is confirmed **not universally supported** even among first-party Anthropic surfaces (Claude Desktop does not support it), so the whole "hide, then notify" shape is fragile by construction, independent of any one bug.

---

## 2. Goals / Non-goals

**Goals:**
- Make a skill's tool-name claims **mechanically verifiable** against the seeding layer — close the exact bug class (A) permanently, for every current and future skill, not just `plan_forge`.
- Establish a **skill-authoring bar**: every tool domain above a complexity threshold gets a skill that is a workflow definition + tool-use guide (mirroring `glossary_skill`/`knowledge_skill`/`plan_forge_skill`'s existing quality), not bare `find_tools` delegation.
- Reconsider `mcp-public-gateway`'s default exposure posture in light of Tool Search Tool / `defer_loading`, without regressing the security-driven scope filtering (anti-oracle, least-privilege) that is a separate, non-negotiable concern from the token-savings concern.
- Give skill authoring a **repeatable quality gate** (eval against a real model), not a write-once-and-forget artifact.

**Non-goals (this pass):**
- Re-litigating `docs/specs/2026-07-06-tool-catalog-simplification.md`'s Part A/B/C/D (group directory, search unification, glossary CRUD consolidation) — that work is shipped and this spec builds on it, not around it.
- Composition/knowledge/translation tool-count *reduction* (CRUD consolidation like glossary's) — a separate, already-flagged follow-on in that spec's §6. This spec is about *skill coverage*, not tool-count surgery.
- Adopting Anthropic's `defer_loading` literally inside chat-service's own OpenAI-style tool loop — chat-service serves arbitrary BYOK/local models (Gemma, etc.) via a manual function-calling loop, not the Claude Messages API, so that specific mechanism doesn't apply there. Chat-service's existing hot-domain + token-budget + `find_tools` design is already the right SHAPE of solution for that surface (confirmed against research — this is essentially a hand-rolled equivalent); this spec's chat-service work is about the skill layer sitting on top of it, not replacing the seeding mechanism.

---

## 3. Decisions requiring PO sign-off before PLAN

### 3.1 Skill-claims lint — mechanism choice

How should "a skill's prose names tool X ⇒ X's domain must be in the skill's declared hot-seed" be enforced?

- **Option A (recommended): a new `hot_domains: frozenset[str]` field on `SkillDef`, cross-checked by a test.** Each `SkillDef` (glossary, knowledge, plan_forge, and every new skill) declares which domain(s) it requires hot. A test extracts tool-name-shaped tokens from the skill's prompt body (regex over the live catalog's actual names — a token that IS a real catalog tool name, not a heuristic guess), and asserts every such name's domain-prefix is in the skill's declared `hot_domains` OR the skill's prose explicitly instructs "search with find_tools" for that name (an allowlist of intentionally-lazy mentions). Mirrors the CAT-4 drift-lock test already in the codebase (`docs/specs/2026-07-06-tool-catalog-simplification.md` §8.12) — same shape, new invariant.
- **Option B: derive hot-domains from the prose automatically** (parse tool names out of the prompt, treat their domains as required-hot with no separate declaration). Less authoring overhead, but silently changes behavior if a skill's WORDING changes (e.g., mentioning a tool only as a "don't confuse this with X" aside would wrongly force it hot) — less precise, more surprising.
- **Option C: do nothing mechanical, rely on human review.** Rejected — this is exactly what already failed for `plan_forge_skill`; a human reviewer missed it once, will miss it again as the catalog grows.

**Recommendation: Option A.**

### 3.2 Skill coverage — which domains get a dedicated skill, and when

The domain table in §1(B) is the input; the threshold needs a PO call. Recommended heuristic: a domain earns a dedicated skill when **any** of:
1. Tool count ≥ ~10 (crosses "the model needs an ordering/pattern guide, not just a list"), or
2. It has a multi-step, order-dependent, or confirm-gated workflow (create→confirm→apply style) that a bare tool list can't convey, or
3. It has already caused a live confusion/misfire (this session's plan-mode bug, or a future eval finding).

Under this heuristic: **`composition` (non-plan) and `translation` are Phase-1 candidates** (both clear (1) and (2)); `book`, `settings`, `jobs` are Phase-2 (moderate tool count, real but smaller workflow surface); `story`, `catalog`, `registry` stay in `universal_skill`'s generic bucket (small enough that a dedicated skill's overhead likely isn't worth it) unless an eval finding says otherwise.

**Open for PO:** confirm this prioritization, or reorder. Also: should `workflow_skill.py`'s existing short cross-cutting ordering fragment be folded into whichever new skills subsume its content (book/translation), or stay a separate always-on fragment? Recommend keeping it separate — it's genuinely cross-domain glue ("do step 2 only after step 1's job finishes"), not owned by any one domain.

### 3.3 `mcp-public-gateway` exposure posture — how much to relax hiding

Four options, weighed against the research:

- **Option 1 — status quo + `invoke_tool` (already shipped).** No further work. Correct and safe, but duplicates/conflicts with Claude Code's native Tool Search Tool for Claude-based external agents, and stays maximally token-expensive in round-trips (discover → activate → invoke, 2 hops) for every client regardless of how small the key's actual scope is.
- **Option 2 — client-identity-conditional exposure.** MCP's `initialize` request carries a client-declared `clientInfo: {name, version}`; the edge could expose the full in-scope list directly to a client that self-identifies as `claude-code` (letting its native Tool Search Tool do the thinning) and keep the lazy-hide path for everything else. Risk: `clientInfo` is client-asserted, not verifiable — but that's fine here, since trusting it only affects a UX/token-cost choice, not a security boundary (a lying client just gets the safe, already-working lazy path).
- **Option 3 — drop server-side hiding for in-scope tools entirely; keep `find_tools`/`invoke_tool` as an aid, not a gate.** Simplest, matches how `ai-gateway`'s own internal `/mcp` already behaves (full catalog, `find_tools` as a convenience search). Regresses the token-savings goal for a broad-scope key talking to a non-Claude client.
- **Option 4 (recommended) — scope-size-adaptive.** If a resolved key's in-scope tool count is small (e.g., under some threshold — recommend measuring the median/p90 real key scope size to pick this, not guessing), expose the filtered list directly (no lazy-hide — the token cost of a small list was never the problem). Only fall back to the `find_tools`/`invoke_tool` lazy path when the in-scope count is genuinely large. Client-agnostic (no reliance on asserted identity), deterministic, and directly targets the actual cost driver (large scope) instead of applying the same aggressive hiding to every key regardless of size.

**Open for PO:** pick an option (recommend 4, optionally layered with 2 as a cheap addition once 4 ships). Needs a threshold number — propose measuring real key-scope sizes from `auth-service`'s `mcp_api_keys` before picking one, rather than guessing.

### 3.4 Skill quality/eval loop — invest now or defer

The repo already has a working quality-gate harness (`scripts/eval/run_quality_gate.py` + `judge_prompt.md`, built for the Context Budget Law effort) that scripts a conversation against a real target model and scores it against a rubric. Reusing it for skill authoring means: every NEW or materially-CHANGED skill runs a small scenario set through the harness before being marked shipped (mirrors how `plan_forge_skill` and the glossary/knowledge skills were already informally tuned via live testing, per session history).

**Open for PO:** build this as a required BUILD-phase step starting with Phase-1 skills (composition, translation), or defer until Phase-1 skills are drafted and revisit? Recommend: required starting Phase-1, since retrofitting an eval step onto already-shipped skills is more friction than building it in from the start.

---

## 4. Design — Part A: Skill-Authoring Contract

Extend `SkillDef` (`skill_registry.py`):

```python
@dataclass(frozen=True)
class SkillDef:
    code: str
    label: str
    surfaces: frozenset[str]
    prompt_loader: Callable[[], str]
    description: str = ""
    # NEW — the domain prefix(es) (GROUP_DIRECTORY keys) this skill's prose names
    # tools from directly. Must be hot-seeded whenever this skill is active, or the
    # skill's "call X directly" instructions point at a tool the model can't see —
    # this is the exact class of bug plan_forge shipped with (2026-07-07).
    hot_domains: frozenset[str] = frozenset()
```

Wire `hot_domains` into `surface_hot_domains()`/`discovery_seed_for_surface()` generically: instead of each mode/surface hand-listing which domains it needs hot (today's `_BOOK_SCOPED_HOT_DOMAINS`, `_STUDIO_HOT_DOMAINS`, `PLAN_HOT_DOMAINS` — three hand-maintained constants, the exact shape that already caused one miss), derive the hot set from **which skills are actually injected this turn** (`resolve_skills_to_inject()`'s output) unioned with any surface-level always-hot domains (e.g., `story`, kept hot per the measured Dracula-eval justification independent of any skill). This collapses "three hand-authored domain-set constants that must independently track which skills exist" into "one lookup from the skill registry," removing an entire class of future drift, not just today's instance.

New test: `test_skill_registry.py::test_every_skills_named_tools_are_in_its_hot_domains` — for each `SkillDef`, extract catalog-real tool names from `prompt_loader()`'s text, assert each name's domain is in `hot_domains` (or the name appears only inside a sentence matching an allowlisted "search for this" phrasing pattern, e.g. adjacent to `find_tools`).

## 5. Design — Part B: Skill Coverage Expansion

Phase 1 (per §3.2, pending confirmation): draft `composition_skill.py` and `translation_skill.py`, matching the depth/shape of `glossary_skill.py` — concrete tool-selection rules, ordering, confirm-flow, common-mistake callouts, trust boundary. Each declares its `hot_domains` (Part A) and ships with an eval pass (Part E) before merge.

Phase 2: `book_skill.py`, `settings_skill.py`, `jobs_skill.py` (or, if any turns out thin enough once drafted, folded as a section into `workflow_skill.py` rather than a standalone skill — decide per-domain once drafted, not upfront).

Each new skill also needs: a `surfaces` declaration (which chat surfaces see it — likely `book`/`editor` for composition/translation, matching the existing pattern), an `L1` one-line `description` for the always-on skill-metadata block, and a `GROUP_DIRECTORY` cross-check (its named tools' domains must already have `GROUP_DIRECTORY` entries — they do, per the 2026-07-06 spec).

## 6. Design — Part C: `mcp-public-gateway` Exposure Posture

Per §3.3's chosen option. If Option 4 (scope-size-adaptive): add a `scopeToolCount(scopes)` helper (count of `TOOL_POLICY` entries the key's scopes satisfy — a pure function over the existing allowlist, cheap), threshold it against a config constant, and branch `filterListResponseText`'s activation-collapse: below threshold → skip the collapse (return the full scope-filtered list, as `filterTools` already produces before the lazy-loading layer was added); at/above threshold → today's collapse + `invoke_tool` path, unchanged. This is additive to the already-shipped `invoke_tool` mechanism — small-scope keys stop needing it at all; large-scope keys keep using it exactly as today.

## 7. Design — Part D: Canonical Taxonomy Consolidation

`GROUP_DIRECTORY` already exists in 2 lockstep copies (`tool_discovery.py`, `find-tools.ts`, CAT-4-tested). Part A adds a THIRD consumer (`SkillDef.hot_domains`, referencing the same domain names). No new drift risk beyond what the existing CAT-4 discipline already guards, provided the new skill-claims test (Part A) is added to the SAME "must change together" doc comment / lockstep convention `tool_discovery.py`/`find-tools.ts` already carry. No code duplication needed — `hot_domains` values are just domain-name strings already validated by construction (the extraction lint in Part A fails if a name maps to an undeclared domain).

## 8. Design — Part E: Skill Quality/Eval Loop

Per §3.4. A new `scripts/eval/skill_scenarios/<skill_code>.json` per skill (mirrors `context_budget_scenarios.json`'s shape) — a handful of realistic user turns exercising the skill's core flow (e.g., for `composition_skill`: "add three outline nodes for act 2", "why did my canon rule get rejected"). Run through `run_quality_gate.py` against the repo's standard eval model (`google/gemma-4-26b-a4b-qat`, per project convention) before a new/changed skill ships; judge rubric scores tool-selection correctness + adherence to the skill's stated rules (batch-vs-loop, confirm-flow, ordering). A failing scenario is a BUILD-phase blocker, same as a failing unit test.

---

## 8b. Edge cases (self-review pass, 2026-07-07)

Grouped by which Part they land on; each has a decided resolution, not left open — matches this repo's mandatory second-pass-review convention (see `docs/specs/2026-07-06-tool-catalog-simplification.md` §8 for the precedent this mirrors).

**Part A — skill-claims lint**

8b.1 **A false-positive risk: field names that LOOK like tool names.** The extraction regex must match against the LIVE CATALOG's actual tool-name set, not a generic snake_case pattern — otherwise field names the prose also uses (`base_version`, `confirm_token`, `kind_code`) would wrongly count as "tool references." Already specified in §4 ("a token that IS a real catalog tool name, not a heuristic guess") — restated here because it's the single easiest way to implement this lint wrong.

8b.2 **The lint as specified only checks the FORWARD direction** (a real catalog name found in prose ⇒ its domain must be hot) — it does **not** catch a STALE or TYPO'D tool-name-shaped token (a renamed/removed tool, or a simple misspelling) that no longer matches anything in the live catalog, because a non-matching token is invisible to a "check every match" lint. **Resolution:** add a second, independent check — any backtick-quoted or otherwise tool-name-shaped token in a skill's prose (matches `^[a-z]+(?:_[a-z0-9]+)+$` AND its prefix is a known `GROUP_DIRECTORY` domain) that is **not** found in the live catalog at all fails the test with a "did you mean" hint (nearest catalog name by edit distance) — this is the skill-prose equivalent of CAT-4's "an orphaned domain silently degrades discovery" concern (§8.12 of the 2026-07-06 spec), applied one layer up.

8b.3 **A skill referencing a `legacy`-tagged tool (CAT-4) is a distinct bug the hot-domain check alone wouldn't catch** (a legacy tool's domain might still be hot for an unrelated reason, satisfying the domain check while the specific tool reference is still wrong). **Resolution:** the lint also calls `is_legacy_tool()` on every matched catalog name and fails if any match is legacy — a fresh skill must never point the model at a superseded tool.

8b.4 **This is chat-service-only; no `find-tools.ts` mirror is needed for Part A itself** — skills are a chat-service concept (ai-gateway doesn't inject skills). `find-tools.ts`'s `GROUP_DIRECTORY` stays the thing `hot_domains` values are validated against (domain names must exist there), but no new TS file/logic is required.

**Part B — composition_skill / translation_skill**

8b.5 **`composition_skill` must not overlap `plan_forge_skill`'s territory.** `composition_*` tools (outline nodes, scenes, canon rules, motifs, direct prose writes) and `plan_*` tools (PlanForge's propose→validate→compile spec flow) are DIFFERENT prefixes, different workflows, and can be simultaneously hot (a studio surface in Plan mode has both). `composition_skill`'s `hot_domains` must be `{"composition"}` only — never `"plan"` — and its prose should explicitly cross-reference PlanForge ("for planning the novel's overall system/arcs, that's a separate flow — see PlanForge") so the model doesn't conflate "write this scene now" with "plan the whole novel-system first."

8b.6 **`translation_skill` will substantially overlap `workflow_skill.py`'s existing one-line translate step** ("Translate — start translation on those chapters... priced job: propose → confirm_action → then ui_watch_job"). Left as two independent teaching sites, they can drift (exactly this session's root-cause pattern, one level up). **Resolution:** once `translation_skill` ships, `workflow_skill.py`'s translate step is trimmed to a ONE-CLAUSE pointer ("see the Translation skill for the propose→confirm→watch flow and version/coverage tools") rather than duplicating the detail — `workflow_skill.py` keeps owning cross-domain ORDERING (translate-after-chapters-exist), `translation_skill` owns the domain's own tool-use detail. Track this trim as part of the same BUILD slice that ships `translation_skill`, not a separate follow-up (so the two never coexist in a drifted state even temporarily).

**Part C — scope-size-adaptive exposure**

8b.7 **The wildcard (`*`) dev/smoke key is untouched by this change** — it already gets the full unfiltered list via `filterListResponseText`'s existing early return, independent of `scopeToolCount()`. The new size-adaptive branch only applies to a real, scope-bounded key; implementation must keep the wildcard check as a distinct, earlier branch (not folded into the size comparison, where a `*` scope's "count" would be meaningless).

8b.8 **A key's scope changing mid-session (edited by its owner) cannot desync the REAL security gate** — `scopeToolCount()` only decides which EXPOSURE MODE a `tools/list` response uses (direct-list vs. lazy-collapse); `isToolAllowed`/`gateRequestBody` re-check the CURRENT scope on every `tools/call` regardless of which list-mode was used to advertise it. Worst case of a stale size-classification: a shrunk-scope key still gets the "small scope, show full list" treatment for one stale `tools/list` response until its next call — cosmetic, not a security gap. State this explicitly at BUILD time so a reviewer doesn't mistake it for a scope-widening bug.

**Part D — hot-domain derivation refactor**

8b.9 **This refactor changes WHEN today's auto/non-curated hot-seed is computed** — today `_BOOK_SCOPED_HOT_DOMAINS`/`_STUDIO_HOT_DOMAINS` are unconditional given surface flags alone (glossary is hot on every book-scoped turn regardless of skill-injection state); after Part D, the hot set derives from which skills `resolve_skills_to_inject()` actually returns this turn. These should coincide in EVERY case that matters today (glossary auto-injects by default on book-scoped surfaces exactly when today's constant would mark it hot) — but this is a behavior-sensitive refactor, not a pure addition. **Resolution:** BUILD this behind a full before/after regression pass — enumerate every existing test asserting a specific hot-seed name set (`test_tool_discovery.py`, `test_tool_surface.py`, `test_plan_mode.py`'s new seeding tests from this session) and confirm each still passes UNCHANGED post-refactor before considering Part D done; any test that needs to change is a signal the refactor altered real behavior, not just its mechanism, and needs its own sign-off.

---

## 9. Governance / contract constraints (must hold)

- Every new skill still obeys `docs/standards/mcp-tool-io.md`'s existing rules (it teaches tools, doesn't redefine their contracts).
- `hot_domains` additions must not blow the existing `HOT_SEED_TOKEN_BUDGET`/`scale_by_window` ceiling — the review-impl HIGH finding from 2026-07-07 (double-budgeting when a new domain is added on top of an existing shared union) is the exact failure mode to avoid; any new skill's hot-domain addition must be verified against the SAME shared budget, not a separate carve-out, unless the shared-union gate genuinely doesn't apply (mirrors the corrected pattern in `tool_surface.py`).
- `mcp-public-gateway` Part C changes must not weaken the scope/anti-oracle guarantees (`isToolAllowed`, `filterTools`) — the exposure-posture change is strictly about WHEN to collapse an already-scope-filtered list, never about widening what's in it.
- Any FE surface (Context Budget Inspector, skill catalog UI) that lists skills/domains must stay in sync — reuse existing `GET /v1/chat/skills/catalog` (`skill_registry.catalog_items()`), extend if `hot_domains` needs FE visibility (e.g., a debug view), not a new endpoint.

---

## 10. Rollout sequencing (proposed)

0. **PO sign-off on §3.1–§3.4.**
1. Part A (skill-authoring contract + lint) — cheapest, highest-leverage, closes the exact bug class permanently. Ship first, independent of everything else.
2. Part D (fold the 3 hand-authored hot-domain constants into a skill-registry-derived lookup) — natural follow-on to Part A, removes the constant-drift risk at its root.
3. Part B Phase 1 (`composition_skill`, `translation_skill`) + Part E (eval loop) together — per §3.4's recommendation, build the eval step in from the start.
4. Part C (`mcp-public-gateway` posture) — independent track, can run in parallel with 1-3; needs the real key-scope-size measurement first (§3.3).
5. Part B Phase 2 (`book_skill`, `settings_skill`, `jobs_skill` or folded fragments) — once Phase 1's pattern is validated.

---

## 11. Open questions — ALL RESOLVED 2026-07-07

1. ~~§3.1~~ — **RESOLVED: Option A.** Declared `hot_domains: frozenset[str]` on `SkillDef` + a drift-lock test extracting catalog-real tool names from each skill's prose and asserting their domain is declared hot (mirrors the CAT-4 pattern).
2. ~~§3.2~~ — **RESOLVED: `composition` + `translation` together, Phase 1.** Both are built in the same pass (not composition-only-then-translation) — the two largest under-invested domains, tackled as one coherent milestone per this repo's "classify the whole EFFORT" convention.
3. ~~§3.3~~ — **RESOLVED: Option 4, scope-size-adaptive.** Measure real key-scope sizes from `auth-service`'s `mcp_api_keys` before picking the threshold (§6's `scopeToolCount()` helper) — do not guess a number upfront.
4. ~~§3.4~~ — **RESOLVED: deferred, not blocking.** Write the Phase-1 skills (composition, translation) first; build/run the eval loop (Part E) as a follow-up evaluation pass afterward, not a Phase-1 build-gate. `scripts/eval/run_quality_gate.py` already exists and is reusable when that pass happens — this only changes SEQUENCING (skill prose first, eval after), not whether eval happens at all.

**Sequencing note (supersedes §10 step 3):** since eval is now a follow-up rather than built-in-from-the-start, Part B Phase 1 (composition_skill + translation_skill) ships as its own milestone; Part E (eval harness scenarios for these two skills) is a separate, subsequent milestone against the shipped prose — not a blocking co-requisite.

---

## 12. Problem — Part F: Intent→Skill Router (NEW, added 2026-07-07, DRAFT/CLARIFY)

Added same-day, after Parts A-E above shipped, from a separate discussion tracked in
[`docs/specs/2026-07-07-mcp-discovery-and-reliability-hardening.md`](2026-07-07-mcp-discovery-and-reliability-hardening.md)
§0.5. That spec's own Layer A fix (harden `find_tools`: true enumeration + retry-cap) was reframed
mid-discussion as **defense-in-depth, not the fix** — `find_tools`-style search can only answer "is
there a tool that might match these words," never "given this ambiguous ask, what procedure should I
follow." Those are different problems (existence-discovery vs. procedure-selection); the second one
lives at the **Skill** tier this spec already owns, not the tool-search tier.

**The architecture already has the right shape, just an incomplete rollout — confirmed by code, not
assumed:**
- `SkillDef`/`SYSTEM_SKILLS` (`skill_registry.py`) is a real Skill tier; `plan_forge_skill` is already
  a genuine first-class **Workflow** (propose→self_check→interpret_feedback→apply_revision→
  review_checkpoint→handoff_autofix→validate→compile), not just a tool-use guide. Parts A/B/D/E above
  are actively closing the **coverage** gap (§1(B)'s table — most domains still thin) and the
  **claims-drift** gap (Part A's lint). Neither closes the gap below.
- **The routing gap, not yet addressed anywhere in Parts A-E:** `resolve_skills_to_inject()`
  (`skill_registry.py:258-269`) takes **zero intent/query-text parameter** — its own module docstring
  states this plainly: *"filters by session pins + **surface flags**"* (`skill_registry.py:4`). Skill
  selection today is 100% structural (`editor`/`book_scoped`/`studio`/`admin`/`permission_mode`), never
  a function of what the user actually typed.
- **Concrete failure this causes, traced to a specific orphaned capability:** `glossary_web_search`/
  `glossary_deep_research` (general-purpose web research, no book required) live only inside
  `glossary_skill`, whose `surfaces=frozenset({"book", "editor"})` (`skill_registry.py:90`) — **not**
  `"chat"`. On the universal surface (no book open), the ONLY skill visible is `universal_skill`
  (`surfaces={"chat"}`, description: *"General multi-step task driver: find and use the right tools to
  fulfil the request"* — pure generic `find_tools` delegation). A general web-research ask on that
  surface has no skill to route to at all, even at the cheap L1 metadata tier (`skill_metadata_block()`,
  `skill_registry.py:210-229` — itself already a working "cheap menu, model self-selects" primitive,
  just currently gated by `surfaces` the same way the L2 body is). This is the exact, traced root
  cause of the 4 failed sessions in the discovery-hardening spec's §1 Layer A.
- **Independent corroboration:** Part E's eval run (`docs/eval/skill-authoring/2026-07-07-part-e-
  first-pass.md`) found the identical `find_tools`-loop-then-silence pattern as the dominant failure
  mode across 37 scenarios on 5 DIFFERENT skills, reproduced on a control run against the untouched
  `glossary_skill` — tracked as `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE`. Two fully independent
  measurements (real user sessions vs. a synthetic eval harness) converge on the same underlying gap.
  **2026-07-08 update:** this item's harness-side root cause is now understood and fixed — see
  [`docs/eval/skill-authoring/2026-07-08-loop-flake-rootcause-and-rerun.md`](../eval/skill-authoring/2026-07-08-loop-flake-rootcause-and-rerun.md).
  The dominant instance was a real `curated_mode` gap (a skill-only pin, exactly how the real frontend
  pins a skill, never hot-seeded the skill's own tools) — now fixed and live-verified. A clean re-run
  still shows a RESIDUAL, smaller loop/give-up pattern (composition's large tool count exceeding the
  hot-seed budget + a small model not always retrying via `find_tools`, plus a reasoning-token/
  max-tokens-before-content pattern unrelated to routing) — this residual is exactly the shape Part F's
  guardrail argument below still applies to; it does not invalidate the Part F rationale, it narrows and
  sharpens what remains architectural vs. what was a fixable bug.
- **External validation (2026-07-07, quick web check, not a full research pass):** the current
  industry consensus 6-layer production-agent breakdown (reasoning/tool-router/planner/orchestration/
  memory/observability) names exactly two gaps for a system at LoreWeave's maturity — a loop/give-up
  guardrail (the discovery-hardening spec's Layer A) and an intent-routing/planning tier (this Part F)
  — matching what was independently found from the 4 sessions + the Part E eval, not expanding it.
  Also: Anthropic's own "Agent Skills" progressive-disclosure pattern (load a one-line description
  always, full body on demand) is exactly `skill_metadata_block()`'s existing L1/L2 design — convergent
  with, not behind, current industry practice.

## 13. Decisions requiring PO sign-off — Part F

### 13.1 Router mechanism

Three candidate mechanisms, weighed:

- **Option A — dedicated LLM classifier call.** A small/fast model call, before the main turn,
  classifying user intent → skill code(s). Most robust to paraphrase/multilingual (the failed
  sessions were Vietnamese — a keyword-only classifier would need multilingual keyword coverage,
  fragile). Costs one extra LLM round trip's latency + tokens on EVERY turn, regardless of whether
  routing was even ambiguous.
- **Option B — same-turn L1-directory, no gating relaxation.** Rely entirely on the existing
  `skill_metadata_block()` menu + the main model's own judgment, with a `load_skill(code)`-style tool
  for on-demand full-body loading. Zero extra round trip, but does nothing for the traced failure
  above unless the orphaned capability first gets a `surfaces` entry that includes the relevant
  surface (a coverage fix, not a routing fix) — this option alone under-delivers on "a general Router
  for future ambiguous asks," which is the scope the user explicitly chose (§ preceding user
  decision) over the narrower coverage-only patch.
- **Option C (recommended) — embedding-similarity router.** Embed the user's per-turn intent once
  (reusing the SAME embedding call the discovery-hardening spec's Layer A item 4 already commits to
  building — see §14 below) and score it via cosine similarity against a small, precomputed set of
  skill-description vectors (~11-15 skills, trivially cheap once tool vectors already justify the
  client existing). No extra LLM call; the added latency is exactly the ONE embedding round trip
  already being paid for tool-search, amortized across two consumers. Falls back to today's
  surface-flag-only behavior on embedding failure/timeout (never worse than today).

**Recommendation: Option C**, with Option B's L1-directory kept as the always-present cheap layer
underneath it (belt-and-suspenders — the router's job is deciding what to INJECT; the model still
sees a menu of what's active, per today's design).

### 13.2 Composition with the existing surface-flag path — additive, never override

The router must be **strictly additive** to `resolve_skills_to_inject()`'s existing static defaults
— it may add a skill the surface-flag path wouldn't have picked (e.g., a new "research" skill on the
`chat` surface when intent scores high), but must never REMOVE a skill the static path already
guarantees (e.g., `knowledge` auto-injecting everywhere per Part D). This mirrors the "one shared
ceiling, not per-source budgets" discipline §9 already mandates for hot-domain token budgeting — the
router's additions must be verified against the SAME `HOT_SEED_TOKEN_BUDGET` ceiling, not a separate
carve-out.

**RESOLVED (2026-07-07):** one global confidence-threshold constant to start, tuned empirically via
Part E's existing eval harness (reusable here — this is exactly the kind of scenario Part E was built
to score). Revisit per-surface tuning only if measurement shows one surface needs a different bar —
not designed upfront on a guess.

### 13.3 The orphaned-capability gap is fixed regardless of the router's timeline

Independent of how long Option C's full build takes: `glossary_web_search`/`glossary_deep_research`
need an actual skill-home visible on the `chat` surface NOW — the router has nothing correct to route
to for that intent without it. **RESOLVED:** fold this into Part B's coverage-expansion track as a
fast-tracked addition (extend `universal_skill`'s prompt to explicitly own general web-research and
name the two tools directly with a calling example, OR a small new skill with `surfaces` including
`"chat"` — decide at PLAN time which reads more coherently against `universal_skill`'s existing
scope), sequenced to ship BEFORE or IN PARALLEL WITH the router build (§15), not gated behind it — a
router with nothing to route ambiguous web-research asks to is no better than today for that specific
case. This is the F0 slice (§15) — small, parallel-safe, no dependency on F1/F2.

### 13.4 Sequencing vs. remaining Part B coverage

A router choosing among 3 deep skills + several still-thin ones (§1(B)'s original table, now improved
by Phase 1/2 but not exhaustive — `story`/`catalog`/`registry` remain in `universal_skill`'s generic
bucket) doesn't help much for domains that still have no real skill. **RESOLVED: ship incrementally,
not gated on a coverage bar.** The router's value is monotonic with coverage, not gated by it, and
waiting for "full coverage" before any router value ships would repeat this spec's own §3.4 lesson
(don't gate a real improvement behind an unrelated completeness bar).

## 14. Design — Part F: Intent→Skill Router

**New chat-service module: an embedding client.** Port `knowledge-service/app/clients/
embedding_client.py`'s pattern (`EmbeddingClient.embed(user_id, model_source, model_ref, texts) ->
EmbeddingResult`, one async HTTP call to `provider-registry-service`'s `/internal/embed`, BYOK,
30s timeout for cold local models) — this is chat-service's FIRST embedding call site, confirmed by
code audit (zero existing embedding capability there today). Shared with the discovery-hardening
spec's Layer A item 4 (same client, same call per turn, two consumers reading the one result vector).

**Skill-vector cache:** precompute one embedding per `SkillDef` (its `description` + a short synonym/
keyword hint authors add per-skill, mirroring how tool synonyms already work in `tool_meta().synonyms`)
at process start / on `SYSTEM_SKILLS` load — a tiny, static set (~11-15 vectors), refreshed only when
a skill is added/changed (not per-request, not per-turn).

**Per-turn routing:** embed the user's current turn text once; cosine-similarity-rank against the
skill-vector cache, filtered to skills whose `surfaces` already include the active surface (the router
narrows WITHIN the structurally-eligible set — it does not override `surfaces`, which correctly
encodes "does this skill even apply given where the user is"). Skills scoring above a confidence
threshold (tuned per §13.2) are UNIONED into `resolve_skills_to_inject()`'s output, additive to the
existing static defaults — never replacing them.

**Shared cosine helper:** per the discovery-hardening spec's Layer A item 4, this is the same
promote-to-`sdks/python` work — one cosine-similarity function serving both the skill-router's
small vector set and the tool-search embedding upgrade's larger one.

**Fallback discipline:** an embedding-call failure, timeout, or empty result set falls back to
EXACTLY today's `resolve_skills_to_inject()` behavior (static surface-flag defaults only) — the router
can only make skill selection better or identical to today, never worse or blocking.

**New test:** a routing-accuracy suite reusing Part E's `run_skill_gate.py` harness and existing
scenario files — score whether the router's additions match each scenario's expected skill, as a
DIRECT reuse of infrastructure already built for a different purpose (skill-content quality), now
also proving router accuracy.

## 15. Rollout sequencing — Part F

1. **F0 (fast-tracked, folds into Part B):** give `glossary_web_search`/`glossary_deep_research` an
   actual skill-home visible on `chat` (§13.3). Cheap, ships independently, closes the specific traced
   bug immediately regardless of the router's timeline.
2. **F1:** port the embedding client into chat-service + the shared cosine-helper promotion (coordinate
   with the discovery-hardening spec's Layer A item 4 — build once, both efforts consume it).
3. **F2:** skill-vector cache + per-turn routing, additive-only, behind the confidence threshold
   from §13.2, with the mandatory fallback-to-static-behavior path (§14) built and tested BEFORE the
   router is turned on for any real traffic.
4. **F3:** re-run Part E's eval harness (`D-SKILL-EVAL-RERUN-AFTER-LOOP-FIX`, already tracked) with
   the router live, to measure whether it actually improves the routing-accuracy signal, not just
   assumed to.

Not started. This is CLARIFY only — needs PO sign-off on §13.1-13.4 before PLAN.
