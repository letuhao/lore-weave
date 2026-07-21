# Spec — Eager tool-index discovery mode (kill the loop for weak LLMs)

> ## ⛔ SUPERSEDED / PREMISE INVALIDATED (2026-07-21) — do NOT build
> This spec's entire premise — *"weak models can't run the `tool_list → tool_load → call`
> discovery loop"* — was **DISPROVEN by live measurement.** The real cause of the failure was a
> plain bug in **our** code: `book_update_details` was **budget-starved out of the advertised tool
> set** (`budget_names_by_tokens` orders reads first, and the tool wasn't in `ALWAYS_HOT_WRITES`),
> so no model was ever shown it. Fixed in one line (`5625b0a3d`: add it to `ALWAYS_HOT_WRITES`).
> **After the fix, weak local Gemma-4 26B ran the FULL discovery loop perfectly** —
> `tool_list → book_list → book_get → book_update_details → diff card` — no eager-index needed.
> So THIS feature — injecting a static index to *kill the discovery loop* — solves a problem that does
> not exist. **Do not invest further** unless a *genuinely* huge tool set later proves discovery is a
> bottleneck for a *capable* model. Kept as a record of the wrong turn.
>
> ### The planner-executor (`tool_plan.py` / `planner_poc.py`) is also PARKED — cost not proven
> A follow-up dogfood turn surfaced a SECOND real routing bug (`D-DOMAIN-HOTSET-NOT-STICKY`): the
> per-turn domain hot set was not conversation-aware, so a low-signal follow-up (*"Go with the third
> one."*) advertised **zero `book_*` tools** and the model wandered / hallucinated success. The
> planner *would* fix this (it reads the FULL catalog, immune to domain mis-detection) — but the
> **cheap, direct fix won on cost:** re-seed the domains the recent `chat_messages.tool_calls` show
> the conversation engaged (`a3028d6f6`), and a stop-note on the minted confirm card
> (`5276586b4`). Both **live-verified on weak Gemma** — a zero-keyword follow-up now reaches
> `book_update_details` and produces one clean diff card, no double-card. **The planner never
> proved a cost advantage over these targeted fixes, so it stays PARKED** — same test the eager-index
> failed. Revisit only if a genuinely harder open-ended agency case appears where no cheap targeted
> fix exists.
>
> ### The one hypothesis that was WRONG vs. the one that was RIGHT
> - ❌ WRONG (this spec's premise): *"weak models can't run the discovery loop."* Disproven live.
> - ✅ RIGHT (the project's foundational bet): *"the problems are mostly OUR code/logic, not the
>   model — a cheap model is enough."* **Confirmed four-for-four** (starved tool, non-sticky domain,
>   OpenAI `chat_template_kwargs` 400, confirm-card blob). Every "the model is weak" verdict dissolved
>   into one of our bugs. **Lesson:** verify the mechanics (is the tool advertised? domain hot? result
>   instructive?) BEFORE theorizing about capability — the cheap deterministic check would have found
>   each bug in minutes.

**Status:** ~~DESIGN (approved direction 2026-07-21)~~ **SUPERSEDED — premise invalidated (see banner).**
**Origin:** dogfood 2026-07-21. The auto-gate `book_update_details` is correct + advertised, yet
weak local models (Gemma-4 26B, Nemotron-3 Nano, even Qwen3.6 35B) never reach it in live chat —
they call `tool_list(book)` then stall, never `tool_load`+call. The **out-of-loop benchmark**
([scripts/eval/tool_liveness/tool_selection_benchmark.py](../../scripts/eval/tool_liveness/tool_selection_benchmark.py))
proves the SAME models route correctly (Qwen3.6 6/6, Gemma 5/6) when handed the whole catalog at
once. And the context-preflight metric proved input is LEAN (~6.5K/pass, 3% window) — so it is NOT
bloat. **The lazy discovery LOOP itself is what weak models can't run.** Built-in pipelines don't
use `tool_list` (they name their tools) and work — same reason.

## The feature

A discovery MODE, per user/session setting:
- **`lazy` (today's default):** `ALWAYS_ON_CORE` advertises `tool_list`/`tool_load`; the model
  searches the long tail on demand. Scales to thousands of tools; needs a capable model.
- **`eager_index` (new):** **hide `tool_list`** (and `find_tools`); inject a COMPACT TOOL INDEX
  (every discoverable tool as `name: one-line-description`, ~30-40 tok each) into the system
  context so the model sees the whole menu at turn start and goes STRAIGHT to the tool. No search
  loop. (`tool_load` MAY stay for the exact schema, OR auto-resolve — see options below.) Best for
  weak models + bounded tool counts.

## Settings boundary (SET-1..8)

Two users want different values ⇒ **user setting** (not env). Name: `chat.tool_discovery_mode`,
enum-closed-set `{lazy, eager_index}`, default `lazy`. Resolution cascade System→User→Session
(session overrides). Expose effective value + source tier (Session Settings panel, next to
Reasoning effort). Server-side (not localStorage). One home; consumers inherit.

## Implementation hooks (located)

- **Setting storage/resolution:** mirror `reasoning_effort` — it flows session→gen_params in
  `stream_service.py` (`_apply_reasoning_kwargs`). Add `tool_discovery_mode` the same way (session
  settings → the advertise path). FE toggle in `frontend/src/features/chat/components/session-settings/`.
- **Hide tool_list + inject index:** [tool_discovery.py](../../services/chat-service/app/services/tool_discovery.py)
  - `ALWAYS_ON_CORE_NAMES` (~:260) — in `eager_index`, DROP `TOOL_LIST_NAME`/`TOOL_LOAD_NAME` (keep
    `tool_load` only if using option B below) + keep ui_*/propose_record_edit/confirm_action/web_search.
  - Build the index from the federated catalog (`sweep._list_tools` equivalent already used by the
    benchmark; chat-service reads the same ai-gateway catalog). Format = the benchmark's
    `_catalog_text` (`name: desc[:160]`). Filter to `visibility != legacy`.
  - Inject the index as a system block in the request assembly (`stream_service.py` around the
    system-prompt build / the `context_breakdown` site ~:4563 — add a `tool_index` category so its
    token cost is measured; ~10K for ~288 tools, well within the window per the preflight metric).
- **How the model actually CALLS the tool (pick ONE, A/B if unsure):**
  - **Option A — index + full schemas advertised:** advertise ALL tool schemas. Simplest for the
    model, but ~288 full schemas is large (100K+ tok) → only viable for a small tool set / a
    hot-scoped surface. Reject for the universal surface.
  - **Option B — index + keep `tool_load` (RECOMMENDED):** the model sees the index, so it goes
    directly `tool_load(book_update_details)` → call (ONE load, no search). Small token cost,
    no loop. This is the minimal, safe change.
  - **Option C — index + auto-resolve:** the model emits a tool call by name; chat-service
    auto-loads the schema + executes transparently (no `tool_load` step). Best UX for the weakest
    models; more plumbing (a name→schema resolve + validate at the call seam).

## A/B RESULT (2026-07-21, live, Gemma-4 26B) — index-as-hint is INSUFFICIENT

Code-free A/B: a chat whose custom SYSTEM PROMPT contained the book tool index + an explicit
"do NOT use tool_list; call book_update_details directly."
- **control (lazy):** `tool_list → book_list → book_get → STOP` (no diff card).
- **treatment (index-in-prompt, tool_list still advertised):** `tool_list → load_skill → book_list
  → book_get → STOP` — the model STILL used tool_list (it's advertised) and STILL stalled at
  book_get; never `tool_load`ed or called `book_update_details`.

**Two conclusions that redirect the implementation:**
1. A prompt hint can't beat an ADVERTISED `tool_list` — the feature must actually REMOVE it from the
   advertised set (not discourage it).
2. Even when it knows the tool's NAME, the weak model won't `tool_load` it on its own — so **Option B
   (keep tool_load) is insufficient for weak models.** The tool must be **directly CALLABLE**.

**⇒ Revised recommendation: Option A/C for a bounded domain.** For book (~20 tools) advertise the
domain's tool SCHEMAS directly when eager/hot (≈10-15K tok, fits per the preflight metric) — OR
Option C auto-resolve (model emits a call by name → chat-service auto-loads the schema + executes).
Then `book_update_details` is immediately callable and the read→write plan can complete. (This is
exactly the "hot-seed the book domain" behavior a BOOK-SCOPED co-writer should already have — worth
testing that path directly as a second A/B arm before/while building the setting.)

## A/B ARM 2 (2026-07-21, live, Gemma-4 26B) — BOOK-SCOPED co-writer: hot-seed WORKS, but budget-capped

Ran the same request in the BOOK-SCOPED co-writer (book domain hot-seeded, book_id in context):
- steps = `book_get → book_chapter_create` — **NO tool_list!** The hot-seed ELIMINATED the discovery
  loop (the model went straight to book tools). ✅ This validates the eager/hot approach's core.
- BUT the model picked **`book_chapter_create`** (Bug2 resurfaced — a chapter for the description),
  NOT `book_update_details`, and produced a `book_chapter_create.batch` card (cancelled).

**Root cause pinned:** the benchmark proves Gemma routes "update the description" → `book_update_details`
correctly WHEN PRESENTED. It failed here because `book_update_details` was **not in the hot-seeded
directly-callable set** — the hot-seed is capped by `HOT_SEED_TOKEN_BUDGET` (a full book domain ≈ 24K
tok), so only SOME book tools get seeded on pass 1; `book_chapter_create` made the cut, the newly-added
`book_update_details` (now Tier-W) apparently did not → the model chose the wrong AVAILABLE hot tool
(and `book_chapter_create`'s disclaimer can't redirect to a tool that isn't callable).

**⇒ THE FIX (concrete):** the eager/hot set for a bounded domain (book) must **guarantee the key
write tools — incl. `book_update_details` — are advertised**, not trimmed by the budget. Options:
(a) raise/scope `HOT_SEED_TOKEN_BUDGET` for a book-scoped surface so the WHOLE bounded book domain
seeds; (b) a priority list so write tools (update_details/create/save_draft/publish/delete) always
seed ahead of the long tail; (c) verify whether book_update_details is even eligible for hot-seed
after the Tier-A→W change (the tier/visibility may affect seeding). Start by inspecting the actual
seeded set for this surface (log it) and confirm book_update_details is present.

## A/B evaluation

Reuse the benchmark harness pattern but LIVE: same request across `lazy` vs `eager_index` × the
model set, measure (1) did it call `book_update_details` → diff card, (2) turns/passes to get
there, (3) loop incidence. The out-of-loop benchmark is the ceiling; this measures how close each
mode gets in the real loop. Emit to `docs/eval/tool-liveness/discovery-mode-ab/`.

## Why this likely fixes M0d's live diff card

The benchmark = eager presentation = models route correctly. `eager_index` brings that into the
live chat. Expected: on `eager_index`, "update the description" → the model directly
`tool_load`s + calls `book_update_details` → the server-built diff card renders (M0c path, already
proven). That is the pasted live re-smoke M0d needs.

## Guardrails already in place (don't regress)

- Context-window gate + per-turn input metric (`2d1b4197c`) — the index adds ~10K; the gate will
  catch it if a small-window model can't fit index+history. Watch the `pct_used` metric.
- The reasoning-loop breaker (`no_thinking_fields`) + `blank_tool_args` breakers stay as the net.
