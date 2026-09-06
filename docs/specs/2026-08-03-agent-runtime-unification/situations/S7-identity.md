# S7 — P1 IDENTITY + LIFECYCLE, coverage interrogation

**Module:** P1 · *a declaration has a stable id, an owner, a lifecycle state, a revision history —
"does this exist, whose is it, is it safe to retire".*
**Status:** interrogation. Two questions only — what situation does identity exist to solve, and what
will certainly happen that it has no defined answer for.
**Method:** grounded against the live catalog (re-measured 2026-08-04), the code that implements
deprecation today (`_meta.visibility`, `superseded_by`, `is_legacy_tool`, `pinned_legacy_tools`),
`scripts/deprecated-tool-scan.py`, the `contracts/` name-keyed artifacts, `services/agent-registry-service`
migrations, and the public edge (`services/mcp-public-gateway`). Every claim carries a file:line or a
measurement command.
**Design read:** `ARCHITECTURE.md` §0, §0.2, §0.3, §3, §4, §6, §7, §8 · `SPEC.md` §3, R9, R13, R15–R21,
§8, §10.0 (Q14 ANSWERED).

---

## 0 · The measurement, re-run today

```
$ python scripts/deprecated-tool-scan.py --list
202 advertised · 114 retired
```

Derived from that catalog (`build_catalog()`, so it is the same source the pre-commit gate uses):

| fact | value |
|---|---|
| retired declarations | **114** |
| …that declare a successor | **53** (46%) |
| …that declare **no** successor at all | **61** (54%) |
| distinct successor targets | **16** |
| fan-in ratio | **3.3 : 1** |
| largest consolidation | **6 → `composition_arc_edit`** |
| next largest | 5 → `composition_structure_template_edit`, 5 → `composition_outline_node_edit`, 5 → `composition_authoring_run_manage` |
| successor edges pointing at a target that is **itself retired, with no onward successor** | **2** — `composition_get_prose → book_get_chapter`, `composition_publish → book_chapter_publish` |
| successor edges crossing an **owner-service boundary** | **3** — the two above plus `composition_write_prose → book_chapter_save_draft` |

This confirms and slightly refines SPEC §10.0's Q14 answer (54 → 17 there; 53 → 16 here — the delta is
one edge whose target has since been re-registered discoverably, which `build_catalog()` resolves by
`legacy.pop(name)`). **The conclusion is unchanged and is the premise of this whole document:**

> **The primary migration operation is CONSOLIDATION, not rename.**

---

## 1 · What situation does identity/lifecycle exist to solve?

Not "we need version numbers." The situation, stated from the evidence:

> **A declaration's NAME is its only identity, and 23 independent artifacts are keyed by that name —
> across five services, three languages, two databases, Redis, and third-party API keys we do not
> control. There is no record of what a name meant, no record that it changed, and no way to ask who
> is holding one. So a change to a declaration is not a change to a declaration: it is 23 silent,
> uncoordinated breakages, and the only one anybody notices is the one that produces a support ticket.**

The name-keyed artifacts, enumerated because the count is the argument:

| # | artifact | file:line | what a consolidation does to it |
|---|---|---|---|
| 1 | `_meta.visibility` / `superseded_by` (Go) | `sdks/go/loreweave_mcp/meta.go:22,27,100-110` | the only place the edge is *written* |
| 2 | `_meta` (Python) | `sdks/python/loreweave_mcp/meta.py:91,135-136` | ditto |
| 3 | `is_legacy_tool` runtime filters ×7 | `tool_discovery.py:501,575,605,736,869,912,1041,1338` | 7 sites decide availability from an artifact flag |
| 4 | `tool_superseded_by` readers ×2 | `tool_discovery.py:922,1043` | **label only** — never forwards |
| 5 | `find-tools.ts` `superseded_by` | `services/ai-gateway/src/federation/find-tools.ts:178-181,217,561` | label only |
| 6 | `chat_sessions.enabled_tools TEXT[]` | `chat-service/app/db/migrate.py:513-514` | stored names go stale silently |
| 7 | `chat_sessions.activated_tools` | same file | ditto |
| 8 | `chat_sessions.pinned_legacy_tools TEXT[]` | `migrate.py:591-592` | validated **at write** only (`sessions.py:317-324`) |
| 9 | `chat_suspended_runs.pending_tool_call JSONB {id,name,args}` | `migrate.py:307-327` | a frozen mid-flight call, 6 h TTL |
| 10 | `chat_suspended_runs.pinned_step_tools JSONB` | `migrate.py:351-360` | the rail's step tools by name |
| 11 | `chat_suspended_runs.working JSONB` | `migrate.py:315-317` | the whole conversation, tool calls by name |
| 12 | `workflows.steps[].tool` (jsonb) | `agent-registry/internal/migrate/migrate.go:405`; shape `internal/api/workflows.go:40-66` | a free string; `validateWorkflow` *"deliberately does NOT check tool-catalog membership"* (`workflows.go:135-138`) |
| 13 | skill named-tools prose | R3 | regex-scraped backticks. **There is no `allowed_tools` column anywhere** — `skills_md.go:41-48` parses only `name/description/surfaces` |
| 14 | `contracts/tool-liveness.json` | keyed by name; **contains retired names** (`book_chapter_publish: RED`) | a CD4 ship-gate keyed on a dead name |
| 15 | `contracts/frontend-tools.contract.json` | 11 name keys with `required` arg lists | the FE bridge breaks on a schema change |
| 16 | `FRONTEND_TOOL_NAMES` frozenset | `chat-service/app/services/frontend_tools.py:47` | "executes on the client" is a name-set |
| 17 | `TOOL_POLICY` — **170 entries**, `{tier, domains}` | `mcp-public-gateway/src/scope/tool-policy.ts:87-338`, lookup `:358` | hand-maintained; **no version, no deprecation, no successor, no sunset** |
| 18 | `mcp_api_keys.scopes TEXT[]` | `auth-service/internal/migrate/migrate.go:205` | issued to third parties; binds to tools *indirectly*, via `TOOL_POLICY` |
| 19 | `mcp_oauth_grants.scopes TEXT[]` | `migrate.go:318` | ditto, and irrevocable-in-practice |
| 20 | idempotency namespace `mcp:idem:${keyId}:${toolName}:${idemKey}` | `mcp-public-gateway/src/idempotency/idempotency.ts:105-107` | **name is in the Redis key** |
| 21 | session tool-activation set (Redis SET of names) | `src/session/tool-activation-store.ts:40-48` | gate at `public-mcp.controller.ts:155-169` |
| 22 | `mcp_pending_approvals.tool_name` | `auth-service migrate.go:~283` | durable rows carrying a name |
| 23 | `mcp_call_audit.tool_name` | `migrate.go:225-231` | append-only; **no `GROUP BY tool_name` query exists**, no index on the column (`migrate.go:249-250`) |

**And the thing that makes it a lifecycle problem rather than a refactor problem is #18/#19: keys we
issued to people we cannot call.** `ARCHITECTURE.md` §1 already names this as what killed A9 big-bang
deprecation. What the design has not yet absorbed is that the *same* fact makes the retire criterion
uncomputable: **there is no way to ask "which tools does key X use."** Row 23 is an event log with no
aggregation endpoint (`auth-service/internal/api/mcp_audit.go:121-127` is a raw newest-first page) and
no index on `tool_name`.

### 1.1 What the current mechanism actually is

Three things wearing one costume, which is R9.2's diagnosis restated with the numbers:

- **`visibility: "legacy"`** — a two-valued enum. No clock, no `deprecated_at`, no `sunset_at`, no
  owner. Read at 7 runtime filter sites with no policy layer.
- **`superseded_by`** — a **single string**, documented as the rename pointer:
  *"Pair it with `WithVisibility(..., VisibilityLegacy)` **when a tool is renamed**"*
  (`sdks/go/loreweave_mcp/meta.go:100-110`). The measurement says renames are 3% of the population and
  consolidations are the rest. **The field's documented semantics and its measured usage disagree.**
- **`pinned_legacy_tools`** — a per-session escape hatch on the `chat_sessions` row. R9.2's proof #1.

And one thing that is neither: **`retired` does not mean removed.** `composition_arc_edit`'s handler
*calls* `composition_arc_create` (`services/composition-service/app/mcp/server.py`, the `op == "create"`
branch dispatches into `composition_arc_create(ctx, _ArcCreateArgs(...))`). The scanner records this
deliberately (`deprecated-tool-scan.py`, `_INTERNAL_DISPATCH`): *"Retired tools deliberately stay
CALLABLE (hidden, not deleted) so undo and cached workflows keep working."* The consolidation target
**depends on** its own predecessors.

---

## 2 · The coverage tests

Legend — **D:** does the design (ARCHITECTURE + SPEC) answer it. **CT:** Ceiling Test (§0.3) verdict on
the mechanism the answer implies. Verdicts: ✅ ANSWERED · ⚠️ PARTIAL · 🔴 MISSING.

---

### S7-1 · SIX declarations consolidate into one 🔴 D: PARTIAL — the edge is defined, the *migration* is not

**Real, and the largest instance.** Six → `composition_arc_edit`.

**What the design says.** SPEC §10.0 Q14 gets the identity part exactly right and I have nothing to add
to it: `tool_id` never transfers; `superseded_by` is a many-to-one **edge**, not an identity
continuation; usage aggregates along the edge.

**Which id survives:** answered. **None.** `composition_arc_edit` gets its own `tool_id`; the six keep
theirs. Correct.

**What happens to the usage history of the other five:** *specified and uncomputed.* Q14 says *"usage
history aggregates along the edge (R9.6's retire criterion sums the sources into the target)."*
Verified today: **no tool-level usage counter exists anywhere.** `used_count` / `last_run_at` /
`last_triggered_at` are columns on `skills` and `workflows` only
(`agent-registry-service/internal/migrate/migrate.go:104-105, 409-410`) and R9.6's claim that nothing
writes them still holds. The public edge has `mcp_call_audit.tool_name` — the only per-name usage fact
in the system — and no query that aggregates it. **The aggregation is a sentence, not a mechanism, and
the only data that could feed it is unindexed.**

**What a third-party key bound to a dead name gets:** 🔴 **and this is the sharp one.**
`-32601` with *"tool '&lt;name&gt;' is not available to this key"*, on HTTP 200
(`mcp-public-gateway/src/scope/scope-filter.ts:20,33-44,55-73`). That message is **deliberately
identical** for *"does not exist"* and *"out of your scope"* — an explicit anti-oracle contract at
`scope-filter.ts:38-40`, with a test pinning it (`test/tool-policy.spec.ts:37-53`).

> **R9.3 requires `retired ⇒ absent + a tombstone error naming the successor`. The public edge has a
> stated security invariant that forbids exactly that.** These are not in tension; they are
> contradictory, and no document notices.

**The real breakage nobody has costed.** A consolidated tool's `domains` is the **union** of its
predecessors' domains, and `isToolAllowed` requires the key to hold `domain:<d>` for *every* `d`
(`tool-policy.ts:360-363`). So an already-issued key that could call all six predecessors may be
unable to call the successor — a silent, permanent 403 on a key we cannot re-consent. This has already
happened once and was worked around by hand: `glossary_web_search` → `web_search` was resolved by
**keeping both rows in different domains**, with a test asserting the alias is *non-transparent*
(`tool-policy.ts:173-179`). That workaround is the only migration mechanism the public edge has, and it
is a comment.

**CT:** the *edge* is an enabler (adds information). The *anti-oracle* answer is a ceiling of the worst
kind — the caller is told "no" with no locus, which is §0.5's failure shape #3 exported to third
parties.

---

### S7-2 · The successor edge names a TOOL, not a CALL 🔴 D: NO

`composition_arc_edit` is **enum-dispatch on `op`**: `op=create|update|delete|restore|move|assign_chapters`,
with per-op required fields (`server.py`, `_ArcEditArgs`). A caller migrating off
`composition_arc_create` is told `superseded_by: "composition_arc_edit"` and that is all it is told. It
must additionally discover:

1. the discriminator field name (`op`),
2. its correct value (`"create"`),
3. that `expected_version` is now required for `update` (OCC) and was not before,
4. that `book_id` vs `node_id` requirements changed per-op.

**None of this is expressible in a single string.** SPEC has a `migration_note` field in the R1 artifact
row (§3, line ~263) — it appears **nowhere else in the spec** and nothing populates it. Q14's corrected
model still models the edge as tool→tool.

**CT: 🔴 ceiling.** The model is told the replacement's name and cannot reach the action without
guessing. §0.3's rule — *"the withheld thing must remain reachable on request"* — is satisfied
literally (the old tool is still callable) and violated in effect (the migration path is not
information the model has).

---

### S7-3 · A declaration is SPLIT (one becomes two) 🔴 D: NO — not representable

`superseded_by` is `map[string]string` (`meta.go:109`) / `meta["superseded_by"] = superseded_by`
(`meta.py:136`). Q14's corrected model is explicitly **many-to-one**. One→two has no shape in either.

This is not hypothetical for this plan. It is the **failure mode of shape 1+4**, and the spec already
asks about it: **N1 — *"how far do the reads consolidate? … does the tail reappear?"*** (§10.0). If N1
answers "the tail reappears", the corrective action is a split, and the migration chain has no edge
type for it, the manifest has no field for it, and R13.2's classifier — `added · removed · renamed ·
additive · breaking` — has no class for it either. A split registers as `added` + a `breaking` change
on the original, with nothing connecting them.

**CT:** neutral (invisible to the model) — but it is the mechanism that decides whether the coarse
capability of shape 1+4 is *reversible*. An irreversible coarsening is a ceiling by §0.3's own
argument.

---

### S7-4 · BEHAVIOUR changes; name and schema do not 🔴 D: NO

The only change-detection artifact on the wire is
`version = sha256(JSON.stringify(tools.map(t => [t.name, t.inputSchema]))).slice(0,16)`
(`services/ai-gateway/src/federation/catalog.ts:85-88`). **`description` is not hashed.** R9.2 point 4
states this; here is what follows from it for the *new* design specifically:

- **R13.2's migration classifier cannot see it.** All five classes (`added/removed/renamed/additive/breaking`)
  are schema-shaped. A rewritten description generates no migration entry, so CI's *"live ≠ snapshot and
  no migration entry ⇒ red"* never fires.
- **R19 makes this a correctness bug, not a hygiene one.** R19: *"the advertised tool block is
  cache-prefix state."* A description change **is** a cache-prefix change. It is the single field with
  the largest effect on model behaviour and it is the one field with no version, no migration entry, and
  no cache-invalidation signal.
- **R18 measured the cost already:** lifecycle state and description prose agree **36%** of the time.

A behaviour change with an unchanged schema (a tool that starts soft-deleting instead of hard-deleting;
a `limit` default that changes; a search that switches ranker) is **completely invisible** to every
mechanism in R13. Nothing in ARCHITECTURE §4's C-1…C-12 requires a semantic version, and nothing
requires that a behaviour change bump anything.

**CT:** neutral, but it silently defeats R19 and R13.2, both of which are load-bearing.

---

### S7-5 · A declaration changes OWNER SERVICE ⚠️ D: PARTIAL

**Real, ×3, today** (§0): `composition_publish → book_chapter_publish`,
`composition_get_prose → book_get_chapter`, `composition_write_prose → book_chapter_save_draft`.

SPEC §3's artifact row has `owner_service`. Nothing says what happens when it changes. Three mechanical
consequences, none addressed:

1. **The name must change.** ai-gateway enforces a provider-prefix gate — a tool escaping its provider's
   prefix is dropped (`catalog.ts`, and the mirrored rule stated for resources at `catalog.ts:141-148`).
   So an owner-service move is *forced* to look like a rename, for a change that is not a capability
   change at all. Identity and hosting are conflated at the wire level.
2. **`TOOL_POLICY`'s `domains` are re-derived**, so §S7-1's scope-union breakage applies to a pure
   re-homing.
3. **`SPEC` Q9 — *"do the 114 legacy tools get retired, or re-homed?"*** is still open, and the answer
   changes which of the two above bites. It is scheduled after the phase that would need it.

---

### S7-6 · A skill's MEMBER SET changes 🔴 D: NO — the member set does not exist yet, and the revision table cannot hold it

Under `ARCHITECTURE.md` §0.2 a skill **is** a named set of declarations plus guidance. Under R20 a
capability and its guidance are one unit. So a member-set change is a change to the skill's substance.

**But there is no member set in data today.** Verified: no `allowed_tools` / `tools` / join table on
`skills` or `skill_revisions`; the SKILL.md parser recognises exactly three frontmatter keys —
`name`, `description`, `surfaces` (`agent-registry-service/internal/api/skills_md.go:41-48`) — so an
authored `allowed-tools:` line is **silently discarded**; and the consumer contract carries no tool set
(`chat-service/app/client/user_skills_client.py:12`). The only skill→tool binding anywhere is
`SkillDef.hot_domains: frozenset[str]` — **GROUP_DIRECTORY domains, hardcoded in Python**
(`chat-service/app/services/skill_registry.py:39`), changeable only by deploy.

So R3 does not *change* a skill's member set; it **introduces one**, as a new mutable substance. Three
things follow, none addressed:

1. **`skill_revisions` cannot snapshot it.** Its columns are `revision_id, skill_id, description,
   frontmatter, body_md, created_at` (`internal/migrate/migrate.go:145-153`) — **no `surfaces`, no
   `steps`, no tools, no author, no revision number**. Even after R3 ships a member set, a member-set
   change is unsnapshotable without a schema change nobody has scoped.
2. **R3 makes the set DERIVED from the manifest** (SPEC §3: *"a skill owns exactly one group; its tools
   follow from the manifest"*). Therefore **admitting one tool into a group silently mutates the content
   of every skill that owns that group** — with no revision, no version bump, and no change to any skill
   row. §6's admission is literally *"one tool at a time"*, so **every single admission is an unrecorded
   edit to a skill.**
3. **Revision creation is not triggered where it matters anyway** (see S7-19).

**CT:** neutral, but it makes R20's *"one arrival channel"* unverifiable — you cannot assert a skill's
guidance matches its members if the members change underneath the guidance with nothing recording it.

---

### S7-7 · A workflow template is edited while a plan derived from it is mid-run 🔴 D: NO

The machinery for a mid-flight freeze already exists and already broke once for this exact reason:

`chat_suspended_runs` persists `pending_tool_call JSONB {id, name, args}`, `pinned_step_tools JSONB`,
and `working JSONB` (the whole conversation, tool calls by name), with
`expires_at DEFAULT now() + interval '6 hours'` (`chat-service/app/db/migrate.py:307-364`). The
`pinned_step_tools` column exists *because* **"the resume pass re-derives the tool surface from scratch"**
and *"the resumed turn read a recipe naming tools it could not call … the flagship rail broke at its
very first gate"* (`migrate.py:351-360`).

**So the situation is not hypothetical; it is the documented origin of a shipped column.** A deploy
between suspend and resume that consolidates a step's tool re-runs that incident, and this time
`pinned_step_tools` does not help — it pins the *name*, which is the thing that died.

**And the mid-run edit case is already live and already silent.** A running rail binds by **slug,
re-resolved from the registry on every pass.** `chat_suspended_runs` carries **no `workflow_id`, no
`revision_id`, and no frozen copy of `steps`**. On resume, `_compute_rail_drive_context`
(`chat-service/app/services/stream_service.py:591-644`) re-fetches by `book_id` (:608-610), reads
`mode_bindings.inject_workflows` — a `TEXT[]` of **slugs with no FK** (`migrate.go:797-798`) —
intersects with the visible slugs (:614-615), and rebuilds `rail_specs` from `wf["steps"]` **as they are
right now** (:626-631), against the live registry row (`workflows.go:817-823`).

> **If a workflow's `steps` change mid-run, the running turn silently adopts the NEW rail on its next
> pass, while `pinned_step_tools` still holds the OLD tool surface. The rail text and the tool surface
> can disagree, and nothing detects or reports it.**

A per-registry version counter exists and is not used for this: `bumpCatalogVersion` increments one
global `registry_meta.catalog_version` (`internal/api/server.go:498-503`, `migrate.go:82-86`) returned
with the workflow list (`workflows.go:858`) — **no consumer pins or compares it per run.**

`ARCHITECTURE.md` §0.4 promotes the plan to a first-class artifact and says the plan is *"cheap to
re-present every turn"*. It does not say:

- whether a plan pins the **workflow id** or a **workflow revision id** (today: neither — a slug);
- whether a plan's step pins a **declaration id** or a **name** (today: a bare name, and
  `validateWorkflow` *"deliberately does NOT check tool-catalog membership"*,
  `internal/api/workflows.go:135-138,173-175` — the only check is `toolBlocked` against a **statically
  embedded** `tool-liveness.json`, `liveness.go:50-51,78-82`, so a deleted or typo'd tool passes as
  merely *"unproven"*, `liveness.go:99-120`);
- what a replan (§0.5) does when the failure class is *"the declaration this step names was retired
  while you were running"* — which maps to none of the four plan-level classes
  (`step-local` / `binding-invalid` / `plan-invalid` / `needs-human`) cleanly. It is arguably
  `plan-invalid` ("the world moved"), but the correct transition is *rewrite the step against the
  successor*, which is not one of the four.

**CT:** 🔴 today (silent absence → the recipe names a tool that is not on the wire, S5-1's shape;
plus a silent mid-run substitution of the recipe itself). The fix is an enabler.

---

### S7-8 · The same logical capability exists on BOTH runtimes during transition 🔴 D: NO — and this bites at brick 2

This is the situation the transition plan *guarantees*, and the one the design is most explicit about
not having thought through.

- `ARCHITECTURE.md` §3: *"Old declarations are not hidden. They are absent. There is no branch in the
  new assembler that can read the old catalog."* The membrane is one-directional.
- `ARCHITECTURE.md` §7: the old runtime **stays live**, serving the public edge, the FE bridge and
  today's chat — *"That is not tolerated legacy. It is the control group."*
- `ARCHITECTURE.md` §8: bricks 2–5 are a zero-arg read, a name-arg read, a two-step pair, a confirmed
  write. **Every one of them is a capability that already exists as an old tool.**

So from brick 2 onward, one capability has two declarations, and no document says whether they are one
identity or two. Both answers are broken as things stand:

| | consequence |
|---|---|
| **same name** | `catalog.ts:78` — `if (map.has(t.name)) continue; // collision — keep first`. **Silent**, no `warn()` (contrast the resource path at `:141-148`, which warns). Which runtime serves the call is decided by provider iteration order. A §0.1 violation — the runtime narrows silently — committed by the *federation layer*, which is outside the new membrane and therefore outside M2's import gate. |
| **different name** | the control-group comparison in §7 has **no join key**. "The new runtime performs better than the old" is measured across two names with nothing in the manifest linking them, and `superseded_by` cannot be used because the old one is not superseded — it is the control. Meanwhile the model can see both and has no way to know they are the same thing (§0.3: it should be *told*, not filtered). |

**Nothing in P1 has a field for "this declaration is the new-runtime counterpart of that one."** It is
neither a revision (different runtime, different contract), nor a supersession (the old one must stay
live and un-deprecated *by design*, or the control group dies).

**CT:** 🔴 the same-name case is a silent narrowing. The different-name case is a measurement failure,
not a ceiling — but it invalidates the one claim the whole plan exists to prove.

---

### S7-9 · How long is a sunset window, and what starts the clock? ⚠️ D: the *length* is an open question; the *trigger* is not even asked

SPEC Q7 asks which window (MCP's 12 months vs a usage-based *"no session used it in N days"*) and is
listed **STILL LIVE**. Three things Q7 does not ask, and all three block answering it:

1. **What event starts the clock.** `_meta` has no `deprecated_at` (`meta.go:18-34` — the full key list
   is `tier, scope, undo_hint, synonyms, visibility, async, paid, superseded_by, ambient_book`). So the
   **114 tools already deprecated have no t=0** and never will retroactively. Whatever window is chosen,
   it cannot be applied to the existing population without inventing a date.
2. **Whether the clock is per-consumer.** MCP's 12 months exists for third-party clients. We have both
   populations behind one flag: our own agent (where the honest gate is a usage fact) and issued API
   keys / OAuth grants (where it must be a calendar). Q7 says *"pick one"* — **the evidence says a single
   answer is wrong**, because the two populations have different observability: usage is *unmeasurable*
   for our agent (no counters) and *unqueryable* for third parties (no aggregation).
3. **Whether we can even announce it.** Verified absent repo-wide: RFC 8594 `Sunset` header — 0 hits.
   `Deprecation` header — 0 hits. Public changelog — none (`docs/specs/2026-06-26-public-mcp/`, 6 files,
   0 hits for `deprecat|retire|rename|sunset|superseded|tombstone`). The edge sets only
   `WWW-Authenticate`, `Retry-After`, `content-type` (`public-mcp.controller.ts:483-488`). **There is no
   channel on which a sunset can be communicated**, so a published clock is currently unpublishable.

---

### S7-10 · A declaration is retired and someone wants the NAME back 🔴 D: NO — and M1 structurally cannot answer it

R9.3: *"`retired` ⇒ absent + a tombstone error naming the successor."* A tombstone is a **record of
something that no longer exists**. M1: the manifest is *"generated only from new-style declarations"*,
and M2 makes it the runtime's only catalog input.

> **A retired declaration has no declaration to generate a manifest row from. The mechanism that
> produces the manifest cannot produce a tombstone.**

Consequences today, which the new design inherits unless this is fixed:

- There is no tool table anywhere (R9.1: `grep -rn "tool_version\|tool_revision" services/` → empty), so
  a retired name is **reusable and the reuse is undetectable**. Re-registering `book_get` with different
  semantics would pass every gate: `deprecated-tool-scan.py` derives its catalog from live registrations
  (`build_catalog()`), and its dedup rule is *"A name re-registered discoverably wins over any legacy
  registration of the same name"* — i.e. **name reuse is explicitly the supported way to un-retire, with
  no check that the capability is the same one.**
- The name-keyed durable artifacts (§1, rows 6–11, 20–22) would silently rebind: a `pinned_legacy_tools`
  entry, a 6-h-old `pending_tool_call`, a `mcp_pending_approvals` row, an idempotency key. A reclaimed
  name makes a stale pointer *resolve* — which is worse than dangling, and is memory-lore's
  *"replacing a surface does not carry its guarantees"* in its most literal form.

**The other two declaration kinds already demonstrate the failure, in both directions.** Skill and
workflow slugs are unique per tier via partial indexes with **no status predicate**
(`migrate.go:116-118`, `:421-423`), so:

- an **archived** skill keeps its slug — a new one gets `409 DUPLICATE` (`skills.go:189-191`). Name
  reclaim is blocked, correctly, and by accident.
- a **hard `DELETE`** frees the slug the same millisecond, with **no tombstone, no reservation, no
  cooldown** (`skills_crud.go:224`, `workflows_rest.go:277`) — and it **cascades the revision history
  away** (`skill_revisions … ON DELETE CASCADE`, `migrate.go:145-153`). Because
  `mode_bindings.inject_workflows`/`inject_skills` reference by **slug string with no FK**
  (`migrate.go:797-798`) and the rail resolver matches on slug (`stream_service.py:614-615`), **a
  re-created object silently inherits every pin the deleted one had.**

So the substrate that P1 is meant to unify contains, today, one kind where the name cannot be reclaimed
and cannot be recorded as retired, and another where it can be reclaimed instantly and inherits the dead
object's bindings. Neither is the behaviour R9.3 specifies.

---

### S7-11 · Do evidence/usage counters aggregate along the `superseded_by` edge? 🔴 D: specified, nothing computes it, and it is undefined for 54% of the population

Q14 says they should. Verified: **nothing does, and nothing can.**

- **No tool-level counter exists.** Only `skills` and `workflows` have the columns
  (`agent-registry-service/internal/migrate/migrate.go:104-105, 409-410`); R9.6's finding that no
  statement writes them still holds, and `skills_crud.go:54` still offers
  `ORDER BY last_triggered_at DESC NULLS LAST` over a permanently-NULL column.
- **The one real per-name usage fact is at the public edge and unqueryable.** `mcp_call_audit.tool_name`
  (`auth-service migrate.go:225-231`); its only read endpoint is an unaggregated newest-first page
  (`mcp_audit.go:121-127`); the sole index is `(owner_user_id, key_id, created_at DESC)`
  (`migrate.go:249-250`) — **no index on `tool_name`**.
- **61 of 114 retired tools have no edge at all.** Their usage aggregates *nowhere*. For 54% of the
  deprecated population the sum has no destination, so R9.6's retire criterion is not merely uncomputed
  — it is **undefined**.
- **Two edges terminate on a retired target with no onward successor** (`composition_get_prose →
  book_get_chapter`; `composition_publish → book_chapter_publish`). Summing along the edge deposits the
  history on a tool that is itself awaiting retirement. **The aggregation is not transitive and nobody
  has said whether it should be.**

**And C-11 does not cover this.** ARCHITECTURE §4's C-11 (*resolvable references*) applies to **S** and
**W** — skill members and workflow steps. The **successor edge on a T is not covered by any clause**, so
the new manifest can ship the same dangling chain the old catalog has.

---

### S7-12 · Versioning: MCP defines no per-tool version 🔴 D: NO — the field is named and has no wire, no consumer, and no producer

SPEC §3's artifact row lists `version`. Three gaps:

1. **No wire field.** MCP has none, and SEP-1300 (the nearest proposal) was rejected (R9.4). The only
   version on the wire is `Catalog.version` — **one 16-hex hash for the entire list**
   (`catalog.ts:85-88`) — which changes when *any* tool's schema changes, so it can neither identify a
   tool's version nor let a consumer pin one.
2. **No stated consumer behaviour.** Nothing says what a client does with a version: pin? warn? refuse?
   The public edge negotiates only the **MCP protocol** version, and uses it solely to gate
   `structuredContent` rehydration for pre-`2025-06-18` clients
   (`structured-content-rehydration.ts:50`; applied `public-mcp.controller.ts:327-329`). That negotiates
   *wire shape*, never tool identity. There is no `X-API-Version`; the BFF mounts the edge at unversioned
   `/mcp` (`api-gateway-bff/src/gateway-setup.ts:290,573`).
3. **No producer.** Nothing in C-1…C-12 requires a version, so M4 (*"a non-compliant declaration cannot
   register"*) will happily boot a declaration with none.

**"Revision history" has the same problem one level up.** P1's own definition includes it; §0's
FRAMEWORK/RUNTIME table says the framework *"has history, versions, migrations"*; but the **manifest —
the only interface between them (§0) — is a snapshot**. No document says where a declaration's revision
history lives, who writes it, or whether the runtime can see it. Skills and workflows have revision
tables; the substrate that is supposed to unify all three kinds has no answer for the kind that has
none today.

---

### S7-13 · A lifecycle transition lands on a LIVE session 🔴 D: NO

R19: *"the advertised tool block is cache-prefix state: chosen once per session shape, never mutated
mid-turn"* — a changed block costs **+65% uncached tokens** and drops hit rate by a sixth.

A deploy that deprecates or admits a declaration changes that block **for every live session at once**.
Nothing says:

- when a lifecycle change takes effect (next turn? next session? on a manifest-version pin?);
- whether a session records the manifest version it started under;
- what happens to a `chat_suspended_runs` row (6 h TTL) whose `working` conversation contains calls to a
  declaration that was retired ten minutes ago.

At the public edge the same shape is already visible and already self-heals *loudly*: the Redis session
tool-activation set (`tool-activation-store.ts:40-48`) holds old names, so post-rename `invoke_tool(new_name)`
returns `TOOL_NOT_DISCOVERED` until the agent re-runs `tool_list` (`invoke-tool.ts:23,120-126`). That is
the good case — visible, recoverable. The chat-service case is the bad one, because the surface is
re-derived silently.

---

### S7-14 · The manifest has no identity clause at all 🔴 D: NO — P1 is named as a primitive and gated by nothing

This is structural and it is the reason most of the above stays missing by default.

- `ARCHITECTURE.md` §0.2 defines P1 in one line: *"a declaration has a stable id, an owner, a lifecycle
  state, a revision history."*
- **M4** — the only admission gate that can refuse a boot — is defined as: *"the registration entry point
  refuses to boot on an incomplete contract … this extends it to all of **P2**."*
- §4's P2 clause table is **C-1 … C-12**: `group/lane`, `tier/scope`, `limit`, `accepts`, no-silent-
  substitution, `emits`, error contract, post-condition, honest scope, monitorability, resolvable
  references, fault locus.

> **There is no clause requiring an id, an owner, a lifecycle state, or a version. P1 is enforced by
> nothing.** M1's gate is *"manifest row count == admitted count"* — a count, which a row with no
> identity fields satisfies perfectly.

Every clause in §4 is justified by a measured failure. The measured failures for P1 are in this document
and in Q14; they have produced no clause. **The first admitted declaration (brick 1–2) will therefore be
admitted with no owner and no lifecycle state**, and Q6 (*who is `owner`*) is explicitly deferred to
"before Phase 3" — after the first bricks are laid.

---

### S7-15 · Two artifacts both claim to be the identity SSOT ⚠️ D: unstated

- **SPEC R1 / §3**: `contracts/mcp-tool-catalog.json` — *"generated, SSOT for what exists"*, carrying
  `name · owner_service · owner · version · group · lane · tier · scope · lifecycle_state ·
  deprecated_at · sunset_at · successor · migration_note`.
- **ARCHITECTURE M1 / §0**: `contracts/agent-runtime-manifest.json` — *"the interface between them, and
  it is the only one"*, generated **only** from new-style declarations, and the runtime's **only**
  catalog input (M2).

These are different files with overlapping purpose and no stated relation. The lifecycle fields live in
the one that must describe **everything including legacy** (R1 is what the migration chain diffs against);
the runtime reads the one that must contain **only new declarations** (M1/M2). A declaration in
`deprecated` state therefore belongs in the first and must be absent from the second — which is
consistent, but means **the runtime never sees a lifecycle state**, and R9.3's policy layer
(*"deprecated ⇒ reachable by name, never hot-seeded, labeled in list"*) has nothing to read. Either the
manifest carries lifecycle state (and M1's "only new declarations" rule needs a stated exception for
deprecated-but-admitted), or the policy layer reads a second file and M2's "only one input" claim is
false.

---

### S7-16 · The retire criterion is computed over the wrong graph 🔴 D: NO

R13.5: *"the edge report tells you when nothing references the old name any more — that is when it may
be removed."* R13.4 defines the edges as **string references**: workflow steps, skill declarations,
policy rows, intent maps, prompt directories.

Three reference classes that report zero and are not zero:

1. **Intra-service handler calls.** `composition_arc_edit` calls `composition_arc_create`. Not a string
   reference; not an edge; invisible to the report. Removing the "retired" tool breaks its own successor.
   `deprecated-tool-scan.py` knows this and exempts it (`_INTERNAL_DISPATCH`) — the exemption is the
   proof that the dependency is real and unmodelled.
2. **Undo hints.** `_meta.undo_hint = {tool, args}` deliberately names the **retired** tool, because the
   successor has a different signature (`deprecated-tool-scan.py`, `_INTERNAL_DISPATCH` docstring:
   *"pointing an undo hint at the 'replacement' would hand it a tool with a different signature and
   silently break the undo"*). A durable `_meta` payload already emitted to clients holds a name.
3. **Third-party keys.** Not in the repo at all. Unqueryable (§S7-11). The population that most needs the
   edge report is the one it structurally cannot see.

`deprecated-tool-scan.py` already holds **9 dead→dead references at a ratchet** (`DEAD_TO_DEAD_BASELINE = 9`)
and states the failure mode plainly: *"It breaks as a class the day the legacy generation is dropped."*
That day is Phase 8.

---

### S7-17 · The declaring flag has no owner and the escape hatch outlives its reason ⚠️

R21 (*a waiver carries an expiry, not only a reason*) applies directly to `pinned_legacy_tools`. R9.3
says it *"disappears in this model: it becomes a declared policy override."* A declared policy override
is a **waiver**, so under R21 it needs an expiry — and today the column has none (a `TEXT[]` on the
session row, `migrate.py:591-592`, validated only at write). Nothing in the design says a policy override
expires, and every prior instance of this shape in this repo became permanent (`_EXEMPT_SKILL_CODES`,
`KNOWN_RED`, the 14 FLIP-PENDING allows).

---

### S7-18 · Published scope vocabulary already drifts from the policy table ⚠️ (pre-existing, and it is the identity problem one layer up)

`Domain` has **12** members (`tool-policy.ts:20-55`): `book, glossary, knowledge, translation,
composition, jobs, settings, lore_enrichment, catalog, story, registry, research`. All three published
lists carry only **9** — `mcp-public-gateway/src/oauth/discovery.ts:8-22`,
`auth-service/internal/api/oauth_meta.go:142-147` (served at `:103`), and the FE's `MCP_DOMAINS`
(`frontend/src/features/settings/api.ts:250-271`). `scopesAllKnown()` hard-rejects anything outside the
published list (`auth-service/internal/api/oauth_pkce.go:57-68`, enforced `oauth_flow.go:109-110` and
`:225-226`).

**So `domain:story`, `domain:registry`, `domain:research` can never be granted via OAuth**, and every
tool in them is permanently unreachable on that path — including `web_search`, the *successor* whose
predecessor `glossary_web_search` is still served. **The successor is less reachable than the tool it
replaces**, which is R9.2's *"granted a deprecated tool whose successor is denied"* still live, in a
second location the spec has not recorded, and hand-duplicated across three languages.

---

### S7-19 · The "revision history" P1 says to copy does not work 🔴 D: NO — **R9.1's premise is false**

R9.1's table is the load-bearing claim that skills and workflows are the model to copy:

| | Artifact axis | Runtime axis | Separated? |
|---|---|---|---|
| **Skill** | `status` + `skill_revisions` | `skill_enablement` | ✅ |
| **Workflow** | `status` + `workflow_revisions` | `workflow_enablement` | ✅ |

**Both ✅ are wrong, measured today.**

1. **A workflow's `status` is write-once.** The CHECK allows `draft|published|archived`
   (`migrate.go:407`), every insert hardcodes `'published'` (`workflows.go:711`, and the seeds at
   `migrate.go:497` ff.), the only `UPDATE workflows SET …` never touches `status`
   (`workflows.go:701`), and **there is no PATCH route** — the routes are GET list / GET one / DELETE /
   PUT enablement / GET revisions (`internal/api/server.go:295-304`). **`draft` and `archived` are
   unreachable states.** A workflow's only lifecycle transition is hard `DELETE`. R9's four-state
   artifact lifecycle is not "already right here and just needs copying to tools" — for workflows it
   has never once been entered.

2. **The two revision streams snapshot opposite images.** Skill: the snapshot `INSERT` runs **after** the
   `UPDATE` (`skills_crud.go:186` then `:192-194`) ⇒ **post-image**. Workflow: the snapshot runs
   **before** the `UPDATE` (`workflows.go:699` then `:700-702`) ⇒ **pre-image**. Reading both tables the
   same way gives you off-by-one histories in opposite directions.

3. **Revisions are not written on the paths that matter.** A skill PATCH that edits `body_md` or
   `frontmatter` **without** a status change snapshots nothing (`skills_crud.go:177-184` — `publishing`
   is true only when `status` is explicitly `"published"`). A skill **proposal approve** — the
   agent-authored edit path — snapshots nothing at all (`proposals.go:190-192`). Both revision writes are
   fire-and-forget `_, _ = s.db.Exec` (`skills_crud.go:192`, `workflows.go:759`).

4. **A revision cannot be read back or restored.** `GET /v1/workflows/{id}/revisions` returns only
   `title/description/notes_md` — **not `steps`** (`workflows_rest.go:174-210`), so the one field that
   defines a workflow is not in its own history API. There is **no restore endpoint for either kind**
   (`grep restore internal/api/*.go` → zero); the DDL comments claiming *"restore = new draft"*
   (`migrate.go:144`, `:452`) are unimplemented. And a parent `DELETE` cascades the whole history away.

**Why this matters for P1 specifically.** SPEC Phase 4's deliverable is *"tools gain versions/revisions
**like skills and workflows already have**"*. That sentence is the plan for the tool half of P1, and its
referent is a mechanism that is write-once, semantically inconsistent between the two kinds, unwritten on
the agent-authored path, unreadable for the field that matters, unrestorable, and destroyed by delete.
**Copying it forward propagates four defects into the substrate that is supposed to unify all three
kinds.**

---

## 3 · MISSING situations, ranked by when they bite

Ranked against `ARCHITECTURE.md` §8's brick order and `SPEC.md` §5's phases.

| # | situation | bites at | why then |
|---|---|---|---|
| **M1** | **P1 has no clause in the admission contract** (S7-14) | **brick 1** | M4 gates on C-1…C-12; none is identity/owner/lifecycle/version. The first admitted declaration has no owner. Q6 is deferred to "before Phase 3", which is after this. |
| **M2** | **Which file is the identity SSOT** — R1 catalog vs M1 manifest (S7-15) | **brick 1** | generation cannot start until it is known which artifact carries `lifecycle_state`, and whether the runtime may read it without breaking M2's one-input claim. |
| **M3** | **Dual identity across the membrane** (S7-8) | **brick 2** | every brick rebuilds a capability that already exists. Same name ⇒ `catalog.ts:78` silent first-wins collision, outside M2's gate. Different name ⇒ the control-group comparison in §7 has no join key. Neither answer exists. |
| **M4** | **Plan/step pins a slug, re-resolved live per pass** (S7-7) | **brick 4** | brick 4 is the first plan. Measured: a running rail carries **no `workflow_id`, no `revision_id`, no frozen `steps`** — `stream_service.py:591-644` refetches by slug every pass, so a mid-run edit swaps the rail **silently** while `pinned_step_tools` still holds the old surface. `registry_meta.catalog_version` exists and no consumer compares it. §0.5's four plan-level classes have no slot for "the declaration this step names changed under you". |
| **M5** | **A lifecycle transition landing on a live session** (S7-13) | first deploy after brick 2 | R19 makes the tool block cache-prefix state; a deprecation changes it for every live session. No effective-at rule, no manifest-version pin, no rule for a 6 h suspended run. |
| **M6** | **The successor edge names a tool, not a call** (S7-2) | Phase 4 (R9 fields) | consolidations are enum-dispatch on `op`; a string cannot carry the discriminator, the new required fields, or the OCC token. `migration_note` exists in one table cell and nowhere else. |
| **M7** | **Usage aggregation is a sentence** (S7-11) | Phase 4 | Q14 mandates it; no tool counter exists; the only per-name usage fact (`mcp_call_audit.tool_name`) has no aggregation query and no index. 61/114 have no edge ⇒ undefined for 54% of the population. Two edges terminate on retired targets and transitivity is unstated. |
| **M8** | **The retire criterion is computed over the wrong graph** (S7-16) | Phase 4 → fatal at Phase 8 | R13.4's edges are string references. Handler-call dependencies, `undo_hint` payloads, and third-party keys are all invisible. `DEAD_TO_DEAD_BASELINE = 9` is the counter already tracking the class. |
| **M9** | **`retired ⇒ tombstone` contradicts the public edge's anti-oracle invariant** (S7-1) | Phase 4 (policy layer) | `scope-filter.ts:38-40` deliberately returns one message for "does not exist" and "out of scope", with a test pinning it. R9.3 requires the opposite. One of the two must be amended, in writing. |
| **M10** | **Scope-union breakage on consolidation** (S7-1) | first public-edge consolidation | a successor's `domains` is the union; `isToolAllowed` requires all of them. Already-issued keys silently 403 with no re-consent path. The one precedent (`glossary_web_search`) was solved by keeping both rows — a comment, not a mechanism. |
| **M11** | **No channel exists to announce a sunset** (S7-9) | before any published clock | no `Sunset`/`Deprecation` header, no changelog, no API version, unversioned `/mcp` mount. Q7 asks which window; a window that cannot be published is not a window. |
| **M12** | **What starts the clock, and can it be per-consumer** (S7-9) | Phase 4 | `_meta` has no `deprecated_at`, so the 114 already-deprecated tools have no t=0. Q7's "pick one" is wrong: the agent population needs a usage gate (unmeasurable today) and the third-party population needs a calendar (unpublishable today). |
| **M13** | **Behaviour change with unchanged name+schema** (S7-4) | Phase 2/4 | `Catalog.version` excludes `description`; R13.2's five classes are all schema-shaped; R19 makes the description a cache-prefix input. The field with the largest behavioural effect is the one with no version and no migration entry. |
| **M14** | **SPLIT is not representable** (S7-3) | when N1 is answered | `superseded_by` is a single string; Q14's model is explicitly many-to-one; R13.2 has no `split` class. If shape 1+4's coarse capabilities prove too coarse, the corrective operation has no edge. |
| **M15** | **Member-set change is not a skill revision — and cannot be** (S7-6) | throughout admission | there is no member set in data today (`skills_md.go:41-48` discards `allowed-tools:`); R3 introduces one and derives it from the manifest, so every one-at-a-time admission silently edits a skill. `skill_revisions` has no column that could hold it (`migrate.go:145-153`). Makes R20's one-arrival-channel claim unverifiable. |
| **M16** | **R9.1's premise is false — the revision mechanism Phase 4 copies does not work** (S7-19) | Phase 4 | workflow `status` is write-once (no PATCH route, `server.go:295-304`) so `draft`/`archived` are unreachable; skill and workflow revisions snapshot **opposite images**; the agent-authored approve path snapshots nothing (`proposals.go:190-192`); `steps` is absent from the workflow revisions API; no restore endpoint; `ON DELETE CASCADE` destroys history. Phase 4 says tools gain revisions *"like skills and workflows already have"*. |
| **M17** | **Name reclaim / tombstone has no producer** (S7-10) | Phase 8 | M1 generates from live declarations, so it cannot emit a row for a thing that no longer exists. `deprecated-tool-scan.py` treats re-registration as the *supported* un-retire path with no same-capability check. For skills/workflows a hard `DELETE` frees the slug instantly and, because `mode_bindings` references by slug with **no FK**, a re-created object **inherits every pin the deleted one had**. A reclaimed name makes stale durable pointers **resolve**. |
| **M18** | **No per-tool version on the wire, and no stated consumer behaviour** (S7-12) | Phase 4 | MCP defines none; SEP-1300 rejected; `Catalog.version` is one hash for the whole list. `version` is in the artifact row with no producer, no wire field, and nothing that says what a client does with it. |
| **M19** | **"Revision history" for a tool has no home** (S7-12) | Phase 4 | P1 requires it; the manifest is a snapshot; skills and workflows have revision tables (see M16 for their condition) and tools have none. Where it lives is unstated. |
| **M20** | **Owner-service move forces a rename** (S7-5) | Q9 | the provider-prefix gate means re-homing looks like a consolidation. Identity and hosting are conflated at the wire. Q9 is unscheduled. |
| **M21** | **`pinned_legacy_tools` becomes a policy override with no expiry** (S7-17) | Phase 4 | R21 requires an expiry on every waiver; R9.3 converts this column into a waiver and says nothing about one. Every prior instance of this shape in this repo became permanent. |
| **M22** | **Published scope vocabulary drifts from the policy table** (S7-18) | live now | 12 domains vs 9 published, hand-duplicated across three languages; `web_search` (a successor) is unreachable via OAuth while its predecessor is served. R9.2's contradiction, second instance, unrecorded. |

---

## 4 · The one-line answer to each of the two questions

**1. What situation does identity/lifecycle exist to solve?**
A declaration's name is its only identity, 23 durable artifacts across five services and three
databases are keyed by it, three of them are held by third parties we cannot contact — and the only
change operation the system actually performs is a **many-to-one consolidation** (53 → 16, 3.3 : 1)
that no field, no gate, and no message shape can express.

**2. What will certainly occur that it has no defined answer for?**
The 22 rows above. The first four bite before the fifth brick is laid, and **M1 is the one that makes
the rest optional**: P1 is the only primitive in `ARCHITECTURE.md` §0.2 with no clause in §4's
admission contract, so nothing forces a new declaration to have an identity at all.

**One correction the spec should absorb regardless of what is built:** R9.1's table marks skills and
workflows ✅ *"three distinct layers"* and uses them as the model for tools. Measured today, a workflow
can never leave `published`, the two revision streams snapshot opposite images, the agent-authored edit
path snapshots nothing, and a running rail re-resolves its steps live by slug. **The thing P1 proposes
to copy has not been shown to work.**
