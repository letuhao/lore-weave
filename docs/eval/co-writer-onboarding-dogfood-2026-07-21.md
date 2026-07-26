# Co-writer onboarding dogfood — bug-hunt findings (2026-07-21)

**Book:** *The Salt Cartographer* (`019f84e1-8716-7c05-9696-1ebf2bde68fc`), fresh, English.
**Model:** Gemma-4 26B-A4B QAT (200K), studio co-writer surface.
**Session goal:** drive the full author onboarding (create → vision → description → ontology+KG →
plan → compile → review-in-UI → adjust → write) as a real user, natural language, no tool names.
**Stopped at:** step 4 (world setup) — the agent **ran away and did steps 4→8 in ONE turn**, so the
controlled step-by-step flow could not be exercised. This is the wall.

> **Verify discipline used:** every approve/tool-call was checked against the **DB**, not the UI
> (per the "sometimes it doesn't persist" rule). Everything below is DB-confirmed.

---

## 💰 COST-FEASIBILITY POC (2026-07-21) — measured, not asserted

**Question (user):** "no one pays for 20K+ mandatory tokens per prompt just to add a few chat lines —
if we can't optimize cost the app is useless." Verified on **real OpenAI gpt-4o-mini** (spend: **$0.0008**).

**Measured (controlled ~6K static prefix, cold then warm, via `loreweave_llm.Client`):**
```
COLD  input=3387  cache_read=0     out=1
WARM  input=3387  cache_read=3328  out=1   ← 98% of the prefix AUTO-cached (no previous_response_id needed)
cold $0.000509 · warm-with-cache $0.000259 (49% off) · warm-NO-cache $0.000509 (what we bill today)
```
1. OpenAI prompt caching is automatic + near-total (98% hit) and `input_tokens` stays the FULL volume
   — caching cuts **cost** (cheaper cache-read rate), NOT token count. 2. Cached input = **50% off**
   gpt-4o-mini / **90% off** GPT-5.x / Claude. 3. **We capture `cached_tokens` (responses/anthropic
   streamers) but the pricing JSONB has NO cached rate → we bill cached at full = ~2× overcharge.**

**20-turn session cost model (measured 98% hit + published rates, our real 13K prefix):**
| model | A: today (13K, no discount) | B: +cache discount | C: progressive 2K + discount |
|---|---|---|---|
| gpt-4o-mini | $0.040 | $0.022 | $0.004 |
| gpt-4o | **$0.66** | $0.36 | $0.068 |
| GPT-5.x | $0.33 | $0.060 | $0.015 |
| Claude Sonnet | **$0.80** | $0.14 | $0.037 |
(agentic multi-pass turns multiply per-turn by pass count → column A hits DOLLARS/session on premium
models; caching helps most there since every re-sent pass hits the cached prefix.)

**VERDICT: viable, but ONLY with two fixes — they are load-bearing, not polish.**
- **(1) apply the cache-read discount in billing** (data already captured; add `cached_input_per_mtok`
  to pricing + consume `cache_read_tok`) → −45-82%.
- **(2) progressive tool loading** (F12: 13K→~2K prefix) → another −90%.
Combined, even premium models are **cents/session**. Without them, column A confirms the user's "useless"
fear for cloud at scale. Local (LM Studio) is $0 real cost regardless (F11 only inflates the ledger).

## 🔴 HIGH

### F11 — BILLING double-charge + inflated + 20× mispriced (real money, not the display)
**Distinct from F10** (F10 is the UI counter; this is the **billed `usage_logs` ledger**). The runaway
turn was recorded by **TWO independent writers**, both billed:

| Writer | request_id | records | input_tok | cost |
|---|---|---|---|---|
| provider-registry per-pass (`stream_billing.go:306`) | uuidv7 (`019f84ea…`) | 14 | 498,158 | **$0.0506** |
| chat-service turn roll-up (`billing_client.py:69` → `/internal/model-billing/record`) | random v4 (`2fbc0a85…`) | 1 | **550,704** | **$1.1056** |

**One "set up the world" turn → ≈ $1.16 billed, on the user's OWN local 4090.** Four compounding bugs:
1. **Double-write** — provider-registry (per pass) AND chat-service (per turn) both write `usage_logs`
   for the same LLM calls. The turn is billed ~twice.
2. **Roll-up bills the cross-pass SUM (550,704)** — the F10 misleading number, charged as real tokens;
   the true unique context was ~35K. ~14× inflation on top of the double-write.
3. **20× price disagreement** — same 12,414-token turn: per-pass writer $0.0012574 ($0.10/1M) vs
   roll-up writer $0.024908 ($2.006/1M). The two cost paths don't agree.
4. **Local/BYOK model billed non-zero** — Gemma runs on the user's GPU; cost should be ~$0 (or an
   untracked "self-hosted" lane), not ~$0.10–2/1M. And **no prompt-cache discount** is applied even on
   the per-pass path (each pass bills its full re-sent ~35K input; cache-read should be ~0.1× or free —
   `caching_monitor.py` already models this but billing doesn't consume it here).

**Fix direction:** ONE authoritative usage writer per LLM call (pick provider-registry per-pass; drop
the chat-service turn roll-up, or make it audit-only/never-billed); never bill the cross-pass sum;
apply the cache-read discount to re-sent context; **local/self-hosted models = $0** (or an explicit
untracked lane). This is the answer to "a few chat lines cost that much?" — **yes, and it's a bug.**
Verify the balance/spend calc sums `usage_logs` (if it dedups by request_id the double-charge may be
partially mitigated — but the 550K roll-up + 20× price + non-zero-local remain).

### F1 — Runaway over-automation (THE headline bug)
On a single **"set up the world for this story"** request, the agent chained the **entire** workflow
in one 35.6s / **↑550,704-token** turn:
```
glossary_propose_entities ×2 → kg_project_create → kg_project_entities_to_nodes
→ plan_propose_spec → book_chapter_create → book_chapter_save_draft
```
**DB-verified persisted (all of it):** 6 kinds · 4 entities (Isolde/Vael/The Shifting Sea/Cartographic
Prophecy) · 1 KG project · **1 plan_run + 3 structure_nodes (plan auto-COMPILED)** · Chapter 1
("The Shifting Tide") · draft prose (3 blocks / 1609 B).

The user asked ONLY to set up the world. The agent proposed entities, built the KG, **proposed a
3-act plan, compiled it, created a chapter, and wrote prose** — with **no stop for review at any of
the user-control gates** (plan review, compile, adjust, write). The user's intended controlled flow
(steps 5–8) is bypassed entirely; there is no way to review/redirect before the agent has already
done everything.

**This is a control failure in the OVER-eager direction** — opposite of the earlier "stalls / won't
act" class, but the same root: no hard stop-gates. `plan_propose_spec` auto-compiling (structure_node
> 0, the `D-G5-DRIVE-EXEC` rules-mode autocompile) compounds it — even the compile checkpoint is gone.

**Fix direction:** the onboarding/world-setup path must become a **CONTROLLED STANDARD WORKFLOW (a
rail)** with hard checkpoints the agent cannot cross without the user (see "Workflow recommendation").
Minimum: writing prose / creating chapters must NOT happen on a "set up the world" turn.

### F2 — Run-on concatenated response (incoherent multi-phase wall)
The single runaway turn's assistant message is **~8 separate phase-closing messages concatenated**:
"I've set up the foundation… **What would you like to do next?**" … "I've laid out the structure…
**How does this look?**" … "I've created Chapter 1… **Shall we draft?**" … "I've written the opening…
**continue?**". It **asks the user for direction repeatedly IN ONE MESSAGE and then proceeds anyway**.
Root: the agent looped phases in one turn, each emitting a "done — what next?" line, none of which
actually paused. Deeply confusing; the reader cannot tell what was done, what is proposed, or what is
being asked.

---

## 🟡 MED

### F3 — Opaque confirm card ("Set up your book's world")
I asked the agent to **"propose the categories it should track."** Instead of a preview of *which*
kinds/standards it would adopt, `glossary_adopt_standards` minted an **opaque confirm card** with no
detail — the user approves blind. The card should surface the proposed kinds (character, location,
item, power_system, terminology, …) so the user can evaluate the proposal, which is what "propose"
means.

### F10 — The per-turn token counter ("↑550,704") is misleading (cumulative-across-passes, ignores caching)
The UI's per-turn "↑N tokens" is the **SUM of `promptTokens` across every tool-loop pass**, not the
model's work or the context size. The runaway turn (F1) showed **↑550,704** — but:
- Our own preflight metric (`2d1b4197c`) shows each pass was **~32–35K** input; **~16 passes × ~34K ≈ 550K**.
- **LM Studio ground truth** (`lms log stream --stats`) for a single pass: `promptTokensCount: 12,414`,
  `timeToFirstTokenSec: 1.78`, `tokensPerSecond: 119` — i.e. one pass is ~12–35K, never 550K.
- **Context was 17% of the 200K window at peak** (`pct_used: 16–17`, `headroom ~165K`) — NOT bloated,
  NOT near overflow. The ~34K is re-sent 16× with **KV-cache reuse** (near-free re-prefill), which is
  how a single RTX-4090 does it in 35s (Gemma-4 26B-A4B is a MoE, ~4B active params, ~7K tok/s prefill).

**Fix direction:** the per-turn chip should show **peak per-pass context** (the real load, e.g. "35K /
200K") — the honest number is already in the `chat context preflight` log. If a cumulative figure is
kept, label it "cumulative across N passes" so it isn't read as context size or GPU work. (Same root
as the earlier "245K for a one-line request" scare — it was always the cross-pass sum.)

### F12 — ~15K fixed agent-surface overhead on EVERY turn (even a 1-line question)
Persisted `context_breakdown` for a trivial "what's the central magic?" turn (~17.9K context):
`mcp_tool_schemas 8,134` (all 44 tools) + `skills 5,117` (8–10 bodies) + `plan_nudge 2,190` +
`frontend_tool_schemas 1,478` = **~14.9K fixed overhead**; history was 1,424, the question ~10 tokens.
Prompt caching helps *compute* (auto-prefix, hit_rate 0.66, ~33% saved) but does NOT reduce the tokens
**sent** — the stateless API ships all ~18K every request (this is the large prompt seen in LM Studio).
**POC RESULTS (2026-07-21, env-tunable A/B harness `LW_HOT_SEED_TOKEN_BUDGET` + `LW_LAZY_ALL_SKILLS`):**
Both levers measured on the real Gemma studio co-writer, quality-gated end-to-end:
| Arm | tools | skills | quality gate |
|---|---|---|---|
| baseline | 8134 | 5117 | — |
| tools index-only (budget=0) | **4842 (−40%)** | 5117 | description edit → `book_update_details` ✅ |
| skills lazy (`LAZY_ALL_SKILLS`) | 8134 | **433 (−92%)** | "add a character" → Gemma `load_skill` on demand → `glossary_propose_entities` → **Captain Vale persisted** ✅ |
| **combined** | ~4842 | ~433 | **prefix 13.3K → ~5.3K (~60% cut)** |
Both viable, no quality loss (Gemma reliably runs the load_skill/tool_load discovery — the "weak model
skips it" fear is disproven). **Trade-off:** lazy adds `load_skill`/`tool_list` discovery passes
(latency); the NET cost is the OpenAI $/turn A/B (smaller per-pass prefix × more passes) — the last
F12 measurement. Harness ships default-off (opt-in) pending that cost A/B.

**Fix direction (optimization, not a defect):** the hot-set/lazy-discovery should advertise a SMALL tool
set (not all 44 → 8.1K), lazy-skill-bodies should keep skill L2 out until `load_skill` (not 5.1K
injected), and `plan_nudge` (2.2K) should not inject on a non-plan question. Trimming the prefix is the
lever; caching already covers the rest.

**Transport confirmed via an LM Studio `/v1/responses` capture (user-supplied):** the co-writer already
runs STATEFUL — `"store": true` + `"previous_response_id"` chain the message history server-side (so
history, ~1.4K here, is NOT re-sent). But the SAME request still ships the full `instructions` (all 6
skill bodies + the entire `vision-to-book` recipe) AND the complete `tools` array (44 schemas) — the
~13K static prefix is re-sent every turn because `tools`/`instructions` are request-level params (no
"register once" in the Responses/Completions API; the deprecated Assistants API had it). Auto-prefix KV
caching mitigates it (hit_rate 0.66) but the TOKENS are still sent. Two extra levers this exposes:
(a) **all 6 skill bodies are inlined** even on a trivial turn — lazy-skill-bodies (L1 index + `load_skill`)
is not trimming on the book/studio surface; (b) the instructions embed a **volatile per-turn "WHERE THE
BOOK ACTUALLY IS" status** inside the otherwise-stable prefix, which breaks prefix-cache reuse partway
(a cause of the 66%-not-95% hit rate) — move per-turn state OUT of the cached prefix (CLAUDE.md "split
context by update frequency"). Net: the transport is correct; the fix is a smaller, cache-stable prefix.

**Related billing refinement (ties F11→F12):** since ~66% of each pass is a cache-read of the re-sent
prefix, the per-pass billing should price cached-input at the cache-read rate (~0.1×), not full input —
`caching_monitor.py` already computes the split; provider-registry billing should consume it.

**2026 web research — CORRECTS the earlier "caching covers it; re-send is inherent" take (it does NOT):**
- **Progressive/lazy tool loading is the 2026 standard and we are NOT doing it.** Anthropic's Apr-2026
  benchmark: a task needing ~150,000 tokens with all tools preloaded dropped to ~2,000 with schemas
  loaded only when used — a **98.7% reduction**. Pattern = a tiny INDEX (name + 1-line desc, ~10-30
  tok/tool) + lazy full-schema fetch on call. Our `tool_list`/`tool_load` IS this pattern, but the
  hot-set overrides it by advertising all 44 FULL schemas (8.1K) every turn. **Highest-ROI fix.**
- **Cache hygiene: dynamic-at-the-end.** Rule is most-stable-first (tools → system → history → dynamic
  → query); any change invalidates that block + everything after. Our volatile per-turn book-status is
  embedded in the prefix → breaks reuse (our 0.66, not ~0.95). ProjectDiscovery moved dynamic working-
  memory to a trailing user message: cache hits **7%→84%, cost −59%**.
- **Local cache is NOT broken for us (empirically verified).** LM Studio bug #1563 silently disables KV
  reuse for some A3B/A4B MoE models (full recompute every turn) — but a 2-request test on
  `google/gemma-4-26b-a4b-qat` showed reuse WORKING (`n_past=1651`, `prompt eval = 1 token`,
  `graphs reused=3169`). So our Gemma is fine; do NOT chase the LM Studio cache bug. The lever is our
  own prefix (progressive tools + dynamic-at-end), not the backend.
- Cache-read discount (10% of input on OpenAI GPT-5.x / Anthropic) is the single highest-ROI cost
  intervention in 2026; our full-rate per-pass billing forgoes it.
Sources: Anthropic code-execution-with-MCP (progressive loading); usewire.io progressive-tool-loading;
digitalapplied/agentbrisk prompt-caching-2026; lmstudio-ai/lmstudio-bug-tracker#1563.

**POC (LM Studio runtime log, `google/gemma-4-26b-a4b-qat`) — tools ARE cached; caching does NOT shrink
the payload.** Three identical-prefix requests (system + 8 verbose tool schemas ≈ 3763 tok):
| req | prompt_tokens SENT | tokens RE-PREFILLED |
|---|---|---|
| A cold | 3763 | 3763 (755 ms) |
| B identical | 3763 | **1** (28 ms) |
| C last-word-changed | 3763 | **6** (55 ms) |
⇒ (1) the 8 tool schemas WERE reused from KV cache (1 token prefilled on B) — "tools can't be cached"
is FALSE; (2) `prompt_tokens` stayed 3763 every request — **caching cuts COMPUTE, not payload**; (3)
LM Studio `usage` reports NO `cached_tokens` (`cached=n/a`) — our `caching_monitor` "hit_rate 0.66" is
an ESTIMATE, not a measured backend value (label it as such). **Correction to an earlier note in this
doc:** the take that re-sending tools is "inherent / caching covers it" was API-centric and imprecise —
caching makes the re-send cheap in compute but the ~13K is still SENT (payload, context-window,
latency, long-session scaling all still pay). The architectural fix (progressive tool loading + lazy
skill bodies + dynamic-at-end) stands; caching is a discount on bad architecture, not a substitute for
fixing it.

### F4 — Stuck agent-runtime status badge
After `glossary_adopt_standards` minted its confirm card (turn ended, awaiting the human), the runtime
badge stayed **"Running tool · glossary_adopt_standards"** for the whole wait — looks hung/working when
it is actually **blocked on the user**. Should read "Awaiting confirmation" / "Idle".

---

## 🟢 LOW / peripheral

- **F5 — `/v1/agent-registry/usage` → 401 Unauthorized** in the studio (console error, non-blocking;
  the usage widget's auth).
- **F6 — `/v1/notifications/stream` → `ERR_INCOMPLETE_CHUNKED_ENCODING`** — the notifications SSE
  stream drops on the studio surface (reconnect/transient, but noisy).
- **F7 — Entities created with empty `source_kind_code`** — the 4 proposed entities carry no kind
  classification (all `draft`, `source_kind_code` blank), so they aren't sorted into character/
  location/power_system.
- **F8 — Adopted kinds are generic, not book-tailored** — character/item/location/power_system/
  terminology + an odd **`unknown`** catch-all kind. The user asked it to propose categories for THIS
  story (maps, tides, prophecy); it adopted the generic standard set.
- **F9 — 6 duplicate "The Tidewright" books** ("No language set", 0 chapters) in the workspace from
  earlier runs — book-create may double-fire / a failed create leaves a ghost. Worth checking the
  create path for duplication.

---

## Observations (not bugs)
- **Slow on Gemma:** TTFT 7–16 s per turn; the runaway turn was **550,704 input tokens / 35.6 s**.
- **Heavy surface:** the studio co-writer seeds **44 tools · 8–10 skills · ~9.6 K tok** before the
  first message.
- **GOOD parts (keep):** vision feedback was engaged + on-point; the **description** routed correctly
  (`book_get → book_update_details` → diff card) and **DB-persisted (879 chars)** with a clean single
  card (the confirm-flow + sticky-domain fixes from earlier hold on the studio surface too); **entity
  extraction was accurate + tailored** (Isolde/Vael/Sea/Prophecy from the pitch).

---

## ⭐ Workflow recommendation (answering the user's ask)
**Yes — the book onboarding / world-setup flow SHOULD become a controlled standard workflow (rail),
not free agent discretion.** F1 is the proof: the agent CAN do every step and persist it, but with no
stop-gates it steamrolls the user's review points. This flow is used on every new book, so it deserves
strong control. Proposed rail with HARD checkpoints (agent cannot cross without the user):

```
1. adopt-standards        → propose kinds (F3: show them)         [auto]
2. propose-entities       → the pitch's core cast/places/powers   [auto]
   ── STOP ①: user reviews the story-bible inbox ───────────────
3. build-KG (project + entities→nodes)                            [auto]
4. propose-plan (spec)                                            [auto]
   ── STOP ②: user reviews the plan in Plan Hub, adjusts ───────  ← NO auto-compile here
5. compile (on user go)                                           [gated]
   ── STOP ③: user reviews the compiled outline ────────────────
6. write chapter (on user go)                                     [gated]
```
Principle: **automate the tedium (adopt/propose/build), HARD-gate the judgment (plan approval, compile,
before-writing).** That is exactly the user's "control strongly / the user shouldn't have to operate
too much" — the tedious setup is one-click, the decisions are protected. The current agent inverts this:
it makes the user click an opaque confirm (F3) for the tedium, then removes the user from every real
decision (F1).

---

## Next fix round — suggested order
1. **F1 + F2 together** (the rail + kill the run-on) — biggest user-facing win; establishes the
   stop-gates. Likely a chat-service rail/skill + a "one phase per turn, stop at a checkpoint" driver.
2. **F3** (adopt-standards card shows the kinds) — small, high-clarity.
3. **F4** (runtime badge state on a minted confirm) — small FE/state fix.
4. **F7/F8** (entity kind classification + book-tailored kinds) — glossary/extraction quality.
5. **F5/F6/F9** — peripheral, batch when convenient.

**Repro:** fresh book → co-writer → paste a 1-paragraph pitch → "set up the world for this story".
The agent will run F1 end-to-end. Book `019f84e1-…` holds the persisted evidence.
