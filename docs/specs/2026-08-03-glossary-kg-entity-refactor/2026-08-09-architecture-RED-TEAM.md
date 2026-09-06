# Red team — the 2026-08-09 knowledge architecture

**Reconciles:** **Reading/writing entity or KG knowledge** · **Module/service boundaries** · **Non-Vacuity** — a red-team OF the overview above. It asserts nothing new: every attack it records is aimed at one of those rows holding or not holding.

**Status:** 🔴 **ADVERSARIAL REVIEW** · ✅ **DISCHARGED 2026-08-09** — all 7 required changes applied; the design is now [SEALED](2026-08-09-ARCHITECTURE-OVERVIEW.md#9--sealed--decision-register) · **Opened:** 2026-08-09 · **Verified against:** `df18e9049`
**Target:** [ARCHITECTURE-OVERVIEW](2026-08-09-ARCHITECTURE-OVERVIEW.md) +
[DIAGRAM](2026-08-09-knowledge-architecture-DIAGRAM.md) +
[MIGRATION PLAN](2026-08-09-kg-storage-migration-PLAN.md) +
[BOOK-LAYER PROPOSAL](2026-08-09-lore-pipeline-architecture-PROPOSAL.md)

> **Method.** Eight perspectives, each attacking to break rather than to note. Every finding states
> the **evidence**, the **counter-argument**, and whether it **SURVIVES**. Findings that do not
> survive are kept — a red team that reports only hits is unfalsifiable.
> **`RT-` prefix.** Severity: 🔴 changes the plan · 🟡 changes a decision · ⚪ noted.

**Headline: 5 of 14 findings survive, and 3 of those change the plan.** The architecture is sound in
shape and **wrong in sequencing**.

---

## 1 · Product / delivery

### 🔴 RT-1 — The architecture defers the PO's actual pain by months, and a cheap fix exists

**Attack.** AC1 (*"the agent cannot know a character is dead"*) and AC2 (*"the agent confuses the
protagonist across chapters"*) are the stated reasons this refactor exists. In the proposed order they
land in **S5** — behind S0 (ports, 22,390 LOC of `db`), S1 (vector migration), S2 (KAL write path),
S3 (consumer migration). That is months of work during which the reported defect is untouched.

**Evidence it is avoidable.** The substrate for AC2 **already works**: `entity_facts` is bitemporal,
`emitChapterFacts` writes every attribute at its chapter ordinal, `maintain_chain` maintains pin-aware
supersession, and `/internal/…/facts?as_of=` implements the correct half-open predicate.
`composition-service` simply never passes `as_of` — **zero occurrences**. A `state?as_of=N` read over
existing tables, and one caller migrated, is days of work, not months.

**Counter.** Doing it before the port means writing it twice.
**Does the counter hold?** No. It is one read endpoint over Postgres tables that no part of the port
work touches. Rewriting it later is hours.

**SURVIVES.** → **Add an S-0.5 slice before S0**: `state?as_of` + AC1/AC2 conformance tests, shipped
against today's schema. It also de-risks everything after it by proving the read shape on real data
before 22k LOC are moved.

### 🟡 RT-2 — "The lore bible is not designed yet" is load-bearing and unowned

**Attack.** The overview's §1 shows the bible compiling the manifest, and the book-layer proposal
excludes it as "not designed yet." But the bible is the artifact the canon check evaluates against —
so `D-CANON-CHECK-BLIND-TO-ROLE`, the register's stated **acceptance case for the whole refactor**,
is closed by a document nobody is writing.

**Counter.** Book-layer work is a prerequisite regardless.
**Does it hold?** Partly — but the register claims this refactor's acceptance case, and the plan does
not close it. **SURVIVES as a scope-honesty defect**: either the bible enters scope, or the register
row is re-pointed and the claim withdrawn.

---

## 2 · SRE / operator

### 🔴 RT-3 — "Rebuildable" is false for the vector layer, so the DR story is fiction

**Attack.** Three separate claims lean on rebuild-from-Postgres: graph HA is unnecessary (§4),
engine-swap rollback (P3), and DR. **Rebuilding vectors means re-embedding.** At 10k books that is
~63 M passages through an embedding model — **an LLM budget event, not a recovery procedure.**
`find_entities_needing_embedding` already exists precisely because embedding is expensive enough to
schedule.

**Counter.** Embeddings could be dual-stored, or exported/reimported as blobs rather than recomputed.
**Does the counter hold?** Yes — but **only if designed in**, and nothing in the plan says so.

**SURVIVES.** → The vector layer needs an explicit **embedding durability** decision: vectors are
either (a) durable primary data with real backups, or (b) recomputable with a stated cost and time
budget. "Derived, therefore free to rebuild" is true for the graph and **false for embeddings**, and
the plan currently treats them identically.

### 🔴 RT-4 — The self-hoster's deployment gets harder, and that was the founding argument

**Attack.** The migration is justified by open-source operability — Neo4j Community's scale path
requires a commercial licence. But the replacement requires a **custom Postgres image**:
`postgres:18-alpine` ships neither AGE nor pgvector, and **pgvectorscale's PG18 support is
unverified** (O2). A self-hoster today runs `docker compose up` and gets a working Neo4j. After the
migration they need a bespoke image with two-to-three compiled extensions, version-pinned together.

Worse: if pgvectorscale lags PG18, the *entire platform's* Postgres is pinned to an older major —
affecting **every service on that instance**, plus Patroni and the backup story, not just knowledge.

**Counter.** Publish a prebuilt image.
**Does it hold?** It reduces but does not remove it — you now own a Postgres distribution, its CVE
cadence, and its upgrade path across three extensions.

**SURVIVES.** → O2 is not a detail; it is a **gate on the whole migration**. Verify before committing,
and state the extension-matrix ownership cost honestly in the plan.

### 🟡 RT-5 — The KAL becomes a write-path single point of failure

**Attack.** Centralizing writes means a KAL outage stops *all* lore writes platform-wide. Today
glossary-service is directly reachable, so a gateway failure degrades rather than halts. The KAL is
also a Node service in front of Go and Python — a third runtime on the critical path.

**Counter.** It is already the read boundary, and `SR06` tiers dependencies.
**Does it hold?** Partly. But the KAL has **no tier classification in `SR06`**, and the write path is
new. **SURVIVES as a gap**: the KAL needs a dependency tier and a documented degraded mode before it
owns writes.

### ⚪ RT-6 — Neo4j and Postgres have different backup/PITR semantics

Consolidating means one backup story instead of two, which is a *win*. Noted only to record that the
current split is not costless in the other direction either. **Does not survive as an objection.**

---

## 3 · Performance

### 🔴 RT-7 — The hot path gets a new hop, and D2 makes it run more often

**Attack.** F3 says knowledge-service's own assembly stays in-process; F4 says the owning service keeps
the transaction. But `state@as_of` for composition is **cross-service and hot** — every chapter of
every drafting run — and D2 makes it **required rather than optional**, so it runs *more* than the
reads it replaces. The path becomes composition → KAL (Node) → glossary (Go) → Postgres, with two
serialization boundaries.

**Evidence of scale sensitivity.** The nearest measured analogue, `anchor_dict`, is ~40 ms p95 for a
5,000-row scan. `state@as_of` for a 3,000-entity book is a larger query, run per chapter.

**Counter.** It replaces `roster` drain, which is also multi-page and cursor-drained.
**Does it hold?** Unknown — **nobody has measured either**, and
[`21` §7](../../03_planning/LLM_MMO_RPG/21_architecture_ceilings.md) forbids inferring headroom.

**SURVIVES.** → `state@as_of` needs a **ceiling measured before S2**, in the doc-21 style: rig stated,
durability stated, ratios not absolutes, with a bite. This is the single measurement most likely to
invalidate the design.

### 🟡 RT-8 — AGE's traversal weakness is excused by today's shallow queries, which the roadmap contradicts

**Attack.** The plan accepts AGE partly because the workload is shallow — 2 variable-length patterns,
0 `shortestPath`. But the same documents argue relationship extraction is *immature* (3 of 8 edges
defensible) and will mature. **The justification assumes the workload stays weak because it is
currently broken.** That is the flattering-number trap in a different costume.

**Counter.** The port makes the engine replaceable if density grows.
**Does it hold?** Yes — this is exactly what the port is for. **Downgraded to 🟡**: record it as a
stated assumption with a trigger (*"if median entity degree exceeds N, re-open the engine choice"*),
rather than leaving it implicit.

---

## 4 · Correctness / data

### 🔴 RT-9 — Shadow comparison cannot catch what it does not see

**Attack.** P2 chooses the engine by diffing two adapters on real traffic. That only covers *executed*
paths. Rare branches — merge, split, restore, coref repair, triage — diverge silently, and the graph
feeds **canon checks**, so divergence there becomes wrong prose rather than an error.

**Counter.** Contract tests over the port cover shape.
**Does it hold?** Shape is not semantics: null ordering, tie-breaking, isolation and index behaviour
differ between engines while shapes match.

**SURVIVES.** → Shadow comparison must be paired with a **property-based differential suite** over the
port (generate operations, assert both adapters agree), not only production sampling. And a
**coverage floor**: no cutover while any port operation has zero shadow observations.

### 🟡 RT-10 — Moving outbox ownership breaks hand-mirrored event contracts

**Attack.** If `TruthStore` consolidates, `glossary.*` outbox ownership moves. Those event types are a
Go `const` block **hand-mirrored by five consumers with no generator and no drift gate** —
`D-GLOSSARY-EVENTS-NO-SOT`, still open, **0 `glossary.*` entries in the registry**. Moving a producer
under hand-mirrored strings is silent breakage by construction.

**Counter.** Consolidation is gated behind identity unification anyway.
**Does it hold?** Yes for timing, no for risk. **SURVIVES as an ordering constraint**:
`D-GLOSSARY-EVENTS-NO-SOT` must close **before** any producer moves.

### ⚪ RT-11 — Two truth stores could diverge during the port period

The port routes by scope, so both remain authoritative for disjoint scopes; no shared rows means no
divergence. **Does not survive** — but only because scopes are disjoint. If consolidation introduces
dual-write, this returns as 🔴.

---

## 5 · Migration / delivery

### 🔴 RT-12 — This repo's own history says foundation work stalls halfway

**Attack.** S0 is a 22,390-LOC substrate refactor with **no user-visible change** — the least
defensible kind of work to protect under pressure. The strongest evidence is local and unflattering:
**the KAL is the previous instance of exactly this plan.** It was specified, contracted, gated, and
reached **18 of 204 routes** before stopping. The temporal-knowledge plan was XL with "serial
foundation then fan out"; the foundation landed and the fan-out is what this document is still
arguing about.

**Counter.** The port is smaller and mechanical.
**Does it hold?** Partly — but the KAL was also framed as mechanical.

**SURVIVES.** → S0 must be sliced so **each port ships independently and separately valuable**:
`VectorStore` first (it carries RT-3 and the only hard ceiling), then `OntologyStore` (smallest,
2.5k), then `GraphStore`, then `TruthStore`. An all-or-nothing S0 is the failure mode this repo has
already demonstrated once.

### 🟡 RT-13 — "Zero allowlist" is cited as proof the mechanism works, but it was scoped narrowly

**Attack.** The plan leans on the HTTP-surface gate's zero allowlist as evidence consumers can be
migrated. But that gate covers **only bi-temporal knowledge reads** — its own comment says the
authored entities-LIST endpoint is *"intentionally NOT here."* The zero was achieved by scoping the
problem small, and S3 proposes the opposite: the **186 remaining routes**.

**Counter.** The mechanism is proven even if the scope was small.
**Does it hold?** The mechanism, yes; the *extrapolation of effort*, no.
**SURVIVES as a claim to soften** — remove "proven at scale" framing; it is proven in miniature.

---

## 6 · The skeptic (YAGNI)

### 🟡 RT-14 — The whole infra case rests on a load nobody has

**Attack.** The dev corpus is **7 books, 5 projects, 6,294 entities, 3,069 edges**. The 10,000-book
scenario drives every infra conclusion — drop Neo4j, adopt pgvectorscale, build ports. Doc 21's own
discipline says **do not infer headroom from unbuilt systems**; this reasons from an unbuilt *user
base*. If the platform never reaches 1,000 deployed books, this is a large investment against a load
that never arrives.

**Counter — and it holds.** It is an **open-source platform**: the operator's scale is not the
author's, and an architecture whose only growth path is a commercial licence is a defect you ship to
*other people*. That argument does not depend on LoreWeave's own adoption curve. Additionally the
30k-index problem is **structural, not load-dependent** — it appears at whatever tenant count a
deployer reaches, and it is a design property visible today.

**DOES NOT SURVIVE as an objection to the migration.** **Survives as a sequencing argument**, which is
RT-1: fix the reported defect first, migrate on a schedule that is not blocking users.

---

## 7 · Verdict

| # | finding | sev | verdict |
|---|---|---|---|
| RT-1 | acceptance cases deferred behind months of infra | 🔴 | **SURVIVES → add S-0.5** |
| RT-3 | "rebuildable" false for vectors; DR is fiction | 🔴 | **SURVIVES → embedding durability decision** |
| RT-4 | self-hoster deployment gets harder; PG version pinning | 🔴 | **SURVIVES → O2 is a gate, not a detail** |
| RT-7 | hot-path hop unmeasured, and D2 increases its frequency | 🔴 | **SURVIVES → measure before S2** |
| RT-12 | foundation work stalls here; the KAL is the precedent | 🔴 | **SURVIVES → slice S0 per-port** |
| RT-9 | shadow comparison misses unexecuted paths | 🟡 | SURVIVES → property-based differential + coverage floor |
| RT-10 | outbox move under hand-mirrored contracts | 🟡 | SURVIVES → close `D-GLOSSARY-EVENTS-NO-SOT` first |
| RT-2 | bible is load-bearing and unowned | 🟡 | SURVIVES → scope it or re-point the register row |
| RT-5 | KAL as write-path SPOF | 🟡 | SURVIVES → needs an `SR06` tier + degraded mode |
| RT-8 | AGE justified by a workload that is weak because broken | 🟡 | SURVIVES (downgraded) → state the assumption + trigger |
| RT-13 | "zero allowlist" over-claimed | 🟡 | SURVIVES → soften the claim |
| RT-14 | building for a load nobody has | ⚪ | does not survive as an objection; **becomes RT-1** |
| RT-6 | backup semantics | ⚪ | does not survive |
| RT-11 | truth-store divergence | ⚪ | does not survive *while scopes are disjoint* |

### What must change before detailed design

1. **Insert S-0.5** — `state?as_of` + AC1/AC2 conformance, on today's schema, before any port work. *(RT-1, RT-14)*
2. **Slice S0 per-port**, `VectorStore` first, each independently shippable. *(RT-12, RT-3)*
3. **Verify O2/O3 as gates**, and price the extension-matrix ownership. *(RT-4)*
4. **Measure `state@as_of`** doc-21 style before S2 commits. *(RT-7)*
5. **Decide embedding durability** — backed-up primary data, or recomputable with a stated budget. *(RT-3)*
6. **Close `D-GLOSSARY-EVENTS-NO-SOT`** before any producer moves. *(RT-10)*
7. **Add a property-based differential suite + shadow-coverage floor** to P2's exit criteria. *(RT-9)*

### What the red team did NOT break

Recorded so the surviving structure is explicit rather than assumed:

- **The two-boundary model** (KAL + ports). No perspective produced an attack on the shape — every
  finding was about *sequencing, measurement or operability*.
- **Memory as a module rather than a service.** The scope-split argument held under attack.
- **`VectorStore` as its own port.** Attacked from three directions; strengthened each time.
- **Neo4j's disqualification.** RT-14 was the strongest available counter and it failed: the licence
  ceiling and the per-tenant index pattern are structural, not load-dependent.
