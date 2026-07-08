# Skill quality-gate — gemma re-run after ALL fanout fixes (round 5, 2026-07-08)

First time `gemma-4-26b-a4b-qat` (the ORIGINAL round-1 model) has been run against the full
Part E harness with **every** fix from the 2026-07-07/08 fan-out live simultaneously: retry-cap
+ enumeration mode + embeddings-blended `find_tools` (with a real resolved embedding model) +
same-pass tool-call dedup + the `is_curated` skill-only-pin fix + the cross-service
`confirm_action` auth fix + F0/F2 skill router, on top of 6 subsequent `/review-impl` rounds
(cache-key model-scoping, real embedding-model resolution, enumeration token-budgeting,
per-tool-name dedup tracking, tracker-leak fixes, a `registry` domain-policy fix, a composition
pending-work backfill fix). Prior baselines: round 1 (gemma, no fixes,
[2026-07-07-part-e-first-pass.md](2026-07-07-part-e-first-pass.md)), round 3 (Qwen, 2 targeted
fixes, [2026-07-08-loop-flake-rootcause-and-rerun.md](2026-07-08-loop-flake-rootcause-and-rerun.md)),
round 4 (Qwen, full fan-out but a confounded fixture,
[2026-07-08-post-fanout-live-verify.md](2026-07-08-post-fanout-live-verify.md)).

Raw transcripts: `docs/eval/skill-authoring/runs/sg-out-gemma-postfix/<skill>/transcript.jsonl`.
Sessions kept (`QG_KEEP_SESSIONS=1`); raw `tool_calls` JSONB pulled directly from
`loreweave_chat.chat_messages` for every session in this run (37 sessions, 117 `find_tools`
calls + 227 other tool calls inspected).

## Setup (Task 1 — stack rebuild, Task 3 — fixture confound)

**Rebuild.** All 8 affected services rebuilt from the current **uncommitted working tree**
(branch `feat/context-budget-law`) and brought up healthy before any test ran, per
`live-smoke-rebuild-stale-images-first`:
`chat-service ai-gateway mcp-public-gateway glossary-service book-service
provider-registry-service composition-service knowledge-service` — 8/8 built clean, 8/8 `Up
(healthy)` on the new images.

**Embedding default.** Confirmed live: `user_default_models` for the test account now has a
row for `capability=embedding` → `bge-m3` (`019eeb08-8bff-75cb-8e86-700efd4033b5`, BYOK via LM
Studio `host.docker.internal:1234`), set immediately before this run (previously empty). LM
Studio itself confirmed reachable and serving `text-embedding-bge-m3` +
`google/gemma-4-26b-a4b-qat` from inside the `chat-service` container — **no queue-wedge, no
`lms` reload needed.**

**Fixture confound (round 4's flagged gap) — fixed, not re-created fresh.** Round 4 used a
throwaway 2-chapter book with no outline/canon/motifs, which didn't match several scenarios'
own `ground_truth` (chapter 3/4, a pre-existing outline node, canon rules, motifs). Round 1's
exact book/project was never recorded (no `QG_KEEP_SESSIONS`, no id in `meta.json`), so instead
of guessing, this run **enriched an existing, real, previously-used book** —
`019eeb09-a4aa-7acf-9281-e812d7975a6c` ("Dracula", used across many past sessions, 7
pre-existing chapters) — via direct REST calls to book-service (`:8205`) and composition-service
(`:8217`) using the same JWT-bearer pattern the harness itself uses (not raw SQL, so every
write went through the real service handlers/validation):

- Added chapter **"The Long Road"** (untouched, real draft prose) for the base-version-guessing scenario.
- Added chapter **"Chapter Two"** with genuinely empty draft prose (byte_size=0) for the publish empty-prose guard.
- Bulk-pre-seeded a chapter under filename **`chapter_2.txt`** so the bulk-import dedup scenario is a real duplicate-filename case, not hypothetical.
- **Trashed chapter IV for real** (`lifecycle_state='trashed'`) so "I trashed chapter 4 by mistake yesterday" is literally true.
- Composition project `019eeb0b-41a4-75b4-902b-09025dd8a381` (already had 4 outline nodes for
  chapters V/VI): added an **Arc node** + a real **"Chapter 3" outline node** bound to the real
  chapter III, with a non-trivial synopsis (so the version-conflict scenario has something to
  version-check against); added a **canon rule** ("the empire's succession law..."); created and
  **book-adopted two motifs** ("chosen one refuses the call", "reluctant mentor") into this book's
  tier via the real create→adopt MCP-equivalent REST flow.

`SKILL_BOOK_ID=019eeb09-a4aa-7acf-9281-e812d7975a6c`, `SKILL_PROJECT_ID=019eeb0b-41a4-75b4-902b-09025dd8a381`.
Translation/settings/jobs scenarios were **not** further seeded: settings/jobs have no book
context at all (`context: null` in every scenario), and translation's own `ground_truth` rules
are about tool-call discipline, not about specific pre-existing translation-job state — round
4's evidenced confound was specifically about book/composition, and that is what this run
targeted.

**One operational snag worth recording**: seeding via direct HTTP from the **host** (not inside
a container) initially 401'd against composition-service with `InvalidTokenError` /
`ImmatureSignatureError: iat`, because of a real few-second clock skew between the Windows host
and the Docker containers — PyJWT's default `iat`-vs-now check treated a host-clock-stamped
token as "not yet valid" from the container's perspective. Fixed by backdating `iat` by 60s in
the seed script. `run_skill_gate.py` itself avoids this because it's always run **inside** the
target container (its own convention), so this doesn't affect the eval run itself.

## Score table (round 5, gemma, ALL fixes, fixed fixture)

Judged by 5 independent cold-start agents (one per skill file), blind, absolute-scoring against
each scenario's own `ground_truth`, same rubric as the prior 3 passes — with one methodology
note: **this round's judges scored at turn-record grain** (41 records for 37 scenarios — a
multi-turn scenario like `cover_generation_confirm_does_not_produce_image` gets 2 rows) rather
than collapsing each scenario to one verdict the way round 1's table did. This is more granular,
not less honest, but means the raw record count differs from the scenario count in the "Total"
row below.

| Skill | Turn-records | PASS | WEAK | FAIL |
|---|---|---|---|---|
| composition | 8 (6 scenarios) | 2 | 5 | 1 |
| translation | 7 (7 scenarios) | 0 | 7 | 0 |
| book | 11 (10 scenarios) | 4 | 2 | 5 |
| settings | 9 (8 scenarios) | 5 | 2 | 2 |
| jobs | 6 (6 scenarios) | 2 | 2 | 2 |
| **Total** | **41 (37 scenarios)** | **13** | **18** | **10** |

**Zero hallucinated tool names across all 41 turn-records** — every judge independently
cross-checked every `tool_calls` entry (and every tool name mentioned in assistant prose)
against the real MCP source (`book-service/internal/api/mcp_tools_*.go`,
`composition-service/app/mcp/server.py`, `provider-registry-service/internal/api/mcp_server.go`,
`jobs-service/app/mcp/server.py`, and `translation_skill.py`'s own documented tool list). This is
the 4th consecutive round (rounds 1, 3, 4, 5) with this result — the highest-severity failure
mode this whole effort exists to prevent continues to hold even under the platform's own
most tool-calling-defective model.

### Comparison across all 4 rounds

| Round | Model | PASS | WEAK | FAIL | Fixes live |
|---|---|---|---|---|---|
| 1 (2026-07-07) | gemma-4-26b-a4b-qat | 13 | 14 | 7 (+4 NEEDS-RERUN) | none |
| 3 (2026-07-08) | Qwen2.5 7B Instruct | 9 | 15 | 14 | 2 targeted (`find_tools` empty-intent directive, `is_curated` skill-only-pin) |
| 4 (2026-07-08) | Qwen2.5 7B Instruct | 7 | 11 | 19 | full fan-out, but **confounded fixture** (fresh 2-ch book) |
| **5 (this pass)** | **gemma-4-26b-a4b-qat** | **13** | **18** | **10** | full fan-out + 6 review rounds, **fixture confound fixed** |

Read plainly: round 5's raw numbers (13/18/10) land almost exactly where round 1's did
(13/14/7+4) — same model, same PASS count, slightly more WEAK/fewer outright FAIL once the
NEEDS-RERUN bucket (which round 1 had no retry-cap to resolve) is folded in. That is **not** a
"nothing improved" result — it's the expected shape once you account for what actually changed
underneath: round 1 had 4 NEEDS-RERUN (scenarios where the model never terminated cleanly at
all), which the retry-cap infrastructure now converts into terminated-but-incomplete WEAKs
instead. Rounds 3/4 (Qwen) are not directly comparable to round 1/5 (gemma) — different models
entirely; the fact that round 4's Qwen numbers look worse than round 1's gemma numbers is
already explained in round 4's own report as fixture confound, independently confirmed by
Task 2's controlled repro in that same report.

## Gemma's specific defect — still present, and now precisely characterized

This round is the **first time the raw `tool_calls` JSONB was pulled for every single session**
in a run (not spot-checked), giving a much sharper picture than rounds 1/3's per-scenario spot
pulls:

**Every one of the 117 `find_tools` calls in this run had blank `args` (`{}`) — zero exceptions,
zero non-blank intents.** The embeddings-blended search path in `tool_discovery.py`
(`search_catalog_semantic`) is only reachable once a call has a non-blank `intent` —
`find_tools_result_async` checks `if not intent.strip(): return _blank_intent_result()` **before**
anything resembling a real search or the retry-tracker runs. Since gemma never once supplied a
non-blank intent in this entire 37-scenario run, **the embeddings path structurally never fired
— not once.** This is an honest negative result the task asked me to check for plainly: I cannot
confirm the embeddings-backed scorer contributes anything for this model in this environment,
because the code path that would exercise it was never reached. (Task 4 of round 4's report
already independently proved the embeddings/enumeration fixes work correctly *when `find_tools`
is actually invoked with real args* — e.g. Qwen's clean single-call web-search repro — so this is
a gemma-specific gap, not evidence the fix itself is broken.)

**The defect is broader than "blank find_tools intent" — it is "blank args to almost any tool."**
Pulling the full `tool_calls` JSONB for all 37 sessions and histogramming by tool name:

| Tool | Calls this run | Args non-blank? |
|---|---|---|
| `find_tools` | 117 | 0/117 |
| `book_list_chapters` | 98 | 0/98 |
| `composition_get_work` | 25 | 0/25 |
| `translation_coverage` | 22 | 0/22 |
| `settings_provider_inventory` | 22 | 0/22 |
| `composition_list_outline` | 19 | 0/19 |
| `jobs_get` | 19 | 0/19 |
| `composition_list_canon_rules` | 15 | 0/15 |
| `translation_job_status` | 13 | 0/13 |
| `translation_start_extraction` | 7 | 0/7 |
| `jobs_list` | 7 | 0/7 |

**Every tool call across all 37 sessions had blank args.** The only calls that "succeeded"
(`settings_list_providers`, `settings_list_models`, `jobs_list`, `book_chapter_create`,
`book_chapter_bulk_create`) did so because either the tool takes no required parameters, or
(for the two `book_chapter_*` writes, which weren't captured in the DB dump — see caveat below)
the call happened to need nothing gemma habitually omits. Every tool requiring so much as one
argument (`book_id`, `service`, `project_id`, `chapter_id`...) failed validation every single
time it was called, regardless of how many times the validation error was fed back. This
confirms and generalizes the loop-flake investigation's finding ("gemma kept sending empty args
regardless of the new message") beyond `find_tools` specifically — it is a general property of
this model's tool-calling in this LM Studio setup, not scoped to any one tool or code path.

**Caveat on completeness**: 4 of the 37 sessions (the two successful `book_chapter_create`/
`book_chapter_bulk_create` writes, plus one `settings_model_set_default` and one `jobs_cancel`
call) had **no persisted `assistant` row with `tool_calls`** in `chat_messages` at all — only the
`user` turn was found on a direct query. The harness's live SSE capture (`TOOL_CALL_START`
events) still recorded the tool names for these in `transcript.jsonl`, so the aggregate tool-name
counts above are accurate, but I could not independently verify their actual argument payloads
against Postgres for those 4. This looks like a possible message-persistence gap on some code
path (worth a dedicated look in a future pass — not chased down further here, out of this run's
scope) rather than anything invalidating the 33-session finding above.

## Which fix bounds this, and which doesn't (the coordinator's requested distinction)

Traced directly in source, not inferred:

- **The ORIGINAL production bug** this fan-out targeted was a *repeated, near-duplicate,
  non-blank* `find_tools` intent (the 4-session Vietnamese repro: 40 iterations/53.8s). The fix
  is `FindToolsAttemptTracker` (`tool_discovery.py:563`) — keyed on `(group, normalized-intent)`,
  flags a repeat on the 2nd+ identical-ish attempt. **This tracker is only ever reached when
  `intent.strip()` is non-empty** (`find_tools_result_async` checks blank-intent and returns
  `_blank_intent_result()` first). Round 4's Task 2 independently live-verified this fix bounds
  the *original* bug to 11-16 iterations for both gemma and Qwen variants of that specific repro.
- **Gemma's blank-intent (and blank-everything) defect bypasses that tracker entirely** — it
  never reaches the code that would flag/bound it as a "retry." This session's fan-out also
  shipped `_drop_duplicate_empty_tool_calls` (`stream_service.py:621`, a genuinely new,
  real production bug this session fixed: a well-formed call followed by an empty duplicate of
  the SAME tool in the SAME pass), but that fix only triggers when a *prior well-formed call for
  that tool name exists to compare against* — gemma's pattern in this run is blank **from the
  very first call**, so there's nothing well-formed to compare against and this dedup never
  engages either.
- **What actually bounds every scenario in this run to a fast, finite stop (worst case 30 tool
  calls / 25.9s, none of round 1's 40-iteration/53.8s or round 3/4's 250-320s non-convergent
  hangs)** is a **pre-existing, untouched-by-this-session** hard safety cap:
  `max_total_passes = max_iterations * 3 = 15` (`stream_service.py:973`, comment: "so a
  pathological find_tools/read loop can't spin forever"). This is a blunt, general per-turn pass
  ceiling, unrelated to any of this fan-out's find_tools-specific work — it just happens to be
  the mechanism that keeps gemma's total-blank-args behavior from hanging indefinitely.

**Net honest conclusion**: this fan-out's retry-cap/dedup fixes are real, correctly scoped, and
proven to work on the exact pattern they target (Qwen's clean single-call repro, the bounded
11-16-iteration gemma repro in round 4's Task 2) — but **gemma's own defect in this run is a
different, broader failure mode that those specific fixes were never scoped to catch**, and it
remains bounded only by the same blunt pre-existing pass ceiling that would have stopped ANY
runaway loop, fixed or not.

## Per-skill findings (from the 5 independent judges)

**book (4 PASS / 2 WEAK / 5 FAIL of 11).** Two genuinely new FAILs worth flagging, distinct from
budget-exhaustion: (1) `cover_generation_confirm_does_not_produce_image` — the assistant's own
prose says confirming will make the request "sent to the generation engine," contradicting the
skill's explicit `outcome: "open_ui"` (a human must manually open Studio); on the user's
follow-up confirm, the assistant then claims "I am now generating that proposal for you" with
**zero tool calls** — narration without action, violating the skill's own "Act, don't narrate"
rule. (2) Three FAILs (`trash_delete...`, `save_draft...`, `bulk_create...`) are the
budget-exhaustion pattern: correct tool selection, correct restraint (never guessed a
`base_version`, never fabricated success), but the final answer is empty/near-empty because the
turn's whole budget went into blank-arg retries on `book_list_chapters`. 4 clean PASSes
(`publish_refused_on_empty_prose`, `sharing_collaborator...`, `trashed_chapter_restore...`,
`pdf_import...`) — all 4 of the "what you cannot do" boundary scenarios held.

**composition (2 PASS / 5 WEAK / 1 FAIL of 8).** One real FAIL:
`project_id_resolution_from_book_id` — after 15 blank-arg `composition_get_work` retries, the
model explicitly gives up and asks the user for a Project ID, the exact behavior the scenario is
designed to catch ("must resolve via `composition_get_work`, never ask the user to supply
`project_id` directly"). Both `no_tool_for_style_profile` and `motif_not_connected_to_planforge`
PASS cleanly — the two "capability boundary" rules held even though tool discovery mostly didn't
fire this round (only 4 of the 117 `find_tools` calls in the whole run were in composition's
transcript; composition mostly loops on hot-seeded read tools it already has instead).

**translation (0 PASS / 7 WEAK / 0 FAIL of 7).** Every single scenario dead-ended in the
blank-intent `find_tools` loop (13-29 calls per scenario) with an empty or near-empty final
answer — but the judge found **zero affirmative rule violations**: no false claims, no invented
tools, no silently-bypassed refusals, no cancel/pause conflation stated outright. Two encouraging
signals survive even under total tool-discovery failure: `translation_job_status_not_generic_jobs_get`
stayed on `translation_job_status` for all 13 attempts (never crossed into generic `jobs_*`), and
`coverage_before_full_redo` stayed on `translation_coverage` for all 22 (never guessed data or
started a priced job). `cancel_job_irreversibility_warning` specifically never got a chance to
surface the pause-vs-cancel warning — 20/20 calls were blank `find_tools`, the domain tool was
never attempted at all.

**settings (5 PASS / 2 WEAK / 2 FAIL of 9).** Both bait scenarios
(`settings_add_provider_key_no_invented_tool`, `settings_update_existing_key_no_invented_tool`)
PASS cleanly — correct refusal, correct `ui_navigate('/settings')` redirect, zero invented
tools. The two FAILs are subtler capability-boundary violations, not tool invention:
`model_update_cannot_repoint_credential` correctly avoids calling `settings_model_update` to
re-point a credential, but then says "once the credential is added, I can then move the model to
it for you" — implying a re-point capability that doesn't exist. `planner_default_requires_chat_capability`
calls `settings_model_set_default` on a non-chat-capable embedding model as `planner` anyway
(should have refused first) and returns **zero characters** to the user — no refusal, no
confirmation, silent.

**jobs (2 PASS / 2 WEAK / 2 FAIL of 6).** Two real content FAILs, not loop artifacts:
`jobs_stop_ambiguous_pause_or_cancel` — after 29 blank `jobs_get` retries, the model calls
`jobs_cancel` (terminal) on an ambiguous "stop" request with **zero clarification and zero
warning**, exactly the violation the scenario exists to catch. `jobs_live_progress_is_ui_watch_job`
— the user explicitly asks to "watch progress live"; the model proposes manually re-checking
("I'll check again in a minute") instead of ever mentioning `ui_watch_job` — the ground_truth
explicitly flags "describing a manual polling loop as the solution" as a failure. Both PASSes
(`jobs_no_generic_resume_tool`, `jobs_pause_requires_multiunit_check`) correctly avoided
inventing/misusing a tool even under retry pressure.

## Honest accounting — no papering over

- **Zero hallucinated tool names, 4th round running** — the strongest, most consistent result
  across this whole effort.
- **The embeddings path is unconfirmed for gemma in this environment** — not because it's broken
  (round 4's Task 4 proved it works when actually invoked), but because gemma never emits the
  non-blank intent that would exercise it. This is a real gap in this round's evidence, reported
  plainly rather than assumed away.
- **`WEAK` is now gemma's dominant outcome (18/41, 44%)**, almost entirely the "correct tool
  discipline, empty/near-empty final answer" pattern from blank-arg retry storms — a `sad but
  bounded` result: nothing false is said, but very little useful is said either.
  `translation` is 7-for-7 in this bucket.
  This matches (and generalizes) the pre-existing, already-catalogued
  `reasoning-model-burns-max-tokens-before-real-answer` lesson, but the ROOT here is specifically
  gemma never producing usable tool arguments, not a reasoning-budget issue per se — the model
  spends its whole turn on failed retries and has nothing left for a real answer.
- **The 10 genuine FAILs are real, mostly content-level, not tool-discovery noise**: a false
  "generation dispatched automatically" claim + narration-without-action (book/cover), a
  falsely-implied credential re-point capability + a silent invalid-default set (settings), a
  silent terminal `jobs_cancel` on ambiguous input + a manual-polling non-answer instead of
  `ui_watch_job` (jobs), and giving up + asking the user for a `project_id` instead of resolving
  it (composition). None of these are new regressions introduced by this fan-out — they read as
  either pre-existing model-capability gaps (blank args → gives up → asks user) or narrow
  prose/behavior gaps this pass surfaces for the first time at this level of scrutiny.
- **This round is NOT directly comparable to rounds 3/4** (different model — gemma vs Qwen); it
  IS directly comparable to round 1 (same model), and the comparison there is a wash on raw
  PASS/FAIL/WEAK counts, with the real, evidenced improvement being *why* scenarios terminate
  (bounded pass ceiling + a real dedup fix for a genuine same-pass bug) rather than *whether* they
  score better — gemma's own tool-calling defect remains the dominant confound, exactly as
  documented in round 3 and round 4's supplementary spot-check, now characterized precisely and
  completely (every tool, every session, not just a spot-check).

## Recommendation for a future pass

Gemma's "blank args to virtually every tool call, every single time" defect is now fully
characterized (this run: 100% blank across every one of 227+117=344 tool calls, all 37
sessions) — it is a candidate for its own dedicated investigation (LM Studio's tool-calling
template for this specific quantized model, or a decode-time constraint issue), separate from
and broader than the already-fixed empty-`find_tools`-intent case and the already-fixed
same-pass-duplicate-empty-call case. Until that's root-caused, gemma is not a reliable model for
tool-calling-dependent skill evals — Qwen2.5 7B Instruct remains the more diagnostic model for
skill-content signal (rounds 3/4), while gemma is now the more diagnostic model for platform
loop-safety-net behavior (this round). Also worth chasing: the 4-session gap where no
`assistant`+`tool_calls` row was persisted to `chat_messages` at all, found incidentally while
pulling this round's evidence.
