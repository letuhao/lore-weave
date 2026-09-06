# S5 — P4 ASSEMBLY, coverage interrogation

**Module:** P4 · *what reaches the model this turn, and why.*
**Status:** interrogation. Two questions only — what must assembly handle, and can a bought
component handle it.
**Method:** grounded against the code being replaced (`stream_service.py`,
`tool_surface.py`, `tool_discovery.py`, `find-tools.ts`, `scope-filter.ts`) and against
`audits/01-tool-surfacing.md`, `redteam/RT3`. Every claim carries a file:line or a doc §.
**Buy-verification:** Pydantic AI toolsets + FastMCP tool transformation were read at
source (docs now at `pydantic.dev/docs/ai/*`; `ai.pydantic.dev` 301-redirects). This is
**Pydantic AI v2** (capabilities + Harness), which changes several answers a v1 reading
would have given. Every verdict below is marked SUPPORTED / PARTIAL / NOT SUPPORTED /
UNVERIFIED.

---

## 1 · What situation does assembly exist to solve?

Not "there are too many tools." That argument (A1 "the set, not the model", A2 "~20
tools") was killed by the red team, and `BUILD-VS-BUY.md` §1 independently confirms it:
the routing paper measures a **10pp oracle-ceiling drop that survives perfect
retrieval**. Assembly cannot be justified by surface size.

The situation assembly actually exists to solve, stated from the evidence:

> **Between a catalog and a model there are today sixteen producers and eighteen
> suppressors of the advertised set, none of which knows about the others, and thirteen
> of the suppressors are silent. The tool is in the catalog, the model can name it, and
> it is not on the wire — for a reason no single place in the system can report.**

The counts are audited, not estimated: `audits/01-tool-surfacing.md` §1 (P1–P16, sixteen
producers) and §3 (B1–B18, eighteen filters; *"Score: 13 of 18 are silent"*). The single
most frequently-firing filter, the hot-seed token budget, has **no log, no counter, no
SSE field** (`tool_surface.py:158-159`).

That is the situation. It has three observable shapes, each with a measured incident:

| shape | mechanism | measured consequence |
|---|---|---|
| **the recipe names a tool that is not on the wire** | `budget_rail_tools` drops a step tool the rail TEXT names (`tool_surface.py:180-214`) | *"glossary_propose_entities was the perpetual drop"*; `kg_propose_edge` failed telling the agent to call a tool that was budget-dropped, the step-runner redrove it **8 times**, the model reported success anyway (`tool_surface.py:55-58, 427-433`) |
| **narrowing changed which of two near-synonyms survived** | budget kept `glossary_propose_entity_edit`, dropped `glossary_propose_entities` | *"the model mapped the create intent onto the similarly-named edit tool, every turn"* (`tool_surface.py:444-456`) |
| **the surface asserts it is complete when it is not** | `tool_list` during a glossary outage returned `count: 1` with no hint | the agent claimed it had *"loaded the glossary tools"*, then **blamed the user** for a platform outage (`tool_discovery.py:948-956`) |

`ARCHITECTURE.md` §0.1 names this correctly and generalises it: `budget_names_by_tokens`
dropping `book_list` *"was not wrong because it narrowed; it was wrong because it narrowed
silently, and then the surface told the model the list was complete."*

**So P4's job is not to choose a set. It is to make every narrowing registered,
communicated, and reversible.** Two of those three words have no mechanism in the design
yet, which is what the rest of this document is about.

### 1.1 What the four surfaces actually differ by

`surface_hot_domains(editor, book_scoped, studio, permission_mode)`
(`tool_discovery.py:362-415`) derives hot domains from
`resolve_skills_to_inject(enabled_skills=[], …)` — **omitting `lazy_bodies`**, so it takes
the legacy branch, while the live call passes `settings.lazy_skill_bodies` (default
**True**, `config.py:272`) and gets `[]`. Audit §5.3: on the default configuration the
surface hot-seeds `glossary`/`book`/`knowledge`/`story` **while no skill prompt is
injected to teach them**, and `skill_named_tools([])` contributes nothing — so
`D-SKILL-NAMED-TOOLS-RIDE`, the invariant added after the entity_edit incident, is
**inert by default**.

`permission_mode` is **per-turn**, not per-session (`messages.py:381-393`), flipped by a
one-key cycle handler (`ChatInputBar.tsx:195-199`). `book_bound` is a per-turn
`context_ids` field (`stream_service.py:2107`). RT3 F7 counts **60 distinct static tool
blocks** before curation, which is combinatorially unbounded.

---

## 2 · The coverage tests

Legend — **D:** does `ARCHITECTURE.md` answer it. **B:** can the bought component do it.
**CT:** Ceiling Test (§0.3) verdict.

---

### S5-1 · The model asks for something that was WITHHELD 🔴 D: NO · B: PARTIAL

**Today.** Two answers coexist and only one is honest. `tool_list`/`tool_load`
(`tool_discovery.py:972-1077`) genuinely defer: a budget-dropped tool is loadable by name.
But **B4** — `INTENT_GATED_SETUP_TOOLS`, five tools — is removed *from the turn catalog
object itself*, the one object all three reach-paths read
(`tool_discovery.py:442-484`). It is un-seedable, un-listable **and un-loadable**;
`tool_load` answers `not_found`, which the same file's comment states *"ASSERTS that no
such tool exists"* (`:1050`). That is `budget_names_by_tokens` deleting `book_list` again,
with a gate in front of it. Whether it fires is decided by an **English-only substring
list** (`_WORLD_SETUP_MARKERS`, `skill_registry.py:434-453`) against a Vietnamese-writing
PO — audit §5.4.

**The design gap.** §0.1 gives three sets: admitted, advertised, withheld. B4 is in none of
them — it is *narrowed out of the runtime's own catalog input*, a fourth state the
vocabulary cannot express. And §0.3's rule — *"the withheld thing must remain reachable on
request"* — names no **mechanism**. It states a property with no owner. Nothing in §0.1,
§0.2 or §5 says what makes a withheld declaration reachable, or forbids a narrowing that
removes reachability.

**The buy, verified — and this is the finding that matters.** Pydantic AI has **two**
narrowing mechanisms and they are not interchangeable:

- `FilteredToolset` / `.filtered()` / `prepare_tools` — *"filters available tools ahead of
  each step of the run"*. A tool removed this way is **gone**. Nothing can ask for it.
- `DeferredLoadingToolset` / `.defer_loading()` / `ToolDefinition.defer_loading` —
  *"marks its tools for deferred loading, **hiding them from the model**"*, reachable via
  the `ToolSearch` capability (*"Discovery of deferred tools — native when supported,
  local `search_tools`"*).

**One is a ceiling and one is an enabler, they are one method call apart, and the design
does not choose.** "Buy P4" as written is satisfied by either. If a future implementer
reaches for `prepare_tools` — the obvious, most-documented API, and the one whose shape
matches today's `_advertise_discovery_tools` — the Ceiling Test fails by construction and
no gate in M1–M5 detects it.

**CT:** the design passes on paper (`defer, never delete`) and has **no mechanism that
makes the pass enforceable**. B4 ships today as a live ceiling.

**Required:** an invariant — *every runtime narrowing is expressed as deferral, never as
removal from the assembler's input* — plus a red-able gate: assert that for every admitted
declaration not advertised this turn, a by-name request returns it.

---

### S5-2 · The model asks for something that DOES NOT EXIST 🔴 D: NO · B: NOT SUPPORTED

**Today.** The distinction is drawn better here than anywhere else in the repo, and it was
bought with an incident. `tool_load_result` splits `not_found` (asserts non-existence) from
`provider_unavailable` (*"This does NOT mean the tool does not exist"*), with the reasoning
in-line: *"Only assert non-existence when the catalog is COMPLETE"* (`:1050-1068`). It
exists because on 2026-07-23, with glossary down, `tool_load("glossary_propose_entities")`
answered `not_found` and *"the model reasoned correctly from that false premise and gave up
on a tool that exists."*

Two paths still lie. B4 (above) returns `not_found` for an admitted tool. And the public
edge returns the same message for both, **on purpose**: *"Anti-oracle: an unknown tool and
an out-of-scope tool give the SAME message, so a probing agent can't distinguish 'doesn't
exist' from 'not in my scope'"* (`scope-filter.ts:38-40`). That is correct security and
directly contradicts §0.3's *visible and appealable* — a legitimate conflict the design has
not noticed.

**The design gap.** §5.2 requires `withheld_tools` — `{tool, stage, reason}` — as
**telemetry**. §0.1 calls a non-registering withholding *"a contract violation"*.
Registration is a row in our database. **Nowhere does the design require the withheld set,
or its reason, to be answerable to the model.** But §0.3 demands every constraint be
*"appealable by the model"*, and an appeal needs an answer channel. **Registered and
communicated are two different artifacts, and the design ships one and asserts the other.**

**The buy.** NOT SUPPORTED. Filtering in Pydantic AI is a pure list→list transform —
`prepare`/`prepare_tools` return the surviving `ToolDefinition`s and omission is simply
absence. FastMCP is explicitly silent too: *"Disabled tools don't appear in `list_tools`
and can't be called."* There is no exclusion-reason channel on either side. **The single
clause §0.1 exists to enforce is the one clause the bought component does not have.**

---

### S5-3 · A plan references a declaration that is not advertised 🔴🔴 D: NO · B: NO

**This is the sharpest gap, and the repo has paid for it three times.**

**Today.** (i) `budget_rail_tools` drops step tools a rail's rendered text names by name —
patched with `D-RAIL-NEXT-STEP-EXEMPT` after the 8× redrive. (ii)
`D-SKILL-NAMED-TOOLS-RIDE` scrapes backtick-quoted tokens out of skill prose with a regex
(`tool_surface.py:527-568`) because *"an INJECTED instruction must never name a tool that
is not on the wire"* — and its own docstring records that guard failing: `co_write` named
its plan tools only in signature form, so `plan_propose_spec` and `plan_compile` were never
advertised, and the co-writer *"wrote 6948 characters of plan prose, called NOTHING
(finish_reason=stop, 0 tool calls)"*. Two guards, each blind in a different way,
intersecting on exactly the two tools that materialise a plan. (iii) Audit §5.3.4: under
the default config `load_skill` returns a body saying *"call `plan_propose_spec` then
`plan_compile`"* while neither is on the wire outside `permission_mode="plan"` — the eager
path was fixed, the lazy path was not.

**The design gap, stated precisely.** §0.4 says *"the tool surface is UNCHANGED by the plan
— the plan informs, never gates."* Correct, and it is what makes plan-as-data pass the
Ceiling Test. **But it forbids only the narrowing direction.** It says nothing about
widening, and the entire measured failure class is the widening direction: the plan names a
declaration, the surface does not carry it, and the plan is unexecutable.

M5/C-11 look like they close this and do not. They make a step reference *"a foreign key
into M1, resolved at generation"* — which proves the reference is **admitted**. Advertised
is a different set (§0.1), owned by a different artifact, decided at a different time.
**M5 closes the plan→admitted seam and leaves the plan→advertised seam wide open**, which
is precisely where all three incidents live.

Worse under §0.4's own carry-forward mechanism: C-6 `emits` lets the executor *"satisfy a
binding directly instead of asking the model to retype a UUID."* If the consuming step's
declaration is not advertised, the binding is satisfiable and uncallable — the plan holds a
correct value for a call that cannot be made.

**Required, and it is one sentence:** *a declaration referenced by any step of an active
plan is advertised, budget-exempt, for as long as the plan is live.* Widening is an enabler
(§0.3), so this costs nothing on the Ceiling Test. It also **deletes** the regex prose
scraper, the rail next-step exemption and the skill-named-tools ride — three heuristics
replaced by one structural fact, which is the §0.4 argument applied to itself.

**The buy.** `prepare_tools` can union a set in; nothing in Pydantic AI knows what a plan
is. Host-built, and small.

---

### S5-4 · A per-turn CONTRACT rewrite, not a set change 🔴 D: NO (not expressible) · B: SUPPORTED (and encouraged)

**Today.** B17: on a book-bound turn `_project_ambient_book_schema`
(`stream_service.py:1272-1294`) **deletes the `book_id` property** from the advertised
schema of every `_meta.ambient_book` tool, and strips it from `required`. The model is
shown a declaration that is not the declaration.

**The design gap.** §0.1's invariant — *narrow, never invent* — and the admitted /
advertised / withheld triad are **set-valued**. They range over *which declarations* are on
the wire. They have no vocabulary for a runtime that rewrites a declaration's `parameters`
before sending it. Yet this is routine here, and it collides with two P2 clauses:

- **C-4** `accepts` declares argument provenance. If the runtime deletes the argument, whose
  provenance is authoritative — the manifest's or the wire's?
- **C-12** requires a rejection to *"name the field path it rejected"*. Which field path:
  the declared one the model never saw, or the projected one? The memory
  *"a field the server drops may never be reported as absent"* is exactly this shape, one
  layer up: here the runtime drops the field from the **schema**, and a downstream
  validator can then reject on the declared name.

**The buy makes this more likely, not less.** FastMCP Tool Transformation ships
`ArgTransform(name, description, default, hide, required, type)` and `Tool.from_tool()` —
`hide` is precisely this operation, promoted to a first-class, documented feature. Buying
P4 buys a component whose headline capability the design's core invariant cannot describe.

**Required:** extend §0.1 to range over *(declaration, projection)*, or forbid wire-time
contract rewriting outright and move ambient-argument injection to execution time where
C-5 already governs it. Not both silently.

---

### S5-5 · Two hosts assembling from the same manifest 🔴 D: PARTIAL · B: NO (Python-only)

**Today there are three, not two.** chat-service Python (`tool_discovery.py`), ai-gateway
TypeScript (`find-tools.ts`), and mcp-public-gateway (`scope-filter.ts` + `tool-policy.ts`,
170 policy entries, third-party keys). **Nine** separate comments instruct *"keep in
lockstep."* Audit §5.5 verified four live divergences:

| concern | Python | TypeScript |
|---|---|---|
| `plan` group description | 9-line sequencing directive | one line of names |
| CD4 liveness gate in `visible_tools` | present, hides `executes:false` | **absent** |
| `tool_list` exclude set | `ALWAYS_ON_CORE_NAMES` | `new Set()` |
| `include_deprecated` executed default | `True` | `false` |

No test compares the two `GROUP_DIRECTORY` objects. The one drift test that exists points
at the wrong handler and is green while the defect it names is live (audit §5.1).

**The design gap.** M1/M2 make the manifest the sole catalog input **to the assembler**
(singular). §0.2 says P4 answers *"what is on the wire, from exactly one input."* The
design never states how many P4 implementations exist or in what languages. And here is the
structural point: **the manifest freezes the CATALOG; it does not freeze the ASSEMBLY
POLICY.** Budget order, hot domains, tier gates, suppression modes are *code*. Two fully
M1–M5-conformant hosts can advertise different sets from a byte-identical manifest, and
M2's import-graph gate is per-repo, per-language, and cannot span the seam.

**The buy makes it worse, and this is a direct buy-decision flag.** Pydantic AI is Python.
Two of the three hosts are TypeScript/Nest. "Buy P4" delivers **one of three** assemblers,
and converts the other two from *re-implementing our rules* into *re-implementing a third
party's semantics* — including undocumented ones (ordering, S5-9). The 2026-07-23 outage
lesson is already absent from the TS twin (no CD4 gate); this widens that class.

**Required:** either declare exactly one assembler and make the others thin relays over it
(the public gateway's scope filter is then a P6 concern, not a second P4), or put the
narrowing **policy** in the manifest as data so all hosts read it rather than encode it.

---

### S5-6 · A declaration is admitted but its service is DOWN 🔴 D: NO · B: WORSE THAN TODAY

**Today: the best-covered case in the repo.** `provider_availability()` →
`_stamp_incomplete()` marks a listing `incomplete: true` with an explicit instruction —
*"do NOT conclude the capability doesn't exist, and do NOT substitute an unrelated tool"*
(`tool_discovery.py:943-969`). `tool_load` answers `provider_unavailable`, not `not_found`.
CD4 adds a third state: a proven-broken tool is hidden from `tool_list` but reported by
`tool_load` with a reason — *"a broken tool is WORSE than an absent one: the model spends a
turn calling it, gets an error, and often reports success anyway"* (`:901-908`).

**The design gap.** §0.1 has three sets. A down service is *admitted, withheld,
reason=outage* — the vocabulary technically stretches. But §0.3's binding rule, *"the
withheld thing must remain reachable on request,"* is **false** for an outage: it is not
reachable, and telling the model to retry later is the correct behaviour. So the design's
one rule about withheld does not hold for the one withholding cause that is certain to
occur weekly. C-9 `honest scope` is the nearest clause and it governs a declaration's
*claim*, not the runtime's *completeness assertion*.

**A production lesson already paid for is not in the new contract.** That is a regression
risk, not an omission.

**The buy, verified: strictly worse than what we have.** `MCPToolset` *"requires an MCP
server to be running and accepting HTTP connections before running the agent, and running
the server is not managed by Pydantic AI."* Transport failures are explicitly excluded from
the tool-result channel: *"Protocol and transport errors are not reported as completed
failed tool calls."* `tool_error_behavior` governs execution, not listing. There is **no**
"exists but temporarily unavailable" advertisement. The nearest primitive is
`ExternalToolset` (a frozen list of host-supplied `ToolDefinition`s) — i.e. we build the
degraded surface ourselves anyway.

**Required:** a fourth state, `unreachable` — advertised-as-existing, not callable, with a
retry horizon — and a hard rule that **non-existence may be asserted only against a
complete manifest view.**

---

### S5-7 · Narrowing a synonym pair silently rewrites intent 🔴 D: NO · B: NO

Not on the original list. It is the measured root cause of the longest-running assembly bug
in the repo, and it breaks §0.1 at the level of meaning rather than the level of sets.

**Today.** The budget kept `glossary_propose_entity_edit` and dropped
`glossary_propose_entities`; the model *"mapped the create intent onto the similarly-named
edit tool, every turn"* (`tool_surface.py:444-456`). Same shape in
`merge_activated_tools`'s eviction loop: the create tool was evicted, *"the model fell back
to the always-visible edit tool whose error said 'tool_load it' — and the cycle repeated,
forever, with the agent never able to create an entity"* (`:625-633`). And audit §5.1: the
chat agent's default `tool_list` is **>50% deprecated names**, each labelled with a
`superseded_by` it must reason past.

**The design gap.** *"The runtime may NARROW the surface. It may never INVENT."* That holds
over the **set**. It does not hold over the **semantics**: removing one of two adjacent
declarations does not leave the survivor unchanged — it makes the survivor the best
available match for an intent it does not serve. A subset operation on the set is a
**meaning-changing** operation on the surface. §0.1 has no clause for it, and no
registration of a withheld tool would have surfaced it: the withheld row would read
`glossary_propose_entities · budget · token-ceiling`, which is true and does not say *"and
the model will now use the edit tool instead."*

**Required:** narrowing must be closed over declared adjacency — a declaration may not be
withheld while a near-neighbour it is confusable with remains advertised. This needs a
manifest edge (`confusable_with`, or derive it from `group` + verb), and it is cheap. It is
also an **enabler**: it removes a lie, exactly like C-5.

---

### S5-8 · The model cannot tell which constraint bound it 🟠 D: PARTIAL · B: NO

Eighteen filters; thirteen silent; the most frequent one (B1, the token budget) has *"no
counter, no SSE field, and no log line."* §5.2 fixes the **recording**. It does not give the
model a way to ask *"why is X not here"* — see S5-2. Ranked separately because the fix is
different: S5-2 needs an answer channel, this needs the *stage* taxonomy (`budget` /
`permission` / `liveness` / `intent-gate` / `pin`) to be a closed enum shared by every host,
or the withheld register degrades to free-text within a release. Memory:
*"a freeform contract schema is the root cause of a FE/BE shape drift."*

---

### S5-9 · Ordering and position 🔴 D: SILENT · B: UNVERIFIED (no guarantee)

**Today, and this is a live defect the design has no field for.**
`_advertise_discovery_tools` ends with:

```python
for name in active_tool_names:      # stream_service.py:1381
```

`active_tool_names: set[str]` (`:1299`, initialised `:1856`), **never sorted**. Python
string hashing is per-process randomised, and set iteration order additionally shifts as the
set grows and rehashes. So the advertised array's order is non-deterministic **across
process restarts** and **as tools are added within a turn** — for an identical tool *set*.

Someone knew position matters: `ALWAYS_ON_CORE_NAMES` is an ordered tuple and the comment
says the discovery pair is *"advertised as core and FIRST"* (`tool_discovery.py:180-181`).
The ordering discipline stops at the core and the tail is a set.

The cost is not cosmetic. RT3 F9: the request order is `tools` → `system` → `messages`, and
Anthropic caches the **cumulative prefix**, so *"a mode toggle on turn 12 invalidates BP1
and BP2 as well as the entire message history"* — measured **+65% uncached, 1/6 hit-rate**.
A reorder alone, with the set unchanged, buys that.

**Design:** silent. §5.1 records `advertised_tools` and never says the record is ordered or
that order is part of the surface.

**Buy:** UNVERIFIED — no documented ordering API or stability guarantee in Pydantic AI or
FastMCP. `CombinedToolset` order is an implementation detail; `prepare_tools` returns a list
you *may* reorder, but nothing states the list order survives to the wire.
`ToolDefinition.sequential` is about execution, not array position. **The buy cannot fix
this and cannot be relied on to preserve a fix.**

**Required:** total order declared and stable (core-first, then manifest order), and
`advertised_tools` recorded as a **sequence**.

---

### S5-10 · The surface must change mid-turn 🟠 D: CONTRADICTS ITSELF · B: SUPPORTED (silently expensive)

**Today it changes constantly, per pass, all silently:** F18 drops `tool_list` after 5 calls
(B12), one-shot de-advertise (B9, default mode `session`), the rail action-space gate (B10,
default `done_suppress`), the repeated-failure breaker (B11), and every `tool_load`.

**The design contradicts itself by one level.** §0.1: advertised changes *"per turn,
freely."* §5.1: record `advertised_tools` *"with `tool_choice` and pass number"* — i.e. per
**pass**. Whether intra-turn mutation is permitted is left to the reader, and RT3 F10
explicitly asked for the acceptance criterion to be written **as a rate** (tool-block
changes per 100 turns) rather than a boolean. `ARCHITECTURE.md` did not adopt it.

**Buy:** SUPPORTED and re-evaluated per step — `prepare` *"is called at each step of a run
… or omit the tool completely from that step"*; `prepare_tools` likewise, per step, applied
after per-tool `prepare`. On caching: **no warning**. The only signal is that the *native*
`ToolSearch` path claims prompt-cache alignment by shipping deferred tools on the wire and
letting the provider reveal them; **no guidance for the local `search_tools` path**, which
is what a non-Anthropic/OpenAI model gets. So the component happily rebuilds the array every
step at full cache cost and never says so.

**Required:** a stated mutation policy plus a per-turn mutation budget, recorded — and the
rate as the acceptance criterion, per RT3 F10.

---

### S5-11 · The same session switches book / project / mode 🔴 D: NO · B: N/A

**Today.** `chat_sessions.activated_tools TEXT[]` (`migrate.py:519-520`) is **session-level
with no book scoping**, while `book_bound` is per-turn (`stream_service.py:2107`) and
`permission_mode` is per-turn behind a one-key cycle. So a session re-scoped to a different
book carries the previous book's activated set, and every `ambient_book` tool's schema is
rewritten across the switch (S5-4) — RT3 F8 calls axis 2 *"not a set change but a schema
rewrite … book-bound and unbound blocks share no bytes."*

**The design gap, and it is the dangerous one.** §0.1 permits per-turn advertised change and
never defines the **scope key** of runtime state. But §0.4 introduces a second, much more
consequential piece of per-session runtime state: **the plan**, carrying `emits` bindings.
The design nowhere says what happens to a live plan when the book, project or mode changes
underneath it.

Follow C-6 through: the executor may *"satisfy a binding directly instead of asking the
model to retype a UUID."* A plan built against book A, surviving a switch to book B, binds
A's `chapter_id` into a call now executing against B — **without the model in the loop**. It
is a **C-5 wrong-object write produced by the C-6 mechanism**, and §5.5's wrong-object
counter is the only thing that would ever see it. §2 records the same class already:
`noop_write_counts` fired 263×, and the memory *"failure disguised as success"* is the worst
shape precisely because no `ok=false` autopsy reaches it.

**Required:** every piece of per-turn runtime state — advertised set, activated set, and
**the plan** — carries its scope key, and a scope change invalidates bindings rather than
re-binding them. This is a §0.4/§0.5 clause, not a P4 detail, but P4 is where it becomes
observable.

---

### S5-12 · A user-curated pin conflicts with what the plan needs 🟠 D: NO · B: N/A

**Today there is no conflict, because every producer is a union.** Curated pins ∪ activated
(`tool_surface.py:608`); rail step tools union unconditionally in both modes (`:402`);
skill-named tools union budget-exempt (`:457`); `pinned_legacy` *"bypasses everything"*
(`:459-463`). So a pin never actually restricts, and the user's mental model — *"I chose
these tools"* — is false. Separately, **B14**: a curated pin naming a tool absent from the
catalog is silently dropped, with no validation at the write path either
(`sessions.py:349`).

**The design gap.** A user pin is a **narrowing authored by a human**. §0.3 exempts exactly
one thing from *visible and appealable*: P6 permission. A curated pin is not P6, is not
visible to the model, is not appealable by it — and the design does not classify it. Nor is
there a precedence rule between a pin and a plan step; both are legitimate and the design
has one word ("advertised") for the output of both.

**Required:** classify human-authored narrowing (I read §0.3 as implying it is a legitimate
ceiling, like P6 — but say so), state precedence (a plan step should widen past a pin, since
widening is an enabler), and validate pins closed-set at the write path.

---

### S5-13 · The withheld set is huge — communicating "you can ask" 🟠 D: NO · B: SUPPORTED, by the mechanism we already retired

**Today.** `group_directory_text()` (`tool_discovery.py:507-511`) injects ~15 one-line
entries, *"≈300-500 tokens total, vs ~24K for a hot-seeded domain"* — a genuinely good
answer. It also **lies twice**: audit §5.2 shows `tool_list(category="research")` returns
*"no tools currently available in this category"* for `web_search`, which is on the model's
wire and named in the directory text in the same prompt; `meta` has the identical shape,
both caused by the production call site passing `exclude=ALWAYS_ON_CORE_NAMES`.

**The design gap.** §0.1 requires withholding be **registered**; nothing requires the
*existence* of the withheld space be communicated at all (S5-2). And BUILD-VS-BUY §4.1
**withdrew** the hierarchical group tree — *"Flat index, no depth"*, on a measured
0.9126 → 0.6398 collapse — removing the design's only candidate answer for
scale-to-thousands and putting nothing in its place.

**Buy: SUPPORTED, and this is the buy's best result — with a barb.** `DeferredLoadingToolset`
+ the `ToolSearch` capability is upstream's hot-set/lazy-tail: native on Anthropic (BM25/
regex) and OpenAI Responses, local `search_tools` elsewhere. It is a direct analogue of
`tool_list`/`tool_load`, which means **our own version is duplicated effort** and should be
retired in its favour. The barb: the local fallback is **semantic top-K**, and F17 retired
`find_tools` for exactly that — *"it is semantic top-K, so it structurally CANNOT surface a
tool the agent needs when that tool falls outside the K matches (dogfood F14: the agent
never reached `book_list_chapters`)"* (`tool_discovery.py:283-289`). The buy's answer to
S5-13 is the mechanism this repo measured and abandoned, for every model that is not
Anthropic or OpenAI Responses — i.e. **the local-first target** (memory: *"Local LLM is
target, cloud is fallback only"*). BUILD-VS-BUY §4.3's own caution applies: the disclosure
gains were *"absent on Chinese"*, and this is a CJK product.

**Required:** if `ToolSearch` is adopted, the deterministic complete-enumeration path
(`tool_list`-equivalent) must be kept alongside it for the local path, not replaced by it.

---

### S5-14 · The manifest is cached, so "only a deploy" is false 🟠 D: NO · B: N/A

§0.1: *"admitted — changes **only by deploy**."* The runtime's **view** of the manifest is
cached with at least four different lifetimes: tool catalog 60 s per user
(`knowledge_client.py:557-624`), embedding vectors 60 s, `_skill_prompt_named_tokens`
`@lru_cache(maxsize=64)` **with no TTL, never invalidated** (`tool_surface.py:527`), admin
catalog **cached for process lifetime** (`knowledge_client.py:643-645`), and ai-gateway's
federated list cached until restart — a standing project lesson (*"restart to re-federate a
tool desc/synonym change"*). A deploy that admits a declaration does not admit it for
minutes, unevenly, across hosts, and one path never until restart. **The design has no
statement of manifest freshness or propagation**, and this is the mechanism by which its
foundational sentence becomes false in production. Ranked mid because it is cheap to fix
(version the manifest, refuse to assemble from a version older than the deployed one) and
loud when it breaks.

---

### S5-15 · The empty surface — Brick 1 🟠 D: ASSERTED, NOT MECHANISED

§8, brick 1: *"the runtime itself, zero tools … the surface is empty and the agent says so
honestly."* Today the empty-surface path is:

```python
else:
    # Ask mode filtered everything out — run the pass tool-free
    offered_tools = False        # stream_service.py:2215-2218
```

An empty array 400s on some providers, so the pass silently becomes tool-free with **no
statement to the model** that a surface existed and was emptied. Brick 1 is the design's
first and most load-bearing test, and it asserts a behaviour for which no mechanism is
named. It is also the cheapest place to build the S5-2 answer channel, since with zero
tools the channel is the *entire* output of P4.

---

### S5-16 · Assembly is re-entrant (subagents) 🟡 D: NO

`subagent_depth == 0` gates `conversation_search`, `chat_search_sessions` and
`run_subagent`; a nested run advertises its own scoped set, clamped read-only, and strips
`_meta` on a different branch (`stream_service.py:2119-2142`). So there is a fourth surface
with its own rules. §0.2 defines P4 as *"what reaches the model this turn"* — singular model,
singular turn. §5.1 keys the record by pass number, not by depth. The withheld register must
be keyed `(turn, depth, pass)` or a nested run's narrowing is recorded against its parent, or
not at all.

---

## 3 · Buy-decision verdict for P4

`BUILD-VS-BUY.md` §2 rates P4 **✅ BUY** — *"composable, swappable, filterable, works against
any MCP server, and its metadata channel is our `_meta`. We would be rebuilding this badly."*
§4.4: *"P4 stops being ours to design. R4's 'one explained tool surface' becomes **configure a
toolset and add the `excluded_by` reason channel**, not write an assembler."*

Verified against the real API, that sentence is right about the assembler and wrong about the
weight of the clause it puts in a subordinate phrase.

| what the buy gives us | verdict |
|---|---|
| per-step filtering | ✅ `FilteredToolset` / `prepare_tools` / `PrepareTools` |
| mid-run mutation | ✅ per model step, `prepare` then `prepare_tools` |
| progressive disclosure with reachability | ✅ `DeferredLoadingToolset` + `ToolSearch` — **retires our `tool_list`/`tool_load`**, with the local-path caveat in S5-13 |
| host-side metadata not sent to the model | ✅ `ToolDefinition.metadata`, `SetMetadataToolset` / `.with_metadata()` — genuinely our `_meta`. (Note FastMCP's `meta` **does** cross the wire; our `strip_tool_meta` discipline still applies on that side) |
| permission / HITL | ✅ `ApprovalRequiredToolset`, `requires_approval`, `DeferredToolRequests` / `DeferredToolResults`, `HandleDeferredToolCalls`. Maps onto P6 **and** onto §0.5's *"asking the user is a SUCCESS state"* — the missing *reason to enter* `awaiting_input` |
| arg-level contract rewriting | ✅ `ArgTransform(hide=…)`, `Tool.from_tool()` — supported, and **that is the problem** (S5-4) |

**What the buy does not give us — the five to own:**

| # | gap | why it is ours |
|---|---|---|
| 1 | **exclusion-reason channel** (S5-2, S5-8) | NOT SUPPORTED either side. `excluded_by` is not a small addendum to a configuration — it is the whole of §0.1, and the component is silent by construction |
| 2 | **filter-vs-defer discipline** (S5-1) | both exist, one method call apart, one is a ceiling. The design must mandate the enabler and gate it |
| 3 | **plan→advertised widening** (S5-3) | nothing in the library knows what a plan is; M5 only reaches *admitted* |
| 4 | **down-service state** (S5-6) | the component is **worse than today's repo**: no "exists but unavailable", transport errors excluded from the result channel, server lifecycle not managed |
| 5 | **ordering + multi-host agreement** (S5-9, S5-5) | no documented order guarantee; Python-only, and two of our three assemblers are TypeScript |

**The honest restatement of the buy decision:**

> Buy the toolset **plumbing** — composition, per-step preparation, deferral, metadata,
> approval. It is real, it is better than ours, and `DeferredLoadingToolset` + `ToolSearch`
> retires code we are still maintaining. But P4's *invariant* — narrow, never invent, never
> silently, and the withheld thing stays reachable — **is not in the box.** The component
> will filter silently, in whichever of two directions the caller picks, at whatever cache
> cost, in whatever order. Every property §0.1 exists to guarantee is a property we still
> build on top, and "buy P4" must not be read as "P4 is handled."

---

## 4 · Ceiling Test summary (§0.3)

| situation | enabler / ceiling | note |
|---|---|---|
| S5-1 withheld reachability | **ceiling if implemented as filtering** | B4 ships a live ceiling today; the design has no gate |
| S5-2 withheld vs never-existed | ceiling | an unappealable bound; §0.3's own words |
| S5-3 plan widening | **enabler** | widening only. Costs nothing; deletes three heuristics |
| S5-4 contract rewrite | ceiling **and unregistrable** | narrows the action space *inside* a declaration |
| S5-6 down service | ceiling | the model cannot distinguish absent from broken |
| S5-7 synonym narrowing | ceiling, **invisible to the withheld register** | removes a lie ⇒ closing it is an enabler, like C-5 |
| S5-9 ordering | neutral to the model, **expensive to the cache** | a correctness-adjacent cost |
| S5-11 scope switch | **correctness bug**, not a ceiling | C-6 auto-binding produces a C-5 wrong object |
| S5-12 curated pin | ceiling, **unclassified** | the only human-authored narrowing; §0.3 exempts only P6 |
| S5-13 scale communication | enabler | provided the deterministic path survives alongside top-K |

---

## 5 · The one-line answer to each question

1. **What does assembly exist to solve?** Sixteen producers and eighteen suppressors, thirteen
   silent, with no single place able to report why a tool the model can name is not on the wire —
   and a surface that then asserts it is complete.
2. **What will certainly occur that assembly has no defined answer for?** S5-3 (a plan naming an
   unadvertised declaration), S5-1 (no mechanism behind *defer, never delete*), S5-4 (a per-turn
   contract rewrite the core invariant cannot express), S5-5 (three assemblers, one manifest, no
   shared policy), S5-6 (a down service, where the bought component is worse than what we have) —
   and S5-11, where a live plan surviving a book switch turns C-6's carry-forward into a C-5
   wrong-object write with the model out of the loop.
