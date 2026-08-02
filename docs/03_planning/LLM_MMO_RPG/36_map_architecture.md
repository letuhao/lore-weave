# 36 — Map architecture: the space graph

> **Status:** DESIGN — SEAL CANDIDATE 2026-07-29. Owns the `SPG-*` stable-ID namespace
> (`SPG-A*` axioms · `SPG-D*` decisions · `SPG-F*` findings · `SPG-R*` amendment rows ·
> `SPG-Q*` open questions).
>
> **Continues, does not re-open:** [32](32_locus_as_actor.md) `WSA-A7..A11` (SEALED 2026-07-28) —
> *a locus is both an entity and an actor*, loci get existence tiers, every WHEN is a turn. This doc
> states the **converse and the container**: an entity may **have** an interior, and interiors form a
> typed graph. Where 32 asked *"can a place act?"*, this asks *"what is a place made of, what may it
> contain, and where is it?"*
>
> **Supersedes scoping in:** [`MAP_001`](features/00_map/MAP_001_map_foundation.md) §3.1 `ChannelTier`
> (the fixed 5-rung ladder) · [`GEO_001`](features/00_geography/GEO_001_world_geometry.md) §2
> `world_geometry` per-continent scope. Both are corrected in §11, with amendment rows.
>
> **PO decisions sealed in this arc (2026-07-29):** free typed tree over fixed ladder · decisive
> rename over mapping layer · `Passage` is a MapKind · entity ⊇ space with a **ruleset-extensible**
> whitelist · kinematic frames · **collision as topology, not dynamics** (PO's own proposal) ·
> hybrid combat siting · **control is a possession mechanic, not an actor attribute** (PO).
>
> **Nothing in this doc is built.** This is a design seal taken deliberately *before* any schema
> exists, because every name here lands in an enum, a table name and a wire contract, and the cost of
> being wrong rises to a migration the moment the first row is written.

---

## 1 — What this closes

Four findings, each verified against code and the corpus rather than against a handoff note.

> **SPG-F1 — the tier ladder is a feature-level invention sitting on a substrate that was already
> free.** [`DP-Ch1`](06_data_plane/12_channel_primitives.md) (LOCKED 2026-04-25) defines
> `Channel { parent: Option<ChannelId>, level_name: String, depth: u8 ≤16, metadata: Json }` — an
> arbitrary tree with a **free-form** level tag. The fixed rungs come from `MAP_001`'s
> `ChannelTier = Continent|Country|District|Town|Cell`. So the PO's free-tree request does **not**
> fight a lock; it removes an enum that narrowed an already-general substrate. But `level_name:
> String` is the opposite error — an open string where the repo's own discipline requires a closed
> set. The correct model is neither: a **closed kind set plus a containment relation** (§4).

> **SPG-F2 — three hierarchies are live and unreconciled, and the shipped code follows none of the
> designed one.**
>
> | Source | Ladder |
> |---|---|
> | shipped `crates/world-gen` (geographic) | World → Continent → Subcontinent → Region → GeoCell |
> | shipped `crates/world-gen` (political) | World → Realm → State → Province → County |
> | `MAP_001` `ChannelTier` (designed) | Continent → Country → District → Town → Cell |
> | `_ui_drafts/MAP_GUI_v2.html` (built demo) | continent → country → **region** → cell |
>
> [`FLAT_TO_3D_MIGRATION_PLAN`](FLAT_TO_3D_MIGRATION_PLAN.md) §C already diagnosed the root cause —
> *"'lift the zone tree as a political hierarchy' silently merges two **different** things"* — and
> chose geometry-first, politics-anchored-on-top. The code implemented that choice; `ChannelTier`
> was never updated to match.

> **SPG-F3 — `GEO_001` scopes `world_geometry` to a CONTINENT channel; the world-tier redesign
> inverted that containment seven days later, and the code followed the redesign.** `GEO_001` (DRAFT
> 2026-05-13) §2: *"One row per continent channel."*
> [`GEO_WORLD_TIER_REDESIGN`](GEO_WORLD_TIER_REDESIGN.md) (LOCKED 2026-05-20): *"the current
> generator is structurally a **region** generator; this spec defines the **world** tier above it."*
> `crates/world-gen/src/hierarchy.rs` now emits one sphere containing **many** continents.
> `GEO_001` is still at DRAFT, so this is correctable without breaking a lock — but it is currently
> a spec that describes the inverse of the shipped containment.

> **SPG-F4 — one word, three meanings; a second word, two; a third, two.** `zone` = frozen
> flat-track subdivision (`flatworld` plate→zone→subzone) **and** a HoMM3 partition inside one
> tilemap (`TMP_001`) **and** the PO's informal word for a world subdivision. `realm` = an empire
> nested in a continent (`world_map.rs:155`) **and** a plane/world in the multiverse. `cell` = a
> Voronoi cell of the world mesh **and** a tavern-sized interior (`CSC_001`). This is
> [`XST-F1`](27_extensibility_stress_test.md)'s class and [`WSA-F4`](32_locus_as_actor.md)'s pattern
> repeating in the spatial vocabulary. §10 retires it.

---

## 2 — Axioms

### SPG-A1 — An entity MAY have an interior, and an interior is a map

> Every addressable thing is an **entity**. An entity may declare an **interior** — a space that
> contains other entities. An entity without one is an ordinary object. An entity with one is
> **simultaneously** an object in its parent's space and a space for its children.

This is the exact converse of [`WSA-A7`](32_locus_as_actor.md) (*a locus is both an entity and an
actor*), and the two together close the circle: **"entity" and "space" are one kind of thing seen
from outside and from inside.** There is no second class, no `Place` table parallel to an `Entity`
table, no special case for a ship or a planet.

Prior art, in production, at MMO scale — Star Citizen's zone system: *"A zone host itself **is an
entity** with coordinates in the zone that hosts it, with an entity's absolute world position being
the **accumulation of the transforms of each zone host above it**… ships acting as nodes… **if a
zone host moves all the hosted entities move relative to it**."* Pixar USD carries the same shape
(any prim may contain prims, and any prim may *reference* another prim's subtree); Godot's node tree
likewise (any scene instantiates as a node inside another scene).

Read across the whole inventory with one rule:

| Thing | From outside | From inside |
|---|---|---|
| a sword | object on the floor | — |
| a chest | object in a room | container |
| a house | object on a settlement tilemap | `Domain` |
| a palace | object on a capital tilemap | `Domain` containing `Domain`s |
| a cave | object on a mountainside | branching `Domain` |
| a ship | object on a `World`'s sea | `Domain` — **and its parent changes over time** |
| a cultivator at 神境 | an actor walking a road | a `World` **born at runtime** (§3) |
| a planet | object on a `Universe` map | a `World` |
| the universe | — (root) | `Universe` |

The second-to-last row is why `Universe → World` needs no special rule: **a world is an object on
the universe map and a map in its own right.** The PO's original request — *"in a universe map you
open straight into a cell map"* — likewise needs no rule: it is an object on the universe map whose
interior happens to be a `Domain`. A shattered fragment of a 秘境 drifting between planes.

### SPG-A2 — The capability is an engine primitive; the whitelist is ruleset data

> `can_have_interior` is a **closed engine primitive**. **Which** entity kinds may hold an interior
> is a **ruleset declaration** — authored, versioned, digest-pinned — never a Rust enum.

The PO's stress case forces this and the design survives it: a cultivator who breaks through to 神境
forms an inner world (内天地). The holder is a *person*, not a structure; the interior is granted **at
runtime by a gameplay event**, not authored at world creation; and the holder is a **moving frame
with an interior**. No hardcoded whitelist of "buildings, caves, ships" could ever have anticipated
it.

The repo already ships this exact pattern twice, so nothing new is invented:
`services/tilemap-service/src/registry.rs` (*"closed-primitive engine enums"* + `TerrainKindDef` /
`ObjectKindDef` loaded from TOML, ADR `2026-05-26-data-model-v2-registry-footprint` §2.3), and the
whole `crates/ruleset-core` + `ruleset-loader` spine (patch / layer / validate / store, `LAW_VERSION`
digest).

Three consequences are load-bearing:

1. **An interior may be BORN by an event**, not only declared. Breakthrough emits an interior-birth
   event down the same pipeline as everything else (EVT-T4 System / T3 Derived).
2. **The acyclicity guard is a real rule, not a hypothetical** (§SPG-A4).
3. It is the strongest possible argument for lazy materialization (§SPG-A12): **99.99 % of actors
   never hold one.**

### SPG-A3 — Containment is a typed relation validated by a matrix, not an ordinal ladder

> A node declares its `MapKind`. A parent-child edge is legal iff the **containment matrix**
> `allowed(parent_kind, child_kind)` permits it. There is no level number, no required depth, no
> mandatory sequence of rungs.

Freedom **with** law, not freedom **from** law. `Universe → Domain` is legal because the matrix says
so; `Universe → Universe` likewise. `MAP_001`'s `ChannelTier` is retired (`SPG-R1`).

> **⚠ Corrected 2026-08-02.** This paragraph used to end *"…and `Channel.level_name: String` is narrowed
> to `MapKind` (`SPG-R2`)"* — stated as fact, in an axiom body, **for an amendment that was retired the
> same day it was written** (§7; [REC-93](19_reconciliation_register.md)). `DP-A13` forbids exactly that
> narrowing: the data plane is deliberately agnostic to level semantics so a reality can name its own
> levels — `phủ` (*a prefecture*), `châu` (*a province*). <!-- doc-language-gate: ok — these two words ARE
> the subject matter, not exposition: the decision under discussion is precisely that a reality keeps its
> own level vocabulary, so replacing them with their English glosses would delete the example. Glossed
> inline on first use, per the standard. Same two words appear verbatim at :459 and in DP-A13 itself. -->
> **Two fields, two jobs** — `Channel.level_name` stays the reality's own word,
> and the closed set lives one layer up on `map_layout.kind`, where `SPG-R1` already put it.
>
> **The rot survived three months because nothing looks for it.** [`amendment-rot-gate.py`](../../../scripts/amendment-rot-gate.py)
> check D catches a retired **identifier** (`ChannelTier`) used as if live; **no check catches a retired
> AMENDMENT ROW cited as if live.** That is the *"scope never reaches it"* shape from
> [`non-vacuity.md`](../../standards/non-vacuity.md) NV-3 — and this is not the only site: `MAP_001:183`
> carried the same claim in a `//` comment, in the future tense, and is corrected in the same pass.

Prior art: HTML's content model (which elements may contain which) is the canonical typed-containment
ruleset; `django-polymorphic-tree` ships the same idea for trees whose *"each node can be a different
model type"* with *"constraints like which node types can have children."*

### SPG-A4 — The containment graph is a strict acyclic tree. The control graph is free. They never interact

| | **Containment** | **Control** |
|---|---|---|
| Relation | what is inside what | who is driving what |
| Shape | strict tree, acyclic, single parent | free, many-to-many, may point anywhere |
| Hard rule | **A is never inside A** | none |
| Enforced by | depth + parent FK + reference-cycle guard (§SPG-A5b) | — |

The inner-world paradox dissolves without weakening either graph, and the resolution is the PO's:
**the cultivator's body stays outside; a 分身 (avatar) — a *different* entity — is inside. One
controller drives both.** Containment stays acyclic because B ≠ A. Control may form any shape it
likes because it is not a containment relation and no traversal ("what is inside X") follows it.

This is not a new split. [`EF_001`](features/00_entity/EF_001_entity_foundation.md) already declares
that `EntityId` (*things in the world*) and `ActorId` (*agents with turn-submission capability*) must
not collapse, *"because collapsing would corrupt either 'things in the world' or 'agents that submit
turns' semantics."* SPG-A4 is that declared split, named as two graphs and given its guarantee.

### SPG-A5 — All coordinates are parent-relative; absolute position is the accumulation of transforms

> A node stores its transform **relative to its parent frame only**. Absolute world position is
> derived by accumulating transforms from the root. **No node ever stores an absolute position.**

This is one line today and it is the difference between "a ship can sail" and "a migration through
the spine". Store absolute and the day a frame moves, every descendant is wrong. Store relative and
the geometry is simply correct; what remains is netcode (§6), a separable problem. USD's `Xform`
and Star Citizen's Local Physics Grids are the same rule.

**SPG-A5b — reference edges need their own cycle guard.** `DP-Ch1` guards cycles on the
**parent** relation (depth + referential integrity). A *reference* (a node whose interior is a
shared definition, §SPG-A14) is **not** a parent edge, so it escapes that guard entirely. Reference
cycles must be detected explicitly — the same error USD must raise.

### SPG-A6 — The frame is the unit of replication, of interest, and of validation

> The server replicates *(frame transform within its parent)* and *(entity position within the
> frame)* as **separate streams**. It never emits an absolute position.

Three properties fall out of one decision:

- **Smoothness.** Emitting absolute positions adds the frame's motion error to the occupant's motion
  error, which is precisely what produces jitter on moving platforms. Split streams interpolate
  independently.
- **Interest.** A frame is a natural AOI boundary — someone in a ship's hold does not need the ocean.
  Composes with `RTM-A6..A8` unchanged.
- **Anti-cheat.** `RTM-A9` position-delta validation runs on the **relative** delta. Moving at
  1 000 km/h relative to the ground is legal aboard a ship; relative to the deck it is not. The rule
  is unchanged; only the reference frame is named.

### SPG-A7 — Changing frame is a discrete, server-authorized event

> Stepping from a dock onto a ship is a **transition event**, never a continuously-inferred
> membership. Coordinates are converted at the instant of transition.

This is the most dangerous seam in the whole model, and the corpus already has its shape:
[`ILR-A2`](09_interaction_layer_reconciliation.md)'s coarse cell membership is
*"evented-on-transition"*. Frame transitions reuse it rather than inventing a parallel mechanism.

### SPG-A8 — Collision is a TOPOLOGICAL event, not a dynamics problem

> When two frames meet, the engine does not resolve forces. It **edits the map graph**. Four
> operations, closed set:

| Op | Meaning | Genre precedent |
|---|---|---|
| **Graft** | two frames become connected by a new `Passage` node; both keep identity and continue moving together | boarding plank / grapple · Space Engineers *temporary* merge · FTL boarding |
| **Merge** | two frames become **one**; identities collapse | Space Engineers *permanent* merge |
| **Breach** | delete part of a frame's boundary, opening it onto another frame | Barotrauma hull breach · breaking into a sealed chamber |
| **Sever** | one frame splits into two | a ship broken in half |

This is the PO's proposal and it is **better than the design it replaces**. The decisive evidence is
that the game which suffered most from rigid-body multi-grid physics *also ships the merge shortcut,
and documents it as the better-behaved path*: Space Engineers' `Merge Block` — *"Separate grids
(ships) merge together via two merge blocks to become one single grid"* — with the wiki stating
plainly that *"a merged grid is one mass and easy to handle in flight, whereas using rotors forms
subgrids whose mass throws off the Inertial Dampers."*

Its deepest benefit is on the wire: **a collision resolution is never synchronized.** What is
replicated is a *discrete event* — "frame A grafted to frame B at fiction-time T, seam at these
coordinates" — which is exactly what an event-sourced spine transports natively, and exactly what
continuous physics synchronization is not. The geometric half already has a home:
`crates/world-gen/src/shape/csg.rs`.

### SPG-A9 — Frames move kinematically. Inter-frame rigid-body physics is REFUSED

> A frame's motion is a server-decided trajectory (route, wind, current, flight path). Frames do not
> collide as rigid bodies, carry no torque, and do not form physics sub-grids.

This is the line between "hard" and "engine rewrite". Space Engineers *"had to redo major parts of
the engine"* for networked multi-grid physics, listing *"player standing on a moving grid"* as its
own special-care system, and multi-grid defects persist years on. Kinematic frames cover the entire
intended surface — sailing a route, fighting on a deck, hauling cargo, a flying 洞府 — at a fraction
of the cost, and §SPG-A8 supplies ramming without any of the dynamics.

**Refusal is explicit, not omission** (per [`WSA-D2`](32_locus_as_actor.md)'s precedent of refusing
sub-cell lattice resolution by name).

### SPG-A10 — Control is a first-class binding, not an attribute of an actor

> Control is a row: `(controller_id, actor_id, since, authority)`. **One controller may hold several
> actors; an actor's controller may change.** The controller is the persistent identity; the body is
> not.

**SPG-F5 — the corpus has the seam but not the relation.**
[`ACT_001`](features/00_actor/ACT_001_actor_foundation.md)'s L3 declares control source as
**dynamic** (`User | AI | Engine`) and [`AGT-A3`](11_agent_decision_standard.md) makes drivers
*"assigned per actor/tier and swappable at runtime"* — the seam exists and is deliberate. But
`control_source` is an **enum on the actor**: it answers *"what kind of thing is driving this"* and
cannot answer *"which controller"*, nor express one controller holding two bodies. Meanwhile
`PCS-A4` locks a *"single `pc_user_binding` V1"* and the PC concept notes recommend
*"`Vec<PcId>` with a V1 cap=1 validator"*. The cardinality is closed at exactly the point the
possession mechanic needs it open.

Promoting the attribute to a relation collapses a startling number of separately-designed features
into one mechanism:

| Situation | Under SPG-A10 |
|---|---|
| 分身: body seals itself in a 洞府, avatar travels | one controller → two actors, in two different frames |
| a dying elder **seizes a disciple's body** | rebind control + `body_memory` (already in `pc_user_binding`) |
| player logs off → LLM takes the character | swap driver (`ACT-D1`, already designed) |
| death → ghost → new body | `pc_mortality_state` Alive/Dying/Dead/**Ghost** = a controller losing and regaining a body |
| a demonic art puppeting a victim | temporarily seizing an NPC's driver |
| riding a mount | possession-lite (`TVL_003`) |
| **a captain steering a ship** | possessing an entity **whose interior is a map** |

The last row is the payoff: **steering a ship and cultivating an inner world are the same
mechanism** — possessing an entity that has an interior.

### SPG-A11 — Interest and streaming key on the CONTROLLED ACTOR, never on the account

> A controller holding two actors in two frames has **two independent interest sets**.

Direct consequence of SPG-A10 and non-optional: keyed on the account, an avatar in an inner world
would never receive its own frame's updates. It also bounds an exploit — per-controller rate limits
must exist alongside per-actor validation, or possession becomes sanctioned multiboxing.

### SPG-A12 — Interiors materialize lazily, on the existence ladder that already exists

> An interior is a **declaration** until something enters it. Channel rows, event logs, writer
> bindings and projections are created on first entry, not at authoring time.

Without this, "every entity may hold an interior" means millions of channels. With it, the cost is
proportional to what players actually touch. This reuses [`WSA-A9`](32_locus_as_actor.md) (loci get
`AIT_001` existence tiers: Untracked → Minor → Major) rather than inventing a second ladder, and it
is the same pattern the repo already shipped twice: `MAP_001`'s lazy-cell `map_layout` (closure fix
S2.6) and `CSC_001`'s *"first PC entry to cell triggers compute"*. USD names the general form: a
**payload** is a reference whose subtree is deferred until explicitly loaded.

### SPG-A13 — A `Passage` is a map whose geometry is DERIVED, never authored

> The road between two places is a **node**, but its map is generated on demand from the world field
> it crosses, and materializes only when something happens on it.

**The journey must be a place, or a large class of emergent play is structurally impossible.** If a
road is only an edge with a timer, an ambusher has nowhere to stand, a traveler has nothing to avoid,
and there is no reason to hire an escort. EVE Online is the proof at scale: *"stargates are the only
fixed routes between star systems, so a camped gate turns an ordinary jump into an ambush you cannot
see coming until you are already in it"* — and systems like Tama, Uedama and Rancer are camped so
consistently that *their names are shorthand for danger*. A road became a reputation, and nobody
programmed it. ArcheAge builds an economy on the same principle: trade packs **slow you down and
make you vulnerable**, value scales with distance, and mercenary companies are hired as escorts.
Black Desert is the counter-example: an ocean covering **two fifths of the map** with *"no sea
combat"* and *"very few reasons to own a ship"* — a vast space that is not a place, so it is dead.

There is a second reason specific to this project: **the LLM needs somewhere to set the scene.**
"Ambushed somewhere on the road" is filler. "Stopped at the dry creek south of the relay post, at
dusk" is a story — and only the second is possible if the road has coordinates.

The cost is near zero because the generator already exists in design: `COMB_002`'s **`TG-D7`
deterministic wilderness arena generator**, driven by `GEO_WORLD_TIER_REDESIGN`'s sealed principle
that *one global field is the source of truth; an area is a derived **view** of it, never an
independent generation.*

### SPG-A14 — A shared interior separates DEFINITION from PLACEMENT

> When a node's interior comes from a shared template, the **template** and **this placement of it**
> are distinct rows. Local edits attach to the placement.

Without the split, editing one cave edits all forty caves that reused it. USD calls the pair
prototype/instance; Unity calls it prefab/instance; Godot calls it `PackedScene`/instance. All three
learned it the same way.

### SPG-A15 — One composition-strength order, not three

> Where a node inherits from a template, a canon layer, and local deltas, the resolution order is
> **declared once, globally, and is total**.

The corpus currently has two independent override mechanisms —
[`03_multiverse/01_four_layer_canon.md`](03_multiverse/01_four_layer_canon.md)'s L1/L2/L3 cascade and
`GEO_001`'s `GeographyDelta` overlay — and SPG-A14 would add a third. USD needed exactly this and
answers it with **LIVRPS**, a single documented strength ordering. Three parallel orders is how
"why did my edit not apply" becomes unanswerable.

### SPG-A16 — Combat always resolves on a tactical grid; only the grid's SOURCE varies

> The hybrid siting decision is **one** mechanism, not two.

The PO chose "fight in place where there is room, arena where there is not". That reads as two code
paths; it is not. Combat always occurs on a tactical grid. The only question is where the grid comes
from: **(i)** sampled from the `Domain`'s existing floor plan — the tavern's tables become cover; or
**(ii)** derived from the world field at the combatants' coordinates — the pass's rocks and trees
become cover. One rule set, one renderer, one generator interface with two implementations. Source
(ii) is the same generator as SPG-A13.

This **reverses** `RTM-D Q4` (*instanced dedicated combat scene*) in the same manner and with the
same justification pattern as [`AUD-F1`](10_medium_blast_radius_audit.md) reversing `COMB_001`'s
abstract-arena stance: the original reason was cost, and the cost is gone. Recorded as `SPG-D1`.

---

## 3 — `MapKind` — the closed set

```rust
pub enum MapKind {
    Universe,   // graph of worlds / planes; nodes are objects, edges are ways between
    World,      // a planet or plane; the equirectangular field world-gen produces
    Region,     // a geographic subdivision of a World; recursive (a Region may hold Regions)
    Locale,     // a HoMM3-class tilemap — the local strategic surface
    Domain,     // an interior: house, palace, cave, ship's hold; recursive
    Passage,    // a derived corridor between two nodes (SPG-A13)
    Arena,      // an ephemeral tactical grid (SPG-A16 source (ii))
    Vessel,     // RESERVED — a Domain whose parent changes over time (§6). Not implemented V1.
}
```

`Vessel` is reserved **now**, unimplemented, precisely so that adding moving frames later is not an
enum change rippling through every contract.

**Political structure is not a `MapKind`.** Empire / state / province / county are `owner_*`
attributes on nodes, per `FLAT_TO_3D` §C's conclusion and `WSA-F6`'s requirement that a locus be an
ownable entity. Territory changes hands by rebinding an ownership relation; it does not restructure
the containment tree.

### 3.1 Containment matrix

| parent ↓ / child → | Universe | World | Region | Locale | Domain | Passage | Arena |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **Universe** | ✅ | ✅ | — | — | ✅ | ✅ | — |
| **World** | — | — | ✅ | ✅ | ✅ | ✅ | — |
| **Region** | — | — | ✅ | ✅ | ✅ | ✅ | — |
| **Locale** | — | — | — | — | ✅ | ✅ | ✅ |
| **Domain** | — | ✅¹ | — | — | ✅ | ✅ | ✅ |
| **Passage** | — | — | — | — | ✅ | — | ✅ |
| **Arena** | — | — | — | — | — | — | — |

¹ `Domain → World` is the 内天地 case (SPG-A2): an interior that contains an entire world. It is
legal, rare, and ruleset-gated — and it is the row that proves the matrix is a *relation* and not a
disguised ladder.

Reading the matrix: every ✅ is a legal edge, validated **on write**. Anything not marked is rejected
with a named rule id. `Arena` is a leaf by construction.

---

## 4 — The node

```rust
pub struct SpaceNode {
    pub id: NodeId,
    pub kind: MapKind,
    pub parent: Option<NodeId>,        // containment; None only for a Universe root
    pub transform: Transform,          // RELATIVE to parent (SPG-A5). Never absolute.
    pub holder: Option<EntityId>,      // the entity whose interior this is (SPG-A1)
    pub definition: Option<DefRef>,    // shared template, if any (SPG-A14)
    pub materialization: Materialization, // Declared | Materialized (SPG-A12)
    pub mobility: Mobility,            // Static | Kinematic { trajectory } (SPG-A9)
}
```

`holder` is what makes SPG-A1 real rather than rhetorical: a `Domain` whose `holder` is a chest
entity, a `World` whose `holder` is a planet entity, a `World` whose `holder` is a **cultivator**.
A `Universe` root has no holder. The containment tree and the entity graph are joined here, at
exactly one field.

---

## 5 — Reference frames and the wire (`SPG-N1..N8`)

Consolidating SPG-A5 / A6 / A7 into the netcode rules a moving frame requires.

| # | Rule |
|---|---|
| **N1** | Positions are parent-relative; absolute = accumulated transforms from root |
| **N2** | Frame transform and occupant position replicate as **separate streams**; absolute positions are never transmitted |
| **N3** | Frame change is a discrete, server-authorized transition event; coordinates convert at that instant |
| **N4** | Authority splits: the frame host owns the frame's motion; each entity owns its motion **within** the frame |
| **N5** | AOI/interest is computed per frame, and keyed on the **controlled actor** (SPG-A11) |
| **N6** | Anti-cheat validates the **relative** delta (`RTM-A9` unchanged, reference frame named) |
| **N7** | 64-bit world coordinates, 32-bit within-frame for rendering — Star Citizen's *"Large World 64-bit world space coordinates with Local Physics Grids… maintaining 32-bit precision for rendering"* |
| **N8** | Nested frame depth is bounded (a rider, on a cart, on a ship, in a storm) |

---

## 6 — Rename register (SPG-F4)

PO decision: **rename decisively, now** — before a schema exists — rather than carry a mapping layer.

| Current | Where | Collision | New name |
|---|---|---|---|
| `Cell` | `world-gen/src/world_map.rs` | vs `CSC_001` cell (an interior) | **`GeoCell`** |
| `Realm` | `world-gen/src/world_map.rs:155` (an empire ⊆ continent) | vs multiverse "realm" (a plane) | **`Empire`** |
| `World` | `world-gen/src/world_map.rs:168` (*"political root… mostly a naming anchor"*) | vs `MapKind::World` | **`PolityRoot`** |
| `cell` | `CSC_001` (a tavern-sized interior) | vs `GeoCell` | **`Domain`** |
| `ChannelTier` | `MAP_001` §3.1 | an ordinal ladder mixing geography with politics | **deleted** → `MapKind` + matrix |
| `level_name: String` | `DP-Ch1` | ~~open string where a closed set is required~~ | **UNCHANGED** — see `SPG-R2`'s retirement (§7). `DP-A13` makes DP **deliberately agnostic** to level semantics so a reality can name its own levels (`phủ`, `châu`). The closed set belongs one layer up, on `map_layout.kind`, and `SPG-R1` already put it there. Two fields, two jobs. |
| `zone` / `subzone` | `flatworld`, `zonegen` (frozen flat track) | vs TMP `zone` | frozen; marked **deprecated vocabulary** |
| `zone` | `TMP_001` (a partition inside one tilemap) | — | **kept, and now unambiguous** |

The last two rows are the elegant part: because the tier ladder that used "zone" is being deleted
anyway, `zone` survives with **exactly one** live meaning — TMP's intra-tilemap partition. No rename
is needed there at all. `reality` (a universe/timeline in `03_multiverse`) is established and
unchanged.

---

## 7 — Amendment register

Doc-32 convention: rows are **PROPOSED** here and applied in a separate, named pass. Confidence is
stated per row.

| # | Target | Change | Confidence |
|---|---|---|---|
| **SPG-R1** | `MAP_001` §3.1 | retire `ChannelTier`; `map_layout.tier` → `MapKind`; positions become parent-relative transforms (SPG-A5) | **verified** |
| ~~**SPG-R2**~~ | ~~`DP-Ch1` `Channel`: `level_name: String` → `kind: MapKind`~~ | **⛔ RETIRED 2026-07-30, THE SAME DAY IT WAS WRITTEN — this row was wrong, and checking it before applying it is why.** [`DP-A13`](06_data_plane/02_invariants.md) states the refusal outright: *"**DP is agnostic to `level_name` semantics; feature/book layer interprets level names**… The tree shape is **per-reality** (book-specific) — a reality declares its own levels via a book schema."* Narrowing the field would have (a) pushed a **game-domain** concept into the **data plane**, breaking the exact invariant DP-A13 exists to state, and (b) destroyed the **per-reality vocabulary** — a wuxia reality could no longer call a level `phủ` or `châu`. It is a recurring DP principle, not an accident: `DP-A17` is agnostic to turn semantics, `metadata` is *"a feature-level bag; DP does not interpret"*, `CausalityToken` is opaque. **`SPG-F1`'s finding stands and is unaffected** — a free string where a closed set is required *is* a defect; it was simply diagnosed at the wrong layer. **It is already fixed by `SPG-R1`**: `MapKind` lives on `map_layout`, a FEATURE aggregate keyed by `channel_id`, which is exactly where the game vocabulary belongs and where `SPG-A2`'s ruleset-extensible whitelist already sits. **Net: two fields, two jobs, no DP change and no lock claim** — `Channel.level_name` = the reality's own word (DP, untouched); `map_layout.kind` = the structural kind the engine understands (feature layer). Recorded as [REC-93](19_reconciliation_register.md) | ~~verified~~ **retired — mechanism was wrong, finding survives** |
| **SPG-R3** | `GEO_001` §2 | `world_geometry` scope: continent-channel → **World node**; state that a World contains many continents (SPG-F3) | **verified** |
| **SPG-R4** | `GEO_001` §2 | `CellGrid` / `GeoCellId` doc text: adopt `GeoCell` (SPG-F4) | **verified** |
| **SPG-R5** | `CSC_001` | "cell" → `Domain`; drop the fixed 16×16 assumption to a **default**, not an invariant (a palace and a cave are not 16×16) | **verified** |
| **SPG-R6** ✅ **APPLIED** | `ACT_001` L3 | `control_source` enum → a first-class **`control_binding`** `(controller_id, actor_id, since, authority)` aggregate (SPG-A10) | **APPLIED 2026-07-30** — aggregate registered to ACT_001 under a `_boundaries` claim; `user_id` extracted from `pc_user_binding`. Many-to-many by construction. `control_source` survives as an L3 *classification*; `AGT-A3`'s drivers untouched |
| ~~**SPG-R7**~~ | ~~`PCS-A4` / PC concept notes: relax the `cap=1` validator~~ | **⛔ RETIRED 2026-07-30 — a MIS-DIAGNOSIS of my own, corrected by reading the target ([REC-96](19_reconciliation_register.md)).** Neither half held. `PCS-A4` is *"single `pc_user_binding` **aggregate**"* — a **packaging** decision, silent on control cardinality. `Q9`'s `cap=1` is **PC-per-REALITY**, recorded reason *"single PC narrative"* vs *"multi-PC for charter coauthors"* — a **narrative scope** call, and it was already shaped as `Vec<PcId>` + a validator specifically so relaxing it is *"a single-line validator change, no schema migration"* (`PCS-D3`). Nor does possession need it: a 分身 can be `ActorId::Npc` driven by a **User** controller, which never touches Q9. **The real blocker was a `user_id` FIELD ON THE BODY**, and `SPG-R6` removes exactly that. **Q9 stays locked.** Second row this arc retired by opening its target instead of acting on the table — after `SPG-R2`/[REC-93](19_reconciliation_register.md) | ~~verified~~ **retired — mis-diagnosis** |
| **SPG-R8** | `RTM-D Q4` | reversed by `SPG-D1` (combat sited in place where the space allows) — record the reversal with its reason, per the `AUD-F1` precedent | **verified** |
| **SPG-R9** | `TMP_001` `TMP-A1` | cell tier has no `tilemap_view` → restate in `MapKind` terms: `Locale` carries the tilemap; `Domain` carries the interior composition | **verified** |
| **SPG-R10** ✅ **APPLIED** | `EF_001` | `SPG-A1`'s `holder` field joins entity ↔ interior; landed **with** `WSA-R19` as required | **APPLIED 2026-07-30.** `SpaceNode.holder: Option<EntityId>` now has a variant to resolve to: a locus is `EntityId::Place(PlaceId)`, the same `PlaceId` `ActorId::Locus` carries (`WSA-R21`). That identity is the point — **one id, addressed as a thing by `EntityId` and as an agent by `ActorId`** — which is `SPG-A1` and `WSA-A7` meeting: *an entity may hold an interior* and *a locus is an entity*. `holder = None` is an ordinary space (a region has no holder); `holder = Some(Place(p))` is an interior belonging to a locus, which is what makes a ship's hold and a cultivator's inner world the same construction. |
| **SPG-R11** | `03_multiverse` + `GEO_001` | unify the two override cascades into the single strength order required by `SPG-A15` | **verify** |
| **SPG-R12** | `TVL_002` / `TVL_004` | composite travel and travel encounters gain `Passage` as their spatial substrate (SPG-A13) | **verify** |
| **SPG-R13** | `TMP_001` + `_boundaries/02_extension_contracts.md` §2.X | **NEW 2026-07-30, discovered while retyping the machine contract.** `tilemap_templates` / `grid_size_per_kind` / `default_template_per_kind` / `skip_kind` were keyed by the retired `ChannelTier`; the **type** is fixed (`MapKind`), but the **semantics** now nearly collapse. That contract assumed **four** tilemap-bearing tiers at decreasing zoom (the `256/192/128/64` default — four values for four tiers, **correct as written**; an earlier note in this session calling it underspecified was wrong). Under `SPG-R9` the tilemap sits on **`Locale` alone**: `World`/`Region` are served by `GEO_001`'s Voronoi mesh, which **did not exist as a render target** when TMP_001 was drafted, and `Domain` carries `CSC_001`'s interior composition. So a per-kind map now has one meaningful key. **Routed to TMP_001, not decided here** — collapsing another feature's DRAFT schema while holding the `_boundaries` lock for a rename is the scope creep the mutex exists to prevent. | **verify** — type applied, semantics OPEN |

**Inherited and still unapplied:** [`WSA-R19..R24`](32_locus_as_actor.md) — doc 32 sealed with its
own amendment rows explicitly *"PROPOSED, not applied: no feature spec was edited by this arc."*
`SPG-R10` depends on `WSA-R19`. The two sets should be applied in one pass, because `WSA-R19`
(`EntityId::Place`) and `SPG-A1` (`holder`) are the same seam approached from two directions.

### SPG-A17 — Absolute position is defined only up to the nearest coordinate root

`SPG-A5` said no node stores an absolute position and that absolute position is the **accumulation** of
transforms up the tree. That rule was **total** — it had no stopping condition — and `SPG-Q3` is what
happens when you ask it to cross `Universe → Domain`.

`Transform` was referenced at §4 and **never defined**. Here it is, with the field the first draft
wanted and review removed:

```rust
/// Parent-relative placement of a node's frame inside its parent (SPG-A5).
/// f64, not f32: precision must survive accumulation across DP-Ch1's <=16 levels.
pub struct Transform {
    /// Origin of this node's frame, in the PARENT's units.
    pub position: [f64; 3],
    /// Orientation of this node's frame relative to the parent's.
    pub rotation: [f64; 4],           // quaternion
}

/// Where accumulation STOPS.
pub enum FrameKind {
    /// Coordinates compose with the parent's. The common case.
    Inherited,
    /// This node ESTABLISHES a coordinate space. Absolute position is defined
    /// only up to here; nothing above contributes a metric.
    Root,
}
```

**What was rejected, and why it matters.** The first draft added
`parent_units_per_local_unit: f64` and composed it down the chain — the obvious reading of "make a
scale-skipping edge meaningful". It fails on contact with real numbers: a light-year→metre edge is
`9.46e15`, which alone eats an `f64`'s ~15–16 significant digits, and two such edges make the
accumulated absolute position noise. Budgeting precision for a quantity nobody needs is the wrong trade.

**The answer is that the quantity is not needed.** There is no use for "this chair's position in
universe coordinates". What the engine needs is position *within a frame* — and every frame that matters
(a world's surface, a ship's hold, a palace's floor) is a root or sits under one. So a scale-skipping
edge carries **no shared metric**, and asking for one was the error. `Universe` knows *where a Domain's
entrance is*; it does not know how many metres wide the Domain is, and never needs to.

**Consequences, stated so they are not rediscovered:**

* A `Root` node's parent edge is a **placement**, not a measurement — `position` locates the entrance,
  and nothing crosses it dimensionally.
* Two nodes under **different** roots have **no defined distance**. Travel between them is `SPG-A13`'s
  `Passage`, which is exactly the right shape: a `Passage` has a duration and a cost, not a length in
  shared units.
* `SPG-A5`'s accumulation is now well-founded: it terminates at the first `Root`, so it is a finite
  walk over at most 16 levels rather than an unbounded product.
* On the wire (`SPG-N2`) nothing changes — the frame's transform and the occupant's position already
  replicate as separate streams, and a root boundary is simply where the chain ends.

---

## 8 — Open

| # | Question |
|---|---|
| ~~**SPG-Q1**~~ | **✅ RESOLVED 2026-07-30 — RULESET DATA, engine-validated on write.** The suspected answer held, and closing it turned out to be the *same work* as an unrelated rot fix, which is why it is settled here rather than deferred. **`map_layout.kind` is AUTHORITATIVE on the row, never derived** — and that is the load-bearing half. The old `map.tier_field_mismatch` validator derived the tier *from the DP channel tree*; under `MapKind` that is **unobtainable**, because [`DP-A13`](06_data_plane/02_invariants.md) keeps DP *"agnostic to `level_name` semantics"*. Replaced by **`map.containment_violation`**: the write path validates the **edge** — `allowed(parent.kind, child.kind)` — not the label. The matrix is ruleset data per `SPG-A2`, so it is per-reality **without DP knowing anything**, which is what makes `Domain → World` (内天地) expressible in one reality and forbidden in another. **On the tenancy concern, which was the real content of this question:** the matrix is a **ruleset** artefact, so it inherits the ruleset's tenancy — content-addressed, digest-pinned, admin/author-authored, never user-writable at runtime. A reality **narrows or widens its own** matrix; no user edits a shared one. See [MAP_001 §3.1](features/00_map/MAP_001_map_foundation.md). |
| ~~**SPG-Q2**~~ | **✅ RESOLVED 2026-07-30 — two bounds already exist and NO third is added.** (1) **Structural:** `DP-Ch1`'s `depth ≤ 16` is not prose — it is a **DB `CHECK` constraint** ([`12_channel_primitives.md:82`](06_data_plane/12_channel_primitives.md): `depth SMALLINT NOT NULL CHECK (depth >= 0 AND depth <= 16)`) plus a stated validation rule at `:66` (*"feature-level books declaring deeper trees fail validation"*). It is already mechanical, at the strongest layer available. (2) **Semantic:** the **containment matrix itself**, per reality — a reality that finds `Universe → Universe` absurd simply omits that cell, and `map.containment_violation` enforces it. The question assumed a semantic bound was *missing*; it was in fact the mechanism introduced two axioms earlier. **Nothing is added, deliberately.** A third bound would be a rule with no mechanism of its own — the exact debt this corpus has been paying down, and `WDS-D3`/`D-WORLD-PAYLOAD-DERIVABLE` records the same reasoning for a different subject: a check with no possible violation is worse than none. |
| ~~**SPG-Q3**~~ | **✅ RESOLVED 2026-07-30 — there is NO single absolute coordinate space, and there does not need to be.** See `SPG-A17` below, added with this resolution. The question was sharper than it looked: `Transform` was **referenced at §4 and never defined**, so the contract did not merely lack an answer — it lacked a *type*. **First design, rejected at review:** give each node a `parent_units_per_local_unit: f64` and accumulate. It does not survive real ratios — one light-year→metre edge is `9.46e15`, which alone consumes an `f64`'s ~15–16 significant digits, and `DP-Ch1` permits 16 levels. **Adopted instead:** absolute position is defined only up to the nearest enclosing **coordinate root**, and a scale-skipping edge **is** a root boundary — you **re-base** across it, never accumulate through it. This dissolves the precision problem rather than budgeting for it, removes a field, and gives `SPG-A5`'s accumulation rule the **stopping condition it never had**. Star Citizen is the same device (64-bit coords *within* a system; separate systems share no space); OpenUSD's `metersPerUnit` is per-layer interchange metadata, not a factor composed down a deep chain. |
| **SPG-Q4** | Two actors under one controller in one fight — turn order and action budget. (`SPG-A10` × `COMB_002`.) |
| **SPG-Q5** | Does `Vessel` need `Kinematic` motion authored, simulated, or player-steered? Steering is possession (`SPG-A10`), but the trajectory source is unstated. |
| **SPG-Q6** | Cost of loci acting has **never been measured** — carried unchanged from [`WSA-F5(c)`](32_locus_as_actor.md), and doc 21 §7 forbids inferring headroom. |

---

## 9 — Cross-references

* [`32_locus_as_actor.md`](32_locus_as_actor.md) — `WSA-A7..A11`; a locus is entity **and** actor
* [`31_world_simulation_architecture.md`](31_world_simulation_architecture.md) — island-local writes, folds
* [`GEO_WORLD_TIER_REDESIGN.md`](GEO_WORLD_TIER_REDESIGN.md) — the derived-view principle (SPG-A13)
* [`FLAT_TO_3D_MIGRATION_PLAN.md`](FLAT_TO_3D_MIGRATION_PLAN.md) §C — geometry vs politics (SPG-F2)
* [`06_data_plane/12_channel_primitives.md`](06_data_plane/12_channel_primitives.md) — `DP-Ch1`
* [`09_interaction_layer_reconciliation.md`](09_interaction_layer_reconciliation.md) — `ILR-A2` (SPG-A7)
* [`08_realtime_movement_authority.md`](08_realtime_movement_authority.md) — `RTM-A6..A9` (SPG-A6)
* [`11_agent_decision_standard.md`](11_agent_decision_standard.md) — `AGT-A3` drivers (SPG-A10)
* [`features/00_map/MAP_001_map_foundation.md`](features/00_map/MAP_001_map_foundation.md) ·
  [`features/00_cell_scene/CSC_001_cell_scene_composition.md`](features/00_cell_scene/CSC_001_cell_scene_composition.md) ·
  [`features/00_tilemap/TMP_001_tilemap_foundation.md`](features/00_tilemap/TMP_001_tilemap_foundation.md) ·
  [`features/00_geography/GEO_001_world_geometry.md`](features/00_geography/GEO_001_world_geometry.md) ·
  [`features/00_actor/ACT_001_actor_foundation.md`](features/00_actor/ACT_001_actor_foundation.md)

### External prior art

* [OpenUSD — Glossary](https://openusd.org/release/glossary.html) · [Introduction](https://openusd.org/release/intro.html) · [Referencing basics](https://docs.nvidia.com/learn-openusd/latest/composition-basics/references.html) — references, payloads, prototypes, LIVRPS
* [Star Engine — Local Physics Grids](https://starcitizen.tools/Star_Engine) · [Object Container Streaming](https://starcitizen.tools/Object_Container_Streaming) · [64-bit spatial management](https://scfocus.org/64-bit-spatial-management-of-objects-for-star-citizen/)
* [Space Engineers — Merge Block](https://spaceengineers.wiki.gg/wiki/Merge_Block) · [Grid](https://spaceengineers.fandom.com/wiki/Grid) · [Multiplayer overhaul](https://blog.marekrosa.org/2018/07/space-engineers-multiplayer-overhaul/)
* [EVE University — Gate camps](https://wiki.eveuniversity.org/Gate_camps) · [ArcheAge — Trade Routes](https://archeage.fandom.com/wiki/Trade_Routes) · [Black Desert review (ocean content)](https://altarofgaming.com/black-desert-online-review/)
* [django-polymorphic-tree](https://github.com/django-polymorphic-tree/django-polymorphic-tree) — typed-node trees with per-type child constraints
