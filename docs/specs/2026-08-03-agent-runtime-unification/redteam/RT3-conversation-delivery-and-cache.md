# RT3 — conversation delivery (A7) and cache stability (A6)

**Mandate:** falsify, not grade. Assigned: **A7** (capability + guidance delivered in the
conversation stay effective, turns later) and **A6** (a static tool block restores prompt-cache
stability).

**Verdicts up front:**

| id | verdict |
|---|---|
| **A7** | **KILLS** — as stated it is *already impossible* on the chat path, and the durability half is falsified by code that exists today: there is no persistence, no pin, and no telemetry for a conversation-delivered announcement. |
| **A6** | **WOUNDS** — the block is not stable within a session; `permission_mode` is a **per-turn** field behind a one-keystroke FE cycle button, and the auto surface re-derives from a mutating recency tail every turn. |

---

## Part 1 — A7. The four deletion paths, in the order they fire

The design says an announcement is delivered "in the conversation, where new information is supposed
to arrive." In this repo, "the conversation" that reaches the provider is rebuilt from Postgres every
turn by `stream_service._build_*`. Four independent mechanisms sit between a turn-3 announcement and
turn 20, and **none of them knows what a pin is** except the last one, which never sees the message.

### F1 (KILL) — there is no row type that can hold the announcement

`chat_messages` has **no `tool_call_id`, no `name`, no `tool` column** and the only writers hard-code
two roles:

- DDL: `services/chat-service/app/db/migrate.py:22-40` — `role VARCHAR(20)`, `content TEXT`,
  `content_parts JSONB`; `tool_calls JSONB` added later at `:187-188`.
- `services/chat-service/app/services/stream_service.py:6903` — `VALUES ($1,$2,$3,'assistant',…)`
- `services/chat-service/app/services/stream_service.py:5998` — same, `'assistant'`
- `services/chat-service/app/routers/messages.py:484-486` — `VALUES ($1,$2,'user',$3,…)`
- `services/chat-service/app/routers/internal.py:927-929` — `'assistant'`

**Nothing ever writes `role='system'`, `role='developer'`, or `role='tool'` to chat history.**
So a capability announcement has exactly two homes:

1. **re-synthesised server-side every turn from durable state** — which is the *system-prompt
   mutation the design claims to abandon*, wearing a message costume. It is not "arrival in the
   conversation"; it is `_advertise_discovery_tools` with a different serialiser. It also
   re-invalidates the cache suffix it was supposed to protect (see A6/F8).
2. **written as a fake `assistant` or `user` message** — at which point F2, F3 and F4 apply, and
   `_is_pinned` (the *only* pin in the codebase) returns **False** for it.

`_is_pinned` — `sdks/python/loreweave_context/compaction.py:266-268`:

```python
def _is_pinned(msg: dict) -> bool:
    """system / steering / anchor / developer messages are never dropped."""
    return msg.get("role") in ("system", "developer")
```

The one pin that exists cannot be reached by anything the persistence layer can store.

### F2 (KILL) — the `LIMIT 50` window deletes it before compaction is even consulted

`services/chat-service/app/services/stream_service.py:5063-5084`:

```sql
SELECT role, content FROM chat_messages
WHERE session_id = $1 AND is_error = false AND branch_id = 0
  AND sequence_num >= $3
ORDER BY sequence_num DESC
LIMIT $2
```

with `history_limit = max(1, kctx.recent_message_count)` (`:5034`) and
`recent_message_count: int = 50` (`services/chat-service/app/config.py:348`,
mirrored in `services/knowledge-service/app/config.py:57`).

This is a **fixed-count sliding window with no pin, no exclusion, and no telemetry.** The pinned-set
logic lives in `compact_messages`, which runs at `:6275` — *after* `messages` has already been built
from this window. An announcement at turn 3 is gone at turn ~28 (50 rows ≈ 25 user/assistant pairs),
**regardless of role, regardless of compaction, regardless of budget**, and nothing is emitted:
the `compaction` frame is gated on `_compaction.did_work` (`:6312`) and a LIMIT-window drop is not
compaction. Grep confirms no counter, no log line, no trace span for rows the LIMIT excluded.

> This is, precisely, the defect the spec exists to kill — *"the budget silently deleted the right
> answer, then the system told the model to pick from what was left"* (`poc/P1-P2-findings.md:800+`)
> — relocated from the tool block to the message array, and made **worse**, because the tool-block
> version at least has 1,973 turns of instrumentation behind it and this one has none.

### F3 (KILL) — persisted compaction is sequence-based and pin-blind

`services/chat-service/app/services/compact_service.py:151-242` (`persist_auto_compact`) picks
`new_before_seq = rows[len(rows) - keep_recent]["sequence_num"]` (`:223`) and writes it to
`chat_sessions.compacted_before_seq` (`:224-228`). The loader then filters
`AND sequence_num >= $3` (`stream_service.py:5068`).

**There is no pin, no role check, and no exemption list in this path.** Everything below the
boundary is representable *only* through `compact_summary`, and the summariser is an LLM told to
emit two prose sections (`compact_service.py:44-63`):

```
FACTS:
- Entities: … - Decisions: … - Established: … - Open threads: … - Keywords: …
SYNOPSIS: A few sentences of prose …
```

A JSON tool schema fed through that prompt comes back as **prose about a tool**, not a callable
contract. `keep_recent=8` (`stream_service.py:5055`), so the boundary advances aggressively.

### F4 (KILL) — the announcement's *effect* survives while its *guidance* does not, and this loop is already in production

The persisted `activated_tools` column keeps a `tool_load`ed tool on the wire across turns
(`tool_surface.py:225`, `:571-608`), but the `role:tool` message that *explained* it is never
replayed — history is `{role, content}` only, and `compaction.py:24-27` states this outright:

> *"The cross-turn send path loads history as `{role, content}` only (tool_calls / tool_call_id are
> NOT rehydrated)"*

So the repo **already runs A7's failure mode, inverted**: the capability persists and the guidance
evaporates. The symmetric version — guidance persists, capability evaporates — is documented as a
*measured live degradation loop* at `tool_surface.py:625-633`:

> *"gemma `tool_load`'ed `glossary_propose_entities`, the next turn's newer rail activations pushed
> it over budget, it was evicted DESPITE being the most recently requested, the model fell back to
> the always-visible edit tool whose error said 'tool_load it' — and the cycle repeated, forever,
> with the agent never able to create an entity."*

**A7's falsifier is not hypothetical. It has already happened here, and the fix was a recency-LRU
band-aid, not a pin.**

### F5 — tool results and tool-call arguments: what actually survives

| artefact | within one turn | across the turn boundary |
|---|---|---|
| `role:tool` result content | **evicted to a placeholder** beyond the newest 3 — `_microcompact`, `compaction.py:319-342`, `keep_tool_results=3`; text becomes `"[tool result cleared to save context]"` (`:59`) | **dropped entirely** — never in the `SELECT role, content` window |
| exact-duplicate results | replaced by `"[duplicate of a later identical tool result — see the most recent read]"` (`:60`, `_collapse_duplicate_reads` `:345-374`) | dropped |
| `web_search` / `glossary_web_search` results | **exempt** from eviction — `DEFAULT_EXCLUDE_TOOLS` (`:58`). **This is the only content-level exemption in the system**, and it is a hard-coded two-name frozenset | still dropped across turns |
| assistant `tool_calls` (names **and** arguments) | present in `working` | **persisted to `chat_messages.tool_calls` and never read back** — the loader selects only `role, content` |
| tool-call args inside a *summary* | — | `transcript_of` (`compact_service.py:66-81`) renders a prose-less tool turn as `f"(called {names})"` — **arguments are dropped, not summarised** |

So: **tool results are dropped, not summarised. Tool-call arguments are dropped at two independent
layers.** Any A7 design that assumes the model can re-read what a capability did, or with what
arguments, three turns later is assuming a mechanism that does not exist.

### F6 (KILL, and it makes A7 *partly impossible as stated*) — chat-service has no callable-by-message path

A7 claims announcing a tool *as a message* works "as well as declaring it in the system prompt."
On the production chat path it does not work **at all**:

- `ALWAYS_ON_CORE_NAMES` (`services/chat-service/app/services/tool_discovery.py:282-318`) is
  `(tool_list, tool_load, confirm_action, web_search)`. **There is no `invoke_tool`.**
  `grep -rn invoke_tool services/chat-service/app` returns **nothing**.
- The envelope that makes shape 4 work lives in a *different service*, for *external* MCP clients:
  `services/mcp-public-gateway/src/scope/invoke-tool.ts:27-42`.
- Arm B of the POC (`poc/P1-P2-findings.md:774-790`) was run against **LM Studio directly**, with a
  fixed core of `tool_load` + `invoke_tool` — a surface that does not exist in chat-service.
- The POC already concedes the constraint (`poc/P1-P2-findings.md:655-657`):
  > *"A tool must be in the `tools` parameter to be callable. Tool state can move into the
  > conversation; tool schemas cannot."*

**What happens today if the model calls a name it only saw in a message:**
`stream_service.py:4213-4265` — if the name is not in `cat_index`, the model gets
`{"error": "no_such_tool", "message": "There is no tool named X. You invented it — do NOT call it
again…"}`. If the name *is* in the catalog, `:4269-4281` **auto-loads it and lets the call proceed** —
i.e. conversation delivery is redundant with the catalog that already exists.

**A7's stated form is therefore not testable on this stack. What is testable is the `invoke_tool`
envelope — a different claim, with a different cost.**

### F7 — argument validation for an envelope-delivered call: nothing validates it

Following the envelope path end to end:

- `invoke-tool.ts:33-42` — `arguments: { type: 'object', description: … }`. **No `properties`, no
  `required`.** The audit records this as an accepted IN-3/IN-4 deviation.
- `services/ai-gateway/src/mcp/handlers.ts:291-350` — consumer-local tools (`ui_*`,
  `propose_edit`) are explicitly validated ("validate (enum/required)"). Every **federated** tool is
  forwarded raw: `federation.executeTool(name, args, env, meta, signal)` (`:349`). The gateway
  performs **zero schema validation** on federated tool arguments.
- Validation therefore lands entirely on the owning provider, which for the Go services is a typed
  struct — and a typed-struct unmarshal **silently drops** an unknown field rather than rejecting it.
  A mis-named argument becomes an *absent* argument, surfacing as a missing-required error that
  blames the wrong thing (the exact "misattributed blame makes an LLM unrecoverable" failure class).

On a genuinely unknown name the model does get an actionable line
(`handlers.ts:399-401`: *"unknown tool — … call tool_list … then tool_load"*), which is fine. The
gap is not unknown names; it is **wrong argument names on a known tool**, and that gap is silent.

---

## Part 2 — A6. Everything that still mutates the tool block

The single advertise chokepoint is `_advertise_discovery_tools`
(`stream_service.py:1297-1395`), called at `:2101-2108`, and its output becomes
`request_kwargs["tools"]` at `:2143-2145`. Its inputs:

| # | axis | where | survives the proposed design? |
|---|---|---|---|
| 1 | `permission_mode` — `ask` filters catalog tools to tier R; `plan` adds `plan_*` | `:1323-1324`, `:1389-1393`; `_filter_tools_for_ask` `:1398` | **YES** — SPEC §1.4 shape 4 explicitly keeps mode variation |
| 2 | `book_bound` — **rewrites the `parameters` of every `ambient_book` tool**, stripping `book_id` | `:1336-1337` → `_project_ambient_book_schema` `:1272-1294` | **YES** — the id-free premise (A3) *requires* it |
| 3 | surface `extra_frontend` (editor → `propose_edit`; studio/admin differ) | `:1374-1375`; `tool_discovery.py:276-281` | **YES** — surface is a design axis |
| 4 | `has_workflows` → `workflow_list` / `workflow_load` | `:1365-1367` | **YES** if A11 holds |
| 5 | shape-3 user curation (`chat_sessions.enabled_tools`) | `:5129`, `tool_surface.py:608` | **YES — it is shape 3, an explicit part of the design** |
| 6 | `subagent_depth == 0` → `+conversation_search`, `+chat_search_sessions`, `+run_subagent` | `:2130-2142` | **YES** — A4 depends on `run_subagent` |
| 7 | `settings.lazy_skill_bodies` → `+load_skill` | `:1372-1373` | deploy-level, not per-session |
| 8 | `suppress_tool_list` (F18 breaker) | `:1354-1355` | R19 says move to conversation state |
| 9 | `suppress_names` — rail gate, failure breaker, oneshot de-advertise | `:2090-2100`, `:1386-1387` | R19 says move to conversation state |
| 10 | `active_tool_names` grows mid-turn via `tool_load` / auto-load | `:2823`, `:2945`, `:3021`, `:3192`, `:4271` | R19 says move to conversation state |
| 11 | **auto-mode re-derivation from a mutating recency tail** | `tool_surface.py:601-607`: `set(hot_seed_names) \| (set(activated_tools) & wf) \| set(activated_tools[-AUTO_ACTIVATED_TAIL:])` | **YES unless `activated_tools` is deleted outright** |

**Variant count under the proposed design.** Axes 1–6 alone: 3 modes × 5 surfaces
(universal / book-scoped / editor / studio / admin) × 2 workflow-visibility × 2 subagent-depth =
**60 distinct static tool blocks**, before shape-3 curation, which is combinatorially unbounded by
construction (any subset of the catalog the user pins). Axis 2 is not a set change but a **schema
rewrite of every book-scoped tool**, so book-bound and unbound blocks share no bytes in the
`parameters` of any `ambient_book` tool.

### F8 (WOUND, and it is the load-bearing one) — the prefix is not stable *within* a session

`permission_mode` is **per-turn**, not per-session:

- `services/chat-service/app/routers/messages.py:381-393` —
  *"permission_mode is per-turn (default None ⇒ omitted); fall back to the account pref"*,
  `turn_permission_mode = _permission or "write"`.
- `frontend/src/features/chat/components/ChatInputBar.tsx:195-199` — a **cycle** handler over
  `MODE_ORDER`, i.e. one keystroke/click flips ask → plan → write, mid-conversation, per message.

So the answer to *"is the prefix actually stable within a session, or does it change on the first
mode switch?"* is: **it changes on the first mode switch, and the mode switch is a one-key control
the product deliberately ships.** A6's claim survives only for a user who never touches it.

Two more within-session flips:

- **book binding.** `book_bound = bool((context_ids or {}).get("book_id"))` (`:2107`) is a per-turn
  FE context field. An embedded chat re-scoped to a different book flips axis 2 mid-session, which
  rewrites `parameters` across the block.
- **auto-mode tail.** Axis 11 changes the block on *any* turn where `tool_load` fired previously,
  even with mode and surface constant.

### F9 — the cache ordering the design assumes is correct, which makes F8 worse, not better

`poc/P1-P2-findings.md:632-635` states the order as **`tools` → `system` → `messages`**, and the
repo's cache accounting is consistent with it: `caching_monitor.py` bills Anthropic writes at 1.25×
and reads at 0.10× (`:26-27`), and `stream_service.py:5103-5116` documents that Anthropic caches the
**cumulative prefix** up to each of at most 4 `cache_control` breakpoints, with BP1 on the stable
memory prefix and BP2 at the end of the persona/skills/steering tail.

Because the caching is cumulative-prefix and `tools` is first, **a mode toggle on turn 12 invalidates
BP1 and BP2 as well as the entire message history** — the measured +65% uncached / −1/6 hit-rate
(`poc:639-644`) is the *between-turns* figure, and a mode flip is exactly a between-turns tool-block
change. A6 is not wrong about the mechanism; it is wrong that the design removes the trigger.

### F10 — the honest restatement of A6

A6 as written ("freezing them makes the prefix stable across a session") is false. The defensible
version is:

> **A6′** — the tool block becomes a function of a small, *enumerable, explicitly-versioned* session
> shape `(mode, surface, book_binding, curation_set)`, so every mutation is a **deliberate, logged,
> user-visible** event rather than an emergent side effect of `tool_load` / rail gating / the failure
> breaker.

That is a real and worthwhile improvement — it converts ~unbounded per-pass churn into ≤60 shapes
plus curation — but it is a **reduction in mutation frequency, not stability**, and the acceptance
criterion must be written as a *rate* (tool-block changes per 100 turns), not as a boolean.

---

## Part 3 — cheapest observations that settle each finding

| finding | observation | cost |
|---|---|---|
| **F2** (window silently deletes) | `SELECT count(*) FROM chat_sessions WHERE message_count > 50;` and `… WHERE compacted_before_seq IS NOT NULL;` — every such session is one where a turn-3 announcement is *already* unreachable today | one SQL query |
| **F1/F3** (no pin path) | add a `role='system'` row to `chat_messages` for a live session, run one turn, assert it is in the wire payload. It will not be — the loader replays it as a bare `{role:"system", content}` before the real system block, and `persist_auto_compact` will delete it by sequence at the next boundary | one insert + one turn |
| **F4** (guidance evaporates, capability persists) | for one dogfood session: `SELECT sequence_num, tool_calls FROM chat_messages …` vs `SELECT activated_tools FROM chat_sessions …` — count tools still on the wire whose `tool_load` result is outside the last 50 rows | one SQL query, no code |
| **F5** (results dropped) | assert on the existing kernel: `compact_messages` with 5 tool results and `keep_tool_results=3` returns 2 × `_PLACEHOLDER`; and grep-proof that the cross-turn `SELECT` has no `tool_calls` column | already provable from `compaction.py:319-342` + `stream_service.py:5066` |
| **F6** (A7 impossible as stated) | run the POC's arm B **through chat-service** instead of LM Studio direct. It cannot be run — there is no `invoke_tool` in `ALWAYS_ON_CORE_NAMES`. That absence *is* the observation | one grep |
| **F7** (args unvalidated) | call any federated tool through `invoke_tool` with one argument key misspelled; observe whether the error names the key. Predicted: it does not — the Go typed-struct drops it and the failure reads "missing required" | one live MCP call |
| **F8** (mode flip breaks the prefix) | `SELECT session_id, count(DISTINCT context_breakdown->>'…') …` — better: read the persisted `chat_messages.context_breakdown` (`migrate.py:198-199`) and compare `mcp_tool_schemas` + `frontend_tool_schemas` token counts between consecutive turns of the same session, split by whether the turn's `permission_mode` differed. This re-runs the POC's 1,973-turn analysis with one extra grouping column and needs **no new instrumentation** | one query over existing data |

---

## Part 4 — what this means for the design, stated plainly

1. **A7 must be split.** "Guidance in the conversation" and "capability in the conversation" are two
   claims. The first is possible and cheap. The second is **not available on the chat path** — a
   schema in a message does not make a call emittable, and this repo has no envelope on that path.
   The design should say `invoke_tool`-style envelope, not "delivered as a message", or A7 is
   untestable.

2. **A durable announcement needs a durable home, and there isn't one.** Before any of A7 can be
   measured, `chat_messages` needs a pinned row type that (a) the `LIMIT 50` window exempts,
   (b) `persist_auto_compact` refuses to cross, and (c) the summariser is forbidden to paraphrase.
   All three are new. Shipping A7 without all three converts one measured silent deletion into
   **four unmeasured ones** — which is a strictly worse position than today.

3. **A6 is non-fatal and should be re-scoped to a rate, not a boolean.** The +65% number is real and
   the mechanism is real; the design reduces the *frequency* of block changes by roughly an order of
   magnitude and cannot eliminate them while `ask`/`plan`/`write` remains a per-message control.

4. **The cheapest rival shape is visible from here.** Axes 8–10 (F18 breaker, rail gating, oneshot
   de-advertise, mid-turn `tool_load`) account for the *entire* mid-turn mutation class and are the
   ones R19 says to move to conversation state. Freezing the block *within a turn only* — leaving
   the per-session shape axes alone — captures the measured mid-turn multiplier (2.03 avg / 24.4 p99
   passes) with none of A7's new deletion surface. That is a substantially cheaper change than
   1 + 4 + 3, and it should be priced before the full rebuild is approved.
