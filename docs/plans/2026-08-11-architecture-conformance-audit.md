# Architecture conformance audit — is the sealed design actually built?

*Opened 2026-08-11. Branch `refactor/entity-lifecycle`.*

## Why this plan exists

The PO's ruling, verbatim:

> **The session is considered done only when the architecture is implemented correctly — not when
> the spec or the run state is complete.**

That reverses the polarity of the last several sessions. The refactor plan
(`2026-08-09-knowledge-architecture-refactor.md`) tracks *tasks*; its checkboxes read 37/37 and
its deferrals are all tracked with mechanisms. None of that is evidence that the **architecture**
is built. A task can be complete, its tests green, its gate wired, and the decision it was meant
to implement still absent from the running system.

That is not hypothetical here. It has now happened three times in one week:

| what the artifact said | what the system held |
|---|---|
| T32 shipped the life-status producer, tests green | **3 status facts**, one book — a producer proven, not a corpus |
| T33's corpus bite PASSES, 5 edges written, acyclic | **4 causal edges out of 1184 events (0.34 %)** — the design's partial order is empty |
| T38's mechanism "IS the checklist and can only shrink" | both gates **exempt T38's entire scope**; they pass with T38 undone |

Each was found by looking at the system, and **none** would have been found by reading the plan.
The plan was not lying deliberately — it was reporting task completion, which is a different
proposition from architecture conformance, and nothing in this repo was measuring the second one.

**So this audit does not read the refactor plan to determine status.** It reads code, schemas and
the running stores. The plan and the specs are inputs only where they make a *claim*; the claim is
then the thing under test.

---

## The unit of audit: one sealed decision

`docs/specs/2026-08-03-glossary-kg-entity-refactor/2026-08-09-ARCHITECTURE-OVERVIEW.md` §9 seals
**31 decisions** — `B1–B6` boundaries · `SH1–SH4` service shape · `T1–T7` storage · `MD1–MD11`
the model · `SQ1–SQ3` sequencing. Every row carries a **basis** (`measured` / `audited` / `PO`),
because the sealing rule was that a row without one does not exist.

That basis is the audit's lever. **Where a decision was sealed on a measurement, that measurement
is a baseline that can be re-taken today**, and the delta is the conformance answer. Three rows
were sealed with the number **zero**, which makes them the highest-yield targets in the register:

- **MD4** — `:EntityStatus` **0 of 21**
- **MD10** — causal edges *"built, wired, **0 instances**"*
- **MD7** — *"99/99/**0 revisions** — latent"*

A decision sealed at zero that is still at zero is not a decision that was implemented.

---

## Verdict vocabulary — five outcomes, and the third is the one that keeps fooling us

Every decision gets exactly one verdict plus a **reproducing command**. No verdict may be recorded
from reading a document.

| verdict | means |
|---|---|
| **IMPLEMENTED** | The decision holds in the running system, proven by a command pasted into its row. |
| **ABSENT** | Not built. Says so plainly; an honest absent is worth more than a generous partial. |
| **⚠️ UNEXERCISED** | The mechanism exists and is provably correct on a sample; **whether it behaves correctly at scale has never been tested by a designed run.** Not the same as "the corpus is empty" — see the methodology rule below on why an empty dev store is not evidence of anything. It gets its own verdict so it is never filed under IMPLEMENTED, and never under ABSENT either. |
| **DIVERGED** | Built differently from the sealed text. Not automatically a defect — T9 shipped a different index *on evidence* and was right to. The audit's job is to decide whether the divergence is **sound and recorded**, or **drift**. |
| **UNMEASURABLE** | No command reproduces the claim. Treated as a finding in itself, not as a pass. A decision nobody can check is not a decision that is being kept. |

---

## ⛔ The methodology rule — the dev database is not evidence

**Added 2026-08-11 after the PO caught this plan's first draft committing the error it was written
to prevent.** The first draft defined its `PARTIAL` verdict as a **coverage ratio taken from the
dev store** — `4/1184` causal edges, `23/4813` entities with a status — and read those ratios as
proof that the architecture was unbuilt.

**That inference is invalid, and the reason is not subtle.** There is no production system and no
production corpus. The dev database holds whatever accumulated from ad-hoc development runs. A low
ratio there has an overwhelmingly likely explanation that has nothing to do with the architecture:
**nobody ran the pipeline over that data.** Reading it as "the design is not in force" is picking a
convenience sample and letting it argue for a conclusion already formed — which is exactly the
failure this audit exists to stop, committed by the audit itself.

### What the dev store can and cannot settle

| the store CAN | the store CANNOT |
|---|---|
| **Existence-prove a path** — a row here means the write path executed at least once, under real wiring. `4` causal edges prove the writer works end-to-end. | **Prove absence of capability.** Missing rows mean the producer did not run, not that it cannot. |
| **Falsify.** A write that *errors* is a defect regardless of corpus — this is how the `entity_facts_kind_chk` incident was caught, and that reasoning was sound. | **Supply a denominator.** `1184` events is not a population the design chose; it is residue. No ratio computed against it means anything. |
| **Reveal schema/structure** — labels, tables, columns, constraints. | **Judge output quality at scale**, which is what `MD5`/`MD10` actually turn on. |

### What replaces it

Claims are sorted by **what kind of evidence can settle them**, and each kind gets its own
instrument:

1. **Structural claims** — does the port exist, is there a second `GraphStore` adapter, does the
   KAL carry domain logic, does `kal/temporal.ts` still exist. **Settled by reading the repo.** The
   database is irrelevant. **This is the majority of the 31 rows**, and those verdicts are
   unaffected by this correction.
2. **Behavioural claims** — does the causal extractor yield a *sound* partial order; is write-time
   dedupe actually in force. **Settled only by a designed run on a controlled corpus**, with the
   hypothesis and the pass criterion **written down before the run**. Never by observing what the
   dev store happens to contain.
3. **Capacity claims** — pgvectorscale at 3072 dims, rebuild-from-Postgres at book scale.
   **Settled by a benchmark at a stated scale** on fixture or synthetic data.

### The instrument this project does not have

Every measurement in this refactor has been taken against whatever data happened to exist. So
category 2 has no valid instrument at all, and that — not any individual verdict — is the finding.

**A reference corpus with ground truth** is the missing tool: a fixture book of known shape where
the correct answer is *known in advance*, so "did the architecture produce the right partial order"
has something to be right or wrong against. Without it, `MD5`, `MD9`, `MD10` and the `T33` stop
condition are **permanently unfalsifiable** — and an unfalsifiable claim is not a passing one.
Building it is Phase A's real work; re-counting the dev store is not.

**Consequence for the stop conditions.** Stop condition 3 (*"T33 yields few or low-quality edges"*)
cannot fire or clear on dev-store counts, in either direction. It needs the reference corpus. What
*does* stand from the earlier pass is repo-grounded and survives: the condition was written against
`HAPPENS_BEFORE`, which exists in neither the code nor the graph, so a literal check returns 0 and
is indistinguishable from a broken query. That is a defect in the condition's wording, independent
of any data.

---

## What is NOT in scope

- **Re-litigating the design.** The register is sealed. If the audit finds a decision that looks
  wrong, it records the evidence and routes it to the PO — it does not design around it. (Sealing
  means the *reasoning* is closed, not that the code exists; that distinction is the whole point.)
- **Fixing what it finds, in the same pass.** Auditing and repairing in one motion is how a scope
  becomes unbounded and how an auditor starts grading their own repairs. Findings land first.
- **Task-level plan hygiene.** Already done and explicitly not the goal.

---

## Method — three axes, one of which is primary

**Axis A · ARCHITECTURE conformance (primary).** For each of the 31 decisions: what would prove it
is implemented? Run that. Record verdict + command + numbers.

**Axis B · SPEC conformance (secondary).** Where the detailed specs make a *structural* claim the
overview does not — a table, an endpoint, an edge type, a scope key — check it the same way.
Restricted to claims that constrain implementation; prose is out of scope.

**Axis C · RUN-STATE truthfulness (derived, not independent).** Axis C is *computed* from A and B:
for every decision whose verdict is not IMPLEMENTED, does the refactor plan represent it honestly?
A decision that is PARTIAL while its task reads `[x]` is a run-state defect **caused by** an
architecture gap, and it is recorded against the gap, not as its own item. This ordering is
deliberate — auditing the run state first is what produced three sessions of document work.

### The rule that makes this audit re-runnable

**Every row records the command that produced its verdict.** A number with no command behind it is
the exact defect (`DRIFT-4`) that let `186 routes` and `77 stale ids` survive — the latter was
wrong by **36×**, the former reproduces from nothing at all. If a decision cannot be reduced to a
command, its verdict is UNMEASURABLE and that is the finding.

**Read-only against shared stores.** Dev Postgres `:5555` and Neo4j `:7688` hold real data. Counts
and schema reads only; anything that writes goes to a throwaway.

---

## Phases

### Phase A — build the instrument *(rewritten 2026-08-11; the first version was the error)*

The first draft of Phase A was *"re-take the three zero-sealed measurements"* on the dev store.
Those observations are recorded below as **existence proofs only** — they are true statements about
that database and **not** evidence about the architecture. Kept, because deleting them would hide
the mistake rather than correct it.

| observed on the dev store, 2026-08-11 | what it legitimately proves | what it does NOT prove |
|---|---|---|
| `4` causal edges over `1184` `Event` nodes | the causal writer executes end-to-end and persists both `CAUSES` and `PRECEDES` | nothing about `MD10`'s conformance — the producer was run on one book by one bite |
| `23` entities with `35` status transitions across 6 projects (`gone` 32 · `active` 3) | the status write path works, and `gone` is reachable | nothing about `MD4`'s conformance |
| `alive` = `7361` rows, **all `true`**, zero `false` | the deprecated column still carries no signal, unchanged since sealing (`7290/0`) | — this one is a **schema/consumer fact**, so it stands: 7 pinned readers still read a column with zero information content |
| `entity_facts.invalidated_reason`: `superseded_same_ordinal` **2032** · `converted_to_alias_facts` 357 · `episode_superseded` **0** | the belief axis is used, by two other reasons | nothing about `MD7` — chapter revisions may simply never have happened |

**A1 · Build the reference corpus.** A fixture book with **known ground truth** — a small cast, a
known event chain, known role changes with known story positions, at least one death and one
rename. Committed as a fixture, not a dev-store artifact, so any run is reproducible by anyone.
This is the instrument every behavioural claim below depends on, and the project has never had it.

**A2 · Write the hypotheses before running anything.** For `MD5`, `MD9`, `MD10` and stop condition
3: the expected output on the reference corpus and the pass criterion, recorded **first**. A pass
criterion written after seeing output is not a criterion.

**A3 · Run the pipeline over the reference corpus, on a throwaway store.** Never the dev stack —
both to keep it clean and because a shared store cannot give a reproducible denominator.

**A4 · Fix stop condition 3's wording regardless.** It is written against `HAPPENS_BEFORE`, which
exists in neither the code nor the graph, so a literal check returns 0 and is indistinguishable
from a broken query. This is repo-grounded and needs no corpus. *(Partly done — the counting
queries were pinned into the condition in `5a6677cc3`; the surrounding claim that the causal layer
is "empty in practice" must be withdrawn as dev-store reasoning.)*

**Do the structural sweep (Phases B–D) in parallel** — it needs no corpus at all, and it is where
most of the 31 rows are settled.

### Phase B — boundaries and storage *(B1–B6, T1–T7)*

Several already have gates; **a passing gate is not the verdict** — the audit asks whether the gate
covers the decision. `D-T38-MECHANISM-IS-VACUOUS` is the precedent: two green gates, and neither
covered the scope they were cited for.

- [ ] **B-1 · B1** — re-measure the sealing number (**128 imports / 67 modules bind `neo4j_repos`**)
- [ ] **B-2 · B2 + B6** — KAL carries no domain logic; does `kal/temporal.ts` still exist?
- [ ] **B-3 · B3 + B4 + B5** — no privileged internal path; reads through the KAL; writes routed
- [ ] **B-4 · T1** — AGE eliminated *(spot-checked 2026-08-11: no AGE/Kuzu/Memgraph in the repo)*
- [ ] **B-5 · T2** — ⚠️ **drafted ABSENT.** Only `neo4j_graph_store.py` + a test fake exist. X1
  requires **both** candidates; a shadow comparison with one adapter is not a comparison
- [ ] **B-6 · T3 + T4** — vectors out of the graph *(writes yes, reads no — drafted PARTIAL)*; and
  T4's backup path: does it exist, and has it been restored from?
- [ ] **B-7 · T5** — prebuilt Postgres image + owned extension matrix: does it exist?
- [ ] **B-8 · T6** — re-measure both tripwires (p50 entity degree, sealed at **0**)
- [ ] **B-9 · T7** — `TruthStore` consolidation *(Phase 8; expect ABSENT — record it as such)*

### Phase C — the rest of the model *(MD1–MD3, MD5–MD6, MD8–MD9, MD11)*

- [ ] **C-1 · MD1** — opaque identity *(5 derived-id callers pinned — drafted PARTIAL)*
- [ ] **C-2 · MD2** — role as a relation fact with a story interval *(T36; count the roles that
      actually carry `valid_from_ordinal` — the acceptance book had **12 of 25** positionless)*
- [ ] **C-3 · MD3** — no lore-bible layer; planforge extended for game-focused lore books
- [ ] **C-4 · MD5** — chapter is the reveal unit *(pairs with A1's naming question)*
- [ ] **C-5 · MD6** — reveal axis subsumes the spoiler window *(T32, 5 surfaces — verify all five)*
- [ ] **C-6 · MD8** — event anchor sits **beside** `source_episode_id` (schema check)
- [ ] **C-7 · MD9** — write-time dedupe *(sealed at **11.7 %** redundant, `gender` 93.2 %;
      re-measure — the ratio is the proof it is in force)*
- [ ] **C-8 · MD11** — the as-of covering index. **Known DIVERGED:** T9 shipped a different index
      on evidence, and the plan's stated rationale was wrong in both halves. Confirm the
      divergence is sound and that the sealed row was amended rather than silently overtaken

### Phase D — sequencing and the meta-rule *(SQ1–SQ3)*

- [ ] **D-1 · SQ1 + SQ2** — S-0.5 first, S0 sliced per port *(both appear satisfied; confirm)*
- [ ] **D-2 · SQ3** — ***"Every gate ships a bite. A gate that cannot fail is decoration."***
  **97 gates are wired.** How many have a recorded bite? This is the highest-leverage row in the
  register, because it governs the trustworthiness of every other verdict in this audit: a gate
  without a bite is an unproven instrument, and the audit leans on gates throughout.
  `D-T38-MECHANISM-IS-VACUOUS` is one confirmed instance already.

### Phase E — report and route

- [ ] **E-1** — Conformance table: 31 rows, verdict + command + numbers. Publish as an artifact.
- [ ] **E-2** — Axis C, computed: every non-IMPLEMENTED decision whose task reads `[x]`.
- [ ] **E-3** — Route: PO decisions separated from implementation work; the refactor plan's RESUME
      re-pointed at whatever the audit shows is actually load-bearing, which may not be T38.

---

## Definition of done

**Not** "all 31 rows are IMPLEMENTED" — that is the refactor's job, not the audit's.

This audit is done when **every one of the 31 rows carries a verdict and the command that produced
it**, PARTIAL rows carry their population ratio, and the gaps are routed. The audit's product is a
*true* picture, which is the precondition for the PO's definition of session-done and is currently
what the project does not have.

## Stop conditions

1. **A sealed decision is found to be wrong** (not merely unbuilt) → stop, present evidence, PO
   re-opens. Do not design around it.
2. **`SQ3` finds that gates broadly lack bites** → the instruments this audit relies on are
   themselves unproven, and gate repair outranks finishing the sweep.
3. **A read against a shared store would need a write to answer** → stop; use a throwaway.
