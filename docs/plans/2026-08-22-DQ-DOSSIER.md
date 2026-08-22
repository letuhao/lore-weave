# THE DEFERRED-QUESTION DOSSIER — thirteen decisions, in one sitting

> **Cycle 0(a) of the [resolution loop](2026-08-22-tool-resolution-RUNBOOK.md).** The predecessor's
> rule was *record and continue, never ask*. That rule is superseded: these were deferred because
> they are **product decisions measurement cannot settle**, and thirteen of them have now
> accumulated, four of them load-bearing for cycles this loop is about to run.
>
> Each entry states **what was measured**, **why it was not decided by me**, the options already
> seen, and a **recommendation**. The recommendation is mine and is not a decision — the whole
> point of this document is that you make them.
>
> Three were unregistered until 2026-08-22 (`T36`, `T37`, `T38`) and now carry ledger rows.
> `DQ-T3` (a) and `DQ-T30` (c) are answered and shipped and are **not** re-asked.

**Load-bearing right now:** `T36` is cycle 1 (25 tools). `T35` blocks `composition_generate` in
cycle 2. `T32` is cycle 8. `T31` is cycle 11. The other nine are independent of the cycle order.

---

## The nine that change the platform's behaviour

### DQ-T36 — what decides which tools a turn advertises? **(cycle 1 — 25 tools)**

**Measured.** 30 of the 65 blocked tools surfaced 0/N across clean runs with zero transport errors.
**Three hypotheses are retired by measurement and must not be re-run:** ranking
(`world_map_update_marker` scores **#1 of 315** for its own prompt with the shipped scorer, and
surfaced 0/5; `world_map_update_region` **#2**), tier/scope/family (`settings_model_set_active`,
`_set_favorite`, `_update` all 0/5 in the batch where `settings_update_profile` went 5/5 and carded
5/5 — same scope, tier and family), and batch composition (`memory_timeline`: 5/5 in a batch, 0/5
alone, 0/5 alone, 0/5 in a batch).

**Why it matters more than reachability.** A dropped tool is still reachable through
`tool_list → tool_load`, and the model *does* use it — `registry_get_workflow` produced *"I do not
have access to its internal instructions without loading it first."* What is not survivable is the
other outcome: **when the missing tool is a WRITE, the turn reports the write as done.**
`world_map_update_marker` 5/5, `kg_triage_resolve` 5/5 (which rendered the post-resolution state to
make it convincing), `plan_keep_material` 4/5 with zero tool calls, `world_map_remove_region` 1/5.

**Options.** (a) reserve a slot for any tool whose declared synonyms match the request; (b) leave
selection alone and make the ABSENCE explicit to the model, as DQ-T3's withheld-stamp already does
for gated tools; (c) status quo — rely on the lazy tail.

> **RECOMMENDED: (a), and cycle 1 measures it before it ships.** (c) is the status quo and is
> measured to produce false success. (b) is already shipped for gated tools and the same batch
> showed the model *not calling* `tool_list`, so the notice would land where nobody reads it.
> **Caveat I want on the record:** the cause is still unknown, so (a) is a *policy* I can implement
> and not yet a *diagnosis*. Cycle 1 opens with diagnosis and this recommendation may not survive
> it — five prose-shaped hypotheses have already been refuted in this loop.

### DQ-T6 — may the hot-seed budget advertise a domain's WRITES while dropping its primary READ?

**Measured.** On the **editor** surface — the one built for authoring — a single turn advertised
**4 of composition's 107 tools** and withheld 49 more with *"did not fit the hot_seed token budget
(2000 tok)"*. Asked in plain prose to READ a chapter, the model called
`book_chapter_save_draft`: `book_read` had been budget-dropped while two writes were seeded.
**One of those substitutions overwrote a real chapter's prose with "This is a test."** and was
recoverable only because the write snapshotted first.

**Options.** (a) reserve a slot for each domain's reads before any write is seeded; (b) spend the
budget by relevance to the request rather than domain order; (c) raise the 2000-token budget;
(d) treat a read/write imbalance in a seeded domain as a loud failure.

> **RECOMMENDED: (a) + (d).** (b) is DQ-T36's option (a) by another name and they should be decided
> together. (c) alone buys headroom without changing the rule that produced a write-for-read
> substitution. (d) is cheap and turns a silent policy into an observable one.
> **These two DQs are the same mechanism seen from two sides** — I recommend answering T36 and T6
> as one decision.

### DQ-T31 — should the world-setup intent gate open on what the request ASKS FOR? **(cycle 11)**

**Measured**, two prompts, same tool, K=3 each. The **vague** ask left the gate open (0 withheld)
and the model correctly asked which kinds. The **concrete** ask — *"a kind called Faction with an
attribute Allegiance, and a kind called Artifact with an attribute Origin"*, world-setup by
definition — **shut it**: 4 tools withheld at `stage=intent_gate`, including the one asked for.
With it invisible the model reached for `glossary_adopt_standards` 3/3 and suspended on **its**
card — which adopts SYSTEM standards and would create neither kind.

**Options.** (a) add a declaration arm — if the request's own words match a gated tool's declared
synonyms, treat the turn as setup intent; (b) widen the skill router's phrase list; (c) leave it,
since N5a-FULL is a deliberate over-reach guard (its docstring records **40,597 characters of one
repeated paragraph** before the author hit Stop).

> **RECOMMENDED: (a).** It is the same shape as the consent check's existing declaration arm, so
> the precedent is in the codebase. (b) fixes these sentences and leaves the class. (c) keeps a
> guard whose current behaviour is *inverted* — it denies the concrete request and permits the
> vague one — and the measured consequence is a card for a different tool with different
> semantics, which is worse than a refusal.

### DQ-T5 — how does a NEW book get its first glossary entity?

**Measured** live across three sessions with every branch tried. A fresh book has no kinds, so
`glossary_propose_entities` refuses. Its remedy `glossary_adopt_standards` is intent-gated and was
**withheld in the same turn as the refusal that named it** — and stayed withheld even on the
explicit *"Set up my book — adopt the standard lore categories for it."* The non-gated alternative
`glossary_ontology_upsert` creates the kind but with no display attribute, so the propose is
correctly refused with *"refusing to create a nameless entity"*; adding a name attribute returned
`ok` and **changed nothing** — the retry produced a byte-identical refusal.

**Options.** (a) a refusal UNLOCKS the tool it names for the rest of the turn; (b) router injects
`glossary_shaping` on setup prose; (c) make `glossary_ontology_upsert` create a usable kind;
(d) bootstrap a default ontology with the book, as a knowledge project already is 197 ms after
creation.

> **RECOMMENDED: (d), with (c) as the honest fix underneath it.** (d) removes the cold-start
> entirely and has a working precedent in the same platform. (c) is a real bug regardless of which
> option wins — a tool that returns `ok` and changes nothing is a silent seam. (a) is elegant and
> re-admits exactly what N5a-FULL exists to stop.

### DQ-T32 — must a declared synonym match as a CONTIGUOUS phrase? **(cycle 8)**

**Measured.** Batch 12's natural experiment: perfect correlation between *"a declared synonym
appears verbatim"* and *"the tool was surfaced"*, 1/5 → 5/5 once declarations were widened. **Every
original miss was a pronoun substitution or an interposed word, never a different meaning.**
Sharpened: `composition_motif_bind_edit` declares `bind motif`; the prompt was *"Bind Emberfall
Vein to the opening arc"* — the two words split by the motif's own **name**. Naming the thing you
want bound is the most natural phrasing there is, and it is exactly what defeats the matcher.

**Options.** (a) keep it contiguous and keep fixing declarations; (b) relax to an in-order word
subsequence with a bounded gap; (c) weight by word rarity across the catalogue.

> **RECOMMENDED: (b), measured against the live catalogue before it ships.** (a) is working and
> scales with every phrasing a user can invent, which is not a bound. **The risk is real and must
> be measured, not argued:** `_synonym_pattern`'s word-boundary work exists because `cat` matched
> inside `category` and cost a live run, and **the consent check now depends on answerability too**
> — a read-only turn sets a standing write grant aside — so widening the matcher changes *consent*
> behaviour, not just surfacing. Cycle 8 should A/B it across all 315 tools before adopting.

### DQ-T33 — when a turn ends with no user-visible text, show the last TOOL error?

**Measured.** 21 runs across 8 tools produced no user-visible text with no card and no approval.
Root cause since found: the turn is **not empty** — it contains a stray `<tool_call|>` delimiter.
Only the RECORDING is fixed (`outcome=failed` instead of `completed`); the author still sees a
blank reply.

> **RECOMMENDED: retry the malformed call once, then surface the last tool error.** The question is
> now narrower than when it was filed — it is *"the model emitted a malformed call; retry, surface,
> or apologise?"* A generic apology is invented prose and **five prose interventions have been
> measured and refuted in this loop**. The tool's own message is usually the most useful sentence
> available. The cost is exposing internal tool vocabulary in the author's chat, which is a
> voice-and-surface call and is why this is yours.

### DQ-T4 — should glossary's 37 non-ambient tools DECLARE `book_id` required, or BECOME ambient?

**Measured** against the live catalogue and confirmed over the wire. 46 glossary tools declare
`book_id`; 6 correctly pair an optional `book_id` with `WithAmbientBook`; **40 declared it optional
without the tag** — a pairing `bookToolAuthAmbient`'s own comment forbids. T10-D1 fixed 3, leaving
37, which a test now logs **by name** so the number cannot quietly grow. Four sampled from
different files all answer *"book_id must be a UUID"* when it is omitted, so the declaration is
wrong for all of them.

> **RECOMMENDED: (a) declare required.** Honest, zero behaviour change, and it can ship this week.
> (b) is the nicer product outcome and is a real behaviour change across 37 tools on a
> studio-binding story that has its own edge cases — it deserves its own cycle rather than riding
> along with a declaration correction. Doing (a) now does not foreclose (b).

### DQ-T35 — should `composition_generate`'s `model_ref` become optional? **(cycle 2)**

**Measured.** 16 of 19 `model_ref` properties across the catalogue are optional and say so —
*"omit to use the author's default planner model"*. Only three are required, and
`composition_generate` is the outlier **on the tool where getting it wrong costs the most**.
Three resolution tiers were checked and **none is clean**: SESSION —
`composer_model_source`/`composer_model_ref` are empty on every harness session; WORK — of 664
`composition_work` rows, **0** carry `model_roles` and 13 the legacy `default_model_ref`, so a
Work-tier default is inert for 98% of books; ACCOUNT — `user_default_models` is populated but keyed
by capability `chat|distill|planner|rerank`, and **there is no composer/prose capability**.

> **RECOMMENDED: add a `composer` capability to `user_default_models`, then make `model_ref`
> optional.** Defaulting a prose-generation call through the `chat` model means spending the
> author's money on a model they never chose for it, which I will not pick for you. The missing
> capability is the actual gap; everything else is a workaround for it.

### DQ-T34 — should a `*_edit` tool accept the human-readable `code` its own sibling lists?

**Measured.** `composition_arc_template_edit(op=archive)` requires `arc_id` and refuses `code` with
*"op=archive requires arc_id"*. 5 of 5: the model would not resolve the name and asked the author
for a UUID. `code` is already unique per owner and is **what `op=create` takes**.

> **RECOMMENDED: yes, accept `code` on the template family.** The same tool already accepts it for
> `create`, so this is an inconsistency rather than a new contract. It also removes one instance of
> cycle 2's whole problem — the model will not walk a supplier chain — without waiting for a
> general fix. It does change the uniqueness story across the family, which is why it is yours.

---

## The four that are architecture or bookkeeping

### DQ-T37 — should `registry_propose_workflow` validate that a step names a real tool?

**Measured.** Of 10 proposed steps across 5 live cards, **3 named `chapter_compose`**, which is not
among the 315 federated tools — checked against the catalogue, not by eye. A direct probe confirms
it: `tool='totally_not_a_real_tool'` is accepted and proposed. **Three of five proposals would have
saved a recipe that cannot run**, under a name the author will trust later. The tool already
declares closed sets for `surfaces[]` and `steps[].gate`; `steps[].tool` is a free string.

**Why it is yours.** agent-registry-service has no access to the federated catalogue — that lives
behind ai-gateway — so validating means deciding *where the registry learns it*.

> **RECOMMENDED: (d) fail at RUN time with a message naming the missing tool, plus a warning on the
> card.** A propose-time call couples the registry to gateway availability on a write path; a
> periodic sync adds a staleness window that will itself produce a wrong answer. Run-time
> validation is where the truth is anyway. **What I would not do is leave it silent**, which is the
> current behaviour.

### DQ-T38 — why does the public catalogue list nothing while 44 books are marked public? **(cycle 7)**

**Measured.** `loreweave_sharing.sharing_policies` holds **44 rows with `visibility='public'`**
(against 13 private, 1 unlisted). `catalog_list_public_books` returns `{items: [], total: 0}`.
`catalog_get_book` returns *"book not found"* for an unknown id, for the caller's own private book,
**and for a book that IS marked public** — uniformly, which is correct (no existence oracle) and
also no help. **Not diagnosed further, deliberately:** `loreweave_catalog` holds only
`catalog_runtime_state`, so the listing is built elsewhere.

> **RECOMMENDED: treat it as cycle 7's diagnosis, not a decision.** I do not think there is a
> product question here yet — there is a pipeline nobody has traced. What I need from you is only
> whether a `sharing_policies` row is *supposed* to be sufficient for publication, or whether a
> separate publish step exists that 44 books have not taken.

### DQ-T2 — must a deprecated tool name its replacement?

**Measured** against the live catalogue. **117 tools carry `visibility='legacy'`; 62 name a
successor and 55 do not** (glossary 28, book 11, kg 11, lore 4, composition 1). `tool_list`'s own
description promises *"deprecated tools are labeled with their replacement"* — so for **47%** there
is no label. Observed live: asked what replaced `book_get`, the model built an accurate migration
table for the tools that name one and could say nothing actionable about `book_create`,
`book_chapter_delete`, `book_purge` or `book_set_cover`.

> **RECOMMENDED: (a) make `superseded_by` mandatory for `visibility=legacy` and fill the 55**, with
> an explicit `superseded_by: null, retired_reason: "..."` for any that genuinely have no successor
> — so the promise `tool_list` already makes becomes true. This is 55 small decisions someone who
> knows each tool must make; I can produce the list grouped by service with a proposed successor
> for each, and you correct it.

### DQ-T1 — what is `entity_lifecycle_ledger` for, and what should write it?

**Measured.** The table exists with an append-only trigger guard and columns `op, prior_status,
new_status, actor_type, actor_id, reason` — the exact vocabulary of a curation status change. It
holds **three rows, all from 2026-08-11, all `op='deleted'/'restored'`, all with `prior_status` and
`new_status` NULL**. A repo-wide search for `lifecycle_ledger` finds **nothing in source**; the only
database function referencing it is the guard. Four entities were moved `draft → active` live and
the ledger gained no rows. **A table with a guard, no writer, and a column set describing a
transition nobody records.**

> **RECOMMENDED: (a) make curation append to it.** The columns already describe what an audit trail
> needs and the append-only guard says someone intended exactly that. **But this is the one I feel
> least strongly about** — (c), dropping it as superseded by `entity_revisions`, is defensible and
> cheaper, and the honest position is that nobody currently depends on it either way.

---

## What happens after you decide

Each answer becomes a cycle or folds into one already scheduled. Answers are recorded in
`contracts/tool-deep-dive-ledger.json` under the DQ's own row as `decision`, with the date and the
option letter, the way `DQ-T3` and `DQ-T30` already are — so no later session re-opens a settled
question.

**T36 and T6 I recommend answering as one decision**, since the measurements are two views of the
same mechanism. Everything else is independent.
