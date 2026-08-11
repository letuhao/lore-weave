# TOOL-V2 LOOP — one tool, one full development cycle

**Status:** open 2026-08-10 · **SSOT for progress:** `contracts/agent-runtime-toolv2-ledger.json`,
written only through `scripts/toolv2-loop.py --record`.

**PO's definition, and it is the whole point:**

> *"1 loop hoàn chỉnh là 1 qui trình phát triển 1 tool v2 giống như mọi qui trình phát triển module
> khác, 1 tool được xem là 1 feature, không phải chỉ có chuyển qua là xong."*
>
> convert → **run and prove it** → failed ⇒ investigate and fix the architecture or the backend,
> across services if that is where the defect is → run again → **proven ends the iteration**;
> still broken ⇒ the tool is **skipped with a reason** and the loop moves to the next one.

---

## 🔴 The correction that produced this design, recorded because it was mine

I first scoped the loop as *"convert what already has evidence (84 tools) and record the other 235
as having no subject."* That treats **evidence as something only history can provide.** The loop
**makes** evidence — it runs the tool. A tool with no recorded traffic is therefore not out of
scope; it merely arrives without a free reproducer.

What survives from that measurement is the **order**, not the exclusion:

| population | tools | what it means for an iteration |
|---|---|---|
| called and **never** succeeded | **34** | a reproducer already exists in the corpus — the iteration starts at *investigate* |
| has recorded successes | 84 (12 admitted) | a shape can be verified against real results before anything is run |
| never called | 201 | the first invocation has to be **constructed** before anything can be proven |

---

## The six phases of one iteration

**1 · PICK** — `python scripts/toolv2-loop.py --next`. The queue is derived from the catalogue and
the live corpus, never typed. Take the top row; the reason is printed beside it.

**2 · INVESTIGATE** — before touching code. What does this tool actually fail on, measured on its
own recorded calls? Split the population; do not trust the aggregate. **This phase has produced
every real finding in CP-5**, and skipping it is how a member gets built for a subject that turns
out to be something else.

**3 · CONVERT** — author the contract against what phase 2 measured. Rules already paid for:

* the `output_contract` shape comes from the **union of every recorded success with a stated `n`**,
  never from the tool's description (measured: description-authored shapes were wrong **4 of 5**)
  and never from one sampled result (**two tools are polymorphic** and one sample named one arm as
  the whole contract);
* a member with no subject **is not written** (§7) — that rule has already withdrawn one spec row
  and one of my own questions;
* promote through `scripts/agentruntime-admit.py --promote`, which is the only path to `admitted`.

**4 · PROVE** — a real turn, real service, real boundary, on a **throwaway book**. Deploy first
(`docker compose build` + `--force-recreate`) and verify the contracts are byte-identical
in-container: **the manifest in the repo is not the manifest on the wire**, and that has caught a
silently-absent registry once already.

**5 · FIX** — if the run fails, the defect is fair game **wherever it lives**: chat-service, the
owning service, the gateway, or the contract itself. Cross-service is explicitly in scope. Re-run
phase 4 after the fix.

**6 · CONCLUDE** — exactly one of:

* `--state proven` — a live run succeeded, with the session id as evidence. **The iteration ends.**
* `--state blocked` — investigated, and it cannot be made to work now. The note must say **what was
  tried and what would unblock it**. The iteration also ends, honestly.

**A blocked tool is a finished iteration, never a silent skip.** The loop stops when every tool is
`proven` or `blocked` — not when every tool is converted.

---

## Rules this loop inherits, each already paid for

* **Every denominator from the SSOT or live data. Never typed** — including the queue.
* **Verify the deployed image matches source before diagnosing.** A stale image cost a full
  investigation once.
* **A content-creating live run uses a throwaway book.** Smoke debris in the dogfood book reads as
  a product bug later.
* **Run the whole suite before claiming green.** A `-k` subset hid 12 failures for a day.
* **Every new guard needs a falsifier that reds it**, or a recorded reason why no edit can.
* **A repair that emits parseable-but-wrong output needs a post-condition.** Disguised ≠ repaired.
* **Prose is not the lever.** Three separate defects had a correct, complete, actionable message and
  failed anyway (101 placeholder ids, 88 unknown kinds, 266 missing arguments). If the proposed fix
  is a better sentence, it is not a fix.

---

## Deferred questions — recorded when they block, cleared by evidence, never by guessing

A question that blocks the CURRENT tool does not stop the loop and does not get invented an answer.
It lands here with its evidence, and the loop moves on. These are revisited when the catalogue has
no remaining independently-executable work, or when new evidence makes one of them live.

### DQ-1 · An explicit JSON `null` for an OPTIONAL string is rejected before the handler runs

*Raised by:* iteration 1 (`glossary_propose_curation`, phase 2) · *Measured:* 2 calls / 1 session —
the tool's only genuine failures that are **not** the singular/plural conflation.

```
{"op":"status_change","status":"active","book_id":null,   "entity_ids":["019fea5a-…"]}
{"op":"status_change","status":"active","winner_id":null, "entity_ids":["019fea5a-…"]}
→ validating "arguments": … /properties/book_id: type: … has type "null", want "string"
```

Go's `json:"…,omitempty"` makes a field optional in the *struct*, but the generated JSON Schema
still says `type: "string"`, so the MCP SDK's validator refuses `null` before any of our code sees
it. Sending `null` for "I have no value" is an ordinary thing for a model to do, and `winner_id`
here is a field of a **different op** — the flat superset invites filling it in with a blank.

**The question, and it is a product/architecture call, not a lookup:** should every optional string
on the glossary MCP surface accept an explicit `null` (`type: ["string","null"]`)? That is a
schema-generator change across *every* glossary tool, and this runtime has already had one
whole-provider de-federation caused by a schema-type edit. **2 measured calls do not justify that
blast radius**, and no amount of local reasoning settles it — so it is recorded, not guessed.
*Would clear it:* a corpus sweep showing the pattern is broad, or an explicit decision to accept it.

### DQ-2 · Five glossary-service DB tests are red against the live `loreweave_glossary`

*Raised by:* iteration 1, phase 4 · *Confirmed **pre-existing** at HEAD `b334fe531`* by re-running
them in a detached worktree — they are not this iteration's regression, and the fix was not allowed
to hide behind them.

`TestTriggerStillFiresOnWatchedFields` (short_description / deleted_at / permanently_deleted_at),
`TestTriggerSkipsRecalcOnUpdatedAtOnly`, `TestK2aSearchVectorRefreshesOnDirectShortDescriptionWrite`,
`TestK3_AutoRegenOnDescriptionUpdate` — all "recalc did not fire", i.e. a **snapshot-recalc trigger
that is absent or disabled in that database**. Plus `TestSyncTool_AvailableApplyRoundTrip`
("fresh adopt: want 0 updates, got 3"), which is shared-state pollution: the test asserts a clean
adopt against a DB that already has three adoptable standards.

Whether these are a real trigger regression or environment drift is **not decidable from the test
output alone** — and this runtime has already spent a full investigation on host-env drift wearing
a code bug's clothes. *Would clear it:* comparing the trigger definitions in `loreweave_glossary`
against the migration chain.

### DQ-3 · `kg_propose_edge` cannot satisfy its own precondition, and INV-K1 says it may not

*Raised by:* iteration 2 · *Measured:* 2 calls / 2 sessions — the only genuine failures the tool
has, once the 14 human denials and 1 pending card are removed from its 17.

Both were refused `KG_ENDPOINT_NOT_NODE`: an edge whose endpoints are not yet graph nodes. The
message is already correct, complete, and names the remedy tool by name
(`kg_project_entities_to_nodes`) — so **a better sentence is not available as a fix**. One of the
two sessions did then call the projection successfully and **never retried the edge**; the other
never projected at all.

The obvious repair — have `kg_propose_edge` project the missing endpoints itself — is **forbidden
by INV-K1**: this tool must never write Neo4j, which is why it parks a proposal for a human instead.
Its own source says so at the precheck (*"This READS Neo4j … the write stays human-gated"*).

**The question:** is a two-call round trip the intended cost of INV-K1, or should the runtime chain
the projection on `KG_ENDPOINT_NOT_NODE`? Chaining is a mechanism built for a 2-call population,
which §7 says is not a subject; weakening INV-K1 is a safety decision that is not mine.
*Would clear it:* traffic after the tool is actually reachable — the corpus cannot say how often
this bites, because the tool has never been permitted to run.

### DQ-4 · A resumed turn OVERWRITES its own first pass's tool calls

*Raised by:* iteration 3 · *Observed directly*, not inferred: session
`019fec80-…-e004` held three rows at `sequence_num 2` — `glossary_search` (done),
`glossary_get_entity` (done), `glossary_propose_entity_edit` (deferred). After the resume it held
**one**. The upsert does `tool_calls = EXCLUDED.tool_calls`, a straight overwrite, and a resumed
turn builds a fresh `tool_calls_history`, so the first pass's calls are gone.

**This corrupts the loop's own evidence, in a direction that flatters nothing and misleads
everything.** Every suspension a human ACTUALLY CAME BACK TO has its `deferred` row erased by the
resume; only the abandoned ones survive to be counted. So §1's *"38 of 41 deferred calls sit in
turns the human never returned to"* is very likely an artefact of this, not a finding about users.

The corpus is consistent with that and **cannot measure the size of it**, which is the worst
property a data loss can have. 53 `deferred` rows survive across 6 tools (42 of them
`glossary_propose_curation`); the resumed ones left no row to count, so the loss is invisible
rather than merely large. The denominator here is not under-reported — it does not exist.
It also means the reads that produced a call's arguments vanish from the record whenever the call
suspended — which is exactly the sequence iteration 3 needed to see.

**Why it is recorded and not fixed here:** the fix is a MERGE rather than an overwrite, and this
row is upserted several times per turn *and* across turns. The file's own comment says both
previous merge strategies for the sibling segment columns were wrong in opposite directions
(*"COALESCE erased the resumed turn's earlier passes, and the concatenation that fixed it
duplicated every pass a checkpoint had already written"*), which is why `segment_merge_sql` exists
and is interpolated at both upsert sites. `tool_calls` needs the same treatment and the same
dedupe-by-id care, and doing it badly silently duplicates or deletes recorded calls.
*Would clear it:* an id-keyed merge with a test that a resumed turn keeps its first pass, both
upsert sites covered.

### DQ-5 · CP-5.3's resolver is structurally unreachable from the frontend path

*Raised by:* iteration 3 · *Measured:* `validate_frontend_tool_args` runs at
`stream_service.py` ~3952; identifier resolution runs at ~4106. The frontend branch either
refuses or suspends, so **it never reaches the resolver**. A name in an id field — CP-5.3's
entire subject, 338 calls across 11 sessions — is answered by the UUID-shape check instead of
being resolved. And `glossary_propose_entity_edit` is the **one `entity_id` field of 19 that is
not bound to `EntityRef`** in the resolver registry.

There is a precedent for the fix in the same function: `_inject_context_ids` had *exactly this
defect one field over* — frontend tools were validated before the backend dispatch's context-id
injection, so the session's known `book_id` never reached them and a weak model invented one
(recorded 2026-07-26, "mình sẽ sử dụng một ID giả định"). It was fixed by running the same
injector inside the frontend branch.

**Why it is recorded and not built:** this tool's corpus contains **zero names**. All 92 are
placeholders (`placeholder_id_1`, `current_book_id_placeholder`, `0`), which no resolver can
serve — `glossary_search("placeholder_id_1")` returns nothing and refuses, correctly. Wiring the
resolver here would move those from a backend 400 to a typed refusal and change no outcome, and
§7 says a member with no subject is not written. Today's model reads first and sends real UUIDs,
so the subject may simply be gone.
*Would clear it:* a measured name-in-an-id-field on any frontend tool. The right shape when it
arrives is to EXTRACT the resolution block and call it from both sites — the same consolidation
`_inject_context_ids` already got — not a second copy.

### DQ-6 · A required-when-X argument the schema declares OPTIONAL

*Raised by:* iteration 7 · *Live-reproduced on today's runtime*, verbatim from the corpus:

```
composition_conformance_run {project_id, scope: "arc"}
→ "arc_id is required when scope='arc'"
```

and the schema for `arc_id` is `anyOf [string, null], default null` — i.e. **optional**. Same for
`chapter_id when scope='chapter'` and `model_ref when scope='arc'`. A model that reads the schema
and omits them is doing exactly what the schema says, and is then refused. 12 of the tool's 31
calls are this.

**Why it is recorded and not built:** corpus-wide, the whole
`X is required when Y='Z'` family is **12 calls in ONE tool across 3 sessions on a single day**.
§7's rule is the one that withdrew a spec row in CP-5: a member with no subject is not written, and
a mechanism for one tool's twelve calls is a member without one. It is recorded because the defect
is real and live, not because it is ready.
*Would clear it:* the same shape measured on a second tool, or this tool's traffic resuming. The
natural home is a `preconditions` contract member declaring the conditional as DATA
(`scope=arc ⇒ arc_id`), checked pre-dispatch like CP-5.8's scope gate — never a reworded message,
which is what the tool already has and what already failed 12 times.

**UPDATE — iterations 12 and 15 found the second and third instances, LIVE rather than in the
corpus:**

```
composition_authoring_run_manage {op: "create", book_id}
  → "op=create requires plan_run_id, budget_usd, and pause_after_each_unit"
composition_error_block_edit     {op: "list", project_id}
  → "op=list requires chapter_id"
```

In both, every named argument is declared OPTIONAL in the schema. So the shape is systemic — three
tools, all op/scope-dispatched — and the clearing condition above is **half met**: the SHAPE is
confirmed on three tools, but the measured TRAFFIC subject is still 12 calls in one tool, because
the other two were reached by this loop's own probes rather than by a model. §7 asks for a subject,
not a pattern, so it stays recorded. What has changed is that a `preconditions` member would now
have three declarations to write instead of one, which is the difference between a special case and
a contract member.

**UPDATE 2 — iteration 40 found a FOURTH, and this one is ORGANIC:**

```
plan_propose_spec {book_id, source_markdown, mode: "llm"}
  → "model_ref required when mode=llm"
```

`model_ref` is `anyOf [string, null], default null` — optional. This is not a probe: a real session
hit it. So the traffic subject is now **three tools** — `composition_conformance_run` 12 calls,
`plan_propose_spec` 1, and `book_list` 3 (`kind=chapters needs book_id`, iteration 43, also
organic) — and the shape holds on five tools.

`book_list` is the sharpest of them, because its field description ALREADY says
*"required for kind=chapters|revisions|scenes"*. The information was on the parameter the model
was filling in, and it was omitted anyway. That is the conditional family's own *prose is not the
lever* datum: the remaining fix is a checked declaration, not a better sentence. Still thin by §7's standard, and still recorded rather than built — but the next
organic instance should tip it, and the declarations are now written down ready to become a member:
`scope=arc ⇒ arc_id`, `scope=chapter ⇒ chapter_id`, `op=create ⇒ plan_run_id+budget_usd+
pause_after_each_unit`, `op=list ⇒ chapter_id`, `mode=llm ⇒ model_ref`.

### DQ-7 · 436 of 438 projects cannot build a graph, and the remedy has never been called once

*Raised by:* iteration 8. `kg_build_graph` refused all 13 of its calls with:

> *"this project has no embedding model configured — call `kg_project_set_embedding_model` first
> (pick one of your embedding models with `settings_list_models`), then `kg_run_benchmark`, then
> retry this build"*

That message is correct, complete, ordered, and names all three tools. **It was delivered 13 times
across 4 sessions and step one was never taken.** Measured corpus-wide:
`kg_project_set_embedding_model` — **0 calls, ever**. `kg_run_benchmark` — **0 calls, ever**.
This is the cleanest *prose is not the lever* datum the loop has produced.

And the reach is not marginal: **438 knowledge projects exist, 2 have an embedding model, 436 do
not.** `kg_build_graph` is unreachable for 99.5% of them.

The tool itself is fine — iteration 8 satisfied the precondition by hand and the whole path ran:
set model (`changed: true`, dimension 1024) → benchmark (`passed: true`, recall@3 1.0, MRR 1.0) →
build returns its cost-gated confirm token. Nothing is broken. The feature is simply gated behind
three steps nobody takes.

**The question, and it is a product decision:** should `kg_project_create` set a default embedding
model, so a new project can build a graph without the detour? It cannot be answered from the code.
The model list is **per-user** (`settings_list_models`), choosing one spends that user's provider
budget on embeddings, and the choice fixes `embedding_dimension` for the project's whole vector
store — changing it later is not a settings edit, it is a re-embed. A default picked by me would be
a guess deciding a cost-and-correctness question on behalf of every future project.
*Would clear it:* a stated default (model + provider + who pays), or a decision that the three-step
path is intended and should instead be surfaced at project creation rather than at first build.

### DQ-8 · 37 tools require a `project_id` nothing supplies, and the scope gate cannot see them

*Raised by:* iteration 9 · *Measured over the frozen catalogue and the live corpus.*

**37 tools declare `project_id` as REQUIRED. Every single one of them declares
`_meta.scope: "book"`. Not one declares `scope: "project"`.** CP-5.8's precondition gate fires on
`scope == "project"` and a missing project — deliberately, and its own comment explains why
`scope: book` must not be gated (`book_list` is `scope: book` and is how a model FINDS a book).
The consequence is that the gate guards the 33 tools where `project_id` is OPTIONAL and resolves
from the envelope, and **guards none of the 37 where it is required**.

So a book-scoped chat asks for an id the runtime never injects, the model cannot derive from the
book it is working in, and no gate refuses before the wire. Measured cost across `composition_*`:

| failure | calls | tools | sessions |
|---|---:|---:|---:|
| project id not found or not accessible | 116 | 10 | 18 |
| missing `project_id` | 38 | 4 | 5 |

`composition_list_outline` alone is 19 calls sending `{}` and 14 sending an id that resolves to
nothing. The tool itself is fine — given a real project id it returned 51 outline nodes first try.

**Why it is recorded rather than built, and the number is the reason.** The obvious fix is ambient
resolution: derive the composition project from the book in scope, the way `ambient_book` already
resolves `book_id` from `X-Book-Id`. But `composition_work` is **not** 1:1 — of the books that have
any project, **328 have exactly one and 52 have two or four**, because derivatives are a feature
(`composition_create_derivative`). Resolving for those 52 would pick a derivative on the user's
behalf, which is the guess CP-5.3 refused to make at 37.5% ambiguity and CP-6.1 refused to make on
near-miss kinds.

*The shape when it is built:* two branches and no third — exactly one project for the book resolves
silently; zero or many refuse and NAME the candidates. That is CP-5.3's contract applied to a new
ref type, and it belongs server-side with the other ambient resolution, not in a 37-way client
table. *Would clear it:* a decision on what a book-scoped call means when the book has derivatives.

### DQ-9 · The two confirm tools disagree about `domain`, and the model hit it on its first try

*Raised by:* iteration 11, **live**. `confirm_action` REQUIRES `domain`
(`enum: glossary|book|composition|translation|settings`). `glossary_confirm_action` has
`additionalProperties: false` and no `domain` at all. A model that has learned either one gets the
other wrong, and in the live run it did exactly that on attempt one:

```
invalid arguments for "glossary_confirm_action":
  Additional properties are not allowed ('domain' was unexpected)
```

It recovered on the retry, so the cost is one round trip rather than a loop — which is why this is
recorded and not built. But it is the same near-identical-siblings problem that produced
`glossary_propose_curation` in the first place: that unification exists because *"a mid-tier model
juggling four near-identical propose verbs mis-picks."* Two confirm verbs with contradictory
schemas is the same shape, one layer down.
*Would clear it:* either accept-and-ignore `domain` on the glossary variant, or retire the variant
in favour of `confirm_action(domain="glossary")` — a consolidation decision, not a bug fix.

### DQ-10 · `settings_provider_inventory` promises "live" and reads a cache no agent tool can fill

*Raised by:* iteration 18, and it nearly became a false defect report.

The tool's description says it lists *"the upstream models a configured provider credential
**currently offers** (its **live** inventory)"*. The handler's own comment says the opposite, and
the code agrees: *"Read the cached inventory only (no upstream sync — that would need the secret;
the agent reads what's already synced)."* It selects from `provider_inventory_models` and nothing
else.

That cache is populated by exactly one path — `GET /v1/model-registry/providers/{id}/models?refresh=true`,
a REST route behind the user's own JWT. **No tool on the agent surface can fill it.** So when the
tool answers `{"models": []}`, the model cannot distinguish *"this provider offers nothing"* from
*"nobody has ever opened the Settings page for this credential"*, and it has no move that would
change the answer.

**How close this came to a wrong finding:** LM Studio was live, serving 69 models, reachable from
inside the service's own container — and the tool returned empty. That reads as a broken tool.
Reading the handler first is what turned it into a description mismatch instead of a bug report.
The proof then ran the real sync (cache 0 → 69) and the tool returned all 69.

*Would clear it:* either correct the description to say "last synced inventory" and say when it was
synced, or give the agent surface a sync it can call. The first is a one-line honesty fix; the
second is a product decision, because syncing needs the provider secret.

### DQ-11 · A rich-text document array sent into a plain-prose STRING field

*Raised by:* iteration 42, and it is the largest genuine defect in
`book_chapter_save_draft` (245 calls, 100 ok).

`body` is declared `type: string` — *"the chapter's PROSE, as plain text… do NOT send
editor/Tiptap JSON unless you also set `body_format:"json"`"*. Ten calls across seven sessions sent
a **Slate-shaped array** instead:

```json
[{"type": "paragraph", "children": [{"type": "text", "text": "The air was thick with…"}]}]
```

The description already forbids exactly this AND names the escape hatch, which makes it another
*prose is not the lever* datum. But the escape hatch does not fit either: `body_format:"json"`
means **Tiptap** (`content`), and what arrives is **Slate** (`children`) — a different dialect, and
an array where a string is required.

**Why it is recorded rather than repaired.** A mechanical fix has to choose:
flatten the array's `text` leaves into paragraphs (lossless for plain prose, **lossy for any mark**
— bold, italic, a link), or refuse. This runtime already has a rule for that choice — *a repair
that emits parseable-but-wrong output needs a post-condition*, and prose that silently loses its
formatting is exactly that. Ten calls do not buy the right to decide it.
*Would clear it:* a decision on whether a marks-dropping flatten is acceptable for a DRAFT save
(it may well be — a draft is re-editable), or a per-dialect converter if it is not.

Note the rest of this tool's failures are already handled: **93 of the 145, across 13 sessions, are
the blank-args streak breaker** — our own refusal, not a tool failure.

### DQ-12 · The corpus cannot separate MEASUREMENT traffic from PRODUCT traffic, and a title regex misses

*Raised by:* iteration 46, with a hard number at last. `book_read` reads 196 calls / 101 ok — a
51.5% headline. Its dominant failure is **78 calls across 46 sessions, all on 2026-08-09, all
missing `book_id`, and not one of those sessions had a book in scope.**

All 46 are measurement runs. The obvious workaround — classify by session title — **misclassified 5
of them**: `LADDER d4 t0`, `LADDER d4 t1`, `LADDER d8 t0`, `LADDER d8 t1`, `CP-3 provenance` match
no sensible keyword regex (`eval|control|smoke|throwaway|probe|test`) and are unmistakably
instrumented once a human reads them. 28 matched `VM3%`, 13 matched the keywords, 5 needed eyes.

So the debt is not "we lack a convenient filter". It is that **every success-rate number this loop
publishes is contaminated by an unknown amount of its own kind of traffic**, and the only available
separator is a heuristic that provably fails. This iteration's own throwaway sessions are in the
corpus too, and they will contaminate the next reader's numbers exactly the same way.

*Would clear it:* a marker stamped at session creation — the thing iteration 1 already noted was
needed and said should be built **with** its first producer. Until then, a phase-2 population split
must look at session titles by hand and say so, as this row does.

---

### DQ-13 · CP-5.3 resolves a name in an id field, but only when the field holds ONE id

*Raised by:* iteration 55. `glossary_propose_status_change` was called with
`entity_ids: ["Carfax Abbey", "Castle Dracula", "Van Helsing", "Mina Murray", "Jonathan Harker",
"Count Dracula"]` — six human names in a list of entity ids — and the identifier resolver, whose
entire subject is "338 failed calls sent a human name into an entity id field", did not fire.

Not a binding oversight. It is structural: `refresolve.pending_for` skips any value failing
`isinstance(value, str)`, so a list is invisible to it no matter what the registry says. Binding
`entity_ids` today would change nothing.

**Measured across the whole corpus, not this tool:** names sent into a list-shaped `*_id*` param
total **8 items in 3 calls across 2 sessions** — 7 in `glossary_propose_status_change.entity_ids`,
1 in `glossary_propose_merge.loser_ids`. That is the honest subject, and it is small.

The reason this is deferred rather than fixed is not the size. It is that a list has a semantic a
scalar does not: **what does a partly-resolved list mean?** If five of six names resolve, does the
call proceed on five, refuse whole, or ask? CP-5.3 chose its shape deliberately — its own registry
note records that ambiguity was REAL at 37.5% of contested calls "which is why there is no 'pick
the best' arm" — and partial-list resolution is exactly a 'pick the best' arm wearing a different
hat. Extending it is a decision about the resolver's contract, not a missing loop.

*Would clear it:* a stated rule for partial resolution of a ref LIST — all-or-nothing, or proceed
on the resolved subset with the refusals named in the result. Either answer is implementable in an
afternoon; guessing between them would silently set the contract for every future list ref.

*Meanwhile the failure is honest:* live control proves the model is told
`at least one valid entity_id is required`, not a silent empty write.

---

### DQ-14 · The "placeholder IDs" headline is mostly a population the repair layer already fixes

*Raised by:* iteration 59, and it corrects evidence **this runbook has been leaning on**. The
goal's standing framing cites "101 placeholder IDs" as proof that actionable messages failed. The
full population, measured — every call whose `book_id` argument is not a UUID, **214 calls**:

| calls | sessions | outcome | last seen |
|---|---|---|---|
| **121** | 29 | **ok=true** — the repair substituted the session's book and the call SUCCEEDED | 2026-08-10 |
| 67 | 16 | failed, and the session had **no book in scope** — the server could not know one | 2026-08-10 |
| 10 | 7 | failed on a DIFFERENT argument (`entity_id`, `query`) with the placeholder merely recorded | 2026-08-10 |
| 10 | 4 | failed for another reason, no book in scope | 2026-08-04 |
| **6** | 1 | failed ON `book_id` while the server knew it — **the only real defect, and it is dated** | 2026-07-26 |

The 121 are decisive: **a call cannot succeed with `book_id="current_book_id_placeholder"`
reaching the service.** So the repair fires, and D-7 is now proven rather than suspected — the
recorded `args` are the model's PRE-repair text. Any count taken from that column measures what
the model typed, never what was dispatched.

The last 6 ran 2026-07-22 → 2026-07-26 17:03 against `glossary_propose_entity_edit`, a
consumer-local tool served by chat-service despite its glossary name. Frontend tools were
validated BEFORE the backend dispatch's injection, so the session's book never reached them.
`D-FE-TOOL-CONTEXT-IDS` fixed exactly that, committed **2026-07-27** — verified in git, not from
the comment that claims it. Every one of the 6 predates its own fix.

*What this changes:* a placeholder in the args column is not evidence of a failed call, and three
iterations of this loop have now split a failure population and found the repair had already won.
The open half is the 67 with no book in scope, and that is not a repair gap — the server has
nothing to substitute. Whether an id field should say "call `book_list` first" when scope is
absent is a message question, and **prose is not the lever**: the 67 are honest refusals today.

---

### DQ-15 · An argument the model cannot possibly fill, advertised on two write tools

*Raised by:* iteration 62. `composition_canon_rule_create` and `composition_canon_rule_edit` both
advertise `kind`, and this is its entire declared schema:

```json
{"anyOf": [{"type": "string"}, {"type": "null"}], "default": null, "title": "Kind"}
```

A free string, no description, no enum, no example — the title merely repeats the name. There is
nothing in it from which a model could derive a correct value.

**Measured from the SSOT:** `canon_rule.kind` is NULL in **45 of 45 rows, across 45 projects**.
The repository layer accepts it (`kind: str | None = None`) and every caller leaves it None. So
the field has never carried a value, from any writer, ever.

This is S1 row 8's shape — a value the code cannot enumerate — except worse, because here nothing
populates it at all, so there is not even a data-valued set to point at. Two answers are
defensible and they are opposite: **drop it from the advertised schema** (an argument with no
information content is a slot for a hallucination — the model has to invent something or omit it,
and 45/45 says it omits), or **declare its vocabulary** and name the tool that lists it, which is
the unadmitted C-20.

*Would clear it:* someone saying what `kind` is for. If the answer is "nothing yet", the schema
should not offer it until it is.

*Deliberately not guessed:* inventing an enum here would write a contract for a field whose
purpose is not recorded anywhere I can find, and a wrong vocabulary is harder to remove than an
absent one.

---

### Carry-forward · `story_search` suggests the mode it has just said it cannot run

*Raised by:* iteration 63, while proving `memory_search`. **S1 row 12 files this defect under the
wrong tool.** It describes `degraded: {"semantic": "not_indexed"}` arriving alongside `hits: []`
and a note recommending `mode='semantic'` — and attributes it to the memory family. Every one of
the 9 rows carrying that pair belongs to **`story_search`** (all 2026-07-15).

`memory_search`'s own degraded note is coherent ("this project has no indexed memory yet"),
verified live in that iteration. But
`services/knowledge-service/app/tools/executor.py:392` still reads
`"no matches — try mode='semantic' for ideas described in your own …"`, so this is **live debt, not
history**, and it must be checked against the degraded branch when `story_search` comes up in the
queue rather than assumed fixed.

Recorded here instead of in the ledger: the ledger holds one conclusion per tool, and a note about
a tool that has not had its iteration yet is not a conclusion.

---

## Debt this loop surfaced but did not absorb

### D-10 · A union-typed argument reports itself twice, in pydantic's internal path language

*Raised by:* iteration 69. `kg_list_templates.scope` is `Literal["system","user"] | list[...] | None`,
so a bad scalar produces one pydantic error **per union arm** and the shared directive renders both:

```
`scope.literal['system','user']`: Input should be 'system' or 'user' (you sent a str);
`scope.list[literal['system','user']]`: Input should be a valid list (you sent a str)
```

One argument, two statements, and the second reads as a contradiction of the first — the caller is
told it should be a list right after being told it should be one of two strings. The loc is
pydantic's discriminator path, not an argument name the caller can use.

**Measured, and it is why this is debt rather than a fix:** across every `invalid arguments for…`
message in the corpus, **10 calls on 1 tool across 5 sessions** leak a union path, none since
2026-07-14; the other **188 calls across 14 tools** render cleanly. The message still names the
valid values and what was sent, so it is noise rather than a dead end — unlike story_search's
note, which recommended an impossible action.

*Would clear it:* collapse union arms to the field name in `loreweave_mcp.validation_directive`,
keeping the arm that matches the sent type. Not done here because the subject is 10 calls and
collapsing can drop the one arm that explains the failure — a redesign of a shared helper wants a
population bigger than this one.


### D-9 · 980 entities stand in projects that no longer exist, and no re-sweep exists to reclaim them

*Raised by:* iteration 56, from the live probe behind the `memory_recall_entity` fix.

Measured from both SSOTs, never typed: Neo4j holds **1103** active `:Entity` nodes for the
dogfood user across **200** distinct `project_id`s; `knowledge_projects` holds **24** of those
200. The other **176** projects are gone, and **980 of the 1103 entities (88.8%)** belong to them.
`memory_recall_entity` answered out of one: the chosen `Lâm Uyên` and all five listed alternates
sit in projects that return `project not found` when you scope a call to them.

**The ratio is contaminated and I will not defend it** — this is a dev database that has absorbed
months of this loop's own eval traffic (DQ-12), and 176 deleted projects for one user is what
repeated test runs look like. What is NOT contaminated is the mechanism, which is code:

* `delete_project` purges the graph (`D-KNOWLEDGE-PROJECT-DELETE-NEO4J-ORPHAN`) — but
  best-effort, and its comment says a failure "leaves an orphan to re-sweep".
* **`purge_project` has exactly one call site.** There is no re-sweep. The reassurance in that
  comment names a mechanism that was never built — so a purge failure orphans permanently.
* The bulk GDPR erasure path did not purge at all. **That one is fixed in this iteration** and is
  the likeliest producer of this backlog.

*Not absorbed because deleting 980 nodes is destructive and irreversible, and it is not mine to
decide.* Two things would clear it: a reclaim sweep (`project_id` present on the node, absent from
`knowledge_projects`) run as an explicit operation with a receipt, and a decision on whether a
read should filter orphans defensively or let them surface as the fix now makes visible.


### D-8 · A whole checkpoint shipped, closed, and never ran — one missing `COPY` line

*Found by iteration 37, and it is the loop's most consequential result.*

CP-6.1 (closed-vocabulary resolution) was designed, built, unit-tested, falsified, admitted and
recorded closed. **It had never executed once in production.** `agent-runtime-vocabularies.json`
was not in the chat-service Dockerfile's per-file `COPY` list, so `/app/contracts/` in the running
image held three registries and not the fourth. `path.exists()` was False, the loader returned an
empty registry, and the entire block was skipped in silence — because *an absent registry is
indistinguishable from a legitimately empty one*, which the Dockerfile's own comment had already
warned about for CP-5.

The proof it was dead: a forced live turn — an unknown kind on the exact bound parameter — went to
the wire and failed at the backend with the old message, `call_outcome: failed`, no `refusal_kind`.
Corpus-wide, `unknown_vocabulary_value` had fired **zero** times since the checkpoint closed.

**And the guard that exists to prevent exactly this did not catch it, because its list was typed by
hand.** `test_THE_DOCKERFILE_SHIPS_EVERY_CONTRACT_THE_RUNTIME_READS` carried three literal
filenames. It now DERIVES them from the runtime's own `*_REGISTRY_FILENAME` constants, plus the
manifest path, with a floor assertion so the derivation cannot silently collapse to nothing. With
the `COPY` removed it goes red naming the exact file; before the change it passed.

After the fix, the same turn: `CP-6.1: 1 vocabular(ies), 1 bound parameter(s)`, both source reads
dispatch, and the call is **refused before the wire** — `refused` / `unknown_vocabulary_value` —
naming the book's real kinds. Its sibling logs `CP-5.3: 1 ref type(s), 19 bound parameter(s)`, so
that registry was loading all along.

**The transferable rule:** *a mechanism is not shipped until something in production says it ran.*
A green suite, a falsified guard and a closed row all held while the feature was inert, and the one
signal that would have exposed it — a log line saying the registry loaded — was available the whole
time and nobody read it.

### D-7 · The recorded `args` are what the MODEL sent, not what was DISPATCHED

*Nearly corrupted iteration 13's reading, and would corrupt any phase 2 that does not know it.*

`_inject_context_ids` replaces a malformed `book_id` with the session's real one, and the recorded
`tool_calls` row keeps **the model's original string**. The repair is invisible in the corpus.

The proof is unambiguous: in August, in book-scoped sessions, **121 calls recorded
`book_id: "current_book_id_placeholder"` and SUCCEEDED** — `glossary_search` ×52,
`glossary_book_ontology_read` ×51, `glossary_get_entity` ×13. Those tools cannot succeed on that
string, so the value on the wire was not the value in the record.

**What this means for every iteration's phase 2:** a claim of the form *"the model sent X"* read
off `tc.args` is the model's ORIGINAL argument. Where the call FAILED with an error naming X the
two agree — the repair either did not fire or did not help — and every finding this loop has made
so far is of that form, so they stand. Where the call SUCCEEDED, the recorded argument may never
have reached the tool, and counting those as "the model gets this wrong" over-counts the defect
while under-counting the repair that already fixes it.

*Would clear it:* record the dispatched arguments alongside the model's, the way `resolution` and
`plan_supplied` already keep the substituted and the typed value apart — the same reasoning, one
repair over. Until then, split phase-2 populations by outcome before drawing any conclusion from
an argument value.

### D-6 · A `proven` row's LIVE evidence can stop being true without anyone touching the code

*Found by tripping over it in iteration 11.* Iteration 1's fix
(`coalesceCurationEntityRef`) was committed, and its live proof was recorded against
`infra-glossary-service` image `ce654254a69b`. Ten iterations later the same call failed again with
the original error. The source was unchanged and committed; the **running container was image
`21c088f0f375`** — something rebuilt or recreated glossary-service from a tree without the fix, and
I did not observe what. A rebuild and `--force-recreate` restored it and the singular
`entity_id` mints a token again.

Nothing regressed in the repository. What regressed is the claim: **"proven LIVE" is a statement
about a deployment, and deployments drift underneath a ledger that records them as settled.** The
memory this repo already carries — *verify the deployed image matches source before diagnosing* —
turns out to cut both ways: here the source was right and the deployment was stale.
*Would clear it:* a cheap re-verification step that replays each proven row's live assertion against
the current images, so drift is caught by the loop rather than by the next iteration stumbling.

Recorded here rather than fixed inline, because the loop's whole design is one tool at a time and
a run that absorbs every adjacent finding never reaches its second row.

### D-1 · Five falsifiers do not red the guard they name

Found by a **clean** `agentruntime-falsification.py --run` (332 of 337 red; the 5 below report
*"GREEN — the guard requires nothing"*). All five predate this loop; every new guard added in
iterations 1–2 reds correctly. The gate exits 0, so this is advisory — but a guard whose falsifier
cannot red it is a green light that means nothing, and each already has a diagnosis:

| guard | why the falsifier misses |
|---|---|
| `test_THE_CREATE_PATH_IS_NOT_THE_LEGACY_TOOL` | the falsifier edits `agent-runtime-vocabularies.json`; the test reads the **hardcoded `vocab()` fixture**, so the registry it claims to protect is never asserted against |
| `test_THERE_IS_NO_FUZZY_SUBSTITUTION_ARM` | the injected arm compares `_normalise('place')` against the book's kinds, and `place` does not normalise to `location` — so the value stays unknown and the guard stays green |
| `test_A_MISSING_OR_WRONG_SHAPE_YIELDS_NOTHING_RATHER_THAN_RAISING` | `seq = [seq]` is caught by the per-row `isinstance` check downstream, so the wrong shape still yields nothing instead of raising |
| `test_NO_FEDERATED_TOOL_DECLARES_ITS_OWN_OWNER` | it injects `_meta_forged`, a key nothing reads; forging the owner needs the tool's real `_meta.served_by` |
| `test_THE_UNION_DERIVES_COMPLETELY` | the replacement still appends whenever a name exists, so it is a no-op on every catalogue row |

### D-5 · Two guards sharing a bare test name silently collapse, and two pairs already do

*Found by colliding with it in iteration 5.* `_guards()` in `agentruntime-falsification.py` builds
`{test name: suite}` across every registered suite. A name defined in two suites keeps **one**, so
the other guard's falsifier is applied and then measured against a test **in a different file** —
which the edit does not touch. The verdict comes back *"GREEN — the guard requires nothing"*, an
accusation aimed at a perfectly good falsifier.

My `test_THE_REFUSAL_IS_TYPED_REFUSED_NOT_FAILED` collided with CP-6.1's and is renamed to
`test_THE_DUPLICATE_REFUSAL_IS_TYPED_REFUSED_NOT_FAILED`. **Two more collisions predate this
iteration and are live right now:**

| name | suites |
|---|---|
| `test_AN_UNKNOWN_LANE_FAILS_CLOSED` | `test_cp5_refresolve.py`, `test_cp6_vocabulary.py` |
| `test_IT_SITS_BEFORE_THE_ONE_REAL_DISPATCH` | `test_cp5_namesource.py`, `test_cp6_vocabulary.py` |

For each pair, one of the two guards is currently counted as proven on the strength of running the
*other* one. Both have falsifiers registered, and both of those falsifiers are measuring a test
they do not name.

**The real fix is in the instrument, not the names:** `_guards()` should REFUSE a duplicate rather
than let a dict overwrite decide which guard is measured — the same posture the census takes when
two refusals share an id (*"Two refusals with one id means an allowlist row does not name a
site"*). Doing that turns these two pairs red immediately, which is why it is a change of its own
rather than a footnote to a tool iteration: it needs the two colliding pairs renamed in suites this
loop does not own.

### D-4 · A NEW suite must be `git add`ed before its falsifiers mean anything

*Learned the hard way in iteration 5.* The falsification harness runs each mutated suite inside a
mirror, and the mirror is built from **tracked** files (`git ls-files`). A brand-new suite that has
not been staged is simply absent there, so `pytest tests/<new>.py` exits *"file or directory not
found"* — non-zero, with the test's name nowhere in stdout.

The harness reads that as `red=True, named=False` and reports, for **every guard in the file**:

> `NOT FALSIFIABLE  test_X: RED, but a DIFFERENT test - the falsifier measured a bystander`

which reads like sixteen badly-written falsifiers and is in fact one missing `git add`. The tell is
the count: *all* of a new suite's guards fail together and none of the old ones change. Stage the
file, re-run, and they pass unchanged — the falsifiers were never the problem.

Worth stating because the failure is silent in the flattering direction's opposite: it under-reports
your own work as unproven, and the obvious response — rewriting perfectly good falsifiers — makes
things worse.

### D-3 · The durable-gate resume infers its outcome instead of stating it

*Raised by:* iteration 5. The `book_task_provide_input` row from an accepted delete gate carries
`call_outcome: done` with **`call_outcome_inferred: true`** — the task path stamps `ok` and lets
the chokepoint's default decide the type, which is the same shape iterations 2 and 3 closed on the
denial and frontend-resume paths. It happens to land on the right answer here because the write
really did succeed, and that is exactly why it is easy to leave: an inferred outcome is only
visibly wrong when it disagrees.

Small and self-contained — the task chunk is built in one place and already knows `_accepted` and
the envelope's success — but it belongs to `book_task_provide_input`'s row, not
`book_chapter_delete`'s, so it is recorded rather than folded into an iteration about another
tool.

### D-2 · Running the falsification harness concurrently with the suite reds tree-mirroring guards

`test_NEITHER_CENSUS_WRITER_CAN_REACH_THE_LIVE_TREE__all_8_cells` went red mid-iteration, and
**reproduced at two earlier commits in a detached worktree** — which looked like a long-standing
break until the variable turned out to be a background `--run` competing for temp mirrors. It
passes clean (23.75s) once nothing else is running. Run the gates serially; a red here is a
scheduling artefact before it is a defect.

**And it cost me a wrong edit before I understood it.** The same racing run reported
`surface.py::SurfaceAssembler.assemble::AssertionError::1` as `NOW GUARDED`, so I dropped it from
the census allowlist — checking only the failure mode the allowlist's header names (digest churn),
which this was not. A clean re-run (159 sites, 12 workers, nothing competing) reports it
`NEWLY SILENT` again, and the row is restored. **A verdict from a gate that was racing another
mirroring gate is not evidence, and it fails in the flattering direction — it claims a guard
exists.** The two vocabulary rows in the same report were real: they are guarded now and gone
from the clean run, which is how the corrupted and the genuine findings are told apart after
the fact.

---

## Ledger

`contracts/agent-runtime-toolv2-ledger.json` records the **conclusion** per tool and nothing else —
it never defines the set, so it cannot flatter the progress number. `--status` computes coverage
against the catalogue every time.
