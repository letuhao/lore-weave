# Pending-refactor debt register

**Opened 2026-08-03** · covers **three tracks whose debt outlived the run that created it**:
the glossary↔KG entity refactor (this folder), the
[chat-service control-plane refactor](../2026-07-30-chat-service-control-plane-refactor.md), and
the [generation SSOT](../2026-07-31-generation-ssot.md).

> **Why one file.** All three are *deferred structural work with residue*, and in every case the
> residue was surviving in a place that will not outlive its run — a Parked row inside a RUNSTATE,
> a sentence in a spec, or nothing at all. Three of the items below were recorded as **closed**
> and are open; four had no written home of any kind.

## How to read it

- **`id`** is `YYYY-MM-DD-NN` — the date the debt was **first recorded in writing**, then a
  sequence within that date. Stable; it does not change when the item moves phase.
- **★ = this file is the item's ONLY home.** Everything else is a pointer, and the linked row is
  authoritative. Do not restate a number here that a command or another register already prints —
  that is how a second source of truth starts (the generation-SSOT run recorded that exact
  mistake as its own debt row).
- **`re-verified`** means the claim was re-run against `24dd7bdac` on 2026-08-03. Rows without it
  are carried from their source document **as written** and have not been re-checked.

---

## A · glossary↔KG entity refactor

Full context: [`README.md`](README.md). All rows also appear in the **Deferred Items** table of
[`docs/sessions/SESSION_HANDOFF.md`](../../sessions/SESSION_HANDOFF.md).

| id | item | state |
|---|---|---|
| **2026-08-03-01** | `D-GLOSSARY-KG-REFACTOR-DESIGN` — three investigations, **no design**. The entry point; nothing else in section A can be worked first | open |
| **2026-08-01-01** | `D-ENTITY-IDENTITY-HASH` — identity is `hash(user, project, name, kind)` over LLM output; a miss mints. **21 of 21** `:EntityStatus` rows unreachable by the guard's FK lookup | **parked** by author 2026-08-02 |
| **2026-08-02-01** | `D-ENTITY-LIFECYCLE` — five private notions of "gone", no event between any two. Game-tier critical | open |
| **2026-08-02-02** | `D-KG-KIND-FACETS` — the **KG-mirror half** of the kind spec's M4 (`kind_code TEXT NOT NULL`) | open |
| **2026-08-02-03** | `D-GLOSSARY-EVENTS-NO-SOT` — three `glossary.*` events outside the "AUTHORITATIVE" registry. **Fires first** of section A: `glossary.entity_deleted` needs it | open |
| **2026-08-02-04** | `D-KIND-FACETS-SURFACE` — the **API + FE half** of M4. 399 entities carry a facet; no consumer can see one | open |
| ★ ~~**2026-08-03-02**~~ | ~~`D-ENTITY-EXISTS-GUARD` — `entity_genres_handler.go:40` has no `deleted_at IS NULL`; guards 6 paths, one of which fires a **paid LLM call** on deleted content and caches it~~ | ✅ **CLOSED** 2026-08-09 · plan T1. The guard resolves liveness through `entityDeleteState`, so *absent* and *in the recycle bin* stay distinguishable and only the second logs `WARN`. **Mechanism:** `entity_lifecycle_guard_test.go::TestDeletedEntity_CanonicalTranslationRefusedAndSpendsNothing` + `scripts/entity-lifecycle-guards-live-smoke.sh`. **Measured, not argued:** on the pre-fix binary rebuilt for the check, a trashed entity returned `200 translating` and **claimed 1 translation row — a paid MT fill launched on author-deleted content**; with the fix, 404 and 0 rows |
| ★ ~~**2026-08-03-03**~~ | ~~`D-KNOWN-ENTITIES-PER-JOB` — `extraction_worker.py:473` fetches before the chapter loop at `:556`; a deleted entity is re-emitted for the rest of the job~~ | ✅ **CLOSED** 2026-08-09 · plan T2. The known set is re-fetched at every chapter boundary; entities the run itself created — below the server's `min_frequency` floor, so invisible to that read — are pruned by a batched liveness probe on the same boundary. **Mechanism:** `tests/test_extraction_known_entities_refresh.py` (4 tests). **Bite:** restoring "fetch once per job" makes the deleted entity survive into chapter 2 and the per-chapter fetch count fall 3 → 1. The cross-service contract the prune leans on (`entities/by-ids` drops a soft-deleted id) is proven live; the worker leg itself is unit-only and takes its live exercise in QC-4 |
| ★ ~~**2026-08-03-04**~~ | ~~`D-OUTBOX-PAYLOAD-TRASH` — `outbox.go:398` re-publishes a trashed entity on edit; knowledge-service re-embeds it, silently reversing the deletion~~ | ✅ **CLOSED** 2026-08-09 · plan T3. The payload read is lifecycle-filtered **and** the transactional emitter checks liveness inside the writing tx — its callers discard the `ok` flag by design, so the filter alone would have emitted an *empty* payload rather than none. **Mechanism:** `entity_lifecycle_guard_test.go::TestDeletedEntity_EditEmitsNoOutboxEvent` + the live smoke. **Measured:** pre-fix, editing a trashed entity published 1 outbox row and **2 frames reached `loreweave:events:glossary`** — the deletion reversed in a consumer's index, observed rather than inferred; post-fix, 0 and 0 |
| ★ **2026-08-03-05** | `D-CANON-CHECK-BLIND-TO-ROLE` — a `cast_plan` names Lâm Trạch the trap-setter; the drafting run gave the trap to `Lâm Diệp`, a `rival` **minted seven minutes earlier** by the `cast` pass, and the critic scored **`canon_consistency = 5/5`** on all three chapters. Nothing holds a role assignment where a check can fail on it: the plan has it as free text, the glossary has two untyped `character` rows, the graph has neither. **Kind was correct on both entities — this is not a kind bug** | open · [evidence §1](2026-08-03-dogfood-entity-consistency-evidence.md) |
| ★ **2026-08-03-06** | `D-BOOTSTRAP-PREVIEW-LIES` — `bootstrap_service.propose()` dedupes glossary seeds against *prior proposals only*, never against the book, while the chapter half of the same function does query the book. Offered **12 "NEW GLOSSARY ENTRIES"** that all existed, each rendered `Character` (real kinds: `power_system`, `organization`, `event`, `item`). Apply is safe — upsert-by-name preserved the kinds — so this is a **human-approval gate showing a claim that is wrong on both novelty and kind**, not corruption | open · [evidence §2](2026-08-03-dogfood-entity-consistency-evidence.md) |
| ★ **2026-08-03-08** | `D-UNKNOWN-PARK-IS-PROSE-NOT-DATA` — an entity parked under `unknown` keeps its unmatched attributes only as PROSE: `appendUnmatchedAttrsToFallback` joins them into `- code: value` lines and appends them to the kind's `description`. That is the right instinct (losing the observation is worse than filing it badly) and the wrong SHAPE for the consumer — the thing that will read them is a later kind-resolution pass deciding what this entity actually IS, and it would have to re-parse prose the extractor had already delivered structured. `source_kind_code` remembers the code it arrived as; the raw attribute payload is the missing other half. **Author-proposed 2026-08-03: a JSONB column on the parked row.** Not urgent while parking is rare; load-bearing the moment the refactor tries to re-kind parked entities in bulk, which is the whole point of the bucket | open · [evidence §2 context](2026-08-03-dogfood-entity-consistency-evidence.md) |
| ★ **2026-08-03-07** | `D-KG-EDGE-TYPING-UNCHECKED` — the relationship proposer offered 8 edges, **3 defensible**: one category error (a `power_system` `enemy_of` a person) and two reversed (`event` `betrayed` the two characters who *are* the betrayers). Every fact needed to reject them is already in the glossary kinds the proposer does not consult | open · [evidence §3](2026-08-03-dogfood-entity-consistency-evidence.md) |

**02 · 03 · 04** were declared *"not deferrals — fix now"* and then described as *"already closed."*
That sentence was their entire tracking mechanism, and it was false. They are **fix-now**, not
deferrals: this register exists so they cannot be lost a second time, **not** to license
deferring them.

> ✅ **All three are now genuinely closed — 2026-08-09, Phase 0 of
> [the knowledge-architecture plan](../../plans/2026-08-09-knowledge-architecture-refactor.md).**
> The difference from the first "already closed" is the point: each row above cites a **test that
> fails without the fix** and a **live smoke run against a rebuilt binary on a real stack**, and each
> quotes what the pre-fix code actually did — a paid machine-translation call bought on deleted
> content, and two event frames re-anchoring a deleted entity in a consumer's index. Prose said
> closed last time; this time the mechanism says it.
> *(No `SESSION_HANDOFF.md` change accompanies these: that file has no Deferred Items table and never
> carried these three ids — this register is their only home, which is why it was created.)*

**05 · 06 · 07** are the 2026-08-03 dogfood rows, and they are a different kind of item: each was
observed in *output a reader would see*, not in code. Their evidence lives in
[`2026-08-03-dogfood-entity-consistency-evidence.md`](2026-08-03-dogfood-entity-consistency-evidence.md),
which also records what the same run proved WORKS — a defect list with no baseline is not evidence.
**05 is the acceptance case for this whole refactor:** a design that cannot prevent it has not
addressed the problem. 06 is small and self-contained (fix-now-shaped, one function); 07 needs the
kind-typing this refactor is already re-cutting, so it waits on the design.

### A-extra · ✅ `D-KG-FACT-VOCAB-DISJOINT` — found AND fixed 2026-08-11 · **CLOSED**

**The story extractor and the KG fact writer speak two vocabularies that share exactly one
word, and the writer silently drops everything else.**

| producer | vocabulary |
|---|---|
| `loreweave_extraction.extractors.fact.FactType` (what the LLM is prompted for) | `description` · `attribute` · `negation` · `temporal` · `causal` |
| `neo4j_repos/facts.FactType` (what `merge_fact` accepts) | `decision` · `preference` · `milestone` · **`negation`** · `statement` · `commitment` |

`pass2_writer` validates the first against the second. The intersection is `negation`.

**The live graph shows the consequence exactly**, which is why this is a measurement and not a
suspicion — 94 `:Fact` nodes, corpus-wide:

```
negation    64      <- the ONLY overlapping type
preference  17  |
decision    11  |-- chat-memory writes, a different producer entirely
statement    2  |
```

Story extraction has contributed **only negations, ever**. Every `description`, `attribute`,
`temporal` and `causal` fact it produced was dropped at
`pass2_writer.py` (*"skipping fact with unknown type"*), and a run observed live logged
`persist-pass2 done entities=4 relations=5 events=0 facts=0`.

**Why this is NOT filed as a fix.** Two reasons, and both are about respecting a seal rather
than working around it:

1. **The enum is a documented 4-site lockstep with an incident behind it.** Its own comment:
   *"Adding it here (the SoT) must move IN LOCKSTEP with the models.py mirror + the
   `knowledge_pending_facts` CHECK x2 — the exact drift that 500'd a `statement` fact at
   merge_fact."* Widening it is a migration, not an edit.
2. **The sealed direction may make the destination wrong.** §9 **O1** consolidates on ONE
   physical truth store and names `entity_facts` the working bitemporal SSOT. If story facts
   belong there, widening the Neo4j chat-memory enum builds on the layer being retired.

## RESOLVED — and the fix was narrower than either option first priced

Neither "widen the enum across 4 sites + a migration" nor "re-home story facts in
`entity_facts`". Checking *who actually writes the pending-facts queue* collapsed the problem:

`knowledge_pending_facts` has exactly **two** writers — `tools/executor.py` (the
`memory_remember` chat tool) and `routers/internal_admin.py` (the diary distiller, always
`'statement'`). **Story extraction never queues**; `pass2_writer` calls `merge_fact` directly.
So the queue's domain is memory-only *by construction*, and no CHECK migration was needed. The
lockstep comment asked for a wider change than the code does.

So the two families are **named** instead of merged into one enum pretending to be homogeneous:

```python
MemoryFactType = Literal["decision","preference","milestone","negation","statement","commitment"]
StoryFactType  = Literal["description","attribute","temporal","causal"]
FactType       = MemoryFactType | StoryFactType
FACT_TYPES     = MEMORY_FACT_TYPES + STORY_FACT_TYPES     # `negation` is shared, appears once
```

`PendingFactType` (models.py) stays **memory-only**, and that is now a stated invariant rather
than an accident: widening it would admit a value nothing can produce and invite the opposite
drift — a queue accepting what the confirm path cannot promote.

**Three lockstep guards fired on the first run and were right to.** One of them caught a
regression the change introduced: `tools/definitions.py` built the `memory_remember` tool's
JSON-schema enum from `FACT_TYPES`, so widening it would have offered *story* kinds to the chat
model and let it queue an unpromotable fact. Both inbox-facing enums (`definitions.py`,
`graph_schema_tools.py`) now derive from `MEMORY_FACT_TYPES`.

**Proven live**, through the real dispatch-extraction path, not a fixture:

```
before   negation 64 · preference 17 · decision 11 · statement 2
after    negation 64 · description 32 · preference 17 · decision 11
         attribute 3 · statement 2 · temporal 2 · causal 1
```

**38 story facts persisted where the vocabulary had been dropping them** — every one of the
four previously-impossible types, first time ever. In the acceptance project alone: description
32, attribute 3, temporal 2, causal 1.

Bitten: `FACT_TYPES = MEMORY_FACT_TYPES` alone → the three guards go red; restored → green.
knowledge-service **4532 passed, 307 skipped**.

**Reproduce:** `MATCH (f:Fact) RETURN f.type, count(*)` — an overlap-only distribution was the
finding; four story types present is the fix.

---

## B · chat-service control plane — [`D-CHAT-CONTROL-PLANE`](../2026-07-30-chat-service-control-plane-refactor.md)

**Nothing has been built.** Verified 2026-08-03: no availability SSOT exists in chat-service
(`grep -rn "def availability\|class Availability\|Withheld" services/chat-service/app` → 0), and
`stream_service.py` is unchanged since the spec was written. The interim fixes of 2026-07-30
shipped and are not a substitute — the spec says so itself.

| id | item | state |
|---|---|---|
| **2026-07-30-01** | §A **tool-availability SSOT** — eight places independently answer *"is this tool available, and if not why?"*. Its invariant test (*"for every step of a pinned rail, availability is never `Withheld`"*) is the check that would have caught the originating incident on the day it was introduced | open |
| **2026-07-30-02** | §B **`TurnState`** — one owner of rail cursor / active tools / breaker counters, recomputed at defined lifecycle points. The mid-turn staleness bug is structural and will return under another name until this exists | open |
| **2026-07-30-03** | §C **guards become policies** over `TurnState`, evaluated in one place with logged precedence. Down-payment already made: `_rail_is_in_flight` | open |
| **2026-07-30-04** | §D **cross-mechanism invariant tests** — every mechanism has unit tests for itself; nothing tests them against each other, which is why a contradiction survived | open |
| ★ **2026-07-30-05** | §E the **anti-rot rule** has no home. It is not a row in [`docs/standards/README.md`](../../standards/README.md) and not in its *Known gaps* list. The index's **Agent Control Plane** row governs a different thing (*consuming* the control layer via the ACP SDK), so it does not cover this. Per CLAUDE.md a cross-cutting rule must have a row there — a rule living only in a spec is the shape the standard itself warns about | open · *re-verified* |
| ★ **2026-08-03-05** | **The deferral has no mechanism.** `docs/sessions/SESSION_HANDOFF.md` contains **no `deferral-registry:begin/end` block** (the repo's only one is in the LLM_MMO_RPG handoff), so `scripts/deferral-gate.py` never sees `D-CHAT-CONTROL-PLANE`. Its trigger — *"before the next feature that adds a control mechanism to the turn loop"* — is enforced by nobody noticing. **Not yet fired:** the only post-spec change to `tool_surface.py` (merge `1dc1509ed`) is a 7-line comment | open · *re-verified* |
| ★ **2026-08-03-06** | **The spec's own inventory is stale or unaddressable**, so whoever executes it recounts from scratch: `stream_service.py` is **7,818** lines, not 7,074; the 16 named caps all exist but `chat-service/app` carries ~8 more cap-shaped constants outside the list (`NARRATED_WRITE_NUDGE_CAP` in the same file, plus `ACTIVATED_TOOLS_CAP`, `RAIL_STEP_TOKEN_BUDGET`, `HOT_SEED_TOKEN_BUDGET`, `STORY_STATE_TOKEN_CAP`, `STEERING_TOKEN_CAP`, `SUBAGENT_MAX_ITERATIONS`, `ROUTER_MAX_ADDITIONS`); and 3 of §A's 8 availability places are not addressable by name (`done_suppress` is not a `def`, the repeated-failure de-advertiser is unnamed, and the eighth is *"(as of tonight) the auto-load guard"*) | open · *re-verified* |
| ★ **2026-08-03-07** | **The spec has no DoD, no order, no size, no gate spec.** §D's three bullets are the closest thing to acceptance criteria, and there is no incremental landing strategy for introducing a `TurnState` into a 7.8k-line function — which is the whole risk of §B | open |

---

## C · generation SSOT residue — [`2026-07-31-generation-ssot.md`](../2026-07-31-generation-ssot.md)

The slice board is **CLEAR** (S1–S13 closed 2026-08-01 → 08-03). These outlived it.

### C1 · Already homed — pointer only

**13 open rows** in the *Debt taken on* register of
[`docs/plans/2026-07-31-generation-ssot-RUNSTATE.md`](../../plans/2026-07-31-generation-ssot-RUNSTATE.md#debt-taken-on)
(the struck-through rows there are cleared; do not re-read them as open). That register is
authoritative and is **not** copied here. Its themes, so this file is greppable: plan-liveness
prevention shipped **disproven** · a second `story_order` convention on 16 dogfood scenes + the
writer that produced it · smoke debris · S13's citation half · `chat.*`/`composition.*` trace
namespacing · the **unmeasured cost** of counting ~40% more CJK/Vietnamese tokens · the kernel
estimator's own ~0.78× skew · an uncached identity resolve · no Rust check-status vocabulary
mirror · red-ability proof missing on most CI gates · 7 of 11 sweep cases not in CI · the
output-budget window clamp never exercised in production · no FE surface renders *why* a stream
was unguarded.

### C2 · ★ NOT homed anywhere — found by the 2026-08-03 completeness audit

Each is a §3.1 carry-forward row of the spec whose **owning slice closed without discharging it**,
or a §5 requirement that no slice ever owned.

| id | item | state |
|---|---|---|
| ★ **2026-08-03-08** | **B1 → S11 (closed):** `cowrite.py:350` `_TOKENS_PER_WORD` still duplicates `loreweave_llm.budget.TOKENS_PER_WORD` byte-for-byte — a third home for language-density constants. `cowrite` already imports from that module at line 30, so the dedup is a two-line change nobody made | open · *re-verified* |
| ★ **2026-08-03-09** | **S12-widen:** `scripts/enforcement-claims-gate.py` still checks **contract files only** (*"That is deliberately narrow"*, per its own docstring). It does not cover the B5 class — a **comment** asserting a guarantee — nor the `INV-*` code-invariant rows in the standards index. Those are the two shapes that produced two of that cycle's three worst findings, and the owner "S12 (widen)" was never a slice on the board | open · *re-verified* |
| ★ **2026-08-03-10** | **B4 → S9 (closed *inverted*):** `learning-service/app/db/online_judge.py` records no `generator_model`/`judge_distinct`. The carry-forward row said it *"needs the `ScoreReport` shape, which is S9's"* — S9 correctly shipped as **extract nothing**, so that shape was never built and the row lost its owner | open · *re-verified* |
| ★ **2026-08-03-11** | **B4 → S6 (closed):** `routers/wiki_judge.py:132` still passes `generator_model=art.generator_model` with the comment `# None ⇒ persisted as judge_distinct: null`, so the wiki path's distinctness stays unrecorded. (The translation path *was* fixed — `decoupled_judge.py:382` supplies the run's `model_ref`) | open · *re-verified* |
| ★ **2026-08-03-12** | **§5 Migration surface has no slice, no owner, no place in §6's order, no risk boundary and no DoD clause** — and two of its explicit demands are unmet: `contracts/guard-status.contract.json` carries `CheckStatus` only (no `wiki.generation_status`, the Go-owned union §5 names as having *"no contract file and no drift test"*), and the per-surface **null-semantics decision** (does NULL fail open or closed?) is recorded nowhere, including §8's decision log | open · *re-verified* |
| ★ **2026-08-03-13** | **B3's declared-unwired pair** — `YamlGuardrail` stays unwired until an L3-event write path exists, and `contracts/.spectral.yaml` stays unwired per DEFERRED 078. Both are honestly *declared* rather than claimed, which is correct; they are listed so the declaration has an expiry to check | declared, open |
| ★ **2026-08-03-14** | **Suite restoration is written and measured but NOT executed** — knowledge-service still carries **561 skips** and `-n auto` remains unsafe there (12 failed + 118 errors). Plan: [`docs/plans/2026-08-01-test-suite-restoration.md`](../../plans/2026-08-01-test-suite-restoration.md) | open *(carried from the RUNSTATE overview, not re-measured)* |
| ★ **2026-08-03-15** | **The spec itself is stale as a live document.** Header still reads `SPEC v2 (post-red-team)`; §6 marks only PHASE 0 + ROT-1 done, while the board is clear. §S6's stated blocker — *"`CompositionSettingsView` contains no `critic` string"* — is false at HEAD (14 occurrences; `modelRoles.ts` calls it *"the only UI that sets a critic"*). §6's order omits **S13** entirely, and the risk boundaries omit S3, S6, S8, S12, S13. DoD item 5's *"one pass registry"* is owned by no slice; S8, S9, S10 and S13 have no DoD clause | open · *re-verified* |

---

## Counts

| track | open | of which this file is the only home |
|---|---:|---:|
| A · glossary↔KG | 9 | 3 |
| B · chat control plane | 7 | 3 |
| C · generation SSOT | 13 + 8 | 8 |
| **total** | **37** | **14** |
