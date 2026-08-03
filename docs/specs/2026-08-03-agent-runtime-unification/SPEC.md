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

### 1.0 The root cause, closed by experiment *(POC, 2026-08-04 — [`poc/`](poc/P1-P2-findings.md))*

A DESIGN-phase POC drove the real frontend, autopsied 7,442 production tool calls, and ran
single-variable experiments against the target model. **The loop has one root cause and it is now
reproducible:**

> The model is handed a tool list that **no longer contains the answer**, told the list is
> **complete and callable**, and **instructed to choose from it**. It complies. Everything downstream —
> the invented identifier, the repeat calls, the breaker messages, the `interrupted` turn — follows
> from **one silent deletion**.

Five arms, identical task, tool sets built from the real catalog:

| arm | tool set | result |
|---|---|---|
| A | 1 tool (`book_list`) | ✅ 1/1 |
| B | fixed envelope; schema delivered **in the conversation** | ✅ 1/1 |
| C | all 35 `book_*` — **19 retired**, 7,921 tokens | ✅ **3/3** |
| D | 16 current-only | ✅ 3/3 |
| **E** | **exactly the 7 the token budget left** | ❌ **0/3** |

**The only variable between 3/3 and 0/3 is whether the correct tool was on the wire.**
`budget_names_by_tokens` dropped it — with no log, no note, no telemetry — and the F18 auto-load then
announced *"these are now LOADED and callable — call one of them now."*

**Hypotheses rejected by measurement, several of them this spec's own:**

| claim | verdict |
|---|---|
| the model is too weak for this surface | ❌ correct in A, B, C, D |
| too many tools to select from | ❌ 3/3 at 35 tools / 7,921 tokens |
| deprecated tools drown the signal (this spec's earlier reading) | ❌ C and D identical — **OQ5's "label, don't hide" is vindicated** |
| the budget systematically favours retired tools | ❌ 1.07×, indistinguishable from noise |
| the context budget is exhausted | ❌ median utilisation **14.4%**; the P2b analysis was withdrawn |
| **a silent filter removed the answer** | ✅ **confirmed, reproducible** |

Two production numbers frame everything else: **57% of real tool errors are the model unable to name
a thing** (and 57% of the surface demands a caller-supplied id), and **58% of "errors" are our own
breaker messages** rather than tool failures.

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

### 1.3 Constraints (PO, 2026-08-03) — these invalidate assumptions, not just add scope

| # | Constraint | What it invalidates |
|---|---|---|
| **C1** | **The catalog is expected to reach thousands of tools.** Today 312. | The discovery triad was designed for ~200 and **structurally cannot survive 3,000** — see below. R14. |
| **C2** | **This repo is maintained for years.** Adding or renaming an MCP tool must be routine, not an event. | Today a rename must be hand-propagated to `GROUP_DIRECTORY` ×3, two prefix maps, `TOOL_POLICY`, 43 intent regexes, skill prose and `workflows.steps[].tool` — **none of them compiler-checked**. R13. |

**C1, measured directly.** DESIGN pulled the live federated catalog from ai-gateway (`tools/list`,
2026-08-03): **315 tools, ~130k tokens of schema, 413 tokens per tool** — higher than the ~375 this
section first estimated from the 2026-07-06 whole-domain figure.

| catalog | full schemas | name+description index | tools per group (17 flat) |
|---|---|---|---|
| 315 (today, measured) | **130k tok** | 16k tok | 19 |
| 1,000 | 413k tok | 50k tok | 59 |
| **3,000** | **1,239k tok** | **150k tok** | **176** |

**And the distribution is already lopsided today**, which matters more than the totals:

| level-1 prefix | tools |
|---|---|
| `composition` | **107** — a third of the whole catalog |
| `glossary` | 54 |
| `book` | 35 |
| `kg` | 31 |
| `world` | 17 |
| …12 more | ≤16 each |

**17 level-1 prefixes exist; `GROUP_DIRECTORY` declares 14.** Three are already unaccounted for — the
same silent-drop class the audit found, visible in the live data.

Three things break, in order:

1. **`tool_list(category)` returns a whole category.** At 214 tools per group that is not a listing,
   it is a context dump — and the F18 loop-breaker's "re-list ⇒ auto-load the category" behaviour
   becomes an instant window overflow.
2. **A flat 14-group taxonomy has no room.** `GROUP_DIRECTORY` is a ~15-line prompt block today; the
   grouping must become hierarchical, which is precisely what SEP-1300 deferred and therefore has no
   standard to inherit.
3. **The catalog itself exceeds the window.** At 3,000 tools even a bare name+description index is
   150k tokens, so *"list everything and let the model pick"* stops being an option at any level.

**C1 is why local patching cannot save this.** Every mechanism in the audit's thirteen is a
*constant-factor* improvement on an approach whose cost is linear in catalog size. The budget trims
harder, the breakers fire sooner — but nothing changes the exponent.

---

### 1.4 The original mistake — and the four shapes that remain *(PO, 2026-08-04)*

**MCP's native architecture is "load the catalog once, into the system prompt."** That is coherent at
the scale it was designed for: a few dozen tools against a ~20K system-prompt budget, which is what
the mainstream chat clients actually ship. **We could not do that** — 315 tools at 413 tokens each is
130K — **and we adopted the architecture anyway, then spent thirteen mechanisms compensating.**

> Importing an architecture without importing its scale assumption is the root mistake. Everything in
> `AUDIT.md` §5's timeline is downstream of it.

That reframes this spec's job. It is not to fix the compensations; it is to **choose a shape that is
sound at our scale** and rebuild on it. There are four, and they are the whole space:

| # | shape | system prompt | tool surface | cost |
|---|---|---|---|---|
| **1** | **Fixed per use-case** — a surface declares its tool set up front and it never changes | static | static per surface | the set must be right up front; the long tail is unreachable |
| **2** | **Lazy load** — accept dynamic context in both the system prompt and the state machine | **volatile** | volatile | **this is today.** Measured: 74% repeat calls, 72% organic failure, cache prefix destroyed |
| **3** | **User-curated** — the person picks the tools for the session | static | static per session, human-chosen | needs a UI, and the user must know what they will need |
| **4** | **State machine in the conversation** — system prompt fixed (or varying only with mode ask/write/plan), capability and guidance arrive as messages | **fixed** | fixed core; the rest arrives in-conversation | the inner call's schema validation must be recovered elsewhere |

**Shape 2 is the one we have, and the POC is its measured failure.** Shapes 1 and 3 are real and
already half-present (curated pins are shape 3; `surface_hot_domains` is a weak shape 1).

### The POC changed which shape leads

**Shape 1 was assumed impractical because the fixed set would have to be large. A fifth idea removes
that reason** (PO, 2026-08-04): **drop the atomic edit tools.** Keep search tools plus a handful of
coarse capabilities that take a **plain-text instruction** and run a whole job to completion through a
sub-agent — PlanForge end-to-end, world setup, glossary build.

Measured support:

- **57% of current tools require a caller-supplied id**, and **57% of real errors are id-resolution
  failures.** A capability taking *text* does not have that failure mode — **eliminated by
  construction, not mitigated.**
- **118 of 198** current tools are writes that collapse into coarse capabilities.
- A 16-tool surface routed a real multi-step request correctly **3/3** on the target model.
- ~20 tools is inside the measured comfort zone (arms A and C: 1 and 35 both perfect).
- The sub-agent boundary already exists: `subagent_runtime.py`'s `tool_scope` is **the only place in
  this repo where a capability genuinely owns a tool whitelist**, enforced at advertise *and* execute.

Its two costs, both measured and both addressable:

- **Prose-instead-of-action is the native failure mode** — 0/3 without a hard anti-prose directive,
  3/3 with one. This is the `co_write` incident (*6,948 characters, zero tool calls*) reproduced on
  demand, so the directive must be a **gate, not a hope**.
- **The 39 id-requiring reads must also collapse** to text-in/references-out, or the 57% class
  survives the refactor. That is a universal search — sound, and its choking risk is **not intrinsic**:
  p50 result size is 171 tokens, and the hazard is concentrated in the **18 of 36 read tools that have
  no `limit` parameter at all**, whose rule (OUT-2) is already written and already gated, with **14
  offenders grandfathered as FLIP-PENDING**.

**The leading design is therefore 1 + 4, with 3 as an explicit override:** a small static core
(one search per domain + coarse capabilities) — cache-stable, id-free, measured to work — plus
**arrival-in-conversation** for the long tail, plus **user curation** where the person wants it.
**Shape 2 is retired.**

**Still not decided:** how far the reads consolidate (whether ~20 is reachable), and whether
sub-agents hold correctness when handed free text. Those are DESIGN's remaining POCs.

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
**R13** the contract migration chain · **R14** discovery that does not scale with the catalog ·
**R12** evals in CI. Execution order is §5's phase table, which differs again.

**Two requirements exist because of the §1.3 constraints and nothing else.** R13 answers C2 (*"adding
an MCP tool is a nightmare"*) and R14 answers C1 (*"thousands of tools"*). They are the reason this is
a re-architecture rather than a cleanup: every other requirement improves a constant factor, and those
two change what the cost is a function of.

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

### R15–R20 — the POC-derived requirements *(see [`poc/P1-P2-findings.md`](poc/P1-P2-findings.md))*

Six requirements came from measurement rather than reasoning, and **R20 is the spine the rest hang
from.** Full evidence in the POC document; stated here so the spec is self-contained.

| id | requirement | measured basis |
|---|---|---|
| **R20** | **One arrival channel** — a capability and its guidance are delivered as one unit, at the same moment, in the same place | on 2 of 3 surfaces **zero skills are injected while tools are seeded**; `GROUP_DIRECTORY` advertises `plan` every turn on surfaces where no `plan` tool is reachable |
| **R19** | The advertised tool block is **cache-prefix state**: chosen once per session shape, never mutated mid-turn | a changed tool block costs **+65% uncached tokens** and drops hit rate by a sixth |
| **R18** | The prompt is a **projection** of state, never a parallel authoring surface. Prose may teach; it may not claim | lifecycle state and description prose agree **36%** of the time; 9 of 12 rails disagree with their own `notes_md` |
| **R17** | **Guidance is a gate** — a tool without effective guidance does not register | **60%** of tools require an id and never name its producer; 20% are legacy with no `superseded_by` |
| **R16** | **One deterministic loop detector**, over the stream, that **terminates** | 14 function-local counters, none aware of the others; the observed turn ended `interrupted`, not `stop` |
| **R15** | A **surface must be able to complete what it advertises** | `/chat` has no book binding and no book hot-seed, yet accepts "list my books" |
| **R21** | **A waiver carries an expiry, not only a reason** | the same pattern three times: `_EXEMPT_SKILL_CODES` hid the `co_write` defect; `KNOWN_RED` rows outlive their deferrals; **14 FLIP-PENDING allows are measurably the choking hazard** |

**R21 is the operating rule the POC kept re-discovering.** Three times today the shape was identical:
*the correct rule was written, the gate was built, an exemption was granted so as not to block
progress — and the exemption became permanent and then became the defect.* A waiver without an expiry
is not a waiver; it is a silent amendment to the rule. Every allow-list in this spec (R6's ratchet,
R17's 189 existing violations, OUT-2's 14) ships with a date, and passing it reds.

**R20 subsumes the old framing.** R3 (skills declare tools) becomes *how R20 is checked*; R15 is R20 at
the surface level; R19's cache argument becomes a *consequence* of R20 rather than a motivation. The
requirements below (R1–R14) are what make R20 mechanically enforceable — a manifest to name
capabilities, a migration chain to change them safely, a bounded discovery to deliver them.

**R10 is re-scoped, and the spec was wrong about it.** P2 measured that **58% of "errors" are our own
breaker messages**, not tool failures — so R10's error contract addresses **42% of error volume and is
not the loop fix**. The loop fix is R16 plus R4/R5 (withhold, do not argue). R10 still matters: an
unactionable error guarantees the next iteration is uninformed (**R10.2a** — name the remedy, not only
the violated constraint).

**R14 is re-justified.** It was written as the budget fix; the budget claim was retracted (P2b). R14
stands on C1 (scale) and on **selection accuracy** — `tool_list` returning 35 entries in a 3,393-token
payload of which **54% are retired tools** is the measured failure.

### R13 — The tool-contract migration chain *(C2 — "adding an MCP tool is a nightmare")*

The PO's framing: **build this the way Entity Framework builds schema change.** That analogy is exact,
and it decomposes into mechanisms we can adopt one at a time. EF's power is not that it prevents
schema change — it is that **the diff is generated, not hand-written**, so a change is cheap to make
and impossible to forget.

| EF Core | What it buys | Here |
|---|---|---|
| POCO model + fluent config | schema is *derived*, never typed twice | typed I/O + `_meta` at the registration chokepoint — **partly present**, see R13.1 |
| `ModelSnapshot` | a committed file stating current schema truth | `contracts/mcp-tool-catalog.json` — **R1** |
| `migrations add` | computes the diff **for you**; you cannot forget it | **R13.2 — missing, and it is the ergonomic unlock** |
| migration history ledger | what has been applied, in order | **R13.2** |
| LINQ over the model | rename ⇒ **compile error** | **R13.3 — missing entirely** |
| provider/consumer edges (Backstage) | find who breaks *before* you break them | **R13.4 — missing entirely** |

#### R13.1 — One registration path per language; the SDK generates the schema

Both SDKs in use are the official ones — `modelcontextprotocol/go-sdk v1.7.0-pre.3` and
`mcp[cli]==1.28.1` (`mcp.server.fastmcp`) — and **both already derive a tool's JSON schema from its
type**. The problem is not a missing capability; it is that the repo has **five registration patterns**
and, in Go, hand-built `InputSchema` overrides (`closedSetSchemaFor`, `relaxAdditionalProps`) that
*replace* what the SDK derived. Hand-written schema is the drift source.

Collapse to one path per language, schema always derived, closed sets expressed **in the type** rather
than patched onto the schema afterwards. The TS surface — which today has **no registration validator
at all** ([audits/04](audits/04-mcp-servers-federation.md) §2, variant E) — is the worst offender and
must join the same discipline.

> **Migration landmine, already visible.** `services/*/requirements*.txt` records that
> **`mcp==2.0.0b2` removes `mcp.server.fastmcp`** — the module all five Python providers are built on.
> That break is coming for ~180 tools at once. R1's snapshot is the difference between *"upgrade and
> see what shatters"* and *"the gate names every tool whose shape changed."*

#### R13.2 — Generated migrations, not hand-maintained lists

A `mcp-migrations add <name>` step that:

1. boots the providers, reads the live `tools/list`;
2. diffs it against the committed snapshot from R1;
3. **classifies every change** — `added` · `removed` · `renamed` (same shape, new name) ·
   `additive` (optional field added) · `breaking` (required field added, type changed, enum narrowed);
4. writes an ordered, committed migration entry with that classification;
5. rewrites the snapshot.

CI then enforces one rule: **live catalog ≠ snapshot and no migration entry ⇒ red.** That single gate
converts every one of the audit's silent drifts into a build failure at the moment it is introduced.

The point is the ergonomics, and it is the whole reason EF scales: **the developer never writes the
diff.** Change the tool, run one command, review what it generated. Today the equivalent is to
remember eight places by hand.

#### R13.3 — Generated typed clients, because the agent is an untyped client

The industry statement of why types help: *"a typed client breaks the build the moment an API contract
changes underneath it — that is the whole point of types: they turn a silent mismatch into a loud
compile error before it ships."*

**Our problem is the exact inverse: the LLM is a client that can never fail to compile.** No amount of
typing inside a provider makes a caller break loudly, because the caller passes a *string*. And it is
not only the model — every in-repo reference to a tool is a bare string too: `GROUP_DIRECTORY` ×3, the
prefix maps, `ALWAYS_HOT_WRITES`, `_STICKY_DOMAIN_IGNORE`, `INTENT_GATED_SETUP_TOOLS`, 43 intent
regexes, and `workflows.steps[].tool`. **Nothing is compiler-checked. That is why a rename breaks the
repo silently.**

Generate typed clients from the snapshot for every in-repo consumer (chat-service, the workflow
resolver, the public-edge policy). A rename then breaks *their* build. The model still cannot be
type-checked — which is exactly why the failure has to move to CI (R13.2), where it can.

#### R13.4 — Reference edges, so a rename knows who it breaks

Register every string reference to a tool as a **consumer edge** in the snapshot: workflow steps,
skill declarations (R3), policy rows, intent maps, prompt directories. A migration that renames or
retires a tool then reports **every broken edge by name**.

This is the Backstage discipline — *"when v2 launches, identify v1 consumers directly from the catalog
and coordinate deprecation"* — and it is what makes C2 tractable. It also answers the PO's *"workflows
collapse whenever an MCP tool changes"*: today `workflows.steps[].tool` is a free string validated at
**four consecutive layers, none of which check it**
([audits/05](audits/05-workflows-registry.md) §4.2). With edges, a workflow referencing a renamed tool
is a red migration, not a rail that silently stops working.

#### R13.5 — Rename becomes a lifecycle operation, not a find-and-replace

The three previous points make this possible; state it as the rule:

> **You never rename a tool. You add the new name, mark the old one `deprecated` with
> `superseded_by` + a sunset trigger (R9), and the edge report tells you when nothing references the
> old name any more — that is when it may be removed.**

Exactly EF's `add column → backfill → drop column`, applied to a tool. It converts the current
all-at-once, silently-breaking rename into a bounded, observable sequence — and R9.6's usage counters
are what make *"nothing references it any more"* a fact rather than a hope.

#### R13.6 — The codegen boundary: generate the CONTRACT, never the PROSE

**Where the EF analogy stops, and it stops at the most important point.** EF's generated artifact is
code read by a compiler, so verbosity is free. **Ours is partly prompt text read by an LLM on every
turn, where every generated token is paid N times, forever.** A naive copy of EF therefore fails in a
specific way the PO named: *bad codegen does not merely fail to improve things — it is worse than the
hand-written version*, because a human at least compresses.

The rule, and it is not negotiable in either direction:

| Target | Read by | Optimise for | Verbosity |
|---|---|---|---|
| snapshot · migrations · typed clients · gates · the group tree | compiler / CI | completeness, explicitness | **free** |
| skill bodies · rail text · tool descriptions · the group directory block | **the LLM, every turn** | token economy | **paid N×** |

**The audit supports the split.** What is broken in the skill layer is the *binding* — a regex
scraping backticks out of prose — not the prose itself, which is pedagogically good and
human-compressed. So: **generate the binding, keep the prose.** R3 already draws this line
(`allowed_tools` is data, the body is prose); R13.6 generalises it to every generated artifact.

**Tooling, by class — and the class decides the tool:**

- **Code (typed clients, models): do not string-template.** The standing critique is that mixing text
  blocks with control logic *"reduces readability, expressiveness, reusability, and analyzability"*,
  and practice has moved toward model/AST-based emitters. Use `datamodel-code-generator`
  (JSON Schema → Pydantic v2 / dataclass / TypedDict) on the Python side and `quicktype` where a
  cross-language model is wanted. On the Go side the official SDK **already derives schema from the
  type**, so what we generate there is the *client*, not the model.
- **Small, stable text artifacts** (the group tree block, gate stubs): a template engine is fine, and
  here a **logic-less** one (Mustache/Handlebars) is preferable to Jinja — when the output lands in a
  token budget, an engine that *constrains logic* is a feature. Go `text/template` covers the Go side.
- **Prompt prose: not generated at all.** Hand-written, gate-checked against the manifest (R3).

**And the gate that keeps this honest — R13.6.1.** Every generated artifact that enters a prompt
carries a **token-budget assertion in CI**. The repo already measures (the group directory at ~188
tokens live, `HOT_SEED_TOKEN_BUDGET`, the W1 frontend/MCP schema-token split); what is missing is the
red. Without it, codegen bloat is invisible until someone reads a transcript — which is precisely how
the 24,000-token-per-turn tax survived for weeks.

Two assembly disciplines from the prompt-bloat literature map directly onto what we already do, and
should be named so they stop being accidental:

- **Task-relevant projection** — project metadata to what the task is likely to reference. This *is*
  the hot-seed. It was right.
- **Priority-ordered composition** — a prompt is typed blocks of differing marginal value, assembled
  greedily under a fixed budget. This is the shape R4's `ToolSurface` should converge on, and it is
  what turns the three separate budgets (§R7 context) into one ordered ceiling.

### R14 — Discovery cost must not scale with the catalog *(C1 — thousands of tools)*

The discovery triad is a **constant-factor** optimisation over an approach that is **linear in catalog
size**. At 3,000 tools the constants stop mattering (§1.3). Three changes make the cost independent of
how big the catalog gets:

**R14.1 — Every discovery result is hard-bounded.** No call may return "the whole category". A bound
(≈20 entries) with an explicit `more: N` and a narrowing hint replaces it. This also removes the F18
auto-load-the-category behaviour, which at 214 tools per group is a window overflow rather than a
loop-breaker.

**R14.2 — Groups become hierarchical.** A flat 14-way taxonomy cannot index thousands. `tool_list` at
any level returns **children, not leaves** — domains, then subgroups, then tools — so a single call is
O(branching factor), never O(catalog). SEP-1300 deferred hierarchical nesting, so this is ours to
define; R2's `group` becomes a path (`glossary/ontology`, `composition/arcs`) rather than a flat token.

**R14.3 — Retrieval for the tail, enumeration for the tree — and this reconciles F17.** F17 retired
`find_tools` because fuzzy top-K *cannot enumerate*. True, and at 3,000 tools **enumeration cannot
enumerate either.** The two are not competitors; they answer different questions at different levels:

| Level | Mechanism | Property needed |
|---|---|---|
| the tree (domains, subgroups) | deterministic enumeration | complete, reproducible, small |
| the leaves within a subgroup | **retrieval** — semantic + metadata filter | recall over a bounded candidate set |

Reported elsewhere for retrieval-filtered selection: tool-selection accuracy **13.62% → 43.13%**, and
a semantic router over 741 tools cutting **127,315 → 1,084 tokens**. The production shape is layered
and *ordered*: intent classifier → metadata filter → semantic search → scoring → the model chooses
from a small clean set. **LoreWeave already owns all five pieces** — the intent router, hot-domain
filtering, embeddings, budget scoring, and the model. They are simply unordered and unlabelled, which
is R4. R14 is what R4's ordering must converge on once the catalog is large.

**Consequence for the spec:** `find_tools` is not resurrected as-is — its unbounded retry bias was a
real defect — but *retrieval* returns as a first-class, bounded stage inside `tool_list`/`tool_load`,
rather than as a competing third tool. §8 must record this as an amendment to F17 rather than a
reversal, or the next reader will read it as the fourteenth swing of the pendulum.

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
| **1** | **R12 evals in CI** · R1 manifest · R2 `_meta` group/lane + R9.5 namespacing + cache hints · R7 enum · **R13.1 one registration path per language** | the four existing harnesses run in CI against a versioned golden set and block a PR on regression; manifest generated in CI; registration panics on a missing group in all 3 languages; schema is SDK-derived everywhere and hand-built `InputSchema` overrides are gone; `_meta` keys namespaced; catalog version hashes description + `_meta`; `GROUP_DIRECTORY`/prefix maps deleted as authored artifacts and derived — the ×3 and ×2 copies **gone**, not synced |
| **1b** | **R13.2–R13.6 the migration chain** — generated diffs, typed clients, reference edges, rename-as-lifecycle, the codegen boundary | `mcp-migrations add` generates and classifies the diff; **CI reds on live-catalog ≠ snapshot with no migration entry**; in-repo consumers build against generated clients; a rename reports every broken edge by name. **No prose is generated, and every generated artifact entering a prompt carries a CI token-budget assertion (R13.6.1)**. Proof: rename one real tool and show the gate naming its consumers *before* anything breaks at runtime; and show the budget gate redding on a deliberately bloated generated block |
| **2** | **R10 tool error contract** (+ retire the breakers it obsoletes) | every tool result carries a closed-set classification decided in the wrapper; `terminal_permanent` names what to do instead; the `isError`/`outputSchema` envelope is specified and proven against a **strict** client; **at least four of the six orchestrator breakers deleted**, with the eval suite green across the deletion |
| **3** | R3 skills declare tools — `allowed_tools` (policy) **and** reachability — + the three hard coverage gates | 100% of tools have exactly one group; every group owned by exactly one skill; the 30 orphans (incl. 17 `world_*`) either assigned or waived with a reason; user-skill frontmatter accepts both fields; the prose scraper is an assertion, not a mechanism |
| **4** | **R9 layers** — artifact lifecycle fields + the declared policy mapping · R9.6 counters | every tool carries `lifecycle_state` + `owner`; tools gain versions/revisions like skills and workflows already have; **one** place maps artifact state → availability, and the seven `is_legacy_tool` filter sites read it instead of the flag; `pinned_legacy_tools` deleted; usage counters written and `sort=last_triggered` demonstrably works |
| **5** | R4 `ToolSurface` · R5 guards register · **R11 retry budget + uncontaminated retry** · R8a state-axis sweep | the 18 filters reachable only through `excluded_by`, each carrying its `layer`; retry budgeted in tokens and money with per-tool retry-ratio telemetry; a retry no longer re-sends the failed attempts verbatim; the cross-mechanism invariant test **passes**: *"for every step of a pinned rail, availability is never Withheld"* — the test the project itself named as *the test that fails today* |
| **6** | **R14 discovery that does not scale with the catalog** — bounded results, hierarchical groups, retrieval for the tail | no discovery call can return more than the bound; `group` is a path and `tool_list` returns children not leaves; retrieval is a bounded stage inside `tool_list`/`tool_load`, not a third tool. Proof: a **synthetic 3,000-tool catalog** in the eval harness, on which discovery token cost and hop count stay flat versus 312 — the only honest way to test C1 before it arrives |
| **7** | R6 workflow-coverage ratchet · lane declaration complete · FSM/chat boundary enforced · R8b post-conditions | every tool carries a lane; the ratchet baseline is recorded and CI-enforced; a Run affordance exists for the FSM lane (closes the no-click-handler gap) |
| **8** | §8 retirement | every superseded doc carries a banner naming this spec |

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
| **The migration chain becomes another hand-maintained list** | the repo has already produced seven of those (`ALWAYS_HOT_WRITES`, prefix maps, `TOOL_POLICY`, …), every one added after an incident | the diff is **generated or it does not exist**. A migration entry a human typed is the failure mode, not the feature. Phase 1b's proof is a real rename whose consumer list the tool produced unaided |
| 🔴 **Codegen makes the context problem WORSE** | EF's output is free; ours is partly prompt text paid on every turn. A generated skill body or a templated tool-description block would be more verbose than the hand-compressed prose it replaced, and the cost is per-turn and permanent — the single most likely way this spec does net harm | R13.6 forbids generating prose at all, and **R13.6.1 puts a token-budget assertion in CI on every generated artifact that enters a prompt**. If a codegen change grows the prompt, the build reds. This risk is the reason that gate exists rather than being a nice-to-have |
| **R14 is designed for a catalog we do not have** | 312 tools today; "thousands" is a projection, and building for imagined scale is its own classic mistake | do not guess — **test it**: the Phase 6 DoD is a synthetic 3,000-tool catalog in the eval harness. If discovery cost stays flat there, the design holds; if it cannot be built, that is the finding |
| **F17 reads as reversed rather than amended** | retrieval returning after `find_tools` was retired looks like the pendulum swinging back, which is how this domain got thirteen layers | R14.3 states the distinction explicitly (enumeration for the tree, retrieval for the leaves) and §8 records it as an amendment with the reason. A reversal nobody explains becomes the fourteenth layer |
| 🔴 **The spec's own reasoning keeps being wrong in the same direction** | measured this session: **R14's justification had to be corrected three times**; P2b was withdrawn entirely; OQ5 was declared falsified and then vindicated; four of my own measurements were errors, **every one from reading a proxy instead of the artifact the consumer receives** | no requirement may rest on reasoning alone where a measurement is available. Each requirement in §3 now carries its measured basis, and where it has none it says so. This is NV-2 applied to the spec itself |
| **The refactor is too large to land** | 21 requirements, 9 phases, 5 services, 3 languages, ~198 tools to re-home | Phases 0–1 are independently valuable and independently shippable: the six lies, the eval net, the manifest. **If the effort stops after Phase 1 the repo is still measurably better off** — that is the test each phase boundary must meet |

---

## 8 · Retirement (R8) — mandatory, Phase 8

Each gets a status banner naming this spec, in the style
`2026-07-21-eager-tool-index-mode.md` used correctly:

- `2026-07-06-tool-catalog-simplification.md` — CAT-4 hidden-vs-labeled is superseded by R1/R6
- `2026-07-07-mcp-discovery-and-reliability-hardening.md` — §0.5's four-tier model is **promoted**
  into this spec; the `find_tools` hardening is retired with the handler
- `2026-07-07-skill-authoring-and-mcp-exposure-standard.md` — Part A `hot_domains` superseded by R3
- `2026-07-09-agent-discoverability-and-workflow/` — C1/C2/C3/C6 re-issued against R1; **that spec's
  own Phase 5 ("retire mandatory semantic search") never ran and no doc says so** — record that. Not
  to be confused with this spec's Phase 5
- **F17 (`find_tools` hidden from the LLM) — AMENDED, not reversed, and the banner must say which.**
  F17's finding stands: fuzzy top-K cannot enumerate, and an unbounded retry bias produced a
  40-iteration / 53.8s / zero-length answer. R14.3 changes only the *scope* of that conclusion — at
  thousands of tools enumeration cannot enumerate either, so retrieval returns as a **bounded stage
  inside** `tool_list`/`tool_load` for the leaves, never as a competing third tool with its own retry
  loop. Anyone reading F17 alone will otherwise build the wrong thing, in either direction
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

### 10.0 Audit of this list *(2026-08-04, post-POC)*

**The POC did not merely answer questions — it made several obsolete**, because the leading design
moved from shape 2 (lazy-load, volatile surface) to **1 + 4** (small static core of search + coarse
capabilities, long tail arriving in the conversation). Questions written *about* the old architecture
do not survive it.

| status | questions | why |
|---|---|---|
| **MOOT or much smaller under 1+4** | 3, 5, 15, 16, 17, 18 | if the advertised set is ~20 tools and the system prompt is static, group granularity, a 312-tool `_meta.group` sweep, hierarchy depth, the group-directory block and its budget all shrink drastically. **Hierarchy and retrieval do not disappear — they move from the advertised surface to the search index**, which is a different and easier problem |
| **ANSWERED by POC** | **10**, **14** | below |
| **STILL LIVE, unchanged** | 1, 2, 6, 7, 8, 9, 11, 12, 13 | none depends on which shape wins |
| **NEW, created by the POC** | N1, N2, N3 | below |

#### Q14 — ANSWERED, and the answer invalidates R13.5's model

Measured on the live catalog: **54 tools declare `superseded_by`, pointing at only 17 distinct
targets — a 3.2 : 1 ratio.** The largest: six tools collapse into `composition_arc_edit`, five into
`composition_authoring_run_manage`, five into `composition_outline_node_edit`.

> **Renames here are not renames. They are many-to-one CONSOLIDATIONS.**

R13.5 assumed 1:1 (*add the new name, deprecate the old, same capability*) and proposed a stable
`tool_id` to carry identity across it. **That model does not survive six capabilities merging into
one — which `tool_id` continues?** The corrected model:

- a tool's `tool_id` is **its own** and never transfers;
- `superseded_by` is a **many-to-one edge**, not an identity continuation;
- **usage history aggregates along the edge** (R9.6's retire criterion sums the sources into the
  target), it does not follow an id;
- and the primary migration operation to design for is **consolidation**, not rename — which is also
  exactly what shape 1+4 does at scale (118 writes → ~8 capabilities).

Also measured: only **54 of 117** retired tools (46%) declare any replacement at all, so 63 have no
edge — matching R17/G2's count exactly.

#### Q10 — PARTIALLY answered; the ranking is measured, the list is not yet complete

Breaker fires in production, by pattern:

| fires | breaker |
|---|---|
| 595 | repeated-read |
| 263 | noop-write (`created=false`) |
| 157 | `find_tools` blank-intent *(historical — `find_tools` is de-advertised)* |
| 122 | blank-args cap |
| 26 | repeated-failure |

**This inventory is incomplete and must not be treated as final**: the pattern set used here missed
the `tool_list` category cap, which a separate measurement counted at **1,180 fires — the largest of
all**. The ranking above is sound; the totals are not. Complete the inventory from the emitting call
sites, not by matching message text, before Phase 2 names the deletions.

What the data already shows: `noop_write_counts` (263) catches a **successful** call that changed
nothing — an R8b post-condition, not an error, so R10's taxonomy cannot absorb it. `repeated-read`
(595) and the `tool_list` cap (1,180) are both *"you already have this answer"* — precisely what R16's
deterministic detector subsumes.

#### New questions created by the POC

- **N1 — how far do the reads consolidate?** Shape 1+4 needs ~20 advertised tools. 80 reads exist, 39
  requiring ids. Does one search per domain (~12) plus coarse capabilities (~8) actually cover real
  usage, or does the tail reappear?
- **N2 — do sub-agents hold correctness when handed free text?** The coarse design *moves* the problem
  behind `subagent_runtime.py`'s `tool_scope`; it does not delete it.
- **N3 — what is the anti-prose gate?** Measured 0/3 without a hard directive and 3/3 with one. The
  directive works; it must be enforced and regression-tested, because the identical failure already
  shipped once as the `co_write` incident.

---

### The questions themselves

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
13. **Does the migration snapshot come from a live stack or a static scan?** Live `tools/list` is
    truthful about federation but needs a booted stack in CI; the static scan runs anywhere but cannot
    see what federation drops. EF has no equivalent of a provider that silently omits a table — this
    one is ours. Probably both, with the live run authoritative and the static one a pre-commit guard.
14. **What is a tool's identity across a rename?** R13.5 says add-new + deprecate-old, which only works
    if the two are known to be the same capability. EF uses the property name; we would need a stable
    `tool_id` distinct from the wire name — a real schema decision with a migration of its own.
15. **How deep does the group hierarchy go, and who decides a tool's path?** R14.2 makes `group` a path.
    Two levels probably suffice at 3,000; the author declares it at registration, but the *taxonomy*
    itself needs an owner or it drifts the way the flat one already did (`world` and `meta` rejected by
    a registry that had 12 of the 14 groups).
16. **Which retrieval backend, and does it need to be in the request path?** R14.3 needs embeddings over
    the catalog. Provider-registry already resolves an embedding model, and `tool_discovery.py` already
    caches tool vectors — but that machinery was built for the de-advertised `find_tools`. Reuse or
    rebuild is a real fork.
17. **Is the group-directory prompt block generated or hand-written?** It is the one artifact sitting
    exactly on R13.6's line: its *content* is derived from the manifest (so it should be generated and
    can never drift), but it is *read by the model every turn* (so every generated token is paid). If
    generated, it needs R13.6.1's budget assertion from day one; if hand-written, it needs a gate that
    it still matches the manifest. Both are defensible; drifting between them is not.
18. **Which prompt artifacts get a budget, and what is the number?** R13.6.1 needs a ceiling per
    artifact, not a global one. The repo has measured values to start from (group directory ~188 tok,
    `HOT_SEED_TOKEN_BUDGET` 2000) but no others — and a budget picked without a measurement is the
    same mistake as `ROUTER_CONFIDENCE_THRESHOLD = 0.35`, which the code itself records as *"NOT yet
    empirically tuned"*.
