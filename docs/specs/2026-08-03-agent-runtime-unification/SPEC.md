# Agent Runtime Unification — Specification

**Status:** DRAFT (CLARIFY complete · PO decisions recorded §1.1) · 2026-08-03
**Size:** XL (logic=20, side effects=6, 3 languages, 5 services)
**Evidence base:** [`AUDIT.md`](AUDIT.md) + [`audits/`](audits/) — do not re-derive; every claim here
cites it.
**Supersedes / retires:** see §8. **This document is void if §8 is not executed** — an unretired
predecessor makes this the fourteenth layer, which is precisely how the previous twelve failed.

---

## 1 · Problem

`AUDIT.md` §0. For tool availability, the architecture never existed: thirteen individually-correct
mechanisms accumulated since 2026-06-10, **one retirement**, no composition, and no artifact anywhere
that assigns a tool to a skill. Measured: 16 producers, 18 filters (13 silent), 8 answers to "is this
tool available", 3 workflow selectors, 4 mutually inconsistent tool counts.

### 1.1 PO decisions (2026-08-03) — sealed

| # | Decision | Consequence |
|---|---|---|
| **D1** | **Both runtimes, with a declared boundary.** Neither the chat rail nor the out-of-agent FSM is deprecated. | §2 must state the boundary as a *rule a reviewer can apply*, not a preference. |
| **D2** | The six cheap prerequisite fixes are **Phase 0 of this spec**, not a separate pre-commit. | Each ships with its anti-vacuity proof (§9), not merely a fix. |
| **D3** | **"Lifecycle" is two orthogonal axes — artifact and runtime — plus the policy layer that maps one onto the other.** Raised by the PO against an earlier single-chain draft. | R9. It also corrected a live defect in R4, whose first `excluded_by` enum mixed all three (§R4). |

Per CLAUDE.md, a sealed decision is re-read, never re-litigated from memory.

### 1.2 One amendment to the stated invariant, and why

The owner's ask was: *every MCP tool belongs to one skill group **and** sits in ≥1 workflow.*

The first half is correct and this spec enforces it at 100%. **The second half, enforced literally, is
wrong** — and would fail on day one at 13% (30/223), which means it gets disabled on day two.

The reason is not the number. It is that **an atomic tool legitimately belongs to no workflow.**
`book_read`, `glossary_search`, `jobs_get` are one call with one effect; wrapping each in a
single-step "workflow" to satisfy a counter would be ceremony that teaches the model nothing. A
workflow's whole value is *ordering that a wrong order breaks* — and a one-step sequence has no order.

So the invariant is **lane-scoped** (§2.3): every tool declares a lane; workflow coverage is required
and ratcheted on the FSM lane only. The owner gets what they actually asked for — *nothing exists
unplanned, and the plan is machine-checkable* — without a gate that must be switched off to keep
working.

---

## 2 · The boundary (D1)

### 2.1 What the contradiction actually was

`AUDIT.md` §5.1: 07-21 and 07-22 measured *"discovery WORKS"*; 07-27 measured *"tool-choice is the
unfixable link."* Both are true, and the corpus never drew the distinction that reconciles them:

> **Discovery is not selection-under-ordering-constraints.**
> Finding *a* tool by name or category is a lookup, and a weak model does it reliably (measured
> four-for-four, 07-21). Choosing *the right tool at the right point of a multi-step job whose steps
> feed each other* is planning, and a weak model does not (measured: E2 horizontal-naive collapsed
> monotonically 7→1 attributes; E3 planner→executor produced 13 entities at 5.7 attrs).

The distinguishing variable is **the job**, not the model. That is what makes it a boundary rule
rather than a model-tier switch.

### 2.2 The rule

A capability is owned by the **FSM lane** when it has **all four**:

1. **≥2 steps**, and
2. **a fixed order a wrong order breaks** (step *n*'s output is step *n+1*'s input), and
3. **an observable artifact** — expressible as a `done_when` predicate over real state, and
4. **the user's assent is to the whole job**, not to each step.

Everything else is the **chat lane**: atomic operations, reads and queries, exploration, and
human-in-the-loop editing where the user's next utterance determines the next step.

**The 12 seeded workflows are the evidence this class exists and that chat keeps failing it.** Each
row in the `workflows` table already asserts conditions 1–3 about itself. Therefore:

> **Migration list = the workflow table.** A workflow row with ≥2 steps and a `done_when` is an FSM
> candidate by its own declaration. A 1-step row (`lore-so-far`) is a chat-lane hint, not a rail.

This also closes `AUDIT.md`/[audits/05](audits/05-workflows-registry.md) §7.6 — the product currently
ships a browsable rack of 12 recipes with **no click handler and no way for a user to run one**. The
FSM lane is what a Run button runs.

### 2.3 What the two lanes share — and this is the load-bearing part

The boundary is about **who drives the sequence**. It is *not* two tool catalogs, two permission
models, or two group taxonomies. Both lanes consume:

- the same generated tool manifest (§3, R1)
- the same `_meta.group` taxonomy (§3, R2)
- the same permission spine — tier, scope, confirm-token, spend gate
- the same `done_when` grounding (already correct — [audits/05](audits/05-workflows-registry.md) §3.3)

A tool declares `lane: chat | fsm | both` in `_meta`. `both` is expected to be common: `book_read` is
an atomic chat read *and* step 2 of `chapter-compose`.

**Anti-fork clause.** Any artifact that exists per-lane — a second catalog, a second group list, a
second surface enum, a second permission check — is a defect under this spec, not a design choice.
The audit found three concepts already tripled (`AUDIT.md` §3); this spec must not add a fourth axis.

---

## 3 · Target architecture

Three layers (R9), and the requirements that build each:

```
╔═ ARTIFACT ═════════════════════════ changes at deploy · has history ══════════╗
║  contracts/mcp-tool-catalog.json     ← R1  generated, SSOT for "what exists"  ║
║    name · owner_service · owner · version · group · lane · tier · scope       ║
║    lifecycle_state · deprecated_at · sunset_at · successor · migration_note   ║
║         ├──────► group taxonomy      ← R2  _meta group/lane, panics at        ║
║         │              │                   registration; GROUP_DIRECTORY,     ║
║         │              │                   alias + prefix maps become DERIVED ║
║         │              ▼                                                      ║
║         │        SkillDef.group      ← R3  a skill owns exactly one group;    ║
║         │              │                   its tools follow from the manifest ║
║         │              ▼                                                      ║
║         │        workflows.steps[].tool  ← FK into R1, at write AND at seed   ║
║         │        skill/workflow/tool revisions + usage counters ← R9.6        ║
╚═════════╪═════════════════════════════════════════════════════════════════════╝
          │  ◄── R9.3: ONE declared mapping. The layer that does not exist today.
╔═ POLICY ╪═════════════════════ artifact state ⇒ availability, to whom ════════╗
║         ▼   deprecated ⇒ by-name only, never hot-seeded, labeled in list      ║
║             retired    ⇒ absent + tombstone naming the successor              ║
║             + tenancy: enablement · tier · spend   (applied BEFORE discovery) ║
╚═════════╪═════════════════════════════════════════════════════════════════════╝
          │  ◄── per-turn selection
╔═ RUNTIME╪══════════════════════ this session, this turn · no history ═════════╗
║         ▼   ToolSurface              ← R4  ONE function; admitted_by /        ║
║                    │                       excluded_by = (layer, reason)      ║
║                    ▼                                                          ║
║              guards register         ← R5  every withholding declares itself  ║
║                    │                                                          ║
║                    ▼   tools/call                                             ║
║              error contract          ← R10 4-class taxonomy at the boundary;  ║
║                    │                       actionable message; isError-safe   ║
║                    ▼                                                          ║
║              retry budget            ← R11 tokens + money, not attempts;      ║
║                                            no contaminated re-send            ║
╚═══════════════════════════════════════════════════════════════════════════════╝
                     │
                     ▼
        coverage ratchets ← R6      evals in CI ← R12  the net that makes
        (skill 100% · fsm ratcheted)                   deletion provable
```

**Requirements index.** R-numbers are **stable identifiers, not an order** — R7–R12 were added after
R1–R6 and keep their numbers so existing references stay valid. This section reads in dependency
order: **R1** manifest · **R2** group/lane at registration · **R3** skills declare tools (twice) ·
**R4** one explained surface · **R5** guards register · **R6** coverage ratchets · **R9** the three
layers · **R8a** durable-vs-session state · **R8b** zero-result post-conditions · **R7** one surface
vocabulary · **R10** the tool error contract · **R11** retry budget + uncontaminated retry ·
**R12** evals in CI. Execution order is §5's phase table, which differs again.

**Three of these are net-negative by design** and that is the point: R10 retires six orchestrator
breakers, R2 deletes five hand-maintained tables, R9 deletes `pinned_legacy_tools`. A requirement that
only adds is how the previous thirteen mechanisms accumulated.

### R1 — The generated tool manifest *(blocking prerequisite)*

`contracts/mcp-tool-catalog.json`, one row per tool. Generated in CI from a live `tools/list` against
a booted stack, with `scripts/deprecated-tool-scan.py::build_catalog()`'s static scan as the offline
fallback. Must include the consumer-local and chat-only frontend tools the current scanner misses
([audits/04](audits/04-mcp-servers-federation.md) §7.5).

Fixes `AUDIT.md` §1.2 by construction: **one denominator, derived, not authored.**

### R2 — `group` and `lane` become data at the registration chokepoint

Add both to `require_meta` (Python) / `NewToolMeta` (Go), and to the TS defs that currently have no
validator at all ([audits/04](audits/04-mcp-servers-federation.md) §2, variant E). The chokepoint that
already **panics on a missing tier** panics on a missing group. Namespace the keys per R9.5 — the same
sweep, not a second migration.

Then `GROUP_DIRECTORY` (×3), `_DOMAIN_ALIASES` (×2), `DEFAULT_PREFIX_MAP` and `EXTRA_PREFIX_MAP`
become **derived from the manifest**. This retires the three-copy hand-lockstep *and* the five-incident
prefix allowlist in one move — the prefix map's own comments are the incident log
([audits/04](audits/04-mcp-servers-federation.md) §4.1).

**Prior art, and why this stays a private extension.** MCP's
[SEP-1300](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1300) proposed this
exact design upstream — `groups[]`/`tags[]` on the tool, `groups/list`/`tags/list`, a `filter` param
on `tools/list` — and was **rejected**. So there is no standard to conform to and no risk of
diverging from one; the obligation is only to namespace (R9.5) so a future spec key cannot collide.

**Replace the 30 s poll while we are here.** Federation currently re-lists every provider
sequentially every 30 s with no per-provider timeout, and versions the catalog as
`sha256(name, inputSchema)` — so a description change, the field that most affects model behaviour,
bumps nothing. MCP 2026-07-28 added `ttlMs` + `cacheScope` on list responses and **deterministic
ordering**, which is what makes catalog caching correct. Adopt both, and hash the fields that
actually drive behaviour (`name`, `description`, `inputSchema`, `_meta`).

### R3 — Skills declare tools, not prefixes — and declare them TWICE, for two different questions

`SkillDef.hot_domains: frozenset[str]` → `group: str`, with `tools` read from R1. Extend user-skill
frontmatter so a user-authored skill can declare tools at all
([audits/02](audits/02-skills.md) §3e — today it physically cannot).

**Two declarations, not one — this is R9's layering applied to skills.** Research 2026-08-03: the
[Agent Skills standard](https://agentskills.io/specification) defines exactly six frontmatter fields,
and `allowed-tools` is one of them — but its semantics are *pre-approval*, explicitly **not**
restriction: *"grants pre-approval but does not block other tools; pair it with deny rules when
restriction is the goal."* So the standard answers **permission**, and says nothing about
**reachability**. A skill needs both:

| Question | Field | Layer (R9) | Standard? |
|---|---|---|---|
| What may this skill **call**? | `allowed_tools` — align the name with the standard | **policy** | ✅ Agent Skills |
| What must be **on the wire** for it to work? | `tools` (derived from `group`, per R1) | **runtime** | ❌ none exists — ours to define |

Today LoreWeave declares **neither**: one regex over prompt prose (`tool_surface.py:556`) is doing
both jobs at once. That is why it is simultaneously wrong (27 tokens scraped from `glossary`, 13 of
them not tools) and incomplete (`plan_propose_spec` missed until 2026-08-02, costing a 6,948-character
plan with zero tool calls). One mechanism cannot answer two questions; splitting them is the fix.

Retires the prose scraper at `tool_surface.py:556` as a *mechanism*; it survives only as an
*assertion* (a backticked tool name must belong to the skill's own group).

### R4 — One explained tool surface

Replace 16 producers / 18 filters with one `resolve_tool_surface() -> ToolSurface`, per-tool record:

```python
name, group, lane, tokens
admitted_by:  (layer, reason) | None
excluded_by:  (layer, reason) | None

layer:   Literal[artifact, policy, runtime]          # R9's three axes
reason:  # closed per layer — a reason may not cross layers
  artifact: not_in_catalog | deprecated | retired | liveness_broken
  policy:   tier_gate | ask_mode | lane_mismatch | intent_gate |
            not_entitled | spend_gate
  runtime:  token_budget | rail_gate | failure_breaker | list_cap |
            oneshot | not_seeded
```

**The `layer` is not decoration — it was the defect this spec nearly shipped.** The first draft of R4
used one flat enum in which `legacy`/`liveness` (artifact facts), `tier_gate`/`ask_mode` (policy
decisions) and `token_budget`/`rail_gate` (this-turn accidents) were siblings. That is precisely the
axis-conflation R9 exists to end, reproduced inside the mechanism meant to end it.

The layer is what makes the answer *actionable*, and the three answers are not interchangeable:

| Layer | *"Why can't you see tool X?"* | What the reader does |
|---|---|---|
| `artifact` | it was retired on 2026-06-30; use `book_read` | fix the caller / the catalog |
| `policy` | your plan does not include it · ask-mode blocks writes | change mode, or buy |
| `runtime` | this turn's budget filled · the rail already did that step | retry, or narrow the ask |

Closed enums, never free strings (the Frontend-Tool-Contract IN-1 discipline, already the rule for
tool args). `excluded_by` is never `None` for a name the model could plausibly want. Emitted on the
SSE surface channel and logged once per pass.

This is `D-CHAT-CONTROL-PLANE` §A, and it is the only thing that makes *"why can't you see tool X
right now?"* answerable by a user, by an agent, or by the next auditor.

### R5 — Guards register what they withhold

A guard removes a tool only by setting `excluded_by`, with declared precedence. This is
`D-CHAT-CONTROL-PLANE` §C and it converts the anti-rot rule from aspiration into mechanism.

### R6 — Coverage gates, shipped as ratchets

| Gate | Scope | Day-1 value | Enforcement |
|---|---|---|---|
| `every tool has exactly one group` | all lanes | fail → fix in Phase 1 | **hard, 100%** |
| `every group is owned by exactly one skill` | all lanes | catches `book` ← 2 skills | **hard, 100%** |
| `every backticked tool name in a skill's prose is in that skill's group` | all lanes | — | **hard** |
| `every fsm-lane tool appears in ≥1 published workflow` | fsm lane | ~13% today | **ratchet** — baseline may only shrink; a waiver row needs a reason |
| `every workflow step tool is in the manifest` | fsm lane | 30 names, 8 unverifiable today | **hard, at write AND at seed** |
| `a step's gate is honourable by the tool's tier` | fsm lane | `gate` is decorative today | **hard** |

The ratchet is not softness. A gate that goes red on day one gets disabled on day two — the repo has
this exact lesson recorded in `DEAD_TO_DEAD_BASELINE` and in `context-budget-defaults-lint`'s 14
FLIP-PENDING rows.

### R9 — Three layers, not one lifecycle *(added 2026-08-03 after PO review)*

An earlier draft of this spec proposed "a lifecycle" as a single chain
(`draft → published → deprecated → retired`). **That framing was wrong, and the error is the same one
the whole audit is about.** There are two orthogonal axes, and collapsing them is what produced the
defects below:

- **Artifact axis** — the tool as a thing that is written, released and retired across deploys.
  Long-lived, has history, changes at deploy time.
- **Runtime axis** — the tool as a thing loaded into *this* session at *this* turn. Ephemeral, has
  no history, changes every turn.

Between them belongs a third thing that does not exist at all today: **the policy that maps an
artifact state onto runtime availability.**

#### R9.1 — What the platform already gets right, and where it does not

| | Artifact axis | Runtime axis | Separated? |
|---|---|---|---|
| **Skill** | `status: draft\|published\|archived` + `skill_revisions` | `skill_enablement` → `resolve_skills_to_inject` | ✅ three distinct layers |
| **Workflow** | `status` + `workflow_revisions` | `workflow_enablement` → pin | ✅ structurally (P0-5 fixes the unread join) |
| **Tool** | `_meta.visibility` + `superseded_by` — **no version, no revision, no table** | 18 filters | ❌ **not separated** |

Verified: `grep -rn "tool_version\|tool_revision" services/` → **empty**. Skills and workflows have
revision tables; the 312 tools have no version, no revision, and no row anywhere.

#### R9.2 — `visibility:"legacy"` is a runtime filter wearing an artifact state's costume

`is_legacy_tool` is read at **seven runtime filter sites** (`tool_discovery.py:501, 605, 736, 869,
912, 1041, 1338`) with no policy layer between. Four proofs that it is policy, not state:

1. **It has a per-session escape hatch.** `pinned_legacy_tools` is documented as *"a deliberate
   per-session override"* (`tool_surface.py:173-177`). You do not override an artifact's history; you
   override a *decision*. The override's existence is the diagnosis.
2. **Two code paths answer the same question differently** — CAT-4 hides, OQ5 labels (`AUDIT.md` §3 /
   audits/06 §3.1) — because "legacy ⇒ what happens at runtime" is written nowhere, so each site
   decided for itself.
3. **It has no time dimension.** A deprecation needs `deprecated_at`, `sunset_at`, a successor and a
   migration note. Ours is a two-valued enum plus a name. **No clock ⇒ no retirement criterion ⇒ 114
   legacy tools served forever.**
4. **The same conflation runs the other way.** `Catalog.version = sha256(name, inputSchema)` is a
   runtime cache-invalidation hash asked to do artifact change-detection — so a *description* change,
   the field that most affects model behaviour, bumps nothing.

The sharpest consequence: the public edge grants `book_get`/`book_get_chapter` (both legacy) and
denies `book_read`/`book_search` (their replacements). `TOOL_POLICY` is a runtime access decision with
no link to artifact state, so *"granted a deprecated tool whose successor is denied"* is not a
checkable contradiction. With the layers split it is a one-line gate.

#### R9.3 — The required shape

```
ARTIFACT   ── changes at deploy · has history
  identity · version · lifecycle_state{draft|active|deprecated|retired}
  deprecated_at · sunset_at · successor · migration_note · owner
        │
        │   ◄── ONE declared mapping. This is the missing layer.
        ▼
POLICY     ── artifact state ⇒ how available, to whom
  deprecated ⇒ reachable BY NAME, never hot-seeded, labeled in list
  retired    ⇒ absent + a tombstone error naming the successor
  + tenancy: enablement · permission tier · spend
        │
        │   ◄── per-turn selection
        ▼
RUNTIME    ── this session, this turn · no history
  seed · budget · rail gate · breakers · excluded_by (R4)
```

`pinned_legacy_tools` **disappears** in this model: it becomes a declared policy override, not a
column on the session row.

#### R9.4 — Borrow the policy, do not invent it

Web research, 2026-08-03. The industry has converged, and **not on the MCP specification** — the spec
deliberately declined this problem:

- **MCP standardises a lifecycle for spec features, not for your tools**: `Active → Deprecated →
  Removed`, **≥12 months**, a 90-day expedited-security exception, a **mandatory migration path** (no
  "tombstone deprecations"), and — worth stealing on its own — *no standards-track change reaches
  Final without a conformance scenario proving it behaves as specified.* Adopt this verbatim as R9's
  artifact policy.
- **MCP has no per-tool versioning and no tool groups.** [SEP-1300 "Tool Filtering with Groups and
  Tags"](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1300) proposed exactly
  R2's design (`groups[]`/`tags[]` on the tool, `groups/list`, a `filter` param on `tools/list`) and
  was **rejected**. R2 is therefore a legitimate private extension — but see R9.5.
- **The lifecycle lives in the registry/catalog layer**, borrowed wholesale from API governance: a
  catalog answers *what it is · who owns it · where it is in its lifecycle* for every artifact;
  ownership is a person or rotation, not a wiki row; deprecation runs on a published clock with a
  named successor (RFC 8594 `Sunset`, the `Deprecation` header); and consumer/provider edges let you
  find who depends on a thing **before** retiring it.
- **Access control is applied before discovery, not after a failed call.** An agent must not see what
  it may not use — and must not be told a withheld thing does not exist. This is the industry's own
  statement of the `not_found`-lie defect (`AUDIT.md` §2.4).
- **Temporal is the one mature workflow lifecycle**, and its retirement criterion is a *data fact*:
  a version is safe to remove once no open executions of it remain. **LoreWeave cannot answer that
  question** — which is why R9.6 is not optional.

#### R9.5 — Namespace the `_meta` keys

MCP 2026-07-28 now uses `_meta` for protocol-level data under reverse-DNS keys
(`io.modelcontextprotocol/protocolVersion`, `io.modelcontextprotocol/clientInfo`). LoreWeave uses
**bare keys** — `tier`, `scope`, `visibility`, `async`, `paid`, … (`sdks/go/loreweave_mcp/meta.go:18-34`).
That is a latent collision with future spec-reserved keys, on the one field this spec is about to add
to. Namespace all of them (`dev.loreweave/group`, `dev.loreweave/tier`, …) in the same Phase-1 sweep
that adds `group`/`lane` — one migration, not two.

#### R9.6 — Usage telemetry, because retirement needs a fact

`used_count`, `last_run_at`, `last_triggered_at` exist as columns and **no statement writes any of
them** (verified: no `UPDATE skills`/`UPDATE workflows` touches them). Two consequences:

- `skills_crud.go:54` offers the user a `sort=last_triggered` ordering over a permanently-`NULL`
  column — a control that cannot work.
- *"Which rails does anyone actually use?"* is unanswerable from data. R6's ratchet needs it to decide
  which rails are worth promoting to the FSM lane, and R9's `retired` state needs it to have a
  criterion at all.

Write the counters. Add the same for tools — the artifact with no row today.

### R8a — Durable state may inform an affordance, never decide it

Absorbed from [`../2026-08-03-tool-reachability-ssot.md`](../2026-08-03-tool-reachability-ssot.md)
§"What is NOT fixed" item 4, which identified the pattern correctly: **any durable-state predicate
used to decide a conversational affordance misbehaves across sessions.** `rail.py` was fixed for one
consumer (`session_done` split from `done`); the sweep was requested and not done.

Audit every consumer of `BookState` / `probe_book_state`, and make the rule explicit: a `done_when`
predicate reads the book to *inform* the model ("already done — do not repeat"), and only a
session-scoped verdict may *remove* an affordance. `excluded_by` (R4) makes the distinction visible
where today it is implicit in which variable a branch happens to read.

**This is R9's axis separation applied to state rather than to catalogs**, and recognising them as one
rule is what makes both enforceable: *durable facts inform; only session-scoped facts withhold.*
`visibility:"legacy"` withholding at seven runtime sites (R9.2) and `done` withholding a rail step
across sessions are the same defect in two subsystems.

### R8b — A tool that produces nothing must not report success

Absorbed from the same document, item 5. `plan_propose_spec(mode="rules")` matched zero headings,
wrote a spec with **0 arcs**, and returned a `run_id` indistinguishable from a working plan — while
`validate.py` already knew (`spec_has_arc` → *"no arcs parsed"*) behind a different tool. That single
instance is fixed; the class is not.

Sweep the synchronous MCP tools whose work can legitimately match zero and give each a
**post-condition**: matched-nothing is a distinguishable outcome carrying the required shape, never a
bare success. This is the repo's `no silent seams` rule un-applied at a tool boundary, and it is the
same failure shape as R4's silent filters — a caller cannot act on information it is never given.

### R7 — One surface vocabulary, one category enum

Per `AUDIT.md` §3. Generated into all consumers (Go `validSurfaces`, Python `SkillDef.surfaces`, the
runtime mapper, the FE types) with a mirror test. **Until this lands, "author more workflows to raise
coverage" is not available as a remedy** — an authored workflow declaring the enum's own first value
(`chat`) is invisible on every book turn.

### R10 — The tool error contract *(added 2026-08-03 — the infinite-loop root cause)*

**The reported symptom:** the agent calls a tool, cannot tell what went wrong, and loops. LoreWeave
answered this with **six reactive breakers** in the orchestrator (`blank_tool_args_streak`,
`read_call_results`, `noop_write_counts`, `fail_by_tool_error`, `failure_suppress`,
`TOOL_LIST_CATEGORY_CAP`) plus `RAIL_REDRIVE_CAP`. All six treat the symptom. **The cause is that no
tool tells the caller whether its failure is worth retrying**, so the retry decision is left to the
model's probabilistic judgement.

The evidence is already in our own code. `fail_by_tool_error` is keyed on the **error signature**
rather than the args, and its comment explains why: *"a weak model varies the args each retry
(measured: `book_get_chapter` ×19, each a DIFFERENT hallucinated `chapter_id`) yet hits the IDENTICAL
error."* That is a **terminal-permanent** failure being treated by the model as **retryable-modified**.
A tool that said so would make the breaker unnecessary.

#### R10.1 — Classify at the boundary, in a closed set

Every tool result carries a classification, decided in the tool wrapper — never inferred downstream:

```
retryable_transient   provider 5xx · timeout · rate limit        ⇒ backoff, same args
retryable_modified    validation failure · malformed args        ⇒ retry ONCE, different args
terminal_permanent    not found · forbidden · wrong state        ⇒ never retry; change approach
terminal_budget       attempt/token budget exhausted             ⇒ escalate or degrade
```

This is the industry-converged taxonomy, and its stated purpose is exactly ours: move the decision
*"from the LLM's probabilistic judgement to deterministic logic in the tool wrapper."*

#### R10.2 — The message must be actionable, not a code

Anthropic's rule, adopted verbatim: not `ERROR: TOO_MANY_RESULTS` but *"Found 847 expenses. This is
too large to return. Please narrow your date range or specify a category filter."* A `terminal_permanent`
must name what to do instead — which is also what R9's `retired` tombstone needs (name the successor).

#### R10.3 — The `isError` / `outputSchema` landmine, before R1/R2 widen it

The MCP specification says output-schema validation is **skipped** for `isError: true` results. Strict
SDK clients **validate anyway**, so a tool that declares an `outputSchema` and reports failure via
`structuredContent` gets `-32602 "Failed to validate structured content"` — the real error is replaced
by a protocol error, and the agent learns nothing. This is a live, documented ecosystem bug
([typescript-sdk#654](https://github.com/modelcontextprotocol/typescript-sdk/issues/654),
[mcp-context-forge#4202](https://github.com/ibm/mcp-context-forge/issues/4202)).

Our GATE-4 rule (`Out=any ⇒ explicit outputSchema`) pushes every tool toward exactly this shape, and
R1/R2 will multiply it. **Specify the error envelope now**: either the advertised `outputSchema` is
widened to admit the error shape, or errors never travel in `structuredContent`. Pick one, gate it,
and prove it against a strict client — not against our own lenient one.

#### R10.4 — Net-negative or it does not ship

R10 is only worth doing if it **removes** machinery. Its DoD includes retiring the breakers it makes
redundant. A taxonomy added *beside* six breakers is the fourteenth layer, not the fix.

### R11 — Retry budget as a first-class constraint, and no contaminated retry

Two findings this spec had no answer for:

**Cost.** An agent retry re-sends the entire conversation, not a request payload. Measured in
production elsewhere: **up to 200× the token cost** of one successful run; a flaky endpoint turning a
$0.01 task into **$2 in under a minute**. Our own equivalent is on record —
`glossary_list_system_standards` called **24 times**, each result ~11k tokens, *"a THIRD of the turn's
whole budget, per call."* Our caps count **attempts**; nothing counts **waste**. Budget in tokens and
money, and instrument it: retry ratio per tool (alert above 0.3), token waste under 5%.

**Contamination.** [Why Retrying Fails (arXiv 2605.08563)](https://arxiv.org/pdf/2605.08563) shows a
naive retry *amplifies* failure: the prior failed attempts stay in context and bias the model toward
repeating them, so failure rates **rise** with successive retries. Our tool loop appends every failed
call and result to `working` and re-sends it each pass — the described mechanism exactly.

Notably, our own de-advertise fix is a crude form of the paper's *explicit divergence signalling*: we
remove the tool so the model physically cannot repeat it. That works, and it is blunt — it costs the
action space. The principled version is to isolate or branch the retry context. R11 adopts it, and
`excluded_by` (R4) is what lets us tell the difference between *"withheld to break a loop"* and
*"withheld because you may not have it."*

### R12 — Evals in CI — the regression net, and the answer to maintenance fatigue

The stated pain is that maintenance is exhausting. The mechanism behind that is precise: **there is no
regression net, so no change can be proven safe, so nothing is ever deleted — and that is how thirteen
layers accumulated.** R8 (retirement) is not executable without this.

We are not short of instruments. Four real harnesses exist and run: discoverability scenarios (18),
skill scenarios (37), the tool-liveness matrix (211/224), and the out-of-loop routing benchmark.
**None is in CI**, each needs a live stack driven by hand, and the last full discoverability run was
2026-07-15 — **19 days and at least four mechanisms stale.**

The converged practice: a golden dataset versioned with the code, run in CI on every PR, scores posted
against a baseline, **deployment blocked when a score regresses** unless a human explicitly signs off.
Deterministic checks should carry **60–70%** of the eval surface; LLM-judge is reserved for genuinely
subjective dimensions. Failed production traces feed back into the offline set.

Prerequisite for R6's ratchet (which needs a trustworthy baseline) and for R8's retirement (which needs
proof that deleting something broke nothing).

---

## 4 · Phase 0 — the six lies, with proofs (D2)

Each is independently correct, each is actively misleading the model or the user *today*, and each
ships with the anti-vacuity obligation in §9. Grouped because they are the tests that R1–R6 will
depend on.

| # | Fix | Evidence | Proof obligation |
|---|---|---|---|
| **P0-1** | `repeat`: one type, one meaning | Go `Repeat string` vs seeds `true`; `_ = json.Unmarshal` discards the type error; 13 steps in 6 rails wrongly disarmed. **A prior fix attempt (commit `363e22f43`, [`../2026-08-03-tool-reachability-ssot.md`](../2026-08-03-tool-reachability-ssot.md) §"Fixed now" item 3) added `repeat: true` to four more seed rows and a guard over the seed SQL. Measured end-to-end on the running stack 2026-08-03, with the seed applied: the `vision-to-book` DB row holds `[true,true,true,true,true,true,true,true]`, and the same rail served over `/internal/workflows` carries `repeat` 0× in 45 steps while `gate` appears 45× and `done_when` 8×. The data is in the database and the Go layer drops it in transit — the fix and its guard are both inert.** See §9 | `TestRepeat_SurvivesTheStepsRoundTrip` — the **twin** of the existing `done_when` test, asserted against the **HTTP response of `/internal/workflows`**, never the seed SQL both sides were generated from |
| **P0-2** | Stop discarding `json.Unmarshal` errors | `workflows.go:850`, `:347`, `:371`; `workflows_rest.go:110`, `:140` | inject a type-mismatched field → the log must name it. This one change would have surfaced P0-1 the day it shipped |
| **P0-3** | `handleCallTool` consults `isPartial()` | `handlers.ts:399-401` returns `NOT_DISCOVERED` for a **down provider's** tool. The discovery path was fixed for this after a real incident; the execution path never was | kill a provider in test → the error must say *unavailable*, not *does not exist* |
| **P0-4** | Retire the three dead `find_tools` strings at the public edge | `invoke-tool.ts:30`, `:124`; `proxy-server.factory.ts:40-47` instruct every connecting client to call a tool F17 removed. `EDGE_FIND_TOOLS_DESCRIPTION` is unreachable | a test asserting no served string names a tool absent from `tools/list` — generalises past these three |
| **P0-5** | `LEFT JOIN workflow_enablement` in `internalWorkflows` | the only reader the agent uses never joins it; its sibling `internalSkills` does. The GUI says "disabled"; the agent keeps pinning | disable a workflow → the internal read must drop it |
| **P0-6** | Unify the surface enum (R7) | three vocabularies; overlap is `{chat, admin}`; `studio` matches nothing at runtime | the generated-mirror test; plus a seed-lint that every seeded `surfaces` value is in the enum |

**Also in Phase 0, because it costs nothing and the audit found it live:** repair the two vacuous
tests that guard this exact class — `test_tool_list_contract_drift.py:57-73` (points at ai-gateway's
handler; chat never routes `tool_list` there) and `test_tool_list_load.py:64-66` (omits the
`exclude=` the production site passes). Both are currently green over live defects.

---

## 5 · Phases and DoD

| Phase | Delivers | Done when |
|---|---|---|
| **0** | §4 — six fixes + two vacuous-test repairs | each fix's proof pasted into VERIFY evidence (§9); full suites green in the 5 touched services |
| **1** | **R12 evals in CI** · R1 manifest · R2 `_meta` group/lane + R9.5 namespacing + cache hints · R7 enum | the four existing harnesses run in CI against a versioned golden set and block a PR on regression; manifest generated in CI; registration panics on a missing group in all 3 languages; `_meta` keys namespaced; catalog version hashes description + `_meta`; `GROUP_DIRECTORY`/prefix maps deleted as authored artifacts and derived — the ×3 and ×2 copies **gone**, not synced |
| **2** | **R10 tool error contract** (+ retire the breakers it obsoletes) | every tool result carries a closed-set classification decided in the wrapper; `terminal_permanent` names what to do instead; the `isError`/`outputSchema` envelope is specified and proven against a **strict** client; **at least four of the six orchestrator breakers deleted**, with the eval suite green across the deletion |
| **3** | R3 skills declare tools — `allowed_tools` (policy) **and** reachability — + the three hard coverage gates | 100% of tools have exactly one group; every group owned by exactly one skill; the 30 orphans (incl. 17 `world_*`) either assigned or waived with a reason; user-skill frontmatter accepts both fields; the prose scraper is an assertion, not a mechanism |
| **4** | **R9 layers** — artifact lifecycle fields + the declared policy mapping · R9.6 counters | every tool carries `lifecycle_state` + `owner`; tools gain versions/revisions like skills and workflows already have; **one** place maps artifact state → availability, and the seven `is_legacy_tool` filter sites read it instead of the flag; `pinned_legacy_tools` deleted; usage counters written and `sort=last_triggered` demonstrably works |
| **5** | R4 `ToolSurface` · R5 guards register · **R11 retry budget + uncontaminated retry** · R8a state-axis sweep | the 18 filters reachable only through `excluded_by`, each carrying its `layer`; retry budgeted in tokens and money with per-tool retry-ratio telemetry; a retry no longer re-sends the failed attempts verbatim; the cross-mechanism invariant test **passes**: *"for every step of a pinned rail, availability is never Withheld"* — the test the project itself named as *the test that fails today* |
| **6** | R6 workflow-coverage ratchet · lane declaration complete · FSM/chat boundary enforced · R8b post-conditions | every tool carries a lane; the ratchet baseline is recorded and CI-enforced; a Run affordance exists for the FSM lane (closes the no-click-handler gap) |
| **7** | §8 retirement | every superseded doc carries a banner naming this spec |

**Why R12 goes first.** Everything after it deletes something — five hand-maintained tables, six
breakers, `pinned_legacy_tools`, 114 legacy tools, thirteen documents. **Without a regression net, none
of those deletions can be proven safe, so none will happen**, and this spec becomes the fourteenth
layer by the same mechanism as the previous twelve. The net is cheap: the harnesses already exist and
already pass; only the CI wiring and a versioned baseline are missing.

**Why R10 goes early and can run parallel.** It depends on nothing in R1–R9 and it is the item the
reported symptom actually asks for. It touches ten services, so it is the widest phase — but it is also
the only one that removes machinery on day one.

**Why R9 lands before R4.** `excluded_by` cannot carry a `layer` until the layers exist as data —
sequencing it the other way would ship the flat enum this spec was about to ship by accident, and then
migrate it. Phase 4 also gives Phase 6's ratchet the usage facts it needs to choose which rails are
worth promoting to the FSM lane.

Phases 0 and 1 are prerequisites under **every** reading of D1 and may proceed independently of any
further boundary refinement.

---

## 6 · Non-goals

- **Not** a rewrite of `stream_service.py`. R4 replaces the *availability* logic; the streaming,
  compaction and provider plumbing stay.
- **Not** a new service. `AUDIT.md` §4 — the registry that must exist is a generated contract file and
  the generator already exists.
- **Not** a change to the permission spine. Tier / scope / confirm-token / spend gates are sound and
  are shared across both lanes unchanged.
- **Not** deprecating the chat rail (D1).
- **Not** per-tool semantic versioning in the SemVer sense. R9 gives a tool an identity, a
  lifecycle state, an owner and a revision history — enough to answer *"is this safe to retire?"*.
  MCP itself defines no per-tool version (R9.4), so inventing a compatibility scheme here would be a
  standard of our own with no consumer.

---

## 7 · Risks

| Risk | Why it is real here | Mitigation |
|---|---|---|
| **This becomes layer 14** | twelve of thirteen predecessors were additive | §8 is a *phase*, not a footnote. Phase 1 **deletes** the authored copies rather than deriving alongside them |
| **A gate ships vacuous** | the audit found ≥6 in this exact domain, incl. two written the day before they were needed | §9 is mandatory per gate |
| **The ratchet is read as "done"** | a self-derived denominator always reads complete — a recorded lesson in this repo | the denominator comes from R1, never from what was built |
| **Phase 1 breaks federation** | prefix maps currently gate what survives `computeCatalog`; deriving them changes a silent-drop path | derive-and-compare for one release: log any tool the new derivation admits or drops vs the old maps, red on a diff, before deleting the maps |
| **The lane field gets guessed** | every layer in this system already guesses from names (12-verb async substring list, 43 intent regexes) | `lane` is required at registration and panics when absent — never inferred |
| **R9's policy layer is added but the old flag stays** | `is_legacy_tool` is read at 7 sites; adding a mapping *beside* them changes nothing and is how twelve of thirteen predecessors failed | Phase 3 is done only when the 7 sites read the policy and `is_legacy_tool` has no non-policy caller. Delete `pinned_legacy_tools` in the same phase — a surviving escape hatch proves the layer was not adopted |
| **Namespacing `_meta` breaks live consumers mid-flight** | keys are read across 3 languages + the FE; a partial rename de-federates or silently untiers tools | dual-read (accept both keys) for one release, gate on "no bare-key reader remains", then drop the bare keys. Never dual-*write* — that reintroduces two sources |
| **R10 becomes the seventh breaker** | a taxonomy is easy to add and the six existing breakers are load-bearing today; leaving them is the path of least resistance | Phase 2 does not close until ≥4 of the 6 are **deleted** and the eval suite is green across the deletion. Net-negative is in the DoD, not the prose |
| **The error taxonomy is assigned by guesswork** | ten services, ~334 tools, and this repo already guesses from names in four places (12-verb async list, 43 intent regexes, read-verb substrings, prefix maps) | classification is set where the failure is *raised*, never mapped from a message string downstream. A wrapper that cannot classify returns `terminal_permanent` — the fail-safe direction, since a wrong "retryable" is what causes the loop |
| **R12 lands as a green rubber stamp** | four harnesses currently pass; wiring passing tests into CI proves nothing and reads as coverage | the baseline is recorded from a run that **includes known-failing cases**, and Phase 1 does not close until one deliberately injected regression is shown to block a PR |

---

## 8 · Retirement (R8) — mandatory, Phase 7

Each gets a status banner naming this spec, in the style
`2026-07-21-eager-tool-index-mode.md` used correctly:

- `2026-07-06-tool-catalog-simplification.md` — CAT-4 hidden-vs-labeled is superseded by R1/R6
- `2026-07-07-mcp-discovery-and-reliability-hardening.md` — §0.5's four-tier model is **promoted**
  into this spec; the `find_tools` hardening is retired with the handler
- `2026-07-07-skill-authoring-and-mcp-exposure-standard.md` — Part A `hot_domains` superseded by R3
- `2026-07-09-agent-discoverability-and-workflow/` — C1/C2/C3/C6 re-issued against R1; **that spec's
  own Phase 5 ("retire mandatory semantic search") never ran and no doc says so** — record that. Not
  to be confused with this spec's Phase 5
- `2026-07-30-chat-service-control-plane-refactor.md` — **absorbed whole** as R4/R5; its 7 DEBT rows
  close against Phases 3–4
- [`../2026-08-03-tool-reachability-ssot.md`](../2026-08-03-tool-reachability-ssot.md) — **absorbed,
  not superseded.** Its diagnosis is independent corroboration of this audit from a live dogfood run,
  and three of its four shipped fixes hold. Its refactor request items 1–3 are R4 / R3 / R6; items
  4–5 become R8a / R8b. **Its item-3 fix is inert** (P0-1) — the banner must say so, or the next
  reader will believe `repeat` works
- `docs/standards/mcp-tool-io.md` — CAT-4 describes only half the live rule (`AUDIT.md` §3 / audits/06
  §3.1). **The reason it could describe only half is R9.2**: CAT-4 states an artifact fact
  (*"legacy"*) and a runtime consequence (*"never hot-seeded"*) in one sentence, so the two code paths
  that disagreed were both quoting it correctly. Rewrite it as an artifact state plus a reference to
  R9's policy mapping, and add the two unenforced gaps (#1 cross-service lint, #4 CAT-4 lockstep) as
  R6 rows
- `docs/standards/README.md` — add rows for this spec, for `tier-tag-gate.py` (wired in CI, listed
  nowhere), and for the anti-rot rule (§E, no row today)
- Dead code deleted with its layer: `tool_plan.py` (no `app/` importer), the unreachable `find_tools`
  branch at `stream_service.py:1344-1347`, `EDGE_FIND_TOOLS_DESCRIPTION`, and
  `sdks/python/build/lib/**` (a checked-in stale duplicate of 19 SDK packages)

---

## 9 · Non-vacuity obligations (NV-1..6 — LOCKED)

Every gate and test in this spec is subject to `docs/standards/non-vacuity.md`. The obligation is
mechanical: **break the guarded thing, watch it go red, put it back, paste the output** into VERIFY
evidence. *"I added a test"* is not evidence.

This spec's domain has produced all four vacuity shapes, each with a live instance found in this
audit — they are the checklist:

| Shape | Live instance found | What this spec must not repeat |
|---|---|---|
| **The scope never reaches it** | `TestSchemaSQL_SameActionMeansTheSameThingInEveryRail` (`migrate_lint_test.go:300-316`) asserts `repeat` is a bool by scraping the **seed SQL**. Measured end-to-end 2026-08-03 with the seed applied: **DB row `[true × 8]` · same rail on the wire, `repeat` 0× of 45 steps** (`gate` 45×, `done_when` 8× — the controls that prove the payload is intact). The guard is green; the field it guards has never reached a consumer. It was written the day before, *specifically for this field*, and proven red-able against a re-injected defect — red-able over the wrong subject | every drift gate must read the **wire**, not the source both sides were generated from, and must carry a **control field that survives** — an all-absent result proves nothing. Red-able is necessary and **not sufficient**: a guard must also be shown to observe the artifact the consumer actually receives |
| **The subject cannot vary** | `find-tools.spec.ts:203-207` "mirrors chat-service GROUP_DIRECTORY" against a **third hardcoded copy typed into the test** | a mirror test must read the other artifact, not a transcription of it |
| **An adjacent decision defeats it** | `D-RAIL-NEXT-STEP-EXEMPT` — a budget exemption computed once at turn start, defeated by mid-turn rail advance | R4's surface is recomputed at declared lifecycle points, and the invariant test asserts across mechanisms |
| **The escape hatch cannot reach its reason** | `_EXEMPT_SKILL_CODES` exempted `co_write` from the named-tools lint; the incident it caused is documented in the *other* guard's docstring | every waiver row carries a reason and a wake-up trigger |

**Deferral discipline.** Any row deferred out of this spec goes inside a
`deferral-registry:begin/end` block so `scripts/deferral-gate.py` can see it. Today **zero** deferrals
in this domain are mechanised — one row is in a table, ~10 live as prose in a 10,198-line handoff
(audits/06 §4). A prose-only row here repeats the failure this spec exists to end.

<!-- deferral-registry:begin -->
<!-- (no deferrals yet — rows are added here as phases close, never as prose elsewhere) -->
<!-- deferral-registry:end -->

---

## 10 · Open questions for DESIGN

1. **Where does `lane` live for a tool that is both?** `both` is expected to dominate; does the FSM
   lane's coverage ratchet count a `both` tool, or only `fsm`-exclusive ones? (Affects the day-1
   baseline materially.)
2. **Does R4 live in chat-service or become a shared SDK primitive?** The FSM lane needs the same
   availability answer. `sdks/python/loreweave_agent_control` already hosts the rail driver.
3. **Group granularity.** `composition` is 53 tools spanning outline, canon, motifs, arcs,
   conformance, derivatives — five capabilities under one prefix. Does "exactly one group" mean
   splitting it, and does that force a skill split too?
4. **Who owns the 17 `world_*` orphans** — a new `world` skill, or folded into `book`?
5. **Phase 1 rollout of `_meta.group`:** 312 federated tools across 3 languages. Backfill from the
   current prefix inference in one sweep, or per-service with the panic enabled last?
6. **Who is `owner` for a platform tool?** R9.4's rule is *a person or a rotation, never a wiki row* —
   on a single-maintainer hobby project that could be the owning **service** plus a CODEOWNERS entry.
   Decide before Phase 3, or the field becomes decoration like `used_count` was.
7. **What sunset window applies to us?** MCP's is 12 months; that exists for third-party clients
   nobody controls. For a tool consumed only by our own agent, the honest gate is *"no session used it
   in N days"* (R9.6) rather than a calendar. Pick one — a clock we will not honour is worse than none.
8. **Where does the policy mapping live?** A generated contract read by every consumer, or a resolver
   in the SDK both lanes import? The anti-fork clause (§2.3) forbids one per lane.
9. **Do the 114 legacy tools get retired, or re-homed?** R9 makes retirement possible; it does not
   decide it. Some are legacy only because a catalog-unification wave renamed them.
10. **Which four breakers does R10 delete?** Six exist; some encode judgement a taxonomy cannot
    express (`noop_write_counts` catches a *successful* call that changed nothing — an R8b
    post-condition, not an error). Name the set before Phase 2 starts, or "net-negative" is unfalsifiable.
11. **Where does the error classification live for a Go tool vs a Python tool?** `_meta` is
    per-tool-definition and static; a classification is per-*call*. It belongs in the result envelope —
    which means the two SDK kits need a shared result builder, not just a shared meta builder.
12. **Does R11's context isolation change what we persist?** Dropping failed attempts from the re-sent
    context is not the same as dropping them from `chat_messages`. The audit trail must survive what the
    model is shown — decide the split before touching the tool loop.
