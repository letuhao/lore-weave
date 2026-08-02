# Tool Reachability has no SSOT — four mechanisms, none authoritative

**Status:** proposed · **Origin:** the Mị Đế dogfood, 2026-08-02/03 · **Owner:** unassigned

## The observation

A user asked the co-writer to plan Arc 1 of their novel. It produced 6948 characters of a good
plan, `finish_reason=stop`, **zero tool calls**, and the book gained nothing. Repeated across a
new session; same result. The user's read was right on the first guess:

> *"sau nhiều lần chỉnh sửa nhưng không define SSOT code nên nó bị phân mảnh quá nhiều"*

Four independent mechanisms decide whether a tool the model is told to call is actually on the
wire. Each was individually defensible. **No one of them is authoritative, none knows about the
others, and the request fell through all four.**

## The four mechanisms

| # | Mechanism | Where | Decides |
|---|---|---|---|
| 1 | `SkillDef.hot_domains` | `chat-service/app/services/skill_registry.py` | seed a whole domain hot |
| 2 | named-tools union (`D-SKILL-NAMED-TOOLS-RIDE`) | `tool_surface._skill_prompt_named_tokens` | put tools a prompt NAMES on the wire, budget-exempt |
| 3 | rail action gate (`RAIL_ACTION_GATE_MODE`) | `loreweave_agent_control.rail.rail_gate_suppressions` | REMOVE a finished rail step's tool |
| 4 | intent router | `chat-service/app/services/skill_router.py` | add a SKILL by embedding similarity |

And a fifth actor that is not a reachability mechanism but behaves like one: a tool may accept a
call, do nothing useful, and report success (§4 below).

## What each one got wrong, and why none of them caught it

**1 · The hot-domain lint has an exemption that the runtime does not mirror.**
`co_write` sits in `_EXEMPT_SKILL_CODES` (`tests/test_skill_registry.py`) on the stated grounds
that it "keeps its tools LAZY". Fine as a seeding decision. But the exemption silenced the only
test that reads the prose for directly-named tools — and the prose names
`plan_propose_spec(book_id, source_markdown, mode)` with a full signature, which is a call claim,
not a discovery hint.

**2 · The runtime union could not see the form the prose used.**
The extractor was `` re.findall(r"`([a-z][a-z0-9_]{3,})`") `` — the closing backtick had to sit
immediately after the name. Every tool written bare (`` `composition_package_tree` ``) rode;
every tool written as a call (`` `plan_propose_spec(book_id, …)` ``) did not. The test-time lint
used a *different* regex (`\b[a-z]+(?:_[a-z0-9]+)+\b`) which DID see them — so the two guards
disagreed about what the prose says, and the intersection of their blind spots was exactly the
two tools that materialise a plan.

Blast radius once fixed: **36 tools across 7 skills** had been named-but-unreachable — `plan_forge`
+10, `translation` +10, `composition` +6, `settings` +6, `co_write` +2, `book`/`jobs` +1.

**3 · The action gate keyed on durable state to answer a conversational question.**
`vision-to-book`'s `arc-plan` step is `{"tool":"plan_propose_spec","done_when":"plan > 0"}`. That
predicate reads BOOK state, so a plan proposed on 2026-07-29 made the step done **forever, in
every session** — and `done_suppress` drops a done step's tool. The author could never plan a
second arc. The gate's own docstring says it exists to kill *"the intra-turn repeat loop"*; it was
fed a signal with no turn, session, or recency in it.

The seeds had also drifted against each other, because nothing compared them:

```
glossary_propose_entities / "cast > 0"     save            no repeat
glossary_propose_entities / "cast > 0"     save-cast       repeat ✓
kg_add_nodes / "connections > 0"           place-cast      no repeat
kg_add_nodes / "connections > 0"           connect-people  repeat ✓
plan_propose_spec / "plan > 0"             arc-plan        no repeat
plan_propose_spec / "plan > 0"             plan            no repeat
```

Whether an author could save a second batch of characters depended on which rail the router
pinned.

**4 · The one semantic mechanism cannot reach tools at all.**
`surface_hot_domains()` calls the SYNCHRONOUS `resolve_skills_to_inject` — the DEFAULT skill set.
So a skill the intent router adds contributes its prompt and **never its `hot_domains`**. Verified
by running it: `router-aware? False`. (After fix #2 a router-added skill's *named* tools do ride,
because `injected_skill_codes` is router-aware; the `hot_domains` half remains inert.)

**5 · And the tool accepted an empty result as success.**
`plan_propose_spec(mode="rules")` is a literal heading matcher. Given a well-formed outline headed
`# Arc 1: …` instead of the required `# 1. Arc Overview`, it created a run, wrote a spec with
**0 arcs**, and returned `run_id` + run detail with nothing to distinguish it from a plan that
worked. `validate.py` knew (`spec_has_arc` → *"no arcs parsed"*) but that verdict lives behind a
different tool. This had happened before: a sibling test records that rules-mode read **6 of 17**
live planning documents as nothing, including the author's own — and the response was to change
the default to `llm`, which helps only when nobody names a mode. Today the model named it.

## Fixed now (2026-08-03)

- `_skill_prompt_named_tokens` accepts the call-signature form; guarded by a new
  `test_every_tool_a_skill_names_is_REACHABLE_on_the_wire` that honours **no** exemption and asks
  the only question that matters — hot_domains **OR** named-union, by some mechanism.
- `StepProgress.session_done` split from `done`; `rail_gate_suppressions` suppresses on the
  session verdict, `resume` still uses the durable one. Book state informs, never disarms.
- `repeat: true` on the four drifted seed steps + `TestSchemaSQL_SameActionMeansTheSameThingInEveryRail`,
  which refuses to let one action mean two things across rails.
- `plan_propose_spec` returns `problem: "no_arcs_parsed"` + the exact required shape when a
  synchronous parse matched nothing.

All three guards were proven red-able against the real defect re-injected into real source
(NV-1), with the file restored and its sha256 re-checked.

## What is NOT fixed — the refactor this document exists to request

The four fixes above are correct and each is guarded. **They do not remove the fragmentation** —
they make four separate mechanisms individually less wrong. The refactor:

1. **One reachability function, one answer.** Today the question *"will the model see tool T this
   turn?"* has no single implementation; it is the composition of a hot-seed, a prose scrape, a
   gate subtraction, a budget truncation, and a set of pins, spread across `skill_registry`,
   `tool_discovery`, `tool_surface`, `stream_service`, and the ACP SDK. Extract a single
   `reachable_tools(surface, skills, rails, pins, budget) -> set[str]` with the mechanisms as
   named, ordered *contributors and subtractors*, and make every current site call it.

2. **A skill may not name a tool it cannot reach — enforced at ONE extractor.** Two regexes
   disagreeing about what a prompt says is the root of §2. The extractor belongs in the SDK, used
   by both runtime and lint, with the exemption list applying to *seeding strategy* only, never to
   *reachability*.

3. **Rail step semantics belong in the contract, not in each seed row.** `repeat` is currently a
   per-row boolean an author must remember. Derive it, or validate it against a per-ACTION
   declaration, so the same (tool, done_when) cannot mean two things. The guard added today
   detects the drift; a contract would prevent authoring it.

4. **Separate "the book has it" from "this chat did it" everywhere, not just in the gate.**
   The conflation fixed in `rail.py` is a *pattern*: any durable-state predicate used to decide a
   conversational affordance will misbehave across sessions. Audit the other consumers of
   `BookState`.

5. **A tool that produces nothing must not return success.** §5 is not a rail bug; it is the
   general `no silent seams` rule un-applied at a boundary. Sweep the synchronous MCP tools whose
   work can legitimately match zero and give each a post-condition.

## Provenance

Every claim above was verified on the running stack (deployed images, live chat session
`019f9f9b-6f0f-7ba4-bd85-f5db96953c63`, book `019f9f2d-f9f1-7037-ba78-8ccc3e19c956`), not read off
the source. The advertised tool-set went `activated=19` (no `plan_*`) → `38` (`plan_*` but not
`plan_propose_spec`, the gate still holding) → `46` (`plan_propose_spec` present), and the model's
behaviour went 0 tool calls → a hallucinated `run_id="arc_1_setup_001"` reaching for the tools it
could still see → a real `plan_propose_spec` call creating run `019fc463-d3ad-7b8e-935e-79652c829f5b`.
The hallucinated run id is worth keeping in mind: given a surface where the tools that CONSUME a
run id are visible and the one that MINTS it is not, inventing one is the reasonable move.
