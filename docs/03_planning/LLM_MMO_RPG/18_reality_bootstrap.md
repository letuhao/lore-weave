# 18 — Reality Bootstrap (design)

> **✅ CORRECTED 2026-07-26 — correction pass applied** (per the same-day banner +
> [`19_reconciliation_register.md`](19_reconciliation_register.md) §12b). What changed:
>
> - **§6 / RBS-A7** — `*Born` events re-anchored on **EVT-T5 Generated** (Generator role =
>   `RealityBootstrapper` per EVT-A4), never EVT-T4. The subset is
>   schema → capability → causal-ref → commit — **reduced, not zero**; the seed-gate justification
>   survives with corrected scope. CS-D9's parallel error is recorded as **REC-52**.
> - **§3.2** — the phase-1 hard blocker resolved with the **seed-root pattern** (RBS-D8): phase 1
>   causal-refs the reality-creation EVT-T8 admin event; later phases ref their predecessor.
>   Checked against `09_causal_references.md`: **EVT-L13 as written has no cross-category
>   restriction**, so a T5→T8 ref passes and no AMEND item is needed for it.
> - **RBS-A2** — rewritten: restore-import is a **new DP-internal primitive requiring an explicit
>   EVT-A3/EVT-A10 exemption — pending AMEND (REC-53 bundle)**; re-emission with fresh ids + an
>   id-mapping table is documented as the fallback if the exemption is refused.
> - **RBS-A5** — re-shaped to the uniform `IdempotencyKey` triple; re-cited to the commit-primitive
>   dedup + **EVT-V3** (EVT-L3 was the wrong citation — that is proposal-bus dedup).
> - **RBS-A8** — names the one gate that actually runs during seeding (**idempotency**); the
>   EVT-G2 trigger-kind and EVT-G4 capacity-ceiling exemption for the bootstrapper ride the AMEND
>   bundle. **RBS-A3** is explicitly marked a **DP-A16 amendment request to the DP owner**.
> - **RBS-F3** — site list gains `07_event_model/02_invariants.md` EVT-A4. **RBS-Q1** gains the
>   mechanical EVT-G4 note.
>
> The phase DAG (§3), the RBS-F1 cycle, the two failure classes (§5) and the three seed sources
> (§1) were unaffected and are unchanged.

> **Status:** DRAFT — 2026-07-26. Detail design for **GDA-F6**, the last item blocking **AUD-F8**.
> **Prefix:** `RBS-*` (registered 2026-07-26; axioms `RBS-A1..A8`, decisions `RBS-D1..D9`,
> findings `RBS-F1..F3`, questions `RBS-Q1..Q2`).
>
> **Why a separate doc.** [`17` §4 B2](17_game_data_architecture.md) resolved *which* of two
> conflicting seeding designs wins and on what principle. It did not specify the thing. Bootstrap is
> the flow that runs before every other flow can run, it is the only remaining blocker on
> `commit-service` implementation, and composing it in detail turned up **a circular dependency in
> the `*Born` event order that ships today in two CANDIDATE-LOCK feature docs** (RBS-F1).
>
> **Reconciliation recap (`17` GDA-A3/D3/D4/D5):** `RealityBootstrapper` is a **role** hosted by the
> `02_storage` §12R.2 seeding worker — the CS-A1 pattern. The worker keeps its lifecycle state
> machine, CAS protection, checkpointing, resumability and progress metric; the Bootstrapper
> contributes what to emit. Input is the **`RealityManifest` only**; output is **events**, never
> direct aggregate writes.

---

## 1. Three seed sources, one lifecycle

The lifecycle is single. What differs is where the initial events come from — and the three differ
far more than "seeding" suggests.

```
provisioning ──► seeding ──► active            (CAS-protected per §12Q, all three sources)
```

| `SeedSource` | Used by | What seeding actually does | Ruleset |
|---|---|---|---|
| **`Manifest`** | new reality · **auto-fork** · author-first-reality | emit the full `*Born` phase DAG (§3) from manifest WorldContent | new reality resolves; auto-fork **inherits the parent's digest** (RLS-D10) |
| **`Ancestry`** | **user snapshot-fork** | **emits almost nothing** — records fork point + inherited digest + a marker event. Projections populate lazily as the child diverges (multiverse §12.2) | inherits parent digest verbatim |
| **`ArchiveReplay`** | restore from MinIO (`17` GDA-D14) | **restore-imports archived events** preserving their original `channel_event_id`s — via the exemption-gated restore-import primitive, **pending AMEND** (see RBS-A2, rewritten 2026-07-26) | the pinned digest (`17` GDA-A8) |

> **RBS-A1 — `Ancestry` is the degenerate case, and that is the point.** A snapshot-fork that emitted
> a full `*Born` set would materialise the parent's entire world into the child, which is exactly the
> storage amplification multiverse §12.2 rejects (*"snapshot = projection populated lazily as child
> diverges"*). Its seeding phase is near-empty by design, and a bootstrap implementation that assumes
> "seeding means emitting" will get this case wrong.

> **RBS-A2 (rewritten 2026-07-26) — `ArchiveReplay` is a *restore-import*, and the event model does
> not have one yet.** The original reasoning stands: archived events already carry
> `channel_event_id`s and causal refs, and re-emitting would allocate new ids and break every stored
> causal reference. But a verbatim bulk insert violates two locked axioms — EVT-A3 (every canonical
> state change passes the validator pipeline) and EVT-A10 (`event_id` is DP-allocated at commit) —
> and the event model has no import/restore concept at all. Therefore: **restore-import is a NEW
> DP-internal primitive requiring an explicit EVT-A3/EVT-A10 exemption — pending AMEND (REC-53
> bundle)**. **Fallback if the exemption is refused:** re-emission through the commit path with
> fresh ids, plus a persisted **id-mapping table** used to rewrite causal refs on import — strictly
> worse (a second copy of every id and a rewrite pass over every ref), recorded here so the choice
> is explicit rather than rediscovered.

---

## 2. Who writes — the chicken-and-egg

DP-A16: *each active channel has exactly one writer node.* During seeding the channels **do not exist
yet** — they are what is being created. So which node holds the writer role for a channel that has no
writer because it has no existence?

> **RBS-A3 — Seeding is a single-writer bulk path under a reality-scoped writer lease.** The CP issues
> the seeding worker **one epoch token for the whole reality**, not one per channel. The worker is the
> only writer for every channel it creates, for the duration of `seeding`. The lease **dissolves at the
> `seeding → active` CAS**, at which point normal per-channel writer assignment (DP-Ch13) takes over.
>
> **Marked 2026-07-26:** this lease is **not this doc's to grant**. DP-A16 knows only per-channel
> writers, so RBS-A3 is a **DP-A16 amendment request, routed to the DP owner** (rides the REC-53
> AMEND bundle). Until granted, RBS-A3 is a request, not a rule.

This is safe by construction rather than by protocol: during `seeding` there are no players, no
sessions, no islands and therefore no contention. It is the one window in a reality's life where
single-writer is a fact rather than an invariant to enforce.

> **RBS-D1 — `channel_event_id` allocation starts at 1 per channel and is assigned sequentially by
> the worker.** `UNIQUE(reality_id, channel_id, channel_event_id)` then does double duty: it is the
> ordering constraint at runtime *and* the idempotency guard for a resumed seed (§4).

---

## 3. The phase DAG

Nobody had written the `*Born` order. Composing it from the six features that emit them produces a
dependency graph — and the graph, as currently documented, **has a cycle**.

### 3.1 RBS-F1 — the `MemberJoined` cycle ⚠

Three locked statements, mutually unsatisfiable:

| Source | Statement |
|---|---|
| **PF_001** §2 | `PlaceBorn` is *"emitted alongside cell-channel `MemberJoined` for canonical actors who start at this cell"* |
| **ACT_001** P2 | `CanonicalActorDecl.spawn_cell` *"MUST resolve to a cell-tier channel from `RealityManifest.places`; reject `actor.spawn_cell_unknown`"* |
| **EF_001** | `EntityBorn` births the actor entity |

So: places must exist before actors (actors reference `spawn_cell`), actors must exist before
membership (you cannot join a member that does not exist) — but `PlaceBorn` is specified to emit
membership **with itself**, before any actor is born. The cycle is `PlaceBorn → MemberJoined →
requires ActorBorn → requires PlaceBorn`.

This has been latent because nothing ever ran the sequence; each doc is locally correct.

> **⚠ RBS-F1 is one instance of a five-way disagreement (AUD-F17 #15, 2026-07-26).** A systematic
> sweep found that **PL_001b §16.2, ACT_001, PCS_001, REP_001 and GEO_001 §11 give five different
> canonical-seed orderings, all citing §16.2 as authority** — and the two Tier-5 versions invert
> `EntityBorn`/`PlaceBorn` relative to §16.2 itself, which is what produces this cycle. Under GEO's
> order every canonical actor placement trips `place.missing_decl`. Three docs also name a
> `MapLayoutBorn` that MAP_001 does not own (it owns `LayoutBorn`). **The fix below is confirmed
> correct and independently re-derived** — and the same one-line edit to PF_001 §2.5 also resolves
> CSC_001's zero-width scene-layout window (#16) and a duplicate `MemberJoined` emission currently
> registered to two owners (#38). **PL_001b §16.2 must be restated as the single normative list and
> the other four corrected to it.**

> **RBS-D2 — `MemberJoined` is a *later phase*, not a `PlaceBorn` cascade.** Structural births come
> first, actors second, membership third. PF_001's *"emitted alongside"* is the defect and needs a
> dated correction: `PlaceBorn` births the place and nothing else. **This is a CANDIDATE-LOCK
> correction** (PF_001 + the ownership-matrix row that repeats the phrasing), not a DRAFT edit.

### 3.2 The order

Eight phases. Each is a checkpoint boundary (§4); dependency is the only thing that fixes the order.

| # | Phase | Emits | Depends on | Why |
|---|---|---|---|---|
| 1 | **Channels** | `create_channel` from `root_channel_tree`, parents before children | — | everything is channel-scoped |
| 2 | **Geography** | `GeographyBorn` per continent channel | 1 | needs continent channels; `world_geometry` is `ChannelScoped` per DP-Ch4 |
| 3 | **Places** | `PlaceBorn` per cell-tier channel | 1 | cells only; higher tiers must **not** have place rows (V1) |
| 4 | **Layouts** | `LayoutBorn` per channel | 1, 3 | MAP_001: *"runs after PF_001 `PlaceBorn` at cell tier"* |
| 5 | **Tilemaps** | `TilemapBorn` per **non-cell** channel | 4 | TMP_001 derives anchor positions from MAP_001 author-positioned `(x, y)` — MAP is canonical, TMP is derived (TMP-A6) |
| 6 | **Actors** | `EntityBorn` · `ActorBorn` · `actor_clocks` from `initial_clocks` | 3 | `spawn_cell ∈ places` (ACT_001) |
| 7 | **Membership** | cell-channel `MemberJoined` for each actor at its `spawn_cell` | 3, 6 | **RBS-D2** — the phase that resolves RBS-F1 |
| 8 | **Holdings** | initial resource + item distribution · faction memberships · reputations · title holdings | 6, and factions/titles from the **Ruleset** | every one names an actor; `ItemDistributionDecl.holder` may also be a Cell (→ 3) |

`SceneLayoutBorn` is **not** a phase. CSC_001 makes it lazy at first cell entry, with an eager
`eager_scene_compute` flag; when the flag is set it appends to phase 5. Keeping it out of the required
DAG is what lets a 16k-cell world seed without computing 16k scenes nobody has visited.

> **RBS-D8 (added 2026-07-26) — the seed-root causal-ref pattern.** EVT-T5 **requires** causal refs
> (*"every Generated event must reference at least one source event"*, enforced by EVT-L13 as
> `CausalRefRequired`/`CausalRefMissing`) — and the first event in a new reality has no game parent,
> which as first written rejected phase 1 at commit. Resolution: **phase 1 events causal-ref the
> reality-creation EVT-T8 admin event** — `Forge:CreateReality` / the §12R.2 `provisioning→seeding`
> CAS transition event — **as their root**, and **every later phase refs its phase predecessor**
> (the first event of phase N refs the closing event of phase N−1; items within a phase ref their
> phase opener). The whole seed is then one connected causal graph rooted at the administrative act
> that created the reality — exactly what audit forensics wants.
>
> **Checked against [`09_causal_references.md`](07_event_model/09_causal_references.md)
> (2026-07-26):** EVT-L13's integrity checks are same-reality, reference-exists, non-forward and
> required-non-empty — **there is no cross-category restriction**, so a T5 event referencing a T8
> event satisfies reference-exists as the check is written. **No AMEND item is needed for this**;
> the conditional item in the correction plan ("if the check rejects cross-category refs") is
> discharged.

> **RBS-A4 — The phase DAG is the same shape as RLS-A9, one level up.** §16 needed a topological order
> over *manifest fields* because they reference each other; bootstrap needs one over *emissions* for
> the same reason. Both were unwritten for the same reason: with one layer, or one emitter, order is
> invisible.

---

## 4. Idempotency, checkpointing, resume

§12R.2 specifies *"resumable, idempotent, progress-reportable"* and *"checkpoint every 100"*. With
events rather than direct writes, that needs one more mechanism to actually hold.

> **RBS-A5 (re-shaped 2026-07-26) — Every seeded event carries a deterministic idempotency key**, in
> the uniform triple shape:
>
> ```
> IdempotencyKey {
>   producer_service:  "reality-bootstrapper",
>   client_request_id: UUIDv5(reality_id, phase, item_index),
>   target,
> }
> ```
>
> A resumed run re-derives the same key for the same item, so double-emission is a **dedup**, not a
> duplicate — enforced by the **commit-primitive dedup + EVT-V3**. (~~EVT-L3~~ was the wrong
> citation: that is *proposal-bus* dedup, and RBS-A8 says seeding never touches the bus. The
> original `H(reality_id, phase, item_index)` hash survives as the `client_request_id`.) Checkpoints
> then remain an *optimisation* — they let resume skip work — rather than the correctness mechanism.
> If checkpoints and reality ever disagree, the keys are what keeps the outcome right.

> **RBS-D3 — Checkpoint granularity is `(phase, item_index)`, written after every 100 items and at
> every phase boundary.** Phase boundaries matter more than the count: a resume that restarts mid-phase
> is cheap, and a resume that restarts mid-*DAG* without knowing which phases completed would have to
> re-derive dependency state it no longer has.

> **RBS-D4 — Progress is `(phase, item_index, total)`, and phases are weighted.** §12R.2's
> `reality_bootstrap_progress` metric as a flat percentage would jump erratically: phase 1 is dozens
> of channels, phase 5 is thousands of tilemaps. Weight by expected item count so the UI number means
> something.

---

## 5. Failure classes

§12R.2 says a failed seed *"stays `seeding`, resumable."* That is right for one failure class and
badly wrong for the other.

> **RBS-A6 — Two failure classes, and conflating them produces a reality that retries forever.**

| Class | Examples | Behaviour |
|---|---|---|
| **Transient** | DB blip · translation-service timeout · worker crash · node eviction | stays `seeding`; resumes from checkpoint; retries with backoff |
| **Terminal (manifest defect)** | ruleset resolution fails (RLS §11) · load-time validator fails (RLS-A10) · seed-time validator fails (RLS-D23) · `spawn_cell` names a cell not in `places` | **abandon**: reality → `failed{reason}`, never `active`; author is shown the defect |

A manifest defect is **not** resumable, because resuming re-runs the same deterministic computation
over the same immutable input and fails identically. Retrying it forever burns a worker slot and
produces a reality permanently stuck in `seeding` with no diagnostic — the failure mode that looks
like a hang.

> **RBS-D5 — Terminal failure at *creation* rejects the request; terminal failure at *fork* rejects
> the fork; terminal failure at *restore* leaves the reality `archived`.** Same class, three
> lifecycles, and in none of them does a half-built reality become visible. Nobody is playing in a
> reality that does not exist yet, which is what makes the strict answer affordable here (`17` §4 B2).

---

## 6. Validation: why seed-time exists at all

This closes a question `17` raised and left implicit.

`commit-service` applies the **EVT-V1 category-declared** subset, and it never chooses one (CS-D9).
~~For **System origin** — EVT-T4, which is exactly what every `*Born` event is — that subset is zero
main-pipeline stages~~ — **corrected 2026-07-26: the category premise was false.** EVT-T4 is
**DP-Internal only** (EVT-P4: *"cannot be emitted from any service"*), a DP-locked closed set of 8
sub-types, none of them `*Born`. **EVT-A4 registers `RealityBootstrapper` as a Generator emitting
EVT-T5 Generated**, whose declared subset is **schema → capability → causal-ref → commit** —
*reduced* (no A6 injection defense, no canon-drift, no world-rule), **not zero**. (CS-D9's table
makes the same T4 error for timers and generators — recorded as **REC-52** and corrected in `15`
§7b.2.)

So bootstrap events run a form-only subset that never checks content references. Which raises: what
checks `spawn_cell ∈ places`, `canonical_pcs ⊆ canonical_actors[kind=Pc]` (PO-C2),
`default_spawn_cell ∈ places` (PO-C3), `TitleBinding::Dynasty ∈ canonical_dynasties` (TIT-C5)?

> **RBS-A7 (rewritten 2026-07-26) — The seed-time gate exists *because* the bootstrapper's EVT-T5
> subset checks form, never content.** The reduced subset verifies an event is well-shaped,
> authorized and causally anchored; **no downstream stage checks content references** for Generated
> events. The conclusion of the first version survives with corrected scope — the subset is reduced,
> not zero, and the seed gate covers exactly what the reduced subset does not. This is the
> justification RLS-D23 was missing when it assigned seed-time validation to `RealityBootstrapper`.
> The three validation times are not an arbitrary three:
>
> | Time | Runs | Because |
> |---|---|---|
> | **Load** | ruleset resolution + referential validators (RLS-A10) | rules reference rules; no content exists yet |
> | **Seed** | content-referencing validators (PO-C2/C3, `spawn_cell`, TIT-C\*) | content exists; **and the bootstrapper's EVT-T5 subset does not check content references** |
> | **Admission** | EVT-V1 subset by origin class | live input, untrusted or semi-trusted |
>
> Remove the seed gate and manifest-defect content enters the log unvalidated, because the stages
> that would have caught it are — correctly — not in the Generated subset.

> **RBS-D6 — Seed-time validators run per phase, immediately after that phase's emissions, not once
> at the end.** Same reasoning as RLS-A9: a failure then names the phase that caused it. A single
> end-of-seed sweep reports `spawn_cell_unknown` after 16k tilemaps have been written.

---

## 7. Interaction with `commit-service`

> **RBS-A8 (corrected 2026-07-26) — Seeding does not go through the proposal bus.** The bus (`15` §2)
> is a per-cell Redis Streams consumer for *live* input. Seeding is bulk, single-writer, and runs
> before any cell is Hot. It uses the same **durability** path — `event_log` insert under the
> reality-scoped epoch token (RBS-A3), same uniqueness constraint, same outbox — and, of the four
> registered EVT-V5 hot-path gates (turn-slot, idempotency cache, mortality, concurrent-turn),
> **exactly one is live during seeding: the idempotency gate** (keyed by RBS-A5) — the other three
> are turn-scoped and vacuous before any actor or turn slot exists. It skips admission-by-bus
> because there is no bus for a channel that does not exist yet.
>
> **Generator registration rides the AMEND bundle (REC-53):** registration is mandatory
> (*"generators in code but NOT in registry"* is forbidden), but **no EVT-G2 trigger kind fits** —
> the trigger sources are a closed set of 5, and bootstrap fires on the CP's
> `provisioning→seeding` CAS, a host lifecycle transition, not a DP event. The bootstrapper also
> needs an **EVT-G4 capacity-ceiling exemption** (every registered Generator is rate-limited by
> construction — *"≥100% → reject emit"* — and a seed is a sanctioned bulk burst). Both are
> amendments to LOCKED `07_event_model/` contracts, not doc-side decisions.

This is the answer AUD-F8 needed: `commit-service` does **not** need a bootstrap mode. Bootstrap
reuses its durability half and bypasses its admission half, legitimately, because the Generated
subset checks form only (RBS-A7) and the seed gate covers the content checks that would otherwise
go unrun.

> **RBS-D7 — At `seeding → active`, the worker's reality-scoped lease is released *before* the CAS,
> and per-channel writer assignment happens *after*.** Overlapping them would put two writers on a
> channel for the width of the transition — briefly violating DP-A16 during the one operation whose
> whole job is to make the reality safe to write.

---

## 8. Open

| ID | Question | Kind |
|---|---|---|
| **RBS-Q1** | **Seeding budget for a `Megaplanet`.** `WorldScale::Megaplanet` is ~16 384 cells → ~16k `PlaceBorn` + ~16k `LayoutBorn` + tilemaps. At §12R.2's checkpoint-every-100 that is a long-running job with a real cost. Is there a **scale cap on synchronous authorability**, or does a Megaplanet simply take hours and report progress? *(Noted 2026-07-26: the mechanical half is already answered — EVT-G4 gives every registered Generator a `capacity_ceiling` with "≥100% → reject emit", so a Generator-registered bootstrapper is rate-limited by construction; the seed-burst exemption rides the AMEND bundle, RBS-A8. Only the product half stays open.)* | product + measurement |
| **RBS-Q2** | Does **`Ancestry`** (snapshot-fork) need seed-time validation at all? It emits nothing, so there is no new content to validate — but it *inherits* a parent whose content was validated under a possibly-different ruleset digest. Probably "no, and record the parent's digest", but it should be decided rather than assumed. | design |

### Findings for other owners

| ID | Finding | Owner |
|---|---|---|
| **RBS-F1** | **`MemberJoined` ordering cycle** (§3.1) — `PlaceBorn` cannot emit membership for actors that do not exist yet. A **CANDIDATE-LOCK correction** to PF_001 §2 and the matching ownership-matrix row. | PF_001 + lock |
| **RBS-F2** | §12R.2's bootstrap worker text still reads *"FOR each book region… FOR each glossary entity"* and creates aggregates directly. Superseded by GDA-D3/D4 — needs the same dated note treatment `02_storage` §4.4 just received. | storage owner |
| **RBS-F3** | `RealityBootstrapper` is described as a *"Synthetic actor"* across **five sites** — PF_001, MAP_001, TMP_001, GEO_001 **and `07_event_model/02_invariants.md` EVT-A4** *(added to the list 2026-07-26)* — while ACT-A7 forbids `Synthetic` in `canonical_actors` **V1**. These are different things — an event-authorship identity vs a canonical game actor — but the same word, and the collision will read as a contradiction to whoever implements it. Worth one clarifying sentence in ACT_001; the EVT-A4 wording rides the EVT owner's cycle. | ACT_001 + EVT owner (EVT-A4 row) |
