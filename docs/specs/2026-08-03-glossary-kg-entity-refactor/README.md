# The glossary↔KG entity-consistency refactor — tracking index

**Status:** 🔒 **DESIGN SEALED 2026-08-09.** Three investigations + one evidence doc were the inputs;
none of them was a design and each said so. A six-document architecture now exists on branch
`refactor/entity-lifecycle`, **red-teamed and sealed** — **all 30 opened questions closed, no code
changed.** SEALED means the *reasoning* is closed and must not be re-litigated from memory — re-read it.
Start at [**ARCHITECTURE-OVERVIEW**](2026-08-09-ARCHITECTURE-OVERVIEW.md); the decision register is its
[§9](2026-08-09-ARCHITECTURE-OVERVIEW.md#9--sealed--decision-register).
**Opened:** 2026-08-03 · **Evidence re-verified at:** `24dd7bdac` · **Proposal verified at:** `df18e9049`
**Umbrella deferral:** `D-GLOSSARY-KG-REFACTOR-DESIGN` (see the register below)

> ### 📐 The 2026-08-09 sealed design — read in this order
>
> | doc | what it is |
> |---|---|
> | [**ARCHITECTURE-OVERVIEW**](2026-08-09-ARCHITECTURE-OVERVIEW.md) | **entry point.** The whole system in one picture · four services / four sentences · the knowledge-service module decomposition · ports & adapters · symptom→cause→fix · order |
> | [**knowledge-architecture-DIAGRAM**](2026-08-09-knowledge-architecture-DIAGRAM.md) | the two boundaries (**gateway-only KAL** + ports), write/read paths, transaction ownership, **five** failure modes, the command vocabulary, gates with bites |
> | [**kg-storage-migration-PLAN**](2026-08-09-kg-storage-migration-PLAN.md) | port-first migration off Neo4j · why the vector layer moves first · **AGE eliminated by dialect audit** · Postgres-relational vs Kuzu · P-0.5 → P3 |
> | [**lore-pipeline-architecture-PROPOSAL**](2026-08-09-lore-pipeline-architecture-PROPOSAL.md) | the **book layer**: physical lifecycle · story status · **world order as a partial order over events** · the two PO acceptance cases |
> | [**current-architecture-blast-radius**](2026-08-09-current-architecture-blast-radius.md) | the survey the proposal is built on — every store, service and wire |
> | 🔴 [**architecture-RED-TEAM**](2026-08-09-architecture-RED-TEAM.md) | **adversarial review, 8 perspectives, 14 findings — 5 survive, 3 changed the plan.** Read it before acting on any of the above: it moved the PO's acceptance cases to **first** instead of last, sliced the port work per-port, and promoted three open questions to blocking gates |
>
> **The PO framing this answers:** the platform lacks a reliable read/write pipeline from disk
> through book → lore bible → manifest → reality; the KG access layer covers reads only; and the
> data layer was never split behind a port, so the vendor cannot be changed.

> 📒 **[`DEBT-REGISTER.md`](DEBT-REGISTER.md)** — date-numbered (`YYYY-MM-DD-NN`) register of every
> open item across **three** pending refactors: this one, the
> [chat-service control plane](../2026-07-30-chat-service-control-plane-refactor.md), and the
> [generation SSOT](../2026-07-31-generation-ssot.md). **40 open · 17 of them have no other home.**
> Added 2026-08-03 at the author's request, because debt from a finished run was surviving only
> inside that run's own RUNSTATE.

---

## 1 · Why one refactor and not three tasks

The three documents were written days apart, from unrelated triggers, by following three
different bugs. They converge on **one** missing concept: *nothing in this system owns what an
entity IS, or when it stops being one.*

| the question nobody owns | the document that found it |
|---|---|
| **what is an entity's identity?** | identity is `hash(user, project, name, kind)` over two LLM outputs; a miss does not degrade, it **mints** — [entity-identity](2026-08-01-entity-identity-under-qualitative-extraction.md) |
| **what is an entity's kind?** | it was whichever extraction batch named it first; **11%** of a measured book disagreed with the model's own modal answer — [entity-kind-resolution](2026-08-02-entity-kind-resolution.md) |
| **when is an entity gone?** | four services keep four private answers and no event connects any two — [entity-lifecycle](2026-08-02-entity-lifecycle-architecture-gap.md) |

Kind is *part of the identity hash*, and lifecycle is *a state on the thing the hash names*. So
a fix to any one of them re-cuts the seam the other two run through, which is why the deferral
rows below all point at this refactor rather than at each other.

---

## 2 · The inputs — three investigations, one piece of evidence, and the map

> **Added 2026-08-09:** [`2026-08-09-current-architecture-blast-radius.md`](2026-08-09-current-architecture-blast-radius.md),
> the storage/service/dataflow survey. Read it **second**, right after lifecycle: the three
> investigations each follow one bug deep, and none of them says how wide the ground is. Its §8
> carries four things none of the other four documents contain — including a **rename/re-kind
> leaving a stale `e.id` in Neo4j**, which the 2026-08-02 kind backfill fired 77 times.

| doc | status | what it is | what it explicitly does NOT do |
|---|---|---|---|
| [**2026-08-01 · entity identity under qualitative extraction**](2026-08-01-entity-identity-under-qualitative-extraction.md) | DIAGNOSIS · **PARKED by the author 2026-08-02** | measured: **21 of 21** `:EntityStatus` rows in the whole dev graph are unreachable by the guard's FK lookup, across 5 projects. Proposes an order **C → D → A → B** (measure the fork · add the missing `CheckStatus` · make "unresolved" first-class · separate identity from the name) | no cost analysis; §6 flags the status-attach mechanism as a **hypothesis reasoned from code, not measured** |
| [**2026-08-02 · entity-kind resolution**](2026-08-02-entity-kind-resolution.md) | DESIGN · **M1–M3 SHIPPED**, M4 open | the one document here that is a design and that has landed: `entity_kind_votes`, hysteresis, hierarchy + refinement, the 173-row backfill (77 re-kinds applied on 封神演義, 399 entities carrying a facet, 33 a live conflict) | does not make `kind_id` nullable or multi-valued; does not re-open `BTG-A28`; does not touch the extraction prompt |
| [**2026-08-02 · there is no entity lifecycle**](2026-08-02-entity-lifecycle-architecture-gap.md) | INVESTIGATION COMPLETE | per-call-site audit across 7 services; §5 is a list of six questions the refactor must answer; §7 re-derives every headline claim from a grep so the next session need not re-investigate | **deliberately stops short of a design** (§5, first line) |
| [**2026-08-03 · dogfood entity-consistency evidence**](2026-08-03-dogfood-entity-consistency-evidence.md) | EVIDENCE · added 2026-08-03 | what the gap costs the READER. An end-to-end authoring run through the real frontend: a `rival` minted by the `cast` pass at 05:47 took the antagonist's defining act at 05:54, and the critic scored `canon_consistency = 5/5` on all three chapters. Also: a materialise preview that claimed 12 new glossary entries when all 12 existed, and 3-of-8 defensible relationship edges | not a design and not an investigation — it proposes nothing. It exists to be the **acceptance case** |
| [**2026-08-09 · current architecture & blast radius**](2026-08-09-current-architecture-blast-radius.md) | SURVEY · added 2026-08-09 at `df18e9049` | **the map the other four do not draw.** Every store, service and wire that holds entity-shaped data: 27 of 47 services · 8 Postgres DBs · 10 Neo4j labels · 31 of 43 FE folders · the state × store table lifecycle §5.2 asked for · the 15-item ranked blast radius of one delete. Adds four findings the inputs miss (§8) | not a design — it decides nothing and proposes nothing. It is the input the design's §5.3 *"which states are load-bearing where"* question is answered **from** |

**Read them in this order:** lifecycle (the widest map) → **blast radius** (how wide the ground
actually is, and every store that has to hear about a state change) → identity (the deepest root)
→ kind (the one worked example of a fix that landed) → **dogfood evidence** (what all of it costs
in finished prose — read last, because it only lands once the rest have named the mechanism).

**The evidence doc is the bar.** The three investigations each end without a design, so there is no
statement anywhere of what "fixed" would mean. §1 of the evidence is that statement, in the only
terms the author can check: *a character invented seven minutes earlier absorbed the betrayal the
plan assigns to someone else, and every automated signal said the chapter was clean.* A design that
cannot prevent that has not addressed this refactor, however much of the identity/kind/lifecycle
machinery it rebuilds.

---

## 3 · Deferral register — everything this refactor owns

Rows marked ⬜ are also in the **Deferred Items** table of
[`docs/sessions/SESSION_HANDOFF.md`](../../sessions/SESSION_HANDOFF.md). This table is the
detail; that one is the index.

| id | what | gate | trigger / state |
|---|---|---|---|
| ⬜ **D-GLOSSARY-KG-REFACTOR-DESIGN** | *(new 2026-08-03)* the refactor has **three inputs and no design**. Nothing sequences them, nothing states what lands first, nothing says what "done" is | #2 large/structural | the author starting this track. **This row is the entry point — the other rows below cannot be worked before it** |
| ⬜ **D-ENTITY-LIFECYCLE** | the whole lifecycle gap: `deleted_at` · `status` · `alive` · KG `archived_at` · `is_glossary_stale`, five notions of "gone", zero events between them. A trashed entity still reads **`canonical`** in the graph | #2 large/structural — **game-tier critical**: the game generates narrative from canon, so a retraction the graph never hears about becomes world state | this refactor |
| ⬜ **D-KG-KIND-FACETS** | knowledge-service mirrors one `kind_code TEXT NOT NULL`, so the graph cannot filter on the facets shipped 2026-08-02 (399 entities carry one). This is the **KG half of the kind spec's M4** | #1 out of scope — cross-service contract, and this refactor re-cuts exactly that seam | this refactor |
| ⬜ **D-GLOSSARY-EVENTS-NO-SOT** | `contracts/events/_registry.yaml` calls itself the *"AUTHORITATIVE list of every event_type"* and holds **zero** `glossary.*` entries; the real list is a Go `const` block hand-mirrored by every consumer, with no generator and no drift gate | #2 large/structural | **adding any new glossary event** — i.e. `glossary.entity_deleted`, which D-ENTITY-LIFECYCLE needs. This one fires *first* |
| ⬜ **D-ENTITY-IDENTITY-HASH** | *(new 2026-08-03)* identity is `hash(user, project, name, kind)` over LLM output; an anchor miss mints a duplicate that only a human can merge. **Consequence to state plainly: the dead-character feature does not work end-to-end while this is parked — the store fills and nothing reads it** | #2 large/structural, and **parked by author decision 2026-08-02** (*"do not dive into KG now"*) | this refactor, or the author un-parking it. Its own §5 says step **C (measure the fork)** must precede everything |
| ⬜ **D-KIND-FACETS-SURFACE** | *(new 2026-08-03)* the rest of the kind spec's **M4** — the API field and the FE badge for secondary labels. Shipped in the DB and applied to real data; invisible to every consumer | #3 naturally-next-phase | after `D-KG-KIND-FACETS`, so all three surfaces move together |
| ⬜ **D-CANON-CHECK-BLIND-TO-ROLE** | *(new 2026-08-03, [evidence §1](2026-08-03-dogfood-entity-consistency-evidence.md))* a character the `cast` pass minted at 05:47 took, at 05:54, the betrayal the same plan assigns to someone else — and `canon_consistency` scored **5/5** on all three chapters. A **role assignment** has nowhere to live that a check can fail on. **This is the refactor's acceptance case** | #2 large/structural — it needs the identity seam this refactor re-cuts | this refactor. Its shape is the design's own test: fix the design, then re-run this book |
| ⬜ **D-BOOTSTRAP-PREVIEW-LIES** | *(new 2026-08-03, [evidence §2](2026-08-03-dogfood-entity-consistency-evidence.md))* the materialise preview dedupes glossary seeds against prior *proposals* only — never the book — and defaults every kind to `character`. Offered 12 "new" entries that all existed, under kinds they do not have. The write is safe (upsert-by-name); the **human-approval gate** is not | **NOT deferred — fix-now shaped**: one function, and the chapter half beside it already does it right | do it whenever this folder is next opened; it does not need the design |
| ⬜ **D-UNKNOWN-PARK-IS-PROSE-NOT-DATA** | *(new 2026-08-03, author-proposed)* the `unknown` parking bucket keeps an entity's unmatched attributes as PROSE lines appended to `description`, not as data. The next reader is a kind-resolution pass deciding what the thing IS, and it would have to re-parse what the extractor already had structured. A JSONB column on the parked row is the proposal | #3 naturally-next-phase — harmless while parking is rare, load-bearing the moment the refactor re-kinds parked entities in bulk | this refactor. **Note the parking path only started working at all on 2026-08-03** — the `unknown` kind had zero attributes, so the (correct) nameless-entity guard refused every park |
| ⬜ **D-KG-EDGE-TYPING-UNCHECKED** | *(new 2026-08-03, [evidence §3](2026-08-03-dogfood-entity-consistency-evidence.md))* 8 relationship edges proposed, **3 defensible**: a `power_system` `enemy_of` a person, and an `event` `betrayed`-ing the two characters who are the betrayers. The kinds that reject both are already stored; the proposer does not read them | #2 large/structural — edge typing is exactly the seam `D-KG-KIND-FACETS` moves | this refactor, after the kind mirror lands |

### 🔴 Three bugs this folder's own spec records as CLOSED, and which are OPEN

[entity-lifecycle §6](2026-08-02-entity-lifecycle-architecture-gap.md) lists three items as
*"not deferred — fix now"* and then says they are *"listed here only so the refactor knows they
were already closed."* **They were not.** Re-verified at `24dd7bdac`:

| id | claim | actual |
|---|---|---|
| **D-ENTITY-EXISTS-GUARD** | *"one line"* | [`entity_genres_handler.go:40`](../../../services/glossary-service/internal/api/entity_genres_handler.go#L40) still reads `WHERE entity_id=$1 AND book_id=$2` with **no `deleted_at IS NULL`**. It guards canonical-translation, fold, append-fact, split-entity and two MCP genre tools — the canonical-translation path fires a **real, paid LLM call** on deleted content and caches the result |
| **D-KNOWN-ENTITIES-PER-JOB** | fixed | [`extraction_worker.py:473`](../../../services/translation-service/app/workers/extraction_worker.py#L473) still fetches `known_entities` before the chapter loop at `:556`. Delete an entity mid-job and every remaining chapter re-emits it |
| **D-OUTBOX-PAYLOAD-TRASH** | fixed | [`outbox.go:398`](../../../services/glossary-service/internal/api/outbox.go#L398) still selects `WHERE e.entity_id = $1` with no lifecycle filter, so editing a trashed entity re-publishes it and knowledge-service re-embeds it — **the deletion is silently reversed in the consumer's index** |

Because all three were declared *not deferrals*, none has a row anywhere: they are invisible to
every gate and to the Deferred Items table. They are still **fix-now** by CLAUDE.md's defer gate
(single-file, root cause known) — they are recorded here so they cannot be lost again, **not** to
license deferring them. The lifecycle spec's §6 has been corrected in place.

---

## 4 · What has already shipped (do not re-derive)

| | evidence |
|---|---|
| **kind resolution M1–M3** | `entity_kind_votes` ledger · `domain.ResolveKind` (pure, hysteresis `>1.5×`/`≥2`, refinement exempt, roll-up + strict-majority descent) · `parent_kind_id` × 3 tiers · the backfill applied **77 re-kinds + 77 outbox events**, idempotent on re-run, **17 of them merges** detected and reported as `blocked_by_duplicate` |
| **glossary↔KG linkage, both holes** | the `term`-vs-`name` display-attribute miss (**215 of 224** terminology entities had no name → no dedup key → endless duplicate rows); and `chapter_index` meaning different things to writer and reader. Both cleared 2026-08-01 *specifically* to stop them corrupting the data this refactor builds on |
| **`archive_entity` exists and is correct** | `knowledge-service/app/db/neo4j_repos/entities.py:1113` preserves every edge, honoured at **38 sites**, `restore_entity` is its inverse — and `reason='glossary_deleted'`, named in its own docstring, **has only test callers.** The deletion path was designed, implemented, and never connected to a trigger |
| **`findEntityCrossKind` filters `deleted_at`** | the scariest hypothesis — that a trashed entity could be resurrected as a dedup target — is **false** |

---

## 5 · What the new design has to decide

From [lifecycle §5](2026-08-02-entity-lifecycle-architecture-gap.md#5-what-the-refactor-has-to-decide)
and [identity §5](2026-08-01-entity-identity-under-qualitative-extraction.md#5--where-the-architecture-should-change),
merged and de-duplicated:

1. **What ARE the states?** Proposed minimum `draft → active → retired → trashed → purged`, with
   `retired` = *"keep it, stop using it"* — the state the product needs and does not have.
   `alive` is orthogonal (narrative death) and should be renamed to say so.
2. **What IS an identity?** An opaque id owned by the glossary layer, with the KG holding
   *mentions* that point at it — not `hash(name, kind)` over model output.
3. **Which states are load-bearing where?** One table: state × consumer × behaviour. Today it
   would be almost entirely blank; that blankness is the finding.
4. **How does a state change TRAVEL?** Event with a real SoT entry, reconcile sweep, or both.
   Merge proves the event path works end-to-end; **no reconcile sweep exists anywhere.**
5. **What is the anti-resurrection rule?** Extraction re-creates by name, and archive is not a
   tombstone (`archive_entity` nulls `glossary_entity_id`, so the next extraction re-matches by
   name and resurrects). Restore is also not symmetric — it must re-anchor, not just clear
   `archived_at`.
6. **Who owns the lifecycle?** glossary is the authored SSOT, KAL is derived; `archived_at`
   should be a **projection** of the authored state, not a peer of it.
7. **What proves it?** A conformance test per consumer — trash an entity, assert it is absent
   from that consumer's output. Written once, run for every consumer, **red before green.**

**Sequencing constraint the inputs already agree on:** measure before you design. Identity §5's
step **C** (how many minted entities fold-collide with an existing anchor under a looser
comparison) is *"the honest size of the problem, and nothing currently computes it."* Lifecycle
§7 ends with the one controlled experiment nobody has run: trash a **live** entity that has a
Neo4j node, then re-run a context selector.

---

## 6 · Known blind spots in the inputs — do not mistake them for clean

The lifecycle audit [names its own boundary](2026-08-02-entity-lifecycle-architecture-gap.md#8-scope-of-this-audit--what-was-not-looked-at)
and the design must close it:

- **The game tier was not audited at all** — `game-server`, world/travel/tilemap, the whole
  LLM_MMO_RPG track. This is the worst gap, because it is where the consequences are worst.
- **The frontend** beyond the glossary feature folder; other panels may hold their own caches.
- **enrichment / learning / usage-billing** and the rest of the 47 services — judged unlikely to
  hold entity copies; that judgement was never tested.
- **Neo4j orphans other than `:Entity`** — `Event`, `Fact`, `Passage` referencing a trashed
  entity were not traced.
- **Historical damage is unmeasured** — nobody knows how many *currently published* wiki
  articles or translated chapters already contain a retracted entity. That number is the real
  cost.
- §3.3 and §3.4 of the lifecycle audit are marked ⚠ (contributed by audit agents, spot-checked
  on the load-bearing claims only).
