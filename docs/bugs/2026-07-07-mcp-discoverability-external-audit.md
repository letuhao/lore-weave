# LoreWeave MCP (`ai-gateway`, http://localhost:5174/mcp) — Discoverability Feedback

**Source:** external, user-supplied — a cold-start exploration session (2026-07-07) with no prior
documentation: an agent given only the endpoint URL and a bearer token, told nothing else about the
server. Goal was to answer: *can an agent self-discover this API's full capability surface using
only the tools it exposes?* Short answer: **no, not reliably** — the write-safety model
(propose/confirm) is solid, but the discovery layer has real gaps that hide working functionality.

Pasted verbatim into the session that produced
[`docs/specs/2026-07-07-mcp-discovery-and-reliability-hardening.md`](../specs/2026-07-07-mcp-discovery-and-reliability-hardening.md)
— see that spec for root-cause analysis, cross-referencing against the internal chat-service
`tool_discovery.py`/`find-tools.ts` code, and the fix design. This file is the raw input, kept
unedited so the spec's citations stay traceable to the original repro steps.

## Summary

| # | Issue | Severity |
|---|-------|----------|
| 1 | `find_tools` under-returns on generic/exploratory queries, sometimes to zero, even for domains with 10+ real tools | High |
| 2 | Entire `knowledge` domain (`kg_*`, `memory_*`) is unreachable via the documented discovery path (`find_tools`→`invoke_tool`), despite the tools existing and working | High |
| 3 | Server's own built-in prompts reference tools that are unreachable per #2 | Medium |
| 4 | `invoke_tool`'s allowlist is inconsistent with what raw `tools/call` accepts (some names it refuses work fine when called directly) | Medium |
| 5 | No "list all tools in a domain" affordance — only fuzzy top-K search | Medium |
| 6 | `registry` / `story` domains listed in `find_tools`'s `group` enum return nothing for any query, and known tool names (e.g. `story_search`) come back "not available to this key" — unclear from the API alone whether this is entitlement-gating or an incomplete rollout | Low/unclear |
| 7 | `composition_create_work` requires an undocumented `project_id`; no discoverable way to obtain one (chains into #2) | High |
| 8 | `confirm_action` fails a valid, unexpired, correctly-formed token with a non-actionable error (`AUTH_APPROVAL_EXECUTE_FAILED`) — no reason, no fix pointer | High |
| 9 | Every response duplicates its payload (`content[0].text` = same JSON again inside `structuredContent`) — ~2x tokens on every call, cutting against the server's own token-efficiency design goal | Medium |
| 10 | At least 4 incompatible error shapes across the API (raw JSON-RPC error / gateway refusal / Pydantic validation text / nested business-code) with no common envelope to branch on | Medium |
| 11 | A propose call with no real target (e.g. `glossary_adopt_standards` with no kinds/genres) silently returns a confirmable-but-no-op token instead of warning | Low |

## Detail & repro

### 1. `find_tools` under-returns on generic queries

Called `find_tools({ intent: "list everything you can do in this domain", group: <g> })` for every
group in the documented enum. Result:

- `book`: **1** tool returned (`book_get_chapter`), `low_confidence: true`.
- `jobs`: **3** tools returned (`jobs_list`, `jobs_pause`, `jobs_summary`).
- `knowledge`, `plan`, `registry`, `story`: **0** tools returned ("No tool matched").

Re-ran with a specific, multi-facet intent instead:

- `book` + `"create a book, list my books, create chapter, update chapter, delete chapter, write
  prose"` → **15** tools.
- `jobs` + `"fetch a single job by id and service"` → **5** tools, including `jobs_get` and
  `jobs_cancel`, neither of which appeared in the generic-query result above.

**Impact:** an agent doing normal, good-faith exploration ("what can I do here?") will conclude the
API is far smaller than it is, and may miss specific tools (`jobs_get`, `jobs_cancel`) entirely
unless it happens to phrase a query that matches their embedding.

**Suggestion:** either add a true enumeration affordance (e.g. `find_tools` with no `intent`, or a
separate `list_tools(group)`, returns everything in that group unranked) or lower the match
threshold / raise `low_confidence` recall so broad queries don't silently drop 80%+ of a domain.

### 2. `knowledge` domain is a dead end through the intended path

`find_tools({ group: "knowledge", intent: <anything> })` returns `{"tools": []}` for every wording
tried, including the exact tool names guessed later (`"memory_recall_entity kg_graph_query
knowledge graph nodes edges"`).

`invoke_tool({ name: "memory_recall_entity", arguments: {} })` and
`invoke_tool({ name: "kg_graph_query", arguments: {} })` both return:
```
{"error": "'<name>' is not available yet — call find_tools with what you want to do, then invoke_tool with a name it returns."}
```

But calling the same names directly at the JSON-RPC level, bypassing `invoke_tool` —
`tools/call {"name": "kg_graph_query", "arguments": {}}` — returns a real, working response:
```json
{"success": false, "error": "no project in scope — pass the optional `project_id` argument (list your projects with kg_project_list), or open this chat from a project"}
```
and `tools/call {"name": "kg_project_list", "arguments": {}}` returns
`{"projects": [], "more": false, "note": "pass a project_id to a project-scoped kg_* tool to act on that project"}` — a fully functional tool.
`memory_search` and `memory_recall_entity` likewise respond with normal Pydantic argument-validation
errors (i.e., they exist and are wired up), not "not available" errors, when called directly.

**Impact:** any agent that follows the server's own documented protocol
(`find_tools` → `invoke_tool`) can never reach the knowledge-graph/memory subsystem, even though it
is live and functional. This isn't a permissions/entitlement gap (direct calls succeed) — it's
specifically the discovery+dispatch layer failing to route these.

### 3. Built-in prompts reference the unreachable tools

The server registers two MCP prompts:
- `entity_dossier(entity_name)` — description: "Compile a deep-dive dossier on one story entity via
  `memory_recall_entity` and `kg_graph_query`."
- `recap_story_so_far(project_id)` — description: "Build a grounded recap ... using the memory
  tools."

Both point an agent at exactly the tools described in #2, which the agent has no documented way to
find. Following the server's own suggested usage (invoke the prompt, then use the tools it names)
leads directly into the `invoke_tool` refusal in #2.

### 4. `invoke_tool` allowlist vs. raw `tools/call` inconsistency

`book_list` (and every other domain tool tried) works identically whether called via
`invoke_tool({name: "book_list", arguments: {}})` or directly via
`tools/call {"name": "book_list", "arguments": {}}` — i.e., `invoke_tool` is not the only path to
execute a real tool, and isn't acting as an access-control boundary. Yet for `kg_*`/`memory_*`
names, `invoke_tool` actively refuses while raw `tools/call` succeeds (#2). The two dispatch paths
disagree with each other about which tools exist. If `invoke_tool`'s allowlist is meant to be
authoritative, raw `tools/call` shouldn't route around it; if it isn't meant to be authoritative,
its refusal message ("is not available yet") is misleading — it reads as "this tool doesn't exist
yet" rather than "this wrapper doesn't know about it yet."

### 5. No enumeration affordance

There is no tool equivalent to "give me every tool in group X, unranked, unfiltered." Everything
goes through similarity search against an `intent` string. For an API surface this large (11
documented domains, 50+ real tools), that makes full discovery dependent on guessing the right
phrasing per domain — reproducible in principle (an agent with unlimited turns can eventually
brute-force it via many query variations, as this session did) but not reliable in one or two
good-faith passes.

### 6. `registry` / `story` — unclear whether gated or unfinished

Every tool name guessed for `registry` (`registry_provider_list`, `registry_credential_list`,
`registry_list_providers`, `registry_model_list`) and `story` (`story_search`,
`story_search_chapters`, direct and via `find_tools`) returned:
```
{"error":{"code":-32601,"message":"tool '<name>' is not available to this key"}}
```
This is a different, more specific error than the `knowledge`-domain case (#2's "not available
yet" wrapper message vs. this JSON-RPC method-not-found on the *real* dispatch). It's plausible
this is intentional entitlement-gating (these domains may require a higher plan/tier), but nothing
in `find_tools`'s output, the `initialize` instructions, or the group enum itself signals that —
a caller has no way to distinguish "this domain doesn't exist for anyone" from "this domain exists
but your key isn't entitled to it" without trial and error.

## What works well (for balance)

- The Tier-W **propose → `confirm_token` → `confirm_action`** pattern for destructive/costly writes
  is consistent, well-documented per-tool, and was never bypassable in testing — this is the part
  that actually needs to be a hard boundary, and it is.
- Tool descriptions themselves (once found) are unusually good: they state preconditions ("VIEW on
  the book required"), reversibility ("Reverse: book_chapter_delete (trash)"), cost implications,
  and cross-references to the tool that should be called next. This is the opposite of the
  discoverability problem — the *content* is high quality, it's the *retrieval* of that content
  that's unreliable.
- `initialize`'s `instructions` field correctly primes an agent to use `find_tools` first, which is
  the right instinct for keeping schema bloat out of context — the gap is in `find_tools`'s recall,
  not the overall architecture.

## Bug tracking log (ongoing, found during live ontology/KG work on book Mị Đế)

New issues found while actually using the API for real work get appended here, dated, instead of
folded into the exploration report above.

### 2026-07-07 — `composition_create_work` requires an undocumented `project_id`

`find_tools({ group: "composition", intent: "create a book, list my books, create chapter, update
chapter, delete chapter, write prose" })` returned this description for `composition_create_work`:

> "Create (or get, idempotently) the composition Work for a book — the authoring context you
> compose in. Returns the Work. EDIT on the book required (auto-applied)."

No mention of any argument besides the implied `book_id`. Calling
`invoke_tool({ name: "composition_create_work", arguments: { book_id: "<real id>" } })` fails:

```
Error executing tool composition_create_work: 1 validation error for composition_create_workArguments
project_id
  Field required [type=missing, input_value={'book_id': '...'}, input_type=dict]
```

So the tool's actual schema requires `project_id` (presumably a `knowledge`-domain project, see
issue #2 above — `kg_project_list` returns `{"projects": []}` for this account, so there may not
even be one to pass yet), but neither `find_tools`'s description nor any error message *before*
this one hints that a knowledge project must exist first, or how to create one. This chains into
issue #2: the `knowledge`/`kg_project_*` tools needed to satisfy this dependency aren't discoverable
via the documented path either. **Net effect: composition Work cannot be bootstrapped for a book
through the documented discovery flow at all.**

**Suggestion:** either make `project_id` optional (auto-create a default knowledge project for the
book, consistent with the tool's own "idempotently" language), or have `find_tools`'s description
for `composition_create_work` state the prerequisite and name the tool that creates a project.

### 2026-07-07 — `confirm_action` rejects a valid, unexpired token with no actionable reason

While applying an ontology change to book Mị Đế (`glossary_adopt_standards`, adopting 5 missing
system-standard kinds — `event`, `terminology`, `plot_arc`, `trope`, `relationship`), the propose
call succeeded normally and returned a well-formed, non-destructive preview:

```json
{"authority":"grant","confirm_token":"eyJ...","descriptor":"adopt","destructive":false,
 "expires_at":"2026-07-07T14:19:32Z",
 "preview_rows":[{"label":"kinds newly adopted","note":"+ unknown (always)","value":"5"}]}
```

Replaying that exact token, well before `expires_at`, via
`invoke_tool({name:"confirm_action", arguments:{confirm_token, domain:"glossary"}})` fails every
time:

```json
{"code":"AUTH_APPROVAL_EXECUTE_FAILED","message":"the action's service rejected the confirmation"}
```

Tried `domain` set to `glossary`, `book`, and `settings` — identical error regardless, ruling out a
domain-mismatch explanation. The `find_tools` description for `confirm_action` states: *"Available
only to keys with self-confirm enabled; otherwise such actions wait for the owner to approve
them."* — so this is very likely that: the key in use was told to us by its owner as having "full
approval rights," but the server disagrees, and self-confirm is not actually enabled for it.

**This is not necessarily a backend bug** — refusing to let a non-privileged key self-approve a
Tier-W action is almost certainly correct, intentional behavior. **The actual defect is
diagnosability**: `AUTH_APPROVAL_EXECUTE_FAILED — "the action's service rejected the confirmation"`
gives the caller (human or agent) zero information to act on. It doesn't say *why* (self-confirm
disabled? key revoked? action expired-but-clock-skewed? wrong domain? owner review required?), and
it doesn't point at the fix (where to enable self-confirm, or that it now sits in an owner review
queue). A caller who was explicitly told "this key can approve anything" has no way to discover from
this error alone that the premise was wrong.

**Suggestion:** make `AUTH_APPROVAL_EXECUTE_FAILED` (or a more specific code) state the concrete
reason — e.g. `"self-confirm is not enabled for this API key; ask the account owner to approve this
action in LoreWeave, or enable self-confirm for this key in Settings"` — mirroring the detail
`find_tools`'s own tool description already has, just not surfaced at the point of failure.

### 2026-07-07 — Every response payload duplicates its data (plain text + structuredContent)

Every single tool result observed this session — from a one-line `jobs_summary` to the 46KB
`glossary_book_ontology_read` dump — comes back shaped as:

```json
{"result": {
  "content": [{"type": "text", "text": "<the FULL result, JSON-stringified and escaped>"}],
  "structuredContent": { /* the SAME result, as real JSON */ }
}}
```

The `text` field is not a summary or a truncated preview — it's the entire payload, double-escaped,
sitting right next to an identical parsed copy in `structuredContent`. For the ontology read alone
this roughly doubles the ~23K-token response for no informational gain to a client that reads
`structuredContent` (which is the correct field to read once it's present).

This is technically MCP-spec-legal (`content` is kept for clients that don't understand structured
output), but it directly cuts against this server's own stated design goal: the entire
`find_tools`/`invoke_tool` indirection layer exists specifically to keep token/context usage down for
LLM callers (see `initialize.instructions`). Paying 2x tokens on every large read (ontology dumps,
`glossary_search`, `jobs_list`, chapter bodies via `book_get_chapter`) works against that goal on
every single call, not just the schema-bloat problem the gateway addresses.

**Suggestion:** when `structuredContent` is present, drop the duplicate JSON blob from `content` and
put something short there instead (e.g. `"see structuredContent"` or a 1-line human-readable
summary) — or make it configurable per-client via a capability flag.

### 2026-07-07 — At least four incompatible error shapes for "this didn't work"

Across this session, failures came back in at least four distinct shapes, depending on *why* the
call failed, with no shared structure a caller could branch on generically:

1. Raw JSON-RPC protocol error — unknown/unpermitted tool name at the real dispatch layer:
   `{"error":{"code":-32601,"message":"tool 'story_search' is not available to this key"}}`
2. `invoke_tool`'s own refusal for a tool its allowlist doesn't recognize (different from #1 even
   though the underlying tool exists — see issue #2 above):
   `{"result":{"content":[{"text":"{\"error\":\"'memory_recall_entity' is not available yet — ...\"}"}],"isError":true}}`
3. Pydantic argument-validation failure on a real, permitted tool:
   `{"result":{"content":[{"text":"invalid arguments for jobs_get — \`service\`: Field required ..."}],"isError":true}}`
   (sometimes as prose, sometimes — e.g. `composition_write_prose` — as a raw Pydantic traceback-style
   dump with a `https://errors.pydantic.dev/...` link, which leaks implementation detail)
4. A business-rule rejection with its own nested code, still wrapped in the generic envelope:
   `{"result":{"content":[{"text":"{\"code\":\"AUTH_APPROVAL_EXECUTE_FAILED\",\"message\":\"...\"}"}],"isError":true}}`

A caller has to pattern-match on prose strings to tell "you typed the wrong tool name," "this tool
isn't in my index yet," "you're missing a required field," and "the backend refused for a business
reason" apart — there's no consistent `{code, message}` envelope across all four, even though shape
#4 shows the server clearly has such a structured-error convention available when it wants to use it.

**Suggestion:** normalize every failure path — missing tool, gateway refusal, validation, and
business-rule rejection — onto the same `{code, message, ...}` shape already used for shape #4
(`isError: true` alone isn't enough signal to build reliable retry/fallback logic on).

### 2026-07-07 — A "propose" call with no real target silently succeeds instead of warning

Calling `glossary_adopt_standards` with only `book_id` (no `kinds`, no `genres`) does not error or
warn that there's nothing meaningful to do — it returns a fully valid `confirm_token` with a preview
showing `"kinds newly adopted": "0"` (only the always-included `unknown`/`universal` are counted,
already present). A caller that doesn't read the preview closely could easily confirm a token that
accomplishes nothing and believe an action succeeded. Minor, but for a system built around "read the
preview before confirming" as its core safety mechanism, a no-op should arguably be flagged (e.g.
`"warning": "no genres or kinds specified — this will adopt nothing new"`) rather than presented as
an equally valid, confirmable proposal.
