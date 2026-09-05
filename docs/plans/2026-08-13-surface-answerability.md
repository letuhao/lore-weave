# Surface answerability — the invariant behind a defect class that has now shipped twice

Reconciles: MCP Tool I/O Standard · MCP Tool `_meta` Completeness Law + Tool Liveness — answerability is the question those rows leave open: both say what a tool must DECLARE, and neither says that a declaration must match the sentence a person actually types. This proposal is that missing half, and it belongs beside them rather than as a third home.

**Status:** proposal
**Date:** 2026-08-13
**Evidence:** ledger `contracts/tool-deep-dive-ledger.json`, pilot run `scripts/toolloop/fe_runner.py`

---

## 1. The defect class

Twice now, the same failure has reached an author's book. Both times it was fixed by adding one
tool name to an allowlist, and both times the *invariant* went unstated — so it recurred.

**v1 — 2026-07-21**, in `tool_surface.py`'s own words:

> `book_update_details` … was never advertised, so **every model mis-routed "update the
> description" to `book_chapter_create`/`save_draft` — the tool it could actually see.**

**v2 — 2026-08-13**, measured 5/5 through the real FE path (`fe_runner.py`, 5 independent
sessions): asked *"Show me the outline I've planned for this book — what chapters and scenes are
in it?"*

- `composition_list_outline` (tier R) was **not advertised in any pass**;
- `composition_outline_node_edit` (tier **A**, a write) **was**, in every pass;
- the model used the write it could see, 2-3 times per turn;
- a standing approval from 2026-07-30 auto-executed it with no confirm card;
- **the store went from 7 outline nodes to 10** — three chapters created by a read question;
- and the reply reported that invented structure back as *"your current plan"*.

Same mechanism, worse blast radius: v1 substituted a write for a write, v2 substituted a **write
for a read**.

**The class:** *the model routes to the tool it can see.* The codebase already knows this — it is
written verbatim in the v1 comment — but treats it as a per-tool accident rather than a law.

## 2. Why the previous fixes could not hold

The advertised surface is assembled by several mechanisms, each locally correct, none accountable
for the result:

| mechanism | local goal | what it does to the surface |
|---|---|---|
| domain selection (skill `hot_domains`) | keep the prefix small | dropped **505** composition registrations as `domain_not_selected` |
| hot-seed budget | fit the most tools in 2000 tok | orders reads by *ascending schema size* — prefers peripheral over primary |
| `ALWAYS_HOT_WRITES` | rescue starved writes | 1986 of 2000 tokens on the editor surface |
| rail step pre-activation | let a weak model start a journey | put the outline **writes** on the wire |
| suppressors (repeat/failure/oneshot) | break loops | remove tools mid-turn |

Every one of them adds or removes tools. **Nothing checks that what comes out can answer the
question that went in.** An allowlist entry fixes one tool on one surface; the next tool starved by
the next mechanism is a new incident.

## 3. The invariant

> **A surface must be able to answer the request it is given.**
> If the user's words match a tool's own declared vocabulary, that tool is on the wire — whatever
> the budget, the domain selection, or the rail decided.

And its corollary, which is the read/write half:

> **No write without its read.** If a resource's write tool is advertised, that resource's primary
> read is advertised too.

Both are checkable against declarations the tools already carry, and both would have caught v1 and
v2 before either shipped.

## 4. Why this is enforceable today

`composition_list_outline` already declares:

```json
{"tier": "R", "scope": "book",
 "synonyms": ["outline", "scene graph", "story structure", "chapters", "beats", "list outline"]}
```

The question contained **outline**, **chapters** and **scenes**. The tool declared that it answers
this question and the surface ignored the declaration. v1 is identical: `book_update_details` was
the declared home for "update the description".

So the signal exists. What is missing is (a) one field to pair a read with its writes, and (b) a
place that is accountable for the result.

**Contract addition — one field.** Tools gain `_meta.resource`, the noun they act on, and the one
read that answers questions about it declares `_meta.primary: true`.

```json
composition_list_outline       {"tier":"R","resource":"outline","primary":true, …}
composition_outline_node_edit  {"tier":"A","resource":"outline", …}
book_read                      {"tier":"R","resource":"book","primary":true, …}
book_update_details            {"tier":"W","resource":"book", …}
```

Derived from the **declaration, never the name** — the repo already deleted a name-substring
classifier for exactly this reason (`CP-4.d`: *"`_is_read_tool` IS DELETED, NOT IMPROVED"*).

## 5. Where it is enforced

One place: `_advertise_discovery_tools`, the single advertise chokepoint. Every path to the wire
already funnels through it — pinned today by
`tests/test_discovery_core_survives_every_suppressor.py`, which asserts `suppress_names=` appears
exactly once in the service.

A final **coherence pass**, after all narrowing:

```
R1  answerability   for each tool whose _meta.synonyms match the turn's request text,
                    force it onto the wire (bounded: only the matched set)
R2  no-write-without-its-read
                    for each advertised tool with tier in {A,W,S} and _meta.resource = R,
                    force the primary read for R onto the wire
R3  report          every forcing is recorded, with which rule fired and what it overrode
```

R1 is per-turn, so its cost is bounded by what the user actually asked about — unlike an
allowlist, which spends the prefix on every turn forever. R2's cost is bounded by the writes
already present.

## 6. Defence in depth — two more layers that each would have stopped the damage alone

**Typed rails (R4).** "Show me the outline" pins `build-a-book` — a *construction* journey — and
that pin is what put the outline writes on the wire. Rails declare `mood: construct | inspect`,
and a request in the interrogative cannot pin a `construct` rail. This is a type rule, not a regex
patch to `build-a-book`'s patterns; patching the patterns leaves the next construction rail free
to swallow the next question.

**Scoped approvals (R5).** A standing approval is currently keyed `(user, tool)` and lives
forever. A two-week-old allow auto-executed a Tier-A write on a turn whose request was a read.
Key it `(user, tool, request-mood)` at minimum: a standing allow granted while building must not
fire on a turn that asked to look.

These are independent. R1/R2 stop the wrong surface; R4 stops the wrong journey; R5 stops the
write. Any one of them turns this incident into a non-event.

## 7. How it is held

- **Registry lint** — every `resource` has exactly one `primary: true` read; every write declares a
  `resource`. A tool that declares neither is a lint failure, not a silent gap.
- **Contract test** at the chokepoint — a matrix of surfaces × suppressor states asserting R1/R2
  hold in the *output*, which is the thing no current test looks at.
- **Acceptance gate** — `fe_runner.py` with a corpus of read-intent prompts, N repeats each,
  asserting **zero writes** and the expected read called. This is the net that would have caught
  both v1 and v2, and it is the only one of the three that exercises the real model. It is also
  the only honest one: the consumer is stochastic, so the gate is a distribution over repeats, not
  a single green run.

## 8. Order

1. **R5, scoped approvals** — smallest, and alone it prevents an unrequested write from landing.
2. **R1 answerability** — needs no contract change (synonyms already exist), and closes both
   recorded incidents.
3. **`_meta.resource` + lint, then R2** — the contract change; do it after R1 has proven the
   chokepoint is the right home.
4. **R4 typed rails** — largest, and the one that needs a product call on what "inspect" means for
   each existing rail.

## 9. What this costs, and what it risks

R1 grows the prefix only for tools the user's own words matched; on the measured turn that is one
tool (~380 tokens). R2 adds at most one read per advertised write.

The real risk is **synonym quality**: a tool with sloppy synonyms could force itself hot on
unrelated turns. That is a lint-able, measurable property — and it is strictly better than the
current state, where a tool with *perfect* synonyms is dropped anyway.

---

## R2 — the measurement, corrected twice (2026-08-14)

Batch 2 derived five tools in RUNBOOK order and `scengen.py` could not write a prompt for two of
them: `glossary_propose_new_attribute` and `glossary_list_ai_suggestions` declare no
`_meta.synonyms`. They were emitted with `needs_prompt` and listed rather than skipped — a tool
that quietly leaves a batch reads as a tool that passed.

**First hypothesis, refuted.** Both descriptions end "NOTE: superseded by …", and the catalogue
carries a `superseded_by` meta key on 62 tools. The obvious reading is that synonyms are omitted
deliberately, so the successor takes the routing. Measured against the live catalogue:

```
315 tools     87 declare no synonyms     62 marked superseded
of the 87 with no synonyms:  1 is superseded,  86 are not
superseded tools that DO declare synonyms:  61
```

So the deliberate-omission story is wrong: supersession and missing synonyms are almost disjoint.
61 of the 62 superseded tools still declare synonyms, and 86 tools are genuinely unaddressable by
the surfacing layer's synonym matching. They cluster hard — **glossary 41, kg 31**, which is 72 of
the 86 in two providers.

**What that means for R1.** R1's answerability pass matches a request against declared synonyms,
so it is blind to those 86 by construction: they can never be pulled onto the surface by what the
user said, only by domain selection or an allowlist. That is the same starvation shape as the two
shipped incidents, with a different cause — not "withheld by a budget" but "never addressable in
the first place".

**Why the fix is not "write 86 synonym lists".** That is the allowlist shape again: a hand-written
list per tool, correct on the day it is written, silently stale after the next rename, and with no
mechanism that notices. R2 remains a CONTRACT plus a LINT — a tool declares the resource it acts
on and whether it reads or writes it, the registry refuses a tool that declares neither synonyms
nor a resource, and the surfacing layer can then answer "which tool answers a question about X"
without anyone maintaining a phrasebook.

The two batch-2 tools get prompts written from their own DESCRIPTIONS in the meantime, marked
`prompt_source: description (no synonyms — R2)`, so the batch measures whether the missing
declaration actually costs reachability rather than assuming it.

### R2, resolved — the defect was not the missing synonyms

Batch 2 ran all five tools live, K=3, and **four of five were surfaced on 0 of 3 runs**. Three of
those four requests were then answered by an ADJACENT tool that wrote the wrong thing:

| asked for | surfaced | what happened instead |
|---|---|---|
| add a *cultivation realm* detail to the character type | 0/3 | created an **entity** (`glossary_propose_entities`), entities 3 → 4 |
| rename an outline chapter | 0/3 | one run renamed the **manuscript** chapter in `loreweave_book` |
| suggested entries awaiting review | 0/3 | nothing called; the question went unanswered |
| add *Factions* as a new category | 0/3 | `glossary_adopt_standards` adopted a whole genre pack — kinds 4 → 5, attributes 29 → 36, genres 1 → 3, kind_genres 4 → 13 |
| compile the plan | 3/3 | reached; `plan_run` created 3/3 |

**R1 is not the problem — it is load-bearing and it works.** Every tool R1 named reached the
surface on 3/3. `plan_compile` was the one tool R1 matched, and the one tool surfaced. The gap is
what R1 has to reason FROM.

Two distinct causes, and only the second is what the R2 section above predicted:

1. **The successor is out-declared by the tool it replaced.** "Rename the chapter … in my outline"
   matched `composition_outline_node_update`, which carries
   `superseded_by: composition_outline_node_edit`. The DEPRECATED tool owns the words a person
   types; the successor owns jargon and CREATE verbs. Swept: **59 of 62 supersession pairs orphan
   at least one phrasing.** `composition_write_prose` → `book_chapter_save_draft` loses "write
   prose" — the same request that in batch 1 reached `save_draft` and overwrote a chapter.

   Fixed at the answerability chokepoint (a match on a superseded tool also surfaces its
   successor — a union, never a redirect) plus
   [`scripts/lint_superseded_synonyms.py`](../../scripts/lint_superseded_synonyms.py) so the
   declarations converge and the next pair fails at build time.

2. **86 tools declare nothing to match on**, so R1 is blind to them by construction — and a
   further case, `glossary_ontology_upsert`, matched the *wrong* tools (`book_media_generate`,
   `book_read`). That is still open. It is the `_meta.resource` half of R2: a tool should declare
   the resource it acts on and whether it reads or writes it, so answerability has a second,
   structured axis when the prose list is absent or ambiguous.

---

## R2 CLOSED (2026-08-14) — declaration is the mechanism, and it does not cost the prefix

The declaration gap is closed on the release surface. Shippable tools that nothing a user types
could reach: **42 → 3**, and the three left (`propose_edit`, `tool_list`, `tool_load`) are the
gateway's own discovery/edit surface, always advertised by construction rather than by matching.

| service | declared | examples |
|---|---|---|
| knowledge | `story_search` + 5 memory + 20 kg | "where did i write", "what do i know about", "how are they connected" |
| glossary | 13 | "look up a character", "set up my story bible", "research this on the web" |
| glossary | `curation_list`, `ontology_upsert` | "suggested entries", "add a category" |

**The invariant, in one line:** a tool must declare the words a PERSON types, not the words the
schema or the feature uses. `glossary_ontology_upsert` declared "add a kind" — the column name —
while the author says "category"; `glossary_curation_list` declared "review inbox" while the
author says "suggested entries waiting for review". Both were surfaced 0/3 and both went to 3/3
once the user's words were declared.

**Why declaration rather than prompting.** Three prose interventions were built, deployed and
measured, and none moved `tool_list` off 0/3 — the model works from what is on the wire. The one
that reached the model demonstrably (book_note 166 → 293 tokens) changed which wrong tool it
called, not whether it discovered a right one.

**And it did not widen the surface**, which was the obvious risk of adding 39 declarations.
Measured against the live 315-tool catalogue over ten representative prompts:

```
chitchat ("how are you today?")   0 tools forced
max seen                          4   (ANSWERABLE_MAX is 8 — never at the ceiling)
mean                              1.7
```

So the pre-filter stays precise: the phrases are multi-word and specific, and the word-boundary
matcher stops short synonyms firing inside longer words ("cat" in "category", "art" in "start").

**What is still owed:** 59 of 86 supersession pairs orphan a phrasing — the runtime union covers
them on the surface, and `scripts/lint_superseded_synonyms.py --max-orphans` ratchets the
declarations toward agreement.
