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

### DQ-16 · A propose card does not say the thing it proposes already exists

*Raised by:* iteration 76. `glossary_propose_new_kind(code="character")` on a book that already
has a book-level `character` kind returns a normal creation card —
`Create kind "Character" (code: character)`, `destructive: false`, preview rows `code` / `name` —
with **nothing saying the code is taken**.

The convention for this exists in the same service. `glossary_propose_status_change` returns its
card with `warning: "all 1 matched entities already have status \"active\" — this will change
nothing"` (verified live in iteration 55). So a propose CAN inspect current state and say the
change is a no-op; this one does not.

**What I did NOT test, and will not assume:** what happens on confirm. The apply may be
idempotent, may error, or may create a conflicting row — and there is no confirm tool on the
glossary MCP surface (confirmation runs through chat-service's action-token path), so settling it
is a bigger detour than this iteration. **The observation is that the card is uninformative, not
that the write is wrong.**

*Would clear it:* confirming one such card on a throwaway book and recording what the apply does.
If it is idempotent, the card should say so the way status_change's does; if it conflicts, the
card is actively misleading and the propose should refuse.

**Sharpened in iteration 80, and it removes the "maybe the check is expensive" defence.** The
DIRECT create path in the same service, on the same rows, already does it — and does it well:

| call | result |
|---|---|
| `glossary_book_create(level="kind", code="toolv2_i80_kind")` | `status: created` |
| the same call again | `a row with code "toolv2_i80_kind" already exists in this book — use glossary_book_patch to edit it` |
| `glossary_propose_new_kind(code="character")`, which exists | a normal creation card, no warning |

The create refuses, names the code, and names the tool that does what the caller wanted. The
propose, for the same conflict, mints a confirm card. One of these two paths has the check.

**Third example, iteration 102 — and it shows the warning is conditional, not decorative.**
`glossary_propose_reassign_kind` returns:

| call | card |
|---|---|
| reassign to a DIFFERENT kind | `warning: null` |
| reassign to the kind it already is | `warning: "the entity is already kind \"character\" — this will change nothing"` |

So **three** glossary propose tools inspect current state and say when the change is a no-op —
`propose_status_change` (iteration 55), `propose_reassign_kind` (here), and the direct
`book_create` path (iteration 80) — and each fires only when the condition holds. The gap is
`glossary_propose_new_kind` alone, which is now the odd one out among its own siblings rather
than an example of a house style.

---

### D-11 · A duplicate propose escapes every breaker, because a confirm card is never identical

*Raised by:* iteration 76. One turn emitted `glossary_propose_new_kind` for four distinct kinds
**twice each** — eight confirm cards for four things. No breaker fires: it is not a read (the
repeat-read breaker fingerprints the RESULT, and every card carries a fresh token and
`expires_at`, so the fingerprint always differs), and it is not a `created:false` write.

**Measured, keyed on ARGS rather than the card title: 8 redundant cards, 7 groups, 2 tools,
4 turns**, last seen 2026-07-15. Small — and worth stating how the first count went wrong: keying
on a truncated `title` merged four *different* kinds into one group and suggested a much larger
problem than exists. The args are the identity; the display string is not.

*Not absorbed because* 8 cards does not justify a fifth breaker, and the natural fix is DQ-16's
— a propose that knows the target already exists has something better to do than be counted.

---

## The phase boundary at iteration 120 — the corpus runs out

**Every tool with recorded traffic is concluded.** From iteration 121 the queue is tools with
**0 calls**, and the method has to change, so it is written down before it is improvised:

* There is **no failure population to split**. Phase 2 has nothing to read, and "the failures are
  all the blank-args era" — the sentence that closed a third of this loop — is unavailable.
* There is **no recorded shape**. Every ledger row so far could check a live result against what
  the corpus said the tool returns. Now the live call IS the only evidence, which makes reading
  the schema first mandatory rather than a shortcut I kept skipping (four tools in this loop
  refused my first call because I guessed an argument name).
* The tool may never have run **at all**, which is a different claim from "it works". Iteration
  100 already met this shape: `glossary_list_merge_candidates` is correct, and no merge candidate
  has ever existed in the database, so its non-empty branch is unverifiable by anyone.

The QC bar does not move. What changes is that CODE and DATA now lean harder on the schema and on
the SSOT, because the corpus can no longer corroborate. A first invocation that fails is still a
finding — arguably a better one, since nothing has ever exercised the path.

---

### ✅ CLOSED — `book_chapter_bulk_create`'s undo hint could not be replayed (iteration 122)

**Found on the first invocation the tool has ever received**, which is the whole argument for the
never-called phase. Live:

```
book_chapter_bulk_create → created 2, chapter_ids [A, B]
  _meta.undo_hint = {tool: "book_chapter_delete", args: {book_id, chapter_ids: [A, B]}}

replaying that hint verbatim →
  validating "arguments": unexpected additional properties ["chapter_ids"]
```

`book_chapter_delete` requires `[book_id, chapter_id]` — **singular**, one chapter per call. The
hint emits `chapter_ids`, a plural array. It names a real tool with an argument that tool rejects,
so the undo is unreplayable. Deleting the two probe chapters took two singular calls.

The service's own test (`mcp_server_test.go:220`) builds an undo hint with the **singular**
`chapter_id` — so the correct shape is known and asserted elsewhere; bulk-create is the one
producer that emits the plural, and it is also the only producer of a MULTI-id undo. Nobody found
it because nothing had ever called the tool.

*Deliberately left unconcluded rather than recorded as proven.* A tool whose undo affordance does
not work is not proven, and the loop's rule is that only `proven` or `blocked` are terminal.
`--next` returns this tool again — verified.

**And the fix is a contract decision, so it is deferred rather than guessed.** `undoResult`'s own
doc says `args` is "its argument **template**", i.e. replayable verbatim, and the format expresses
exactly ONE call. A bulk create's undo is N calls. There is **no plural delete tool** — checked.
So the two candidate fixes are:

1. **Extend the hint format** with repeat-per-item semantics (e.g. an explicit `each` key). That
   changes a shared contract consumed by ~8 call sites across book-service, and every consumer of
   `_meta.undo_hint` would need to understand the new shape.
2. **Add a plural `book_chapter_delete`** (or a bulk variant) so one hint really is one call. That
   adds a destructive tool to the surface, which is a product decision about the agent's reach.

Both are defensible and they are not equivalent; picking one silently would set the undo contract
for every future bulk operation. **The question:** should `undo_hint` be able to describe N calls,
or should every reversible bulk write have a bulk reverse tool?

*Meanwhile the damage is bounded and stated:* the hint is unreplayable, not wrong about the ids —
`chapter_ids` holds the correct list, so a human or a consumer that understands the intent can
still undo by iterating. Nothing is lost; it just cannot be replayed mechanically.

---

### ✅ CLOSED — `book_chapter_purge` minted an irreversible card for an ACTIVE chapter (iteration 123)

**Found on the first invocation this tool has ever received.** Its own description:

> "Propose PERMANENTLY purging a **trashed** chapter (irreversible)."

Live, against a chapter whose `lifecycle_state` is **`active`** (verified in the database first):

```
book_chapter_purge{book_id, chapter_id: <an ACTIVE chapter>}
  → confirm card, destructive: true,
    title "Permanently purge chapter (irreversible)"
```

The precondition the description states is **not checked when the card is minted**. A human is
handed an irreversible-purge card for a live chapter, having been told the tool only purges
trashed ones — and the card's own title reinforces that it is irreversible without saying the
target is not trashed.

**SEVERITY CORRECTED.** I wrote that this might be "data loss reachable from a mislabelled
affordance" and that settling it required a destructive test. It did not — *reading*
`mcpTransitionChapter` settles it: its `purge_pending` arm returns `errActionBadState` unless
`cState == "trashed"`. **The apply path guards; only the mint path did not.** So confirming that
card would have errored, not destroyed a chapter. This was a misleading card and a wasted human
confirmation. Still worth fixing, and materially less severe than I first framed it — recorded
because the alarming reading was mine, and it was wrong.

**FIXED** at both propose sites: a purge is refused at mint time unless the chapter is trashed,
with a message naming the precondition and its satisfier. Live A/B on the deployed image: the
exact call that minted a card now returns *"chapter is not in the trash — purge only removes an
ALREADY-TRASHED chapter; delete it first (book_chapter_delete), then purge"*.

*Concluded `proven`.* Tier W, `visibility: legacy`, deprecated ("irreversible chapter purge is a
MANUAL UI action — never the agent"), and 0 recorded calls — the deprecation is holding, which is
why nobody had hit this.

---

### Audited and CONTAINED — `uuid.UUID` on an MCP output struct (iteration 124)

The `book_chapter_reorder` defect (schema says `array`, JSON is a string, every successful
response rejected) is a **class**, not a typo, so it was swept rather than assumed unique.

| sweep | result |
|---|---|
| struct fields typed `uuid.UUID` carrying a `json` tag, all services | **59** |
| …of those, reachable from an **MCP tool output type** (transitive, incl. nested structs) | **1** |
| …of that one, genuinely on the wire | **0** |

The 59 are overwhelmingly REST-only structs, where no schema is generated and nothing validates.
The single transitive hit — `chapterSummary.ChapterID` in glossary-service — is a
**deserialization target** for an internal HTTP client (`fetchBookChapters`), never an MCP output;
the closure matched it by type name, not by a real output path. **Verified by reading its call
sites rather than trusting the sweep**, which is the same discipline that caught my first sweep
returning a false `0` because it did not follow nested types.

*Method worth reusing:* the naive sweep (top-level output structs only) returns **0 and would have
missed the very defect that prompted it** — `reorderedChapter` is nested inside
`chapterReorderOut.Chapters`. Any audit of an output-shape defect has to close over field types.

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

**Corrected in iteration 73:** "1 tool" describes the CORPUS, not the code. A live control on
`jobs_list.status` — a different service, a different union — produced the same doubled render:

```
`status.literal[...]`: Input should be 'pending', 'running', … (you sent a str);
`status.list[literal[...]]`: Input should be a valid list (you sent a str)
```

`jobs_list`'s one recorded failure predates the one-line rewriter, so it never entered the count.
The corpus number is a floor: **any union-typed argument on any of the three services renders this
way**, and low recorded traffic is not evidence that the shape is rare — only that few callers have
hit those arguments since the rewriter shipped.


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

**Corroborated independently in iteration 119, and it raises the severity.** `lore_timeline`
found the same backlog from the other side: the user holds **452 `:Event` nodes across 10
project_ids**, and `knowledge_projects` contains **none** of the two largest (139 and 120 events).
The tool answers `project not found` for every one of them.

So the cost is not only stale rows that read oddly. It is **lost read access to real data**:
entities surface through a name lookup (iteration 56) because that path searches across projects,
but anything scoped BY project — timelines, and every other project-scoped read — cannot reach
them at all. Two tools, two data types, one cause.


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

## DQ-17 — a fabricated `X-User-Id` makes "book not accessible" TRUE, and it looks like the defect

Iteration #138's live A/B first came back UNCHANGED after a verified-byte-identical redeploy. The
cause was not the fix: I had typed a plausible user UUID into the header instead of reading the
book's `owner_user_id`. With an unknown user the grant genuinely fails, so `mcpRequireGrant` →
`mcpOwnershipError` → "book not accessible" — the exact string the whole false-noun class is about,
produced by the one site where it is correct.

`SELECT owner_user_id FROM books WHERE id=$1` gave `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`; with that
header the same absent `part_id` answered "no active part or chapter with that id in this book", and
a `book_structure_read` control on the same book/user succeeded — which is what makes the book
demonstrably accessible rather than assumed so.

**Rule for every remaining live control: read the owner from the DB, and run a same-book read
control in the same request batch.** A deny-shaped answer with an unverified identity measures the
header, not the tool. This is the same failure mode as the typed denominator — a value I supplied
being read back as evidence.

Scope of the doubt, stated rather than waved away: the earlier sites in this class (#86, #129, #130,
#132, and the four swept here) were argued from the CODE — each raise sits downstream of a grant
check that has already passed, so the message is false regardless of which user called. The bad
header can invalidate a TRIGGER, not those fixes.

## DQ-18 — apply drops the template's `tracks`/`roster` onto the arc node, so extract cannot return them

Measured in #146 on a clean apply→extract round trip. The source template
(`019f0d28-…`, "W10 FE Smoke Arc") carries `tracks: 2` and `roster: 2`. The arc node
`apply_arc_to_spec` created carries `tracks: []` and `roster: []`, and the template extracted back
out therefore carries `tracks: 0` — while its placements still reference `thread: "combat"` and
`"romance"`, tracks that no longer exist anywhere in the template.

The extractor is not at fault: it faithfully copied what the arc node holds. The loss is upstream,
in what apply writes onto `structure_node`.

**The open question is which behaviour is intended**, and it is a product decision rather than
something the code settles:

- If an arc is meant to be a full instance of its template, apply should copy `tracks`/`roster`
  onto the node, and the round trip becomes lossless.
- If tracks are meant to live only on the template and be referenced by name, then `layout`
  placements naming a `thread` that the template does not define is the real inconsistency, and
  extract should either carry the threads it observed or drop them.

Both readings are defensible from the current code, `composition_arc_edit` accepts `tracks` and
`roster` as first-class create arguments (so an arc CAN hold them), and #146's fix — which closed
the `motif_code` half of the round trip — does not depend on the answer. Recorded rather than
guessed; the placements' `thread` values survive either way, so nothing is lost by waiting.

## DQ-19 — arc_template archive's anti-oracle is defeated by its own documented inverse

`composition_arc_template_archive`'s description states the design: "A foreign/missing/system row
is a uniform no-op (returns archived:true — no existence oracle)."
`composition_arc_template_restore`'s states the opposite: "a foreign/system/not-archived id is not
restorable (uniform deny)."

Measured live, both halves behave exactly as written:

| call | nonexistent id | the caller's own id |
|---|---|---|
| archive | `archived: true` | `archived: true` |
| restore | uniform deny | returns the full row |

So archive-then-restore distinguishes existence perfectly. The oracle archive pays an actionability
price to deny is readable through the tool documented as its reverse.

**The safety half is fine and was checked**: the UPDATE is scoped
`WHERE (owner_user_id = $1 OR (book_shared AND book_id = $3)) AND id = $2`, so a foreign row is
genuinely untouched — the no-op is a real no-op, not a silent cross-tenant write. And the leak is
narrow: restore requires ownership, so what the pair reveals is "this id is MY archived template"
versus "it is not", which is information about the caller's own data.

**The open question is whether the no-op-success is still worth its cost**, and it is a product
decision rather than something the code settles:

- If the oracle matters, restore should arguably answer uniformly too — but a restore that cannot
  report failure is a worse tool than one that can.
- If it does not (the pair already leaks it, and only over the caller's own rows), archive could
  report honestly that nothing matched, which is what an honest caller with a typo needs. This is
  the shape #143 fixed on `arc_assign_chapters` — the difference being that there the silent zero
  was undocumented, and here it is a stated, deliberate choice.

Recorded rather than overridden: the loop does not reverse a documented security posture on its own
authority. Nothing is lost by waiting — the write is correctly scoped either way.

### DQ-19, second half — restore denies a row the caller can read

Measured in #159, completing the pair. `composition_arc_template_restore` answers "not found or
not accessible" for **the caller's own ACTIVE template** — a row they can fetch in full through
`composition_arc_template_get`. The description documents it ("a foreign/system/not-archived id is
not restorable (uniform deny)"), so the behaviour is intended, but the sentence is false about a
row whose existence the caller can prove one tool away.

This is the false-noun class the loop has fixed seven times in book-service (#86, #129, #130, #132,
#138), and the argument that settled those applies here too: downstream of a passed ownership
check there is no enumeration oracle left to protect, so uniformity buys nothing and costs the
caller its next move. "This template is not archived" leaks nothing, because ownership was already
provable.

It is recorded rather than fixed for one reason only: **consistency with DQ-19's first half**. That
entry declined to change `archive`'s documented no-op-success on the loop's own authority. Fixing
`restore`'s message while leaving `archive`'s would settle half a documented contract arbitrarily.
Both halves want the same product decision, and they should get it together.

## DQ-20 — archiving a derivative hides it from the panel that would restore it

Measured in #195. `composition_list_derivatives` returns only the canonical Work for a book whose
two derivatives are archived — including when called with an ARCHIVED derivative's own project_id.
There is no `include_archived` / `status` parameter, so an archived branch is unreachable through
the tool surface.

**This is not agent-only.** The REST route `list_book_derivatives` is documented as "the REST twin
of the MCP composition_list_derivatives (the DivergenceManagerView's read side)", and both call the
same repository method. The product's own divergence manager is equally blind.

The cause is a shared primitive with two callers that want opposite things:

```
resolve_by_book: WHERE book_id = $1 AND status = 'active' AND book_lifecycle = 'active'
                   AND NOT pending_project_backfill
```

Its docstring shows it is the **work-RESOLUTION** chokepoint (`work_resolution.resolve_work` maps
len==1 → found, len>1 → candidates). For resolution the `status='active'` filter is *correct* — an
archived Work must never resolve as the live one. For a **manage panel that offers Restore** it is
exactly wrong. Each caller's fix is the other's defect, which is why this wants a decision rather
than an edit.

The consequence is concrete: `composition_derivative_edit op=restore` works (proven in #180), but
its input is discoverable only if the caller wrote the project_id down before archiving.
`composition_get_derivative_context` still answers for an archived derivative, so nothing is lost —
it is *unfindable*, not gone.

Sibling precedent exists in this same service and shows the intended shape: `composition_arc_list`
takes `include_archived`, and `composition_arc_template_list` takes `status ∈ draft|active|archived`
(#158 measured an archived template correctly listed under it). Derivatives simply never got one.

**Open question:** should the listing get its own repository read (leaving `resolve_by_book` a pure
resolution primitive), or should it gain an `include_archived` flag threaded through? Recorded
rather than chosen, because the shared function is load-bearing for resolution and picking wrong
turns a listing convenience into a resolution bug.

### DQ-20, second half — an ARCHIVED derivative can be made the ACTIVE Work

Measured in #228, and it makes the first half materially worse. `composition_switch_active_work`
accepted an archived derivative as the book's active Work:

| check | result |
|---|---|
| that derivative's `status` | `archived` |
| listed by `composition_list_derivatives` | **no** (0 matches) |
| accepted by `composition_switch_active_work` | **yes**, `active_project_id` set to it |

So the studio — whose editor and panels follow this preference — can be pointed at a Work that no
listing surface will show. A user who archives a branch and then switches onto it is editing inside
something they cannot find, and `composition_list_derivatives` will keep reporting only the
canonical Work.

The tool does validate membership: an unrelated project_id is refused with the specific
`NOT_A_WORK_OF_THIS_BOOK`. It simply does not check `status`. One guard is present and its sibling
is missing.

**Open question, same shape as the first half:** should switching refuse an archived Work, or should
the listing surface archived Works so the state is at least visible? Either closes the hole; doing
both is redundant, and doing neither leaves a studio that can resolve to something its own manage
panel denies exists. Recorded rather than chosen for the same reason as the first half — the
listing's blindness comes from a shared resolution primitive (`resolve_by_book`, filtered to
`status='active'`), so the two halves want one decision, not two edits.

## DQ-21 — the wiki job pays to write articles about entities a human REJECTED

Found while proving `kg_build_wiki` (#248). The label defect on that card is fixed; this is the
behaviour underneath it, which I am recording rather than deciding.

`_resolve_entity_ids` passes `status_filter=None` to known-entities, deliberately and for a good
reason spelled out in its own comment: both entity creation paths insert `status='draft'`, so an
active-only filter would produce an empty wiki. The consequence is that NO status is excluded —
including `rejected`.

Measured across the instance, `glossary_entities` where `deleted_at IS NULL`:

| status | rows |
|---|---|
| draft | 6393 |
| active | 925 |
| rejected | 10 |

So a "generate for all" wiki build on a book containing rejected entities spends caller money
drafting and revising articles about entities a human already declined. The count is small today
(10 rows instance-wide), which is exactly why it is worth recording now rather than after it is
not: nothing about the resolver bounds it, and `rejected` is a triage outcome users produce by
using the product as intended.

**Open question:** should `_resolve_entity_ids` exclude `rejected` specifically — `status != 'rejected'`
rather than the active-only filter that was correctly rejected — or is a rejected entity still a
legitimate wiki subject (rejected *as an extraction suggestion*, not necessarily as lore)?

I cannot answer this from the code. The two readings of `rejected` lead to opposite edits, and the
distinction lives in what the triage UI tells a user they are doing when they reject something. The
glossary status vocabulary is shared with the suggestion-triage rail (`queryAISuggestions` treats
`draft` as the pending pile), which is evidence for the second reading but not proof of it.

Not blocking #248: the card now states the set truthfully in either case, so a human confirming a
wiki build is no longer told a false denominator. Whichever way this resolves, the fix is one
predicate in `_resolve_entity_ids` plus the card note that #248 anchored to it.

## DQ-22 — should a manual "make sure this node exists" call bump the node's version?

Found while proving `kg_create_node` (#249). The description defect is fixed and the tool now warns
about the cost; this is the behaviour underneath, which I am recording rather than deciding.

`_handle_kg_create_node` delegates to the shared `merge_entity`, whose ON MATCH branch is
unconditional:

    e.version = coalesce(e.version, 1) + 1,
    e.updated_at = datetime()

Measured on one node across three identical calls: version 1 → 2 → 3. And `version` gates writes —
PATCH `/v1/knowledge/entities/{id}` requires If-Match (428 without) and 412s on mismatch. With a
control, same entity, same body:

| step | result |
|---|---|
| read ETag `W/"4"`, PATCH immediately | **200** |
| read ETag `W/"5"`, one `kg_create_node` (same name+kind), then PATCH | **412** |

**Open question:** should the manual path skip the bump when the merge changed nothing?

I did not change it, for a reason that cuts both ways. `merge_entity` is shared with extraction,
where a merge folding new evidence into an existing node genuinely *is* an update and *should*
bump — so a blanket "don't bump on match" is wrong. A no-op-detecting bump (compare the ON MATCH
SET's inputs against current state, bump only on real change) would be correct for both callers,
but it changes a primitive on extraction's hot path, and I have no measurement of what that costs
or of what else reads `version` as a change signal.

The team already knows the effect and mitigated it in ONE place: the frontend's knowledge-effects
handler invalidates the cast/arc caches after `kg_create_node` specifically, its comment saying
"else the next human rename 412s against an unseen version". That mitigation covers the FE's own
caches. It does nothing for an agent, or for a second client, holding a version across the call —
which is the case #249 measured.

Not blocking #249: the description now states the cost and tells a caller not to make the
defensive call, so the hazard is at least visible to whoever hits it.

## METHOD — a second `docker cp` of the tests dir in one container's life runs STALE tests

Hit during #252 and worth writing down, because the failure mode is a FALSE GREEN.

`docker cp <host>/tests <container>:/app/tests` behaves differently depending on whether the
target already exists:

| state of `/app/tests` | what happens |
|---|---|
| absent (fresh container from the image) | created correctly |
| already present | the source is NESTED as `/app/tests/tests` |

The image carries no `tests/`, so the first copy after a `--force-recreate` is always correct. The
trap is the SECOND copy within the same container's life — the one you make after editing a test
file. It lands in `/app/tests/tests`, `pytest tests/unit/...` keeps reading the copy from before
your edit, and the run is green against a test you have already changed.

In #252 this showed up as a guard that stayed red after I had fixed it. That is the lucky
direction. The same mechanism would just as easily have shown green on an assertion I had
tightened, and I would have recorded a conclusion the tests did not support.

`rm -rf /app/tests` first does NOT work — the copied files are root-owned and the app user gets
permission-denied on every one.

**The reliable sequence, and the only one to use:**

    docker compose ... up -d --force-recreate --no-deps <service>   # fs comes fresh from the image
    docker cp <host>/tests <container>:/app/tests                   # exactly ONE copy per container life
    docker cp <host>/pytest.ini <container>:/app/pytest.ini

Verify it worked rather than assuming — `ls -d /app/tests/tests` must find nothing, and grepping
the container's copy for a phrase you just added must return 1. Single files (`docker cp x.py
<container>:/app/app/.../x.py`) are safe to repeat, which is why the red-proof injections in this
loop were never affected.

## DQ-23 — `canEmbed` fails open at DISPATCH time; should it also fail open at CONFIGURATION time?

Found while proving `kg_project_set_embedding_model` (#253). Recorded, not decided — the fail-open
decision it rests on is deliberate, documented, and defensible.

Measured: I passed the tool a model whose provider-registry `capability_flags` are
`{"chat": true, "tool_calling": true}` — nvidia/nemotron-3-nano, the chat model this loop has been
using as an LLM all session. It was ACCEPTED: `changed: true`, `embedding_dimension: 1024`, and
the project's embedding model was set to it. A UUID I do not own is correctly refused
(`EMBED_MODEL_NOT_FOUND`), so the probe is real — the upstream genuinely answered an embeddings
request for a chat model with a 1024-dim vector.

That is NOT a bug in the tool. provider-registry's `canEmbed` gate is deliberately fail-open on
`chat`, and `embed_capability_test.go` says why in a case name: *"chat token fails open (not
rejected) — 'chat' is the discovery DEFAULT, not an affirmative exclusion. A BYOK embedding model
whose name misses the 'embed' heuristic is tagged chat; rejecting it would break a working
embedding call (review-impl HIGH-2)."* Only affirmatively-other capabilities (rerank, stt,
image_gen) are rejected. The tool's own comment inherits the assumption — "a probe failure means
the ref is unreachable or is not an embedding model at all" — and the probe cannot tell.

**Open question:** the fail-open trade was reasoned about for the DISPATCH path, where the cost of
a false reject is breaking a call that works. Configuration is a different trade. Setting a
project's embedding model is a one-time choice that then defines the vector space every future
passage is embedded into; a wrong one is not a failed call but a silently useless graph, and
correcting it later hits the orphaned-passage wall this same handler already refuses by name
(D-EMB-MODEL-REF-04). A false reject at configuration costs one clear error message the user can
route around by fixing their model's flags; a false accept costs a re-embed.

So: should `kg_project_set_embedding_model` (and the REST branch it mirrors) apply a STRICTER
capability check than the dispatch path — warn, or refuse, when the chosen model's flags carry no
positive embedding signal?

I did not change it. Deciding it needs the discovery-tagging accuracy I have not measured (how
often IS a real BYOK embedding model tagged chat-only in practice?), and knowledge-service holds
no provider-registry client today, so enforcing it here would introduce a cross-service dependency
and a new failure mode — registry unreachable means no model can be configured at all.

The tool's `embedding_model` parameter already tells the caller "pick one whose capability_flags
include embedding", which under a fail-open platform is exactly the right guidance. What is
missing is any signal when they do not.

## DQ-24 — `lore_entity` windows the facts but not the STATUS its description says it windows

Found while proving `lore_entity` (#268). The spoiler guarantee on facts is exact and verified;
this is one field beside it.

The description reads: "One entity's spoiler-windowed **status** + known facts, bounded to the
reader's furthest-read chapter". Measured on the same entity, same call, only the reading position
changing:

| reader state | window_available | kg_entity_id | status | facts |
|---|---|---|---|---|
| pinned at chapter 5 | true | 831f58cd… | `active` | **14** (of 27 — exactly the entitled set) |
| position removed | false | 831f58cd… | `active` | **0** |

Facts are windowed perfectly. `status` is returned identically either way, so it is not windowed
at all, and the description says it is.

**Open question:** is a KG entity's lifecycle status spoiler-bearing?

The argument that it is: status is `active` / `archived` / `merged`, and an entity archived or
merged at chapter 90 would show that state to a reader at chapter 5 — revealing that the character
is written out, or turns out to be the same person as someone else. That is a genuine plot
disclosure, and it is exactly the kind this tool exists to prevent.

The argument that it is not: status is a KG bookkeeping flag about the author's own curation, not
a narrative fact with a valid_from_ordinal. There may be no ordinal to window it by, in which case
the honest fix is the DESCRIPTION (drop "status" from the windowed list) rather than the code.

I did not decide it because the two readings lead to opposite edits and the answer depends on
whether entity status transitions carry a chapter ordinal at all — which I did not measure. What
IS measured: the field is not windowed today, and the description says it is.

Not blocking #268: no leak was demonstrated. Every entity I read was `active`, so I never observed
a status that would disclose anything, and the fact axis — the part carrying narrative content —
is provably correct.

## DQ-25 — should `registry_propose_workflow` check that a step's tool exists?

Found while proving the tool (#289). Everything else about it is sound and recorded there; this is
one question I will not answer by guessing.

Measured: a proposal whose only step names `no_such_tool_289` was accepted without comment and
recorded as `pending`, identical in every respect to a proposal naming a real tool. A user opening
the "Workflow Proposals" panel is therefore asked to approve a workflow that cannot run, and
nothing on the propose path tells either of them.

**Open question:** should propose validate each step's `tool` against the live tool catalogue?

For: the step's `gate` IS validated against a closed enum, with a self-correcting "not one of:
[...]" error, so the tool already draws a line between "a value I can check" and "a value I
cannot". A tool NAME is equally checkable in principle, and a workflow that names a tool nobody
serves is dead on arrival — catching it costs one refusal instead of a human review cycle.

Against: the agent-registry does not currently know the tool catalogue. Validating would couple it
to the federated MCP surface at propose time, adding a cross-service dependency and a new failure
mode (catalogue unreachable ⇒ no workflow can be proposed) to a path that today has neither. It
would also make a proposal's validity depend on WHEN it was made, which is awkward for a record
the user approves later.

A middle answer exists — record the unknown tool but flag it on the proposal so the review panel
can show it — and choosing between the three is a product decision about where that check belongs,
not something the code implies.

Not blocking #289: the tool's own contract (propose, never create) is verified, and the human
review step is exactly where a bogus tool would be caught today.


### DQ-26 — should a trashed book still count as a world member? (#308)

`world_delete`'s guard no longer counts `trashed` books, because `delete_book` produces exactly
that state and there is no detach on `world_move_book`, so the refusal's own remedy could not
clear it. But the world's **read** paths (`worlds.go:187/478/509/548`) still exclude only
`purge_pending`, so a trashed book keeps counting toward `book_count` and keeps appearing in the
world's member list.

Not resolved here: whether a book in the trash should show as a member of a world is a product
decision about the world detail view, and the tool under test was `world_delete`.

### METHOD — read the state, not the row's existence (#307 → #308)

In #307 I recorded that `world_delete` "left the bible book behind". I had queried `count(*)` and
seen 1. The row existing was the **purge queue working** — `lifecycle_state` was `purge_pending`
with `purge_eligible_at` stamped, which I never read. A surviving row is not a surviving object
when the schema has a lifecycle column. The #307 ledger note now carries the correction.
