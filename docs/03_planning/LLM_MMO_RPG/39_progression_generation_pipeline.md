# 39 — The progression generation pipeline: a book's cultivation ladder becomes rules

<!-- design-lint: ok prefix ML — `ML-4` is a Multilingual / Anti-Language-Bias rule owned by docs/standards/multilingual.md on the PLATFORM track. It is cited here (2026-07-31) because a /review-impl probe found this module's tier-name expansion could only emit ASCII digits over a Chinese corpus. Registering `ML` in this track's id catalog would claim another track's namespace, which is the opposite of what the catalog is for. -->

> **Status:** DESIGN v2 — rewritten 2026-07-30 after a four-lens red team. Prefix `PGN-*`, registered
> in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> **Parent:** [38 — the content pipeline](38_content_pipeline_architecture.md). Doc 38 says each
> element gets its own module under one six-part contract (`CPL-A3`). **This is the first module**,
> and the POC: if the pipeline cannot be trusted for progression, it cannot be trusted for anything,
> because progression most directly decides what happens to a player.
>
> **Target schema:** [`PROG_001`](features/00_progression/PROG_001_progression_foundation.md) §4–6,
> LOCKED. This document does not design `ProgressionKindDecl`; it designs how one gets built from a
> book without anyone having to take a model's word for it.

---

## 0 — What this document must prove

**Produce a progression manifest, and make every value in it accountable to something a human agreed
to.**

Not "produce plausible output." A model will produce a beautiful 24-tier ladder from a two-paragraph
prompt. The hard part is that six months later, when a player asks why Foundation Building takes
forty hours, somebody can answer.

### 0.0 — Two exit criteria, and only one of them is this pipeline's

v1 said *"loads **and plays**"* as one sentence. It is two claims with two different owners and two
very different prerequisites, and merging them would have let this document claim credit for engine
work it does not do.

| | Claim | Needs | Owner |
|---|---|---|---|
| **POC-1** | book → wiki → questions → answers → fold → policy → generate → **admitted by the real validator → pinned → the ruleset digest moves → the epoch switch fires** | `S-1` + the fixture | **this pipeline** |
| **POC-2** | a spawned actor trains, breaks through, and the ladder changes what happens in a fight | `Q2 B4` (the `QTY-A8` caps arm) + **`Q4`** (the L3 contribution trait) | the **engine** — doc 35's build plan |

**POC-1 is the pipeline proof and is what this document is accountable for.** POC-2 is sequenced,
not deferred: `Q4` is unbuilt work in doc 35's own slice list, not an external dependency.

> **`PGN-A19` — the pipeline generates DECLARATIONS (L2) against a FIXED vocabulary of compiled-in
> contribution mechanics (L3). It can never generate L3.**
>
> Doc 35 §3 prices the layers and the price is the whole constraint: an L2 declaration costs *a
> ruleset edit, no engine release*; an L3 source costs *an engine release*. A new progression system
> needing new logic is **two separately-priced events**, and the pipeline can only ever buy one of
> them.
>
> So the honest claim ceiling is: **this pipeline produces realities that are re-tunings and
> re-namings of mechanics an engineer already wrote.** A book with a genuinely novel cultivation
> mechanic needs an engineer. This is `CPL-A17` (*a generated effect is a composition of engine
> primitives, never executable logic*) one tier up, and it is why `PGN-A20` below is a refusal rather
> than a smaller scope.
>
> ⚠ Doc 35 §3 also states the schedule fact: *"L2 is the layer that does not exist today. **L3 exists
> only as an unfilled label.**"* A generated ladder before `Q4` is **inert** — correctly named,
> correctly capped, admitted, pinned, and contributing nothing to any stat.

### 0.1 — What the first draft got wrong

Kept in place, not laundered. A document about trustworthiness that hides its own review damage is
self-refuting — and the pattern in these findings is the reason the rest of the document is shaped
the way it is.

| # | v1 claimed | Actually |
|---|---|---|
| 1 | §7: the `CapRule`×`CurveDecl` matrix is *"a real refusal surface that **exists today**"* | **`ProgressionSchemaValidator`, `progression.training.rule_invalid`, `ProgressionKindDecl`, `TierDecl`, `CapRule` — ZERO hits across `crates/`, `services/`, `contracts/`.** `PROG_001` §5.5 is a markdown table containing a sentence about a validator. No validator exists. |
| 2 | `PGN-A6` bite-test: *"perturb the policy, assert `structure_hash` unchanged"* | S5 is `fn(structure, policy) → artifact` and fetches S3 **by digest** — `structure_hash` is an input the test supplies. **It asserts an input equals itself.** `NV-2`. |
| 3 | `PGN-A2`: a fingerprint makes *"coverage computable"* | It compares brief-version to type-version. **Deleting a question row moves neither operand** — the stated failure mode is the one case it cannot see. `NV-2`. |
| 4 | T6: *count-in = count-out + count-refused* | Well-defined only at S5→S6, the one boundary with nothing at risk. S2→S3 is many→one, S3→S5 is one→many. **`PGN-A9`'s own example passes T6.** |
| 5 | §8.3: i18n exclusion *"already enforced"* by `QuantityError::BadName` | The quoted sentence is a **`Display` format string**. The real validator is `QuantityName::new`, whose subject is declared-quantity identifiers and **never reaches `TierDecl.name`**. `NV-3`. |
| 6 | §8.1: *"3 kinds × 24 tiers × ~48 B ≈ 3.5 KB exceeds the 2312 B ceiling"* | `48 B` drops two of `TierDecl`'s six fields (~6× low); "three heap `Option`s" is four; "3 kinds" contradicts **this document's own §10**, where only one kind is `Stage`; and `24 × 48 = 1152 < 2312`. **The headline did not follow from its own numbers.** |
| 7 | §8.2: a second binding hash *"cannot"* ride the epoch path | Buildable — `ALTER TABLE`, JSON payload, serde struct. *"I'd have to build it"* ≠ *"cannot"*. The real objection was missed (§8.2 below). |
| 8 | S3 produced the *"creative structure"* | S3 was an **ungated LLM pass**, so the concatenation `PGN-A3` forbids happened **inside inference**, where no column constraint reaches. S3 was the laundering stage. |
| 9 | §4.1's nine questions cover the schema | **23 schema positions had no producer at all.** ~19 authored values were expected to fill ~195 required fields. |
| 10 | Eight trust properties | An **all-`not_stated` run passed all eight** and shipped a manifest authored 100% by the policy file. |
| 11 | `PGN-Q1`: *"3 × 24 × 9 is a few hundred"* | Assumes all three fixture systems are staged; §10 makes one staged. Real count **121**. |
| 12 | `gamegen_numeric_policy` | Declared **no tenancy tier**, while every sibling table did — the omission that decides who authors magnitudes. |

Five of those (1–5) are checks that **cannot fail**, in a document whose §11 preamble states the rule
and whose `PGN-A8` cites `NV-1` by name. [`non-vacuity.md`](../../standards/non-vacuity.md) records
the defect shipping 27 times, twice by authors who had the standard in mind, and concludes **"intent
is not a mechanism."** That is the finding this rewrite is built around, not a footnote to it.

**Measured during review** (`2312` → `2311`, build, revert):

```
size_of::<Ruleset>() <= 2311  →  error[E0080]: evaluation panicked
size_of::<Ruleset>() <= 2312  →  passes
```

`size_of::<Ruleset>()` is **exactly 2312. Headroom is zero** — any addition trips it, even a `u8`.

---

## 1 — The trust question, stated concretely

A book says 陳玄一在寒潭閉關三年，終於破入築基。 A manifest says
`tier_index: 9, tier_max: 500, breakthrough: AtMaxPlus{...}`. Between them sit **five** decisions
with five different owners:

| Decision | Owner | Auditable how |
|---|---|---|
| 築基 is a *tier* | the book | cites a chunk span |
| it follows 練氣, which has nine sub-levels | the book | cites a chunk span |
| the sub-levels are named 一層…九層 by convention | the book (a **pattern**, stated once) | cites a span; expanded deterministically |
| advancing needs a pill and a sealed place | **model** (enrichment) | marked, no span, human-approved |
| `tier_max` is **500** | **the numeric policy** | a human-authored artifact |

> **`PGN-A0` — those five decisions have five different owners, and the pipeline's shape is whatever
> keeps them separate.** Everything below follows.

v1 had four rows. The missing one was **naming**, and its absence was load-bearing: `PGN-A5`'s
cardinality/magnitude split returns *no verdict* on a string, so 22 tier names were being invented
below the human signature by a stage nobody reviewed. Naming is now an owner, and the owner is the
book — as a **pattern**, which is how these books actually work.

---

## 2 — The stage chain

```
S-1  SCHEMA + VALIDATOR      Rust: ProgressionKindDecl, ProgressionTable, the validator
      │                      ── BUILT FIRST. It does not exist (0.1 #1).
S0   corpus                  source_corpus / source_corpus_chunk + a SEAL   EXISTS (seal is new)
      │
S1   brief                   question set, derived from the RECURSIVE schema closure
      │
S2   interrogation           one prose answer per (question, target) ──────── gate
      │                      says[] (span REQUIRED) │ proposed (span FORBIDDEN) │ not_stated
S3   fold                    DETERMINISTIC. no model. dense. ─────────────── gate
      │                      + consumption ledger, both directions
S4   policy                  magnitudes. human-authored. System-tier default. fixed-point.
      │
S5   candidate               procedural: shape x policy -> typed rows ────── gate
      │                      admitted by S-1's validator; repair is TYPED
S6   pinned                  progression bytes in the store;
                             progression_digest inside the Ruleset          EXISTS (Q0b/Q2)
```

**S-1 is new and is the critical path.** `CPL-A2`'s second clause already required it — *"where none
exists the validator is built BEFORE the generator"* — and v1 skipped it by misreading a catalog row
as shipped code. There is nothing to generate *into* until S-1 lands.

**S0–S2 are Python** (`lore-enrichment-service`; the language rule puts AI/LLM work there).
**S-1 and S3–S6 are Rust** — including S3, because it is now deterministic.

### 2.1 `PGN-A10` — S3 is a fold, and no model runs at consolidation

> **The creative work happens in S2 and is gated there. S3 assembles approved answers by code.**

v1 had creativity in *two* places and gated only one. The S3 pass took both columns of every approved
row into one context window and emitted a document — so the merge `PGN-A3` forbids happened where no
column constraint reaches, and the `content_hash` attested only that nobody edited the model's output
afterwards.

This preserves what the LLM is for — reading the wiki, answering in natural language, proposing what
the book implies — and removes the one place where its output was never reviewed.

**Consequence, and it is the real cost:** the brief must be **total**. With no creative pass to fill
gaps, every required field path needs a question. That is the same obligation §4.1's recursive
fingerprint imposes, so the two fixes carry each other.

**Consequence for contradictions (answers `PGN-Q2`):** when the fold finds two approved answers that
disagree, it **refuses and mints a new S2 question** naming both `answer_id`s. A conflict is never
silently resolved, and never resolved by a model.

---

## 3 — Data architecture

### 3.1 What exists and is not rebuilt

`source_corpus` (license fail-closed at `'unknown'`) · `source_corpus_chunk` · `enrichment_job`
(+ token budget) · `enrichment_eval_runs` · `enrichment_book_profile` · `outbox_events`.
`app/gaps/`'s deterministic ranking is reusable; its dimension sets are the wrong shape and are
replaced.

### 3.2 What is not reused

> **`PGN-A1` — a wiki proposal and a manifest candidate are never the same row.**
> `enrichment_proposal` is non-canon **by construction**: `origin='enrichment'`,
> `CHECK (confidence > 0 AND confidence < 1.0)`, terminal state `promoted` → a *glossary entity*.
> This pipeline's output is canon by construction. Sharing a table makes one invariant a lie, and the
> `CHECK` says which breaks first.

### 3.3 The tables

Every row carries **`element_kind`** — what makes these serve every generator module — plus the
tenancy scope keys `owner_user_id` and `book_id`.

```
gamegen_element_brief        S1
  brief_id · element_kind · brief_version
  schema_closure_fingerprint                      recursive; see §4.1
  questions_json · coverage_map_json              field-path -> question_id  (ASSERTED total)
  ── System tier: platform-authored, admin-write, world-readable.

gamegen_corpus_seal          S0
  seal_id · corpus_id · merkle_root · sealed_at
  ── a job binds a seal; says[] is verified against it, not against live rows.

gamegen_decision             S2   THE APPROVAL UNIT  (§3.4)
  decision_id · job_id · element_kind · target_ref · question_class
  review_status   proposed|approved|rejected
  approved_by · approved_at · rejected_reason
  batch_id · batch_size                            bulk is visible, not merely deprecated

gamegen_answer               S2   evidence, not the click
  answer_id · decision_id · question_id · target_ref
  says_json        [{chunk_id, span, quote}]       span REQUIRED
  proposed_text    TEXT NULL                       span FORBIDDEN
  not_stated · not_stated_reason                   closed set
  answer_hash                                      APPEND-ONLY; supersede, never UPDATE
  UNIQUE (job_id, question_id, target_ref) WHERE superseded_by IS NULL   ← PARTIAL

gamegen_creative_structure   S3
  structure_id · job_id · element_kind · content_hash
  body_json                                        DENSE + schema-governed, deny_unknown_fields
  consumption_json      answer_id -> [JSON-Pointer]     every approved answer maps to >=1
  answer_refs_json      [(answer_id, answer_hash)]      hash-linked, not id-linked
  brief_id · approved_by · approved_at

gamegen_numeric_policy       S4
  policy_id · element_kind · policy_version · body_json · policy_hash
  tier             system|book                     ← v1 omitted this (0.1 #12)
  parent_policy_id                                 a book policy NARROWS a System default
  authored_by

gamegen_candidate            S5
  candidate_id · structure_hash · policy_hash · artifact_hash · repair_round
  verdict          admitted|refused
  verdict_findings_json
  read_set_json                                    leaf pointers S5 actually consumed
  default_provenance_json                          every engine-defaulted field, named
  repair_ops_json                                  TYPED; see §7.1
  review_status · approved_by · approved_at        ← v1 had NO human at S5 at all
  engine_schema_version · engine_law_version
```

#### 3.3.1 What building S0/S2 changed about this sketch

Recorded rather than silently diverged from, because a sketch that no longer matches the DDL is a
second source of truth. Built in `services/lore-enrichment-service`: `app/db/migrate.py` (DDL),
`app/gamegen/answer_hash.py`, `app/db/repositories/gamegen.py`.

1. **The `UNIQUE` on `gamegen_answer` had to become PARTIAL.** As written it contradicts the
   append-only rule one line above it: a superseding answer carries the same
   `(job_id, question_id, target_ref)` **by definition**, so the plain constraint makes supersession
   impossible and the only way to correct an answer becomes the `UPDATE` the rule forbids. The
   constraint that was meant is *exactly one **live** answer per question per target*.

2. **`superseded_by_answer_id` is a DEFERRABLE FK, and that is load-bearing.** With a partial unique
   index, a supersession must **retire the old answer before inserting the new one** — otherwise the
   index correctly sees two live answers, which is precisely the instant the chain has two truths.
   Retiring first means naming an `answer_id` that does not exist yet. (The first implementation did
   it the other way round and failed here.)

3. **`batch_size` is checked, not merely recorded.** A self-reported count makes T3's *"bulk is
   visible"* a claim: declaring `batch_size = 1` while approving 24 renders as twenty-four careful
   individual reviews. A `DEFERRABLE INITIALLY DEFERRED` constraint trigger compares it to the real
   count at COMMIT — which catches both understating at write time and **adding a decision to a
   committed batch afterwards**, the second being invisible to any application-level check.

4. **`PGN-A14` is structural before it is implemented.** `gamegen_corpus_seal` exists now, ahead of
   the verifier that will read it, so that `CHECK (says[] = [] OR verified_against_seal_id IS NOT
   NULL)` can hold from the first row. A verifier added later has somewhere to record its result; a
   verifier never added leaves rows that visibly point at an unverified seal, rather than rows that
   look complete. `PGN-A14`'s **span disjointness** is enforced today, inside a `CHECK`, by an
   `IMMUTABLE` function — it is the arm that kills citing one span 24 times for 24 tier names.

5. **Two silent-drop paths the sketch did not close**, both reachable through a legal API and both
   now refused: superseding an answer to a **different question** (which retires that question's only
   live answer and gives the slot to another), and **sealing another user's corpus** (a seal anyone
   can mint over anyone's bytes grounds nothing).

6. **`gamegen_answer` needed a sixth column: `value_json`, the ANSWER as a structured value.**
   Building S3 is what showed why. With only `says_json` and `proposed_text`, the fold would have to
   *read* `"I'd call it a staged ladder"* and decide that means `ProgressionType::Stage` — **a model
   at consolidation, which is precisely the stage `PGN-A10` exists to remove.** So the value is
   resolved at S2, under the human signature, and S3 stays a pure fold over settled values. This does
   **not** re-merge `PGN-A3`'s two halves: provenance stays exact and derivable — `says[]` non-empty
   means EXTRACTED with a span behind it, `says[]` empty with `proposed_text` means INVENTED. A
   `CHECK` makes value and silence exclusive and exhaustive: `(value_json IS NULL) = not_stated`.

7. **A tier-name pattern must be able to say 一層.** §1 states the sub-levels are named *一層…九層 by
   convention* — one pattern, one decision. The first fold expanded `{n}` with `str(index + 1)` and
   produced **`1層, 2層, 3層`: ASCII digits for a Chinese corpus.** An author wanting the real names
   would have had to fall back to an explicit nine-item list, which is nine decisions and defeats
   `PGN-A11` exactly where the fixture needs it. `{n:cn}` now renders Chinese numerals (1–99, the
   whole range `MAX_TIERS_PER_KIND` reaches), and an unknown system is a refusal **by name** rather
   than a placeholder shipped to a player. Multilingual standard ML-4, in the one module whose corpus
   is Chinese.

8. **An allow-list keyed on a name the INPUT controls is not an allow-list.** The magnitude guard
   carried its leaf name down through nested values, so a cap-rule answered as
   `{"soft_cap": null, "tier_count": 500}` re-bound the leaf to `tier_count` and **500 sailed
   through**. Only a number sitting *directly* at a cell's own `value` slot may be ordinal now.

9. **`schema_fingerprint` is part of the content ADDRESS.** Outside the hash, re-folding the same
   answers after the schema moved produced the same `content_hash`; `ON CONFLICT` returned the old
   row and the new fingerprint was **silently discarded**, so the stored structure claimed a schema
   nobody asserted — the exact drift the column exists to make loud. The fingerprint and the
   `question_id → path` map are also no longer **parameters**: `fold_and_store` loads the brief
   itself, because a caller-supplied placement map and fingerprint are self-reported in precisely the
   way the seal's caller-supplied digest was.

Corrections 7–9 were all found by an adversarial probe at `/review-impl`, not by reading — the same
method that found S2's two tenancy holes, and with the same hit rate.

### 3.4 `PGN-A11` — the approval unit is the assertion class, not the row

The POC's honest row count is **121**, not v1's claimed few hundred — and 121 rows is not 121
judgements. It is a normalization artifact:

- 24 `difficulty` rows are **one** judgement — *"which tiers are walls?"* — shown 24 times.
- 24 `ordinal` rows are **one** judgement over **one** ordered list.
- 24 name rows are **one** judgement about a **naming pattern** (§1).

Collapsing the approval unit to `(question_class × target)` gives **~29 decisions**: 1 cardinality +
24 system-level + ~4 list-level reviews. Per-row provenance still *exists* — it stops being the thing
a human *clicks*. That is also what makes a signature mean something: 29 signatures over 29 reviewed
assertions beats 121 over rows nobody read.

**Ranking is not the fix.** Ranking orders a count, it does not reduce one, and it marks the tail as
provably least important — an instruction to click through it.

---

## 4 — S1/S2: interrogation

### 4.1 `PGN-A2` — the brief is derived from the RECURSIVE schema closure, and coverage is ASSERTED

> Every **non-defaultable field path** in the reachable type graph of `ProgressionKindDecl` has a
> question, **or** a `defaultable(path, value, rationale)` row. A third state does not exist.

v1 named one struct. The reachable graph is seven types deeper — `TierDecl` (6 fields × 24 rows),
`WithinTierCurve`, `BreakthroughCondition` + `ResourceCost`, `CapRule` payloads, `TrainingRuleDecl` +
`TrainingSource` + `TargetMatch` + `InstrumentMatch` + `TrainingAmount` + `TrainingCondition`,
`DerivationDecl`. All nine of v1's questions were top-level; every gap was below the first level.

**The mechanism, and how it fails:** `coverage_map_json`'s key set is asserted **equal** to the set of
non-defaultable field paths. A missing question reds. Bite-test: delete one row, watch it red, restore
it, paste the output.

**`PGN-A13` — a closed-set question's options are GENERATED from the enum, never authored.** v1's
questions were narrower than the enums they claimed to cover: *"body or mind?"* made
`BodyOrSoul::Both` unreachable; *"absolute or per-stage?"* made `Unbounded` unreachable and collapsed
`SoftCap` and `HardCap` — which are opposites (`HardCap` *rejects* training past the cap). Generating
options from variants means a new variant breaks the brief loudly, which is what §4.1 claims.

**Cross-field constraints need their own questions.** `CapRule`×`CurveDecl` is a joint constraint over
two independently-answered fields, so `PGN-A2` — which is per-field — can never derive the question
preventing an invalid pair. The matrix must be a **data table** the brief generator reads, and a
violation is a **refusal to the S3 gate naming both `answer_id`s**, never a repair (§7.1).

### 4.2 `PGN-A3` — two halves, never merged

`says[]` **must** cite a span; `proposed_text` **must not**. Separate columns, expressible as a DB
`CHECK`. Merge them once and the author/model distinction is gone *permanently* — nothing downstream
can reconstruct it. This survived the red team intact; `PGN-A10` is what makes it hold, by removing
the stage that merged them in inference.

**`PGN-A14` — a citation is verified, never trusted.** The gate never renders `says_json.quote`. It
renders bytes fetched live from the sealed corpus at `[chunk_id, span]`; a mismatch is an S2
**refusal**. Otherwise the model supplies both the claim and the evidence for the claim, and the human
compares the model against itself. For an ordered list, spans must be **disjoint** and the citation
count must not be below the item count — which kills citing one span for 24 tier names.

### 4.3 `PGN-A4` — "the book does not say" is a complete answer, and it is ACCOUNTABLE

`not_stated = true` with empty `says[]` is approvable and must stay one click. But v1 stopped there,
and the consequence was that the cheapest path through the gate became the **all-`not_stated` run**,
which passed all eight trust properties and shipped a manifest authored entirely by the policy file.
The cost gradient is ~30–45:1 (verify a span ≈ 60–90 s; click unknown ≈ 2 s), so this is the *modal*
outcome, not an adversarial one.

Three constraints, none of which add a click:

1. `not_stated_reason` is a closed set — `absent_from_corpus | contradicted | out_of_scope`.
2. **`not_stated` on a required, non-defaultable field is an S5 REFUSAL naming the field.** Approvable
   ≠ resolvable.
3. `not_stated_ratio` is gated **per question class** against the classes §10's fixture declares
   answerable. `not_stated` on a magnitude is expected; on tier *names*, against a corpus whose
   fixture requirement says it *names the tiers*, it is a red flag.

---

## 5 — S3: the fold

Deterministic, dense, schema-governed. `body_json` carries **24 tier objects**, not two plus a count —
each field either a value or an explicit `{not_stated, answer_id}` sentinel, with `deny_unknown_fields`.
v1's sparse `{tier_count: 24}` required S5 to synthesize **132 required values** from one integer, of
which exactly one had a policy path.

Patterns expand deterministically: *"sub-levels are named 一層…九層"* is **one** approved answer that
the fold expands to nine dense rows. The human approves the pattern; the code does the expansion.

> **`PGN-A9` — nothing is silently dropped, and it is a LEDGER, not a count.**
>
> - **S2→S3:** every `approved` answer maps to ≥1 JSON-Pointer in `consumption_json`, or S3 refuses.
> - **S3→S5:** S5 records `read_set_json`; a leaf in `body_json` outside it is a **refusal** with its
>   pointer in `verdict_findings_json`.
>
> Bite-test: add an unconsumed key to a fixture structure, assert `verdict = refused`, remove it,
> paste the output.

v1 stated `PGN-A9` as a sentence and gave T6's count identity as its mechanism — which cannot see
`PGN-A9`'s own worked example, because rows-in equals rows-out while a leaf vanishes.

**`answer_refs_json` is hash-linked.** v1 referenced answers by bare id, so an `UPDATE` on
`gamegen_answer` after pinning could retroactively convert an invented tier into an extracted one with
every hop of the chain still green. Answers are now append-only; S5 recomputes `answer_hash` and
refuses a mismatch.

---

## 6 — S4: where numbers come from

> **`PGN-A5` — a model may emit CARDINALITY, ORDER, and NAMES THE BOOK CONTAINS. Never MAGNITUDE.**

How many tiers, which is fourth, and what the book calls them are facts a span supports. How much
grinding a tier costs is a balance decision no amount of reading produces.

**`PGN-A15` — the policy is System-tier by default and a book policy NARROWS it.** ✅ **BUILT**
(`app/gamegen/policy.py` + `gamegen_numeric_policy`). A policy maps every **magnitude path** to a
`Band` — `[min, max]` plus a default inside it — and both halves are refusals:
`assert_covers_magnitudes` asserts the band set **equals** the contract's magnitude set (both
directions, the same mechanism as the brief), and `narrow()` refuses a book band not contained in its
System parent's, **by path**. `tier='book' ⇒ parent_policy_id IS NOT NULL` is the axiom as a **schema
fact**: you may narrow a shipped baseline, you may not author from scratch. `publish_system_policy`
takes a required `is_admin` with **no default**, so every call site has had to state whose authority
it acts under. v1 declared no tier, and the consequence was concrete: a novelist reaching S4 faces knobs she has no basis to set,
no default to narrow, and one complete plausible example in the document — so §6's illustrative
numbers become the platform's de-facto global balance, reviewed by nobody, while every gate reports a
human-authored policy. This is the `effective = AND(deploy_allows, user_enables)` shape the Settings
& Config standard already mandates, and it converts S4 from authorship into *review of a diff against
a shipped baseline* — a decision a novelist can actually make.

**`PGN-A16` — policy arithmetic is fixed-point, saturating-integer.** `PROG_001` §5.1's closure-pass
converted all five `f32` fields to milli-units precisely because *"floats in a replayed,
event-sourced engine are a determinism liability."* v1 cited that for the *output* and wrote
`wall_multiplier = 3.0` in the *input* with no stated normalization. `crates/world-gen` is the
cautionary precedent, not the supporting one: its byte-identical BLAKE3 pin had to be **deleted** over
a 1-ULP libm divergence between MSVC and glibc, and its golden test is now an epsilon band. If S5
multiplies in `f32`, T4 is that problem verbatim.

**A fact appears in exactly one artifact.** v1 had `curve_family` in both the structure and the
policy with no precedence rule — so changing the policy to contradict an approved structure passed
`PGN-A6`'s test perfectly. The structure owns the shape token; the policy owns a token→parameters
table and **refuses an unmapped token**.

### 6.1 `PGN-A6` — rebalancing never re-runs the LLM, and here is a test that can fail

Change the policy, re-run S5: a **new `policy_hash` against an unchanged `structure_hash`**.

v1's bite-test asserted `structure_hash` unchanged — but S5 fetches S3 *by digest*, so that arm
asserts an input equals itself and is green on any codebase, including one leaking magnitudes into
`body_json` every run. The replacement has two arms that can actually red:

1. **Sweep** the policy across a range against a fixed structure; assert *achieved* tracks *target*
   within tolerance. A target unreachable without a ladder change reds at the boundary.
2. **Refuse any numeric literal in `body_json`** outside the `{ordinal, tier_count}` class. Bite-test
   by planting `tier_max: 500` in a fixture structure and watching S5 refuse.

---

## 7 — S5: admission

> **`PGN-A7` — the validator is the engine's binary, and the verdict records which binary.**

**It does not exist yet** (0.1 #1) — S-1 builds it. Until then this axiom stamps a version from
nothing. `engine_schema_version` + `engine_law_version` on the verdict means a candidate admitted
under schema 4 has *not* been admitted under schema 5; without it a stale verdict launders a candidate
past a validator that would now refuse it. This property survived the red team and is worth keeping —
it just needs a binary to be true of.

### 7.1 `PGN-A17` — repair may ADJUST; it may never REMOVE, WEAKEN or SUBSTITUTE

v1 said only that repair increments `repair_round`, constraining *how many* repairs, never *what a
repair may change*. Doc 38 and `PGN-Q6` both constrain the **failure** path. Nobody constrained the
**success** path — and repair runs entirely below the human signature.

The attack needs no adversary: the validator refuses a tier whose `location_required` resolves to
nothing; repair round 2 sets it to `None`; verdict **admitted**, `repair_round: 2` honestly recorded,
every trust property green, and the human-approved *"advancement requires a sealed place"* is gone.

`repair_ops_json` is a typed list. `Adjust` (a magnitude moves within policy bounds) is admissible.
`Remove` / `Weaken` / `Substitute` of any structure-bearing element is a **refusal that returns to the
S3 gate**. Test: a run whose repair list contains a `Remove` cannot reach `admitted`.

### 7.2 The S5 human gate, and what it is shown

v1's T3 named a gate at S5 and the schema had nowhere to record that anyone looked. Worse, the
machine check there is **type legality** — `tier_max: 500` and `tier_max: 500000` are equally
admissible — so the one stage where a magnitude error becomes visible was guarded by a check
structurally unable to see magnitudes.

**Do not show a numeric diff.** Nobody reviews 24 integers. Show the **policy diff** (~6 TOML lines)
plus **consequences in human units** — *"tier 9: 12 h → 36 h; full ladder: 210 h → 480 h; the first
wall is now 3.4× the tier before it"* — plus the **default count** from `default_provenance_json`:
*"you are approving 24 tiers of which 132 fields will be engine-defaulted."* That last number is what
turns an invisible hole into something a human can veto, which is §0's whole thesis.

---

### 7.3 `PGN-A20` — an out-of-scope element is a REFUSAL that names its owner, never a smaller schema

**`PGN-Q9` is closed: `TrainingRuleDecl` is out of POC-1 scope, because it crosses the world pipeline.**

`TrainingCondition::LocationMatch` needs a `PlaceTypeRef`; `InstrumentMatch` needs an item;
`TargetMatch` needs both. Those are other `CPL-A3` element modules and none exists. Progression cannot
be generated in isolation from them — which is a **correction to doc 38's element roster**, where
progression's dependency column read *"rules"* alone (`PGN-R7`). `CPL-A9` said dependency order is a
property of the pipeline, not a scheduling convenience; this is the first place it bites.

**What survives is genuinely self-contained:** `TrainingSource::Time { period: DailyBoundary }` with
`conditions: []` — the `Scheduled:CultivationTick` generator (`PROG-12`/`PROG-21`). No place, no item,
no interaction. It is also the canonical wuxia case: 閉關, secluded cultivation, measured in years.

**But the cut may not become a silent drop.** Cutting scope by *narrowing the schema* would delete the
requirement; the pipeline must instead **refuse and name what is missing**:

```
book:      陳玄一在寒潭閉關三年，終於破入築基
           └─ 閉關 三年  → TrainingSource::Time      ✅ generated
           └─ 寒潭       → TrainingCondition::LocationMatch(PlaceTypeRef)
                          ⛔ REFUSED — "requires the PLACE element module,
                             which does not exist. Owner: CPL-A3 place module."
```

The fixture's own headline sentence therefore exercises the refusal path, which makes `PGN-A9` its
first real bite-test: assert the run refuses the location condition **by name**, and that the refusal
carries the owning module. A pipeline that silently generated a place-less training rule would be the
`QTY-Q5` class shipping in the POC that exists to prove it cannot.

---

## 8 — S6: where the bytes land

The decision survives review; the argument for it did not, and is replaced.

### 8.1 Progression cannot live inline in `Ruleset`

Not *"too big"* — **structurally impossible, and the ceiling has zero headroom.**

`size_of::<Ruleset>()` is **exactly 2312** (measured, §0.1). Any addition trips the assertion.

More decisively: `TierDecl` transitively owns `String` (`I18nBundle`, `PlaceTypeRef`), `Vec` and
`HashMap` (`BreakthroughCondition::AtMaxPlus`'s **four** heap-carrying `Option`s). So it can never be
`Copy`, never be `const`-constructed, and **cannot be measured by `size_of` at all** — which is the
`QTY-A6 ⊥ QTY-A12` trap already recorded as row 6 of the non-vacuity register. Every field of
`Ruleset` today is `Copy`; `CombatRules`, `StatRules`, `QuantityTable`, `ResourceTable` all are.
Inlining progression does not cost too much — it **abandons the no-heap shape the whole quantity
design rests on**.

*(The `const fn` framing v1 leaned on is real but secondary: `engine_default()` is never invoked in a
`const` context anywhere in the tree. The constraint that actually bites is that a heap pointer
defeats `size_of`.)*

### 8.2 A second hash on the binding is wrong here — for a better reason than v1 gave

v1 said the epoch path *"cannot"* carry it. It can: `ALTER TABLE` is not blocked by the binding's
`ENABLE ALWAYS` trigger, the payload is JSON, `RealityBinding` is plain serde. Saying *"cannot"* when
you mean *"I'd have to build it"* is the tell this repo has a rule against.

**The real objection:** `Domain::rules_digest(rules: &Self::Rules) -> RulesetDigest` is commented
**"DERIVED, never supplied."** A second artifact hash is not a function of `Rules`, so carrying it
would make the island's pin *partly supplied* — destroying the exact `RLS-A13` property the derivation
exists to protect.

### 8.3 The shape the codebase already uses, one level down

*"The envelope carries the digest, not the ruleset."* Apply it one level down:

```rust
pub struct Ruleset {
    pub quantities: QuantityTable,
    pub resources:  ResourceTable,
    pub progression_digest: [u8; 32],   // +32 B → 2344. INSIDE the hash.
}
//   └──→ ProgressionTable — variable-length, nested, content-addressed, deduped
```

| Property | Mechanism |
|---|---|
| progression is inside the reality's digest | **`CanonEncode for Ruleset` destructures exhaustively with no `..`** — a new field is a **compile error until it is hashed**. `law_version` already broke that line when added. |
| a ladder edit moves the digest | ⇒ `Q0b B3`'s epoch switch works unchanged; no second version axis |
| variable-length, deduped | 200 realities on one preset store the table once |
| substitution refused | `store.get` re-digests the **decoded** value at `src_version` and returns `DigestMismatch` |

**Honest costs.** `Q2 B1`'s four guards bite again (`classify!` totality · `s1b_subjects` · the
`size_of` assertion · the golden digest) — schema 4 → 5, two repin-log entries. `RulesetStore` is
`Ruleset`-typed and needs generalising or a sibling. A **dangling `progression_digest`** needs a
refusal — this is a *second instance of an existing class*, not a new one:
`RealityError::RulesetMissing` already covers a binding pointing at absent bytes. The genuinely new
hazard is that `store.get` verifies only the **outer** artifact, so the nested resolve-and-verify is
separately written — and a tolerant nested decoder would re-create non-vacuity register row 7
(`QTY-A11 ⊥ get`) one level down.

**This does not settle `CPL-Q1`.** It places *this element*.

---

## 9 — `PGN-A18` — labels live outside the digest, and their coverage is refused at load

v1 marked i18n *"already enforced"* citing a `Display` string (0.1 #5) and then never said where
labels go — so `display_name`, `description` and all 24 `TierDecl.name`s were produced nowhere and
stored nowhere, and the ladder would ship as `tier_9`.

Labels are a **sibling content-addressed artifact**, referenced by the binding, **not** inside the
ruleset digest — because a Vietnamese translation fix must not strand a live reality. Coverage is a
**load-time refusal**: every `kind_id`/`tier_index` in the progression table has a label entry, or the
reality does not load. Same shape §8.3 demands for a dangling digest.

This is **unbuilt work**, and `PGN-R1` carries it. A `ProgressionName` validator in the shape of
`quantity.rs`'s (which bite-tests that `"khí"` and `"氣"` are refused) does not exist.

⚠ It also has a cross-doc consequence: doc 17 `GDA-D6` sources *"tier names"* from the ruleset store,
and `GDA-D5`'s seeding step localizes *manifest-derived* strings. `PGN-R3` moves progression out of
the manifest, so that step no longer reaches tier names. `PGN-R6` tracks it.

---

## 10 — The corpus fixture

A 武俠 book and its wiki. Chinese source prose, English stable IDs per `PROG-A7`.

> **`PGN-A8` — a fixture that already contains the answers makes every stage vacuous.** `NV-1`
> applied to test *data*.

| Requirement | Forces |
|---|---|
| names the tiers, states **no magnitude** | `PGN-A5` is exercised |
| states the sub-level **naming pattern** once | §1's naming owner is exercised |
| **one contradiction** across two wiki pages | the fold's refuse-and-mint-a-question path (§2.1) |
| **one system implied but never named** | enrichment does real work |
| **one flavour detail with no mechanical consequence** | the pipeline must **discard** |
| **one tier named but never ordered** | `not_stated` on a required field ⇒ an S5 refusal (§4.3) |

| id | 中文 | `ProgressionType` | `BodyOrSoul` | exercises |
|---|---|---|---|---|
| `internal_energy` | 內功 | `Stage` | Body | tiers, breakthrough, `TierBased` |
| `swordsmanship` | 劍術 | `Skill` | Body | `derives_from`, action training |
| `comprehension` | 悟性 | `Attribute` | **Soul** | soft cap, the xuyên-không path |

---

## 11 — Trust properties and their mechanisms

A property whose mechanism reads *"by convention"* is a property we do not have. v1 had five such
rows and did not notice. **NOT ENFORCED is now a legal value** — an honest gap beats a false green.

| # | Property | Mechanism | Status |
|---|---|---|---|
| T1 | I can tell what the model invented | two columns, span required/forbidden, DB `CHECK`; **`PGN-A10`** removes the merging stage | ✅ |
| T1b | a citation supports its claim | live bytes from the **sealed** corpus; quote mismatch = refusal; span disjointness for lists | 🔨 **half built** — span disjointness + the seal requirement are `CHECK`s (S2); the live-byte comparison needs the corpus ingested |
| T2 | I can tell where a number came from | `(structure_hash, policy_hash)`; no numeric literal in `body_json` | ✅ `assert_no_magnitude_leaked` refuses any number outside `{tier_index, tier_count, initial_tier, kind_count}` **by pointer**, and only at a cell's own `value` slot; `policy_hash` covers the **tier**, so the same numbers as a System baseline and as one book's narrowing are different facts about who chose them |
| T3 | nothing reaches players unreviewed | `gamegen_decision` with `approved_by`; **`batch_id`/`batch_size` make bulk visible**; S3 refuses a batch above a declared size | ✅ the table, the `approved`⇒`approved_by` `CHECK`, a DEFERRED trigger refusing a `batch_size` that disagrees with the real count *in either direction*, and `fold(max_batch_size=…)` refusing the whole run above the ceiling. S3 folds `approved_answers`, never `live_answers` |
| T4 | same inputs → same artifact | S3 is a fold; S5 is fixed-point saturating-integer (`PGN-A16`); artifact content-addressed | 🔨 **S3 half done** — the fold is pure and its output content-addressed (`uq_gamegen_structure`, re-folding is a no-op). S5 still at risk until `PGN-A16` is built — see `world-gen` |
| T5 | a wrong rule is traceable **to a person** | 5 hops + `approved_by` on the decision. v1's chain contained **no human at all** | ✅ |
| T6 | nothing is silently dropped | **consumption ledger, both directions** (`PGN-A9`) — not a count | ✅ enforced twice: `fold()` refuses an unconsumed approved answer, and `gamegen_ledger_is_total` re-checks it as a `CHECK` so a row not written by the fold cannot carry a ledger nobody verified |
| T7 | a stale verdict cannot launder | version-stamped verdict | 🔨 needs S-1's binary |
| T8 | the artifact cannot be swapped | `store.get` re-digests the decoded value | ✅ |
| T9 | approved content survives repair | typed `repair_ops_json`; `Remove`/`Weaken` refuse (`PGN-A17`) | 🔨 unbuilt |
| T10 | labels exist for every key | load-time coverage refusal (`PGN-A18`) | ✅ `ruleset-loader::labels` — `admit()` refuses a missing label file, an uncovered kind/tier, and an empty name, each named |

### 11.1 Limits accepted, stated rather than hidden

- **T4 holds from S3 onward, not from S0.** The LLM stage is not reproducible. "Deterministic" means
  *below the human signature*.
- **Self-sufficient for REPLAY, not for AUDIT.** The bytes carry two hashes; the chain lives in the
  pipeline DB. Lose it and the rules still run — *why* is gone. Unmitigated in the POC.
- **No stage asks whether a magnitude is GOOD**, only where it came from. §7.2's consequence
  rendering is the closest thing, and it is a human judgement, not a mechanism.
- **The store's "append-only" is convention** — no `delete` on the API, but the root is a directory
  with no guard. T8 survives (pruning yields `RulesetMissing`, not substitution).

---

## 12 — What this changes elsewhere

⚠ **PROPOSED, not applied.**

| Target | Change | Row |
|---|---|---|
| `ruleset-core` | `ProgressionKindDecl` + `ProgressionTable` + the validator — **built first**; `progression_digest` on `Ruleset`, schema 4 → 5; a `ProgressionName` validator | `PGN-R1` |
| `ruleset-loader` `store.rs` | generalised over content, or a sibling store; nested resolve-and-verify | `PGN-R2` |
| `PROG_001` §11 / `PROG-19` | `progression_kinds` land in the ruleset, **and a disposition for the other three §11 fields** — `class_defaults`, `actor_overrides`, `strike_formula` are all keyed by `ProgressionKindId` and would dangle across the seam | `PGN-R3` |
| `38` `CPL-Q1` | narrowed, not answered | `PGN-R4` |
| `lore-enrichment-service` | `gamegen_*` family + corpus seal; `enrichment_*` untouched | `PGN-R5` |
| `17` `GDA-D5`/`GDA-D6` | tier-name sourcing and locale seeding follow the label artifact (§9) | `PGN-R6` |
| `38` §6 element roster | progression's dependency column read *"rules"*; it also depends on **place** and **item** via `TrainingCondition::LocationMatch` / `InstrumentMatch` / `TargetMatch` — **applied**, since doc 38 is unlanded | `PGN-R7` |

**Checked in shipped code during review.** The red team reported
`app/services/book_grounding.py:128`'s `license="licensed"` as a fail-closed licensing bypass. **It is
not** — that path grounds the user's *own* uploaded book, scoped by `user_id`/`project_id`/`book_id`,
and a user holds rights to their own manuscript. §3.1's gate exists to stop an operator re-cooking
copyrighted third-party material, which is a different path. Claim withdrawn.

**What survives from that line is a different and real problem, and it is ours:** the same call passes
`kind="other"`. §10's fixture is *"a 武俠 book **and its wiki**"* — and a wiki is **derived** text. With
`says_json` storing only `chunk_id`, a citation to a wiki chunk and a citation to book prose are
**indistinguishable**, so T1 falls with nobody lying: the model cites, accurately, a chunk of another
model's output. `PGN-A14`'s seal must therefore record `is_authored_source` per chunk, and `says[]`
may cite only `true`. Carried by `PGN-R5` as unbuilt design — no defer row, because it is inside this
doc's own scope.

---

## 13 — Open

**Closed by this rewrite, recorded rather than deleted** (ids are never reused):
**`PGN-Q1`** (the gate's review budget) — answered by `PGN-A11` §3.4: the approval unit is the
assertion class, 121 rows → ~29 decisions, and ranking was the wrong fix.
**`PGN-Q2`** (what the pipeline does with a contradiction) — answered by `PGN-A10` §2.1: the fold
refuses and mints a new S2 question naming both `answer_id`s. Never a silent pick, never a model's.
**`PGN-Q9`** (`TrainingRuleDecl` scope) — answered by `PGN-A20` §7.3, **by the PO**: it crosses the
world-generation pipeline and cannot complete now. Out of POC-1 scope as a *refusal that names its
owner*, not a narrowed schema. Surfaced a wrong dependency edge in doc 38's roster (`PGN-R7`).

| # | Question |
|---|---|
| **PGN-Q3** | **Who supplies a required field the book does not state?** §4.3 makes it an S5 refusal, which is honest but not an answer — someone must still decide. If the policy supplies `cap_rule`, the policy is making a *structural* decision, and `PGN-A5`'s line is not drawn there. |
| **PGN-Q4** | **Who judges the judge?** `enrichment_eval_runs` scores with a model. If the eval is S2's trust mechanism, T1–T10 rest on an unaudited model call. Advisory-only seems right — then what is the actual S2 gate? |
| **PGN-Q5** | **Is the brief System-tier per element, or per book?** A wuxia book and a hard-SF book plausibly need different questions for the same element. |
| **PGN-Q6** | **What is the repair budget** (`CPL-Q4` upstream), and does exhaustion refuse or emit a reduced artifact? §7.1 constrains repair's *kind*; its *count* is still open. |
| **PGN-Q7** | **Who is the human?** `CPL-Q2`, unanswered upstream and sharper here: S2 needs a close bilingual reader, S4 a balance designer, S5 an engine engineer. Three competences, one word. `PGN-A15` softens S4; S2 and S5 remain. |
| **PGN-Q8** | **What resolves a cross-element reference?** *"a refined pill"* → `ConsumableKindId`, *"a sealed place"* → `PlaceTypeRef`. Doc 38's Manifest stage is the named home and this doc does not instantiate it. Unresolved, `PROG_001` §6.2's *"silent skip if conditions unmet — no reject"* makes the rule permanently dead at runtime — the defect PL_007 ITM-C7 already documents. |
