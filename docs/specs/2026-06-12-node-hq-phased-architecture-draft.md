# LoreWeave Distributed Topology — Phased Architecture Draft (v0.2)

**Date:** 2026-06-12 (v0.2 — same day, after a shallow scan of `lore-weave-game-foundation`)
**Status:** 📐 **DRAFT** — parallel design track (Track 2). **Build NOT authorized** — MVP-first stands.
**Relations:** builds on [local-first/Rust research](2026-06-12-local-first-rust-rewrite-research.md) (§10 verified findings) + [VCTĐ ontology](2026-06-12-van-co-than-de-entity-ontology.md). **Consumes** (does not re-litigate) the LLM-MMO-RPG design corpus in `lore-weave-game-foundation/docs/03_planning/LLM_MMO_RPG/` (179 features, ~150 locked decisions).
**v0 → v0.2:** v0 assumed the T1 tier was unbuilt. Wrong — it is in active construction in the sibling repo. The draft's job narrows accordingly: **design the missing tier (T2 node) + the seams connecting three existing bodies of work.**

---

## 0. The reframe (v0.2 — three bodies of work, one missing tier)

| Body of work | Where | Status | Role in target topology |
|---|---|---|---|
| Novel-platform MVP (E0 collaboration, glossary/knowledge campaign…) | `lore-weave-security` (this repo) | **ACTIVE** (Track 1) | **T0 HQ-Global** candidate + the canon-semantics source (glossary/KG/ontology) |
| **Game foundation** — Rust workspace, 28+ cycles: `dp-kernel` event-sourcing kernel (+proc-macros), per-reality projections (11 tables incl. canon), rebuilder, canon guardrails (YAML), xreality fan-out protocol, world/travel/tilemap services, `world-gen`, game-server, WS contracts, **Stateright-model-checked protocols** (I7 xreality fan-out, I9 lifecycle CAS, I13 outbox); V1 Solo RP on a 30-day implementation plan | `lore-weave-game-foundation` | **ACTIVE** | **T1 HQ-World** tier — *already being designed/built as the topmost coordination layer* |
| Node tier — player/author machine, single binary | new **`world-core` repo** (planned, non-AGPL — G2′) | **MISSING** | **T2** + the T1↔T2 distribution layers |
| **Foundation kernel** — generic event-sourcing/projection machinery, zero domain logic | new **permissive-license repo** (planned — milestone E-K) | **PLANNED (early)** | shared substrate under BOTH the AGPL T1 and the non-AGPL `world-core` |

Key implications:

1. **The end state was never "smaller."** The game-foundation system is itself hyper-distributed (per-reality DBs, projections, fan-out, ~40 services). Adding the node fleet makes it *more* so.
2. **The architecture bet from the research doc is independently validated.** `dp-kernel` is a **hand-rolled** Aggregate/event kernel (`#[derive(Aggregate)]`, `#[handles_event]`) — exactly the research §10.1 verdict (no cqrs-es/esrs; decide/evolve shape) arrived at separately. Convergent evolution = confidence.
3. **The extension seam already exists by design.** `dp-kernel`'s `EventStore` trait deliberately hides the Postgres pool *"so future backend swaps only touch the EventStore trait impl boundary"* — a **SQLite EventStore impl for the node tier is the planned extension point**, not a retrofit.

---

## 1. Target topology (end state)

```
T0  HQ-Global ──────────── accounts/identity · catalog · billing/usage · marketplace
     (novel-platform        cross-world services
      services — exist)
        │
T1  HQ-World ───────────── per-world/per-reality coordination — IN ACTIVE BUILD:
     (game-foundation)      meta layer (meta-worker, meta-outbox-relay) ·
        │                   per-reality event logs + projections (dp-kernel) ·
        │                   canon guardrails · xreality fan-out · world/travel/
        │                   tilemap · game-server · WS via api-gateway-bff
        │
T2  Node ───────────────── MISSING — player/author machine, single binary:
     (fleet, NEW)           pure world-core + SQLite EventStore + embedded graph ·
                            BYOK/local AI · tool shell / game client shell
```

### Domain semantics: the multiverse model is canonical (already locked — consumed as input)

- **BOOK = canon source** (axioms + seeded facts), *not* a reality.
- **Realities = peer timelines** seeded from the book; fork at any event; none is "main."
- **Four-layer canon:** L1 axiomatic (never drifts) · L2 seeded (per-reality overridable) · L3 reality-local events (immutable within their reality) · L4 flexible runtime state.
- **Canonization** = the reverse flow: a player-reality moment promoted to L2 under author review.

### The two planes, mapped onto the four layers

| Plane | Canon layers | Owner today |
|---|---|---|
| **CANON plane** | L1+L2 (book/glossary semantics) + L3 (per-reality event log) | L1/L2: `lore-weave-security` glossary/KG · L3: `dp-kernel` |
| **SIM plane** | L4 (runtime state, ECS projections, NPC mood) | game-server / node runtime |

**Two distinct time axes** — and they must never be conflated:
- The book's **narrative chapter axis** (VCTĐ temporal KG, `chapter_id` edges) lives in L1/L2.
- Each reality's **event time** lives in L3.
- They meet exactly once: at **reality seeding** (L2 → initial L3 state, cf. `reality_seeder`'s deterministic UUIDv5 seeds).

Invariant across all phases: **the canon plane never real-time merges; the sim plane is never source of truth.**

---

## 2. Phase ladder (v0.2 — topology dimension over the existing V1/V2/V3 game staging)

The game roadmap already stages the *experience*: **V1 Solo RP → V2 Coop Scene → V3 Full MMO** (server-side, in build). This draft adds the *topology* dimension — when each tier exists and what ships on it. Every phase remains a self-sufficient product.

### P0 — *(ACTIVE — both repos, Track 1 + game-foundation's own cycles)*
- T0 MVP completion (`lore-weave-security`) · T1 foundation + V1 Solo RP (game-foundation 30-day plan) · **ontology validation through ≥1 real book → opens Gate G1**.
- Node-tier footprint: zero.

### E-K — Foundation-kernel extraction *(early + time-sensitive — runs during P0, locked PO 2026-06-13)*
Extract the generic core of game-foundation into a **new repo under a permissive license** — recommend **dual MIT OR Apache-2.0** (the Rust-ecosystem convention; Apache-2.0 §5 makes inbound contributions automatically licensable to everyone, **no CLA needed**) — so the AGPL T1, the non-AGPL `world-core`, the closed node, *and the community* can all consume it.

- **Why early:** game-foundation is public AGPL — the lift-and-relicense right exists only over *owned* code, and **every external PR that lands before extraction shrinks what can be lifted**. Extract while copyright is still 100% owned; afterwards, community contributions land in either repo without ever blocking the closed product.
- **Boundary rule:** *generic machinery in, domain semantics out.* Lift candidates: `dp-kernel` + `dp-kernel-macros` (Aggregate/EventStore/Projection traits), `rebuilder`, the `projection-golden` harness pattern, possibly `world-gen` (already a standalone lib+CLI) and `foundation-model` (Stateright). NOT in: canon rules, ontology, reality semantics — those are `world-core` domain.
- **First task:** a kernel-boundary audit of the workspace (which crates/items are domain-free) — small, read-only, runnable anytime.
- **Resulting license layering:**

```
            foundation-kernel  (MIT / Apache-2.0 — everyone)
              ↑                          ↑
  game-foundation (AGPL — T1)     world-core (non-AGPL)  ←  node shells (closed)
```

### P1 — Node Foundation (T2 exists)
- **Builds:** pure `world-core` extracted along the seam game-foundation already reserved: `dp-kernel` domain logic behind a **SQLite `EventStore` impl** + purity extraction from tokio/sqlx (Rail G3); embedded graph (Spike S2); BYOK/local AI (LM Studio path exists in both repos).
- **Ships:** offline authoring tool **and/or** local Solo RP client (V1 logic running on-node) — archetype order is Open Q2.
- **Schema freedom:** no cross-version contract yet; Rail G4 (save versioning + upcasting) applies from the first public build.
- **License path settled (G2′ ✅ + E-K):** kernel extracted permissive first; `world-core` lifts owned logic into its non-AGPL repo.

### P2 — Staging ↔ HQ Sync
- **Builds:** **Delta contract v1** (frozen post-G1; derived per Spike S3); the node's L3 event log ships to HQ (delta-log + HLC + LWW for single-author surfaces); account binding; encrypted backup. HQ side: one thin sync service.
- **Ships:** multi-device + cloud backup — first node↔HQ revenue surface.

### P3 — Shared Worlds (nodes join T1 realities)
- **Builds:** node participation in T1-hosted realities (V2 coop semantics over the fleet); **canonization flow live** (player moment → author review → L2); membership/authz = **E0 grant model** (built in Track 1).
- **Ships:** collaborative worldbuilding; async shared realities.
- Server-authoritative arbitration at T1 — explicitly NOT CRDT.

### P4 — Full MMO over the fleet (V3 × T2)
- **Builds:** sim plane networked — game-server + region/instance shards (T1), interest management, state replication. **Game-networking class, not knowledge-sync class.** Canon plane unchanged.
- **Ships:** the MMO.
- Deliberately under-specified here; it inherits a validated canon plane, an installed node fleet, and the V3 server-side design.

---

## 3. Asset map (v0.2 — three provenances, nothing wasted)

| Asset | Lives in | Role in target |
|---|---|---|
| Outbox → event spine (Redis Streams) | security | P2 sync-protocol pattern; T0 events |
| `entity_revisions` (VG-1) | security | Delta/undo design input (S3) |
| **E0 grant model** (5 client copies!) | security | P3 membership/authz |
| provider-registry BYOK (ENFORCED) | security | node AI port — same port, local adapters |
| Eval suite (extraction F1, golden sets) | security | `world-core` conformance gate |
| VCTĐ ontology + glossary semantics | security | L1/L2 canon vocabulary (post-G1) |
| **`dp-kernel` + macros** (hand-rolled Aggregate ≈ decide/evolve) | game-foundation | **`world-core` seed** — needs SQLite EventStore impl + G3 purity extraction |
| Projections (11) + rebuilder | game-foundation | anchor+delta in production form → node read-models + rebuild |
| `projection-golden` fixtures | game-foundation | the conformance-harness pattern, already practiced |
| Canon guardrails (YAML) + contracts-prompt | game-foundation | node-side narrator guardrails (same rules file, two runtimes) |
| xreality protocol (Stateright-checked) | game-foundation | T1 fan-out today; input to T1↔T2 distribution design |
| `world-gen` / tilemap-service | game-foundation | node procedural content (already a standalone lib+CLI) |
| `foundation-model` (Stateright) | game-foundation | protocol-verification rail — **extend to the P2 sync protocol** |

---

## 4. Gates, rails, spikes (v0.2)

| ID | What | Blocks |
|---|---|---|
| **G1** | Ontology survives extraction of ≥1 real book (research §10.1.3) | Delta v1 freeze (P2); not P1 prototyping |
| **G2** | License rail for node deps: MIT/Apache/BSD/MPL only (research §5.1) | every P1+ dependency |
| **G2′** | **✅ RESOLVED (PO 2026-06-12) — the AGPL boundary.** Locked: `lore-weave-game-foundation` **stays AGPL**; `world-core` is **extracted into its own repo under a different (non-AGPL) license**. Legal basis: the owner holds full copyright of the source → relocating and relicensing their own logic across repos is clean (dual-licensing right). **Residual rail (ongoing):** this right covers *owned* code only — the moment an outside contribution lands in game-foundation, that code is no longer freely liftable. Discipline: extract-before-accepting external contributions on lift-candidate code, or adopt a CLA. **Operationalized as milestone E-K (§2): extract the kernel early, while copyright is 100% owned.** | rail, ongoing |
| **G3** | Core purity: extracted `world-core` crates ban tokio/rusqlite/reqwest/clock/rand (CI-enforced) — concretely: separating `dp-kernel`'s domain logic from its sqlx/tokio shell | P1 onward |
| **G4** | Save-compat: `schema_version` + load-time upcasting from the first public node build | P1 release |
| **S1** | Spike: node client tech — **check what `frontend-game`/game-server V1 actually uses before assuming Bevy**; then engine choice + KG→ECS hydration | P1 game shell |
| **S2** | Spike: node graph store (in-mem+SQLite vs CozoDB) on a real book's KG | P1 storage |
| **S3** | Spike: derive Delta v0 from **three** sources: security outbox payloads + `entity_revisions` + `dp-kernel` event schemas (`07_event_model`) | P2 contract |

---

## 5. Consistency regimes per phase

| Phase | Regime | Mechanism |
|---|---|---|
| P2 | single-author, multi-device | delta-log + HLC + LWW-per-entity (research §10.2 ◐) |
| P3 | multi-author canon | server-authoritative arbitration at T1 + **canonization review** (already designed: L-layer promotion) |
| P4 | real-time shared simulation | authoritative game networking — sim plane only |

---

## 6. Parallel-work contract (v0.2 — three tracks)

1. **Track 1** (`lore-weave-security`): MVP — absolute priority, untouched by this draft.
2. **Track 1.5** (`lore-weave-game-foundation`): T1 foundation — already running its own cycle cadence; this draft *consumes* its outputs, never redirects them.
3. **Track 2** (node tier): **begins with milestone E-K** (kernel extraction — early, time-sensitive); node work proper not started. Homes: the permissive kernel repo + the **new `world-core` repo** (non-AGPL — G2′ resolved). Zero file overlap with either monorepo before P2's thin sync service.
4. The only planned couplings remain: (a) P2 sync service (additive), (b) Delta contract derived from existing payloads.

---

## 7. Open questions

- **Q1 — ✅ RESOLVED (PO 2026-06-12):** `world-core` gets **its own repo under a non-AGPL license**; game-foundation stays AGPL; owner's full copyright makes the lift-and-relicense clean. Remaining sub-question (Q1b): do the node *shells* (tool / game client) live inside the world-core repo or in a separate closed repo?
- **Q2 — P1 archetype order:** authoring tool first (Tauri) or local Solo RP client first (reuses V1 logic)?
- **Q3 — Monorepo relationship:** both repos contain the full novel-platform service set; which is canonical for shared services going forward, and how do changes flow between them?
- **Q4 — T1 granularity:** coordinator-per-world vs multi-tenant world-coordinator; P4 shard unit.
- **Q5 — T1 economics:** who pays for world coordination (owner / subscription / P2P-assist)?
- **Q6 — P4 authority model:** full server-authority vs node-hosted realities with HQ arbitration.
- **Q7 — T1 ↔ `world-core` domain-semantics sharing:** the AGPL T1 cannot depend on a closed `world-core`. Options: (a) shared *machinery* lives in the permissive kernel and each side owns its domain impl, **conformance-locked by shared golden fixtures** (the `projection-golden` pattern); (b) owner-vendors world-core code into the AGPL repo (clean while sole-owner; re-opens contamination on contributor patches); (c) make more of world-core permissive. **Default lean: (a).**

## 8. What this draft deliberately does NOT do

No Delta schema (G1) · no engine choice (S1) · no P4 networking design (premature) · no dates (phases are ordered, not scheduled) · **no re-litigation of the ~150 locked MMO decisions** — the multiverse model, four-layer canon, and V1/V2/V3 staging are inputs to this draft, not outputs.
