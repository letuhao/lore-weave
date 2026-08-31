# World & Map — what is BUILT, and where to attach

> **Status:** ACTIVE · **Measured:** 2026-08-23 at `f157cd037` (branch `feat/game-logic`)
> **Audience:** any agent or human about to touch the map, the space graph, movement, places, or where an entity is.
> **Companion:** the *design* track is [`MAP_001`](../03_planning/LLM_MMO_RPG/features/00_map/MAP_001_map_foundation.md) · [`GEO_001`](../03_planning/LLM_MMO_RPG/features/00_geography/GEO_001_world_geometry.md) · [`TMP_001`](../03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_001_tilemap_foundation.md) · [`41_space_dataflow`](../03_planning/LLM_MMO_RPG/41_space_dataflow.md). **Those say what it should be. This says what it IS.**

## Why this file exists

The map is one of the most thoroughly *designed* areas in the repo and one of the least
*inventoried*. An agent handed "build the map feature" will find eight design documents, no
statement of what already runs, and will reasonably conclude nothing does.

**That conclusion is wrong and expensive.** The space graph, its validator, its seeder, its spawn
path and its read model are built, constrained, tested and wired to a browser against a real
reality. A from-scratch rebuild does not merely waste the work — it produces a **second** world
model beside the first, and this repo already has one of those (see §5).

So the rule this file exists to enforce:

> **Before designing anything in this area, establish which of the three states each capability is
> in — BUILT, HOLLOW, or ABSENT — and attach to the existing seam. Re-measure (§6); do not trust
> this file's age.**

---

## 1 · The 60-second orientation

There are **two** independent world systems in this repo. Know which one you are in.

| | **The space graph** | **The tilemap** |
|---|---|---|
| owns | *where things are* — topology, places, siting | *what a surface looks like* — tiles, terrain, zones |
| service | `world-service` | `tilemap-service` |
| channel id | `i64`, per-reality database | `String` newtype (`ChannelId`), Phase 0a |
| state | persistent rows in the reality's DB | **stateless**, procedurally generated per request |
| authority | `PF_001` · `SPG-A3` · `DP-Ch1` | `TMP-A1` · `SPG-R9` |
| **they are joined by** | **nothing today.** See §5. |

Everything in §2–§4 is about **the space graph**. If your task says "map" and means *pixels*, you
are in tilemap-service and §5 is the section you need.

---

## 2 · BUILT — do not rebuild any of this

Cited by **symbol**, not line number, deliberately: line numbers rot within a week and a guidance
doc with wrong pointers is worse than no doc.

| Capability | Owner (the symbol to call) | Proven by |
|---|---|---|
| Validate a world declaration — containment matrix, depth ≤ 16, single root, place-on-domain 1:1, cycles, unknown parents | `world_seed::validate` (**pure**, touches no DB) | `tests/world_declarations.rs` — 2 refusal arms |
| Write a world — `channels` + `map_layout` + `place` in **one transaction**, idempotent | `world_seed::seed_world` | `tests/world_seed_live.rs` incl. a re-run arm |
| Seed a reality **that already exists** | `POST /internal/v1/world/seed` → `handlers::world::seed_world` | `scripts/smoke/world-in-a-running-reality.sh` |
| Seed a reality **at provision time** | `provisioner::Effects::seed_world_structure` (step 12 of 12) | `provisioner_live` |
| Site an entity in a cell, atomic with actor creation | `spawn::site_in_cell` (takes `&mut PgConnection` **on purpose** — a pool would let it commit independently and orphan the entity) | `tests/spawn_atomic_live.rs` |
| Create/adopt an actor, optionally sited | `actor_registry::create_actor` / `adopt_actor` | `tests/spawn_atomic_live.rs` |
| "Where is entity N" — three distinct facts (`unbound` / `in_cell` / `not_in_a_cell`) | `space_view::where_is` → `POST /internal/v1/space/where-is` | `frontend-game/e2e/running-reality.spec.ts`, bite-proven |
| "What is at node X" — here + ancestors + portal ring + occupants + `truncated` | `space_view::assemble` → `POST /internal/v1/space/view` | `space_view_measure_live.rs` — **but see §4, it has no caller** |
| An authored world, validated in CI | `contracts/world/demo_v1.json` | `tests/world_declarations.rs` |

**Two design facts that are easy to undo by accident:**

- **`Whereabouts` is a sum type with three arms and must not be flattened to a nullable location.**
  *No binding at all* and *held in someone's hand* are different truths; `0025_entity_binding`
  models this with a `CHECK` enforcing exactly one arm, and collapsing it at the edge undoes that.
- **`SDF-A26` — a reader chooses a BUDGET, never a field set.** `SpaceViewRequest` carries caps, not
  a field list. Which layers render is the layer owner's declaration. Do not add `fields[]`.

---

## 3 · HOLLOW — the table exists, nothing writes it

These three shipped as schema with deferral triggers attached (`OR-1` on the
[world-in-a-running-reality board](../plans/2026-08-22-world-in-a-running-reality-RUN-STATE.md)).
They are honest placeholders. **Adding a writer is the work; adding the table is already done.**

| Table | Rows | Writer | Reader | What its emptiness costs you |
|---|---|---|---|---|
| `portal` | 0 | none | `space_view::assemble` | **No cell connects to any other.** The world is a containment tree with zero lateral edges. `portal_ring` is computed correctly and is always `[]`. |
| `layer_registry` | 0 | none | none | No layer declares a projection, so a view has nothing to render beyond raw ids. |
| `encounter` | 0 | none | none | Encounters exist only as folded events in memory, never as world state. |

`portal` is the load-bearing one. **Movement is meaningless until it has a writer** — there is
nowhere to move to.

---

## 4 · ABSENT — genuinely not started, and where to attach

This is the honest gap. There is no stub to extend here; there is a seam to attach to.

### 4a · Movement

**Nothing in the repo updates `entity_binding.cell_id`.** The only write is the initial `INSERT` in
`site_in_cell`. Sited once is sited forever.

**`combat_v1`'s `move` is not movement.** It takes a `stance` — `Kite · Flank · Cover · Hold` — and
produces `CombatEvent::Moved { actor, stance }`. It has no destination and never touches the world.
Do not extend it into world movement; a tactical stance and a change of room are different verbs
with different rules, and merging them makes them indistinguishable in the event log.

**Where to attach.** A move needs four things, in this order:

1. A writer for `portal`, so a destination can be *legal* rather than arbitrary (§3).
2. Its own vocabulary entry — a new tool, not a widened `move`.
3. A producer beside `spawn::site_in_cell` in `spawn.rs`. Note that **re-siting is currently an
   error by design** ("moving is a different verb with different rules — letting an `INSERT` double
   as a move would make the two indistinguishable in the log"). Honour that: write `move_to_cell`,
   do not relax `site_in_cell`.
4. `R-52` — evacuate, never delete.

### 4b · Seeing the room you are in

`space_view::assemble` is finished, careful work — recursive ancestor walk, explicit budget, a
`truncated` flag so a reader can tell an empty room from a crowded one — and **nothing calls it.**

**This is the cheapest real progress available.** The endpoint exists; it needs a consumer. Adding
one immediately surfaces the empty `portal_ring`, which is the honest next problem.

### 4c · Rendering the space graph

No frontend module reads `channels`, `map_layout` or `place`. The player-facing surface is one line
of text in `ChannelPanel.tsx` (`data-testid="frame-place"`), fed by `w1.frame.place`.

The place lookup in `services/game-server/src/ws/place.ts` is **advisory on purpose** — a failed
place lookup degrades to no location rather than refusing the join, so a space-view outage cannot
take down joins that never needed it. **Keep that asymmetry** if you extend the frame.

---

## 5 · The two-worlds seam — read before touching either

`/play` renders **both** systems at once and they do not know about each other:

- `PhaserGame` draws a tilemap from `useZoneTilemap({ seed, tier, gridWidth, gridHeight })` — the
  seed comes from **a spinner in the HUD**, not from the world.
- The request *does* carry a `channel_id`, so the contract anticipated the join — but the client
  never passes one and falls back to the literal `DEFAULT_CHANNEL_ID = 'ch_v1_viewer'`.
- `ChannelPanel` shows real kernel state and the real place name for the real actor.

So **the map you look at is not the place you are in.** This is a *known* seam —
`services/tilemap-service/src/types/channel.rs` says its `ChannelId` is "Phase 0a … Phase 2 will
swap in the real DP-K1 `ChannelId`" — but nothing fails while it stays open.

**If you are asked to "connect the map":** passing the real channel id is a small change. Deciding
what a tilemap *means* for a `Domain` — which `TMP-A1` explicitly excludes from tilemaps, since
`CSC_001` owns the in-scene interior — is not. Settle that question before writing code.

---

## 6 · Re-measure before you trust this file

Every claim above is reproducible. **Run these rather than believing a dated document** — the whole
point of this file is to stop an agent acting on a stale premise, and it can go stale itself.

```bash
# What the world tables actually hold, in a seeded reality
for t in channels map_layout place portal layer_registry encounter entity_binding actors; do
  docker exec infra-postgres-1 psql -U loreweave -d lw_reality_00c7e2c5cabc \
    -tAc "SELECT '$t: '||count(*) FROM $t"
done

# Does anything WRITE the hollow three yet?
grep -rn "INSERT INTO portal\|INSERT INTO layer_registry\|INSERT INTO encounter" \
  --include=*.rs --include=*.ts --include=*.go services/ crates/ | grep -v /tests/

# Does movement exist yet?
grep -rn "UPDATE entity_binding" --include=*.rs --include=*.ts services/ crates/

# Has /space/view acquired a caller?
grep -rn "space/view" --include=*.ts --include=*.tsx frontend-game/ services/game-server/

# Is the tilemap still on the literal viewer channel?
grep -n "DEFAULT_CHANNEL_ID\|channelId" frontend-game/src/api/tilemap-client.ts
```

A live run of the whole chain, end to end, against a real reality:

```bash
bash scripts/smoke/world-in-a-running-reality.sh --reality <uuid> --seed-only
```

It refuses an unknown reality and a reality behind the migration manifest, and it writes
**only through the service's own endpoints** — there is not one `INSERT` in it. Keep it that way if
you extend it: a demo that reaches past the API proves the database, not the system.

---

## 7 · The three mistakes this file exists to prevent

1. **Rebuilding the space graph** because the design docs are richer than the code. §2 is the
   inventory; attach to it.
2. **Extending `combat_v1`'s `move`** into world movement because the name matches. It is a stance
   (§4a).
3. **Building a third world model.** There are already two (§5) and they are unjoined. Anything new
   that describes *where things are* belongs in the space graph or it becomes the next seam.

---

## Maintenance

This file is an **inventory**, and an inventory that is not re-measured is a rumour. When you change
what is built in this area, update the row *and* the `Measured:` header. When you close a HOLLOW or
ABSENT item, move it into §2 with the symbol and the test that proves it — a capability that ships
without leaving this table is exactly the drift the
[world-in-a-running-reality board](../plans/2026-08-22-world-in-a-running-reality-RUN-STATE.md)
recorded five separate times.
