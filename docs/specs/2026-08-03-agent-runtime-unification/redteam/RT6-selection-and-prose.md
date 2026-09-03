# RT6 — A1 (selection is a property of the SET) and A8 (anti-prose as a GATE)

**Mandate:** falsify, not grade. Assigned: **A1** (load-bearing) and **A8**.
**Method:** the POC record, the source, and the live `loreweave_chat` history (docker, read-only).

**Headline:**

> **A1 is proven for single-step lookup with a static set, and for nothing else.** Every arm that
> supports it (A/B/C/D/E) ran the *identical* single-step task. The spec's own multi-step evidence
> (§2.1's E2/E3) comes from an experiment **that has no `tools` parameter in it at all**. And in
> production, **2,408 of 4,010 tool failures (60%) occur on a tool that had already SUCCEEDED earlier
> in the same session** — the set demonstrably contained the answer.
>
> **A8's single 🟢 (the `co_write` incident) belongs to A1, not to A8.** The repo's own root-cause
> document says the tool was off the wire and the fix was reachability. A8 is left with one prompt on
> one model. A mechanical anti-prose detector already exists, fires **3 times in 2,176 traced
> messages**, argues instead of withholding, and is blind to the exact failure mode arm F produced.

---

## Part 1 — A1: *selection failure is a property of the SET, not of the model*

A1 as written (`DESIGN-HYPOTHESIS.md:44-52`):

> **Claim.** A weak model picks correctly whenever the correct tool is present and honestly described.
> **Falsifier.** A task where the correct tool *is* present, the set is ≤20, and the model still picks
> wrong at a material rate.

### RT6-A1-1 — The task family is a monoculture. Every supporting arm ran ONE single-step lookup.

| where | text |
|---|---|
| `poc/P1-P2-findings.md:777` | *"Two arms against the real target model … **same task: "List my books."**"* (arms A, B) |
| `poc/P1-P2-findings.md:853` | *"Five arms … **identical task — "List my books."** … temperature 0.2"* (arms A–E) |

**All five arms are the same request.** "List my books" is a **zero-argument, single-step lookup with
no ordering constraint and no state to carry forward.** It is the easiest shape a tool surface has.

A1's 🟡 caveat in the register says *"one model, one task family."* That is not strong enough. It is
**one task**, run five ways. The register then reports the result as if it settled selection in
general, and §2 (`DESIGN-HYPOTHESIS.md:160-174`) makes A1 the node the whole tree hangs from.

**Reproducibility gap:** `eval/` contains `glossary_build_poc.py` and `schema_recall_poc.py` only.
The `§4 · Reproduce` block (`poc/P1-P2-findings.md:1060-1077`) gives commands for **P1 and P2 only**.
**No script for arms A–G is committed anywhere in the repo.** The load-bearing evidence for the
load-bearing assumption exists as a markdown table and nothing else.

### RT6-A1-2 — 🔴 The spec's multi-step evidence is an experiment with NO TOOLS IN IT.

`SPEC.md:205-209` draws the boundary the entire two-lane architecture rests on:

> *"Choosing the right tool at the right point of a multi-step job whose steps feed each other is
> planning, and a weak model does not (measured: **E2 horizontal-naive collapsed monotonically 7→1
> attributes; E3 planner→executor produced 13 entities at 5.7 attrs**)."*

Source: `eval/glossary_build_poc.py`. The request builder is:

```python
# eval/glossary_build_poc.py:57-59
body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
        "temperature": 0.4, **NO_THINK}
```

**There is no `tools` key. There is no `tool_choice`. No tool is offered, selected, or called in E1,
E2, E3 or E4.** `e2_horizontal_naive()` (`:103-116`) asks for a **JSON array in the message content**;
`e3_planner_executor()` (`:119-146`) makes a planner call and then N executor calls, **all plain chat
completions**. What was measured is **attribute depth per entity in a generated JSON blob** — a
generation-quality result, correctly reported as such in
`docs/specs/2026-07-27-glossary-kg-build-workflows.md:96-97`.

**It is cited in this spec as evidence about tool selection. It contains no tool selection.**

Consequences:

- The claim *"discovery is not selection-under-ordering-constraints"* (`SPEC.md:205`) has **no
  measurement behind its second half** anywhere in this corpus.
- §2.2's four-condition lane rule (`SPEC.md:216-221`) — which decides what migrates to the FSM lane —
  is justified by that citation.
- A1's scope ("one task family") is therefore **not narrowed by a known multi-step result**; the
  multi-step result does not exist. A1 is unqualified on the half that matters.

### RT6-A1-3 — 🔴 Arm F IS A1's stated falsifier, re-filed under A8 so neither assumption owns it.

`poc/P1-P2-findings.md:936-943`, the only genuinely multi-step tool experiment in the record:

| arm | surface | result |
|---|---|---|
| **F** | 16 tools (8 searches + 8 `run_*`), ~1,549 tokens, normal descriptions | ❌ **0/3** — fluent prose, `finish_reason: stop`, **no tool call** |
| **G** | same 16 tools + a hard anti-prose directive | ✅ 3/3 |

Match arm F against A1's falsifier clause word for word:

| A1 falsifier condition | arm F |
|---|---|
| the correct tool *is* present | ✅ `run_world_setup` present |
| honestly described | ✅ *"describes the tools normally"* |
| the set is ≤20 | ✅ **16** |
| the model still picks wrong at a material rate | ✅ **0/3 — a 100% rate** |

**Arm F satisfies A1's falsifier on all four clauses.** The design escapes by classifying "emitted no
call" as a *prose* failure (A8) rather than a *selection* failure (A1). That partition is not
defensible: from the surface's point of view, "chose nothing" and "chose wrong" are the same
observable — the job did not happen with the answer on the wire.

**And the partition is circular.** A1 is exonerated on multi-step by handing the counterexample to
A8; A8's only production evidence turns out to be a set problem (RT6-A8-1). Each assumption's escape
hatch is the other one.

Note also what arm G actually demonstrated: **one** call, `run_world_setup`, *"world chosen before
plot"* — a correct **first-step** choice. The remaining steps ran inside a sub-agent that does not
exist yet. **No arm anywhere observed the model select step *n+1* given step *n*'s output.**

### RT6-A1-4 — 🔴 Production: 60% of failures are on a tool that had ALREADY SUCCEEDED in that session.

Live query, `loreweave_chat.chat_messages.tool_calls`:

```
TOTAL_FAILS = 4010
FAILS_ON_A_TOOL_ALREADY_SUCCEEDED_EARLIER_SAME_SESSION = 2408   (60.0%)
```

A tool that succeeded at sequence *n* was, by construction, **on the wire, correctly named, correctly
described, and correctly argued** at sequence *n*. Its failure at sequence *m > n* cannot be a
property of the set — the set is *proven* to have contained the answer, by the model's own prior
success with it.

This is A1's falsifier at n=2,408 in real usage, not in a lab.

### RT6-A1-5 — 🔴 The killer trace: the model's own successful call returned the UUID, and it sent `'0'`.

Session `019faf5b-77b8-717f-9e1f-92fbda37fee5` (the Mị Đế dogfood session already cited in
`stream_service.py:970-975`). Ordered, from the live DB:

```
seq 12 | glossary_propose_entities   | ok=true
         result: {"results":[{"name":"Lâm Uyên","status":"created",
                  "entity_id":"019fafa2-1979-7b0e-af52-af1d1f092173"}, …]}
seq 12 | glossary_propose_entity_edit | ok=false
seq 14 | glossary_propose_entity_edit | ok=false
seq 16 | glossary_propose_entity_edit | ok=false
         error: entity_id must be a real UUID, got '0'
seq 16 | glossary_propose_entity_edit | ok=false   (identical repeat)
```

**Two messages after its own successful call handed it `019fafa2-1979-7b0e-af52-af1d1f092173`, the
model sent `entity_id: "0"`.** The identifier was not missing from the surface, not missing from the
catalog, and not missing from the context — **it was in the transcript, produced by the model itself.**

Same session, same turn boundary, the model also *changed* `book_id` from
`019faf5a-29a5-795a-a250-d0d5f3f69fc7` (seq 12, valid) to `019faf5a-2a1e-7a98-bc98-191f6618213e`
(seq 14) and back again (seq 16) — swapping one well-formed UUID for another between passes.

And at seq 34, with everything on the wire and working:

```
seq 34 | composition_get_work        | ok=true
seq 34 | composition_get_work        | ok=true
seq 34 | composition_get_work        | ok=false  "already called … with these exact arguments 3 times"   ×7
seq 34 | composition_get_outline_node| ok=true
seq 34 | composition_get_outline_node| ok=false  "already called … with these exact arguments"           ×11
```

**This wounds A1 and A3 together.** A3 claims text-in capabilities eliminate id-resolution failure
*by construction* because the caller never supplies an id. But the failure here is not *naming a tool
that needs an id* — it is **failing to carry a value that was already returned**. A coarse capability
surface still has capability→capability handoffs, and this trace says the handoff is where the model
breaks. A3's stated risk (`DESIGN-HYPOTHESIS.md:69-72` — *"the ambiguity was never in the interface,
it was in the request"*) understates it: here the ambiguity was in **neither**. There was no ambiguity.

### RT6-A1-6 — "74% byte-identical repeats" is not what a set-property theory predicts.

Measured over the whole corpus:

```
REPEATS (rn>1, same session+tool+args)                = 4921
REPEATS WHOSE FIRST IDENTICAL CALL SUCCEEDED          = 2353   (47.8%)
```

If selection failure were a property of the set, repeats should concentrate where the set lacks the
answer — the model gropes, fails, gropes again. **Nearly half of all repeats follow a call that
already returned the answer.** Nothing about the set changed and nothing about the result was
unhelpful; the model re-asked a question it had already had answered.

That is a **belief-update and termination** defect, in the model and in the loop — the class R16
addresses (`poc/P1-P2-findings.md:379-415`). A1 does not cover it, and the design's cut-the-loop table
(`DESIGN-HYPOTHESIS.md:26-32`) attributes zero of the four links to it.

### RT6-A1-7 — Honest ledger: where A1 still holds.

Checked the 12 sessions containing a failed `glossary_propose_entity_edit` (the 0/101 tool). In **7 of
12** there was **no prior successful call of any kind**; in the other 5 the priors were `tool_list`,
`tool_load`, `glossary_list_system_standards`, `composition_get_work` — **none of which returns an
entity id**. So for `glossary_propose_entity_edit` specifically, the producer usually **was** absent,
and **that half of P8 supports A1 and supports R17/G3.**

**A1 is right about the head of the chain and wrong about its generality.** Removing silent filtering
is necessary. It is not sufficient, and the design treats it as sufficient.

### A1 — verdict

| scope | verdict |
|---|---|
| single-step lookup, static set, one call | **SURVIVES** (arms A/C/D, 3/3, robust to 35 tools and 54% retired) |
| multi-step / ordered / state-carrying | **NOT PROVEN — and never tested.** §2.1's citation contains no tools |
| "selection failure is a property of the SET, **not of the model**" as stated | **WOUNDED, near-killed.** 2,408 production failures and 2,353 repeats occur with the answer proven present |

**Blast radius, per the design's own dependency graph (`DESIGN-HYPOTHESIS.md:160-174`): total.**
A2/A4/A11 all inherit "the model plans the multi-step job correctly once the set is honest," which is
the untested half.

---

## Part 2 — A8: *"call a tool, don't write prose" can be enforced as a GATE*

A8 as written (`DESIGN-HYPOTHESIS.md:111-118`): 🟡 0/3 → 3/3 with a directive; 🟢 *"the `co_write`
incident (6,948 characters, zero tool calls) is the production instance."* Open question **N3**:
*"what is the gate, as opposed to the hope?"*

### RT6-A8-1 — 🔴 The `co_write` incident is A1's evidence, double-counted. A8 has no 🟢.

The repo's own root-cause document, `docs/specs/2026-08-03-tool-reachability-ssot.md`:

- `:13-15` — *"**Four independent mechanisms decide whether a tool the model is told to call is
  actually on the wire.** … the request fell through all four."*
- `:31-36` — `co_write` sits in `_EXEMPT_SKILL_CODES` (`services/chat-service/tests/test_skill_registry.py:435`),
  which silenced the only test reading the prose for named tools.
- `:38-44` — the runtime extractor `` re.findall(r"`([a-z][a-z0-9_]{3,})`") `` matched bare names but
  **not** the call-signature form `` `plan_propose_spec(book_id, …)` `` that the prose actually used;
  the lint used a *different* regex that did see them. *"the intersection of their blind spots was
  exactly the two tools that materialise a plan."*
- `:46-47` — blast radius once fixed: **36 tools across 7 skills** were named-but-unreachable.
- `:135-140`, verified on the running stack: advertised went **19 → 38 → 46**, and behaviour went
  **0 tool calls → a hallucinated `run_id="arc_1_setup_001"` → a real `plan_propose_spec` call**.

**The tool was not on the wire. The model wrote prose because it had nothing to call.** That is
exactly arm E's mechanism — the right answer deleted from the set — and it is **A1's evidence.**

**The actual fix contained no anti-prose gate.** `:85-98` lists it: the extractor accepts the
call-signature form, `StepProgress.session_done` splits from `done`, `repeat: true` on four drifted
seeds, `plan_propose_spec` returns `problem: "no_arcs_parsed"`. All reachability and post-condition
work. **Did it hold?** For the reachability defect, yes — `test_every_tool_a_skill_names_is_REACHABLE_on_the_wire`
(`test_skill_registry.py:623-628`) honours **no** exemption. For prose-instead-of-action, there was
nothing to hold: no gate was built.

**A8's evidence therefore reduces to 🟡 alone — one prompt, one model, N=3, no adversarial variation,
no second model.** The register should be corrected; as written it lends A8 a production instance it
does not have, and lends it from A1.

### RT6-A8-2 — A mechanical detector already exists. It argues, it is capped at 1, and it fires 0.14% of the time.

`_narrated_uncalled_writes` (`services/chat-service/app/services/stream_service.py:934-954`) is a real,
mechanical prose-where-action-was-required detector — no NLP, three closed conditions: the token is a
**registered catalog tool**, its tier is a **write (A/W/S)**, and the turn **never attempted it**.
Fired at `stream_service.py:2570-2650`.

Its three defects are the three P2 already proved fatal:

1. **It argues.** The action is `working.append({"role": "user", "content": "[SYSTEM DIRECTIVE] …"})`
   (`:2645-2650`) — a message injected into the very context it is trying to break out of. P2:
   *"a guard withholds; it does not argue … A message cannot stop a model. Only an absent affordance
   can."* (`poc/P1-P2-findings.md:76-84`, `:111-113`).
2. **It is capped at one and then gives up.** `NARRATED_WRITE_NUDGE_CAP = 1` (`:925`), with the comment
   *"a cap above 1 would let it become the very loop it prevents"* — an honest admission that the
   mechanism is the same class as the breakers. **There is no terminal outcome.** If the model ignores
   the single nudge, the turn ends with the false claim intact and the author is sent to look at work
   that was never made (`:970-975`).
3. **It almost never fires.** Live telemetry: **3 fires across 2,176 messages carrying a trace
   (0.14%)** — against 12 tools at 0% success and documented hallucinated-success incidents.

### RT6-A8-3 — 🔴 The existing detector is blind to arm F's failure mode BY CONSTRUCTION.

The trigger requires a token that **matches a registered tool name** (`:952-954`). Arm F's observed
failure is *"answers in fluent prose, `finish_reason: stop`, no tool call"*
(`poc/P1-P2-findings.md:942`). A model that simply **writes the world-building plan itself** and never
types the string `run_world_setup` produces **zero** detector hits.

This is not a tuning gap; it is the structure of the failure. The narrated-write guard catches *"I
called X"* when X was not called. A coarse `run_*` surface fails as *"here is your world, in prose"* —
a claim about **the work**, not about **a tool**. **The one mechanical enforcement the repo owns
cannot see the failure A8 exists to suppress.**

### RT6-A8-4 — `tool_choice` IS plumbed end-to-end to the target model, and chat never uses it.

Traced in code, top to bottom:

| layer | file:line | state |
|---|---|---|
| Python SDK | `sdks/python/loreweave_llm/models.py:146` | `tool_choice: dict \| str \| None` — free-form |
| Rust SDK | `sdks/rust/loreweave_llm/src/models.rs:118, 190-195` | `with_tool_choice(json!(…))` |
| contract | `contracts/api/llm-gateway/v1/openapi.yaml:476-483` | declared |
| gateway handler | `internal/api/stream_handler.go:64, 412` | forwarded; `:251-255` 400s if the provider lacks support |
| OpenAI adapter | `internal/provider/adapters.go:1045-1046, 1068` | forwards |
| Ollama adapter | `adapters.go:1383-1384, 1395` | forwards |
| **LM Studio adapter** | **`adapters.go:1590-1596, 1611`** | **forwards — the target model's backend** |
| Anthropic adapter | `adapters.go:1184, 1251` | shape-converted |
| **chat-service** | **`stream_service.py:2145`** | **`request_kwargs["tool_choice"] = "auto"` — hardcoded** |
| chat-service final pass | `stream_service.py:433, 1759` | `"none"` to force termination |

**`"required"` appears nowhere in chat-service.** The transport supports it all the way to LM Studio;
the chat lane has simply never asked for it. That makes the cheapest A8 experiment on the board a
one-line change.

### RT6-A8-5 — 🔴 But `required` is not a gate either — the repo already recorded the model ignoring it.

`services/commit-service` is the one place that already does this, against the same class of local
backend:

```rust
// services/commit-service/src/llm_driver.rs:162-164
// "required": the model must call SOME tool but chooses which — that is
// the whole point of a bounded vocabulary (vs tilemap's forced single).
.with_tool_choice(json!("required"))
```

…and its own test suite names the outcome:

```rust
// services/commit-service/tests/dispatch.rs:113-124
/// Prose-only response (model ignored tool_choice) → NoToolCall reject.
async fn prose_only_response_rejects() { … finish_reason:"stop" … contains("no tool call") }
```

Its system prompt already carries the maximal directive — *"You MUST respond with exactly one tool
call chosen from the provided tools — no prose"* (`llm_driver.rs:118-119`) — **on top of**
`tool_choice: "required"`. **Belt, braces, and the test still exists**, because the model still does it.

So `required` is **advisory** on this stack: the OpenAI-compat backends forward the field, the local
model may decline, and the platform learns about it only after the fact. **A8's "gate" is not
available in the compel form.**

**What IS available — and it is already shipping in this repo.** commit-service's design:

```rust
// services/commit-service/src/llm_driver.rs:97-100
/// Failure is DATA here, never an `Err`: a reject/timeout resolves through
/// the fallback, and the incident is the metric.
```

Detect mechanically (`:219-231`: no call from the bounded vocabulary ⇒ `Reject::NoToolCall`), then
**complete the job deterministically without the model**, and **count it**. That is the only shape of
"gate" the evidence supports: not *the model must act*, but *when it does not, a deterministic path
finishes and the incident is a first-class number.*

For a `run_*` capability surface, that means every coarse capability needs a **non-LLM completion
path or an explicit user-visible refusal** — which is a substantially larger commitment than the spec
currently books, and it should be priced before shape 1+4 is chosen.

### A8 — verdict

**WOUNDED.** Enforceable only as **detect + deterministic fallback + count**, never as *compel*:

- its 🟢 belongs to A1 (RT6-A8-1) — the register must be corrected;
- the mechanical detector that exists argues, is capped at 1, never terminates, and fires 0.14% of the
  time (RT6-A8-2);
- that detector is structurally blind to the coarse-surface failure mode (RT6-A8-3);
- `tool_choice` reaches LM Studio but is pinned to `"auto"` in chat (RT6-A8-4);
- and `"required"` is advisory — the repo already ships a test for the model ignoring it (RT6-A8-5).

The design says *"the mitigation is cheap and it works — but it must be a gate, not a hope"*
(`poc/P1-P2-findings.md:950-951`). **On this stack the compel form of that gate does not exist.**
N3's honest answer is: the gate is the fallback, not the directive.

---

## Cheapest observations that settle these

| # | attacks | observation | cost |
|---|---|---|---|
| **O1** | **A1** | Re-run arms C/D/E with a **two-step, state-carrying** task where step 2 needs step 1's output (*"find my book with the most chapters, then rename its second chapter"*), correct tools present, set ≤20. A1 predicts 3/3. RT6-A1-5 predicts the id is dropped between calls. | ~1 h, LM Studio, free |
| **O2** | **A1, A3** | Replay session `019faf5b` seq 12→16 with **one** change: seed the successful `entity_id` verbatim into the next user message. If it still sends `'0'`, the defect is carry-forward, and **text-in capabilities do not fix it**. | ~30 min |
| **O3** | **A1** | Commit the arm A–G scripts to `eval/`, as `glossary_build_poc.py` is. Until then A1 is unreproducible. | ~1 h |
| **O4** | **spec §2.1** | Replace the E2/E3 citation. It has no `tools` parameter (`eval/glossary_build_poc.py:57-59`). Either cite a real tool experiment or mark §2.1's second half 🔴. | 5 min, doc-only |
| **O5** | **A8** | Flip `stream_service.py:2145` to `tool_choice="required"` behind a setting on a `run_*`-only surface and count `finish_reason=stop` with zero calls. Measures how advisory `required` is for gemma. | ~2 h |
| **O6** | **A8** | Extend `_narrated_uncalled_writes` with a **null-action** arm: a turn on a `run_*` surface whose user message matched an action intent and which emitted **no** tool call at all. Today's detector needs the model to name a tool; arm F never does. Then measure the fire rate against the 0.14% baseline. | ~4 h |
| **O7** | **A8** | For one coarse capability, write the deterministic fallback commit-service already has (`llm_driver.rs:97-100`) and price it. If it cannot be written, "prose instead of action" has no terminal outcome and A8 is false for that capability. | ~1 day |

## The cheaper rival this evidence supports

`DESIGN-HYPOTHESIS.md:192-194` invites an attack on the shapes. The measurements point at one:

**Delete `budget_names_by_tokens` from the advertise path, add `excluded_by`, and fix G3 — change
nothing structural.** That captures arm E (the silent deletion), P13 (`book_list` dropped at 970
tokens), and the head of P8's chain. It requires **no** new architecture, and it is the *only* part
of the causal chain the arms actually measured. The remaining 60% — failures on tools already proven
present — is untouched by **any** of the four shapes, because it is not a surface property at all.

**A surface refactor justified by A1 will not move the number A1 was measured against.**
