# Entity kind: from *first writer wins* to a resolved vote over a hierarchy

**Status:** DESIGN · **M1–M3 SHIPPED 2026-08-02** (77 re-kinds applied, 399 entities carrying a
facet, 33 a live conflict); **M4 open** — split across `D-KG-KIND-FACETS` (the KG mirror) and
`D-KIND-FACETS-SURFACE` (API + FE badge), both tracked in [`README.md`](README.md).
2026-08-02 · supersedes the open half of `BTG-A49` / `BTG-A66`
**Services:** glossary-service (Go, owner) · translation-service (Python, the voter) ·
knowledge-service (KG mirror, consumer) · frontend (consumer)

---

## 1. The defect, measured

An entity's kind is decided by **whichever extraction batch names it first**, and never
revisited. `findEntityCrossKind` is *oldest-wins* and returns the entity's **stored** kind so
that an incoming mis-tag cannot re-kind a settled entity — deliberate, documented, and the
reason a corrected ontology cannot correct the data the wrong ontology produced.

Measured on 封神演義 (1,597 distinct entity names, ~84 observations for a frequent one):

| | |
|---|---|
| stored entities with at least one recorded model observation | **1,531** |
| store agrees with the model's **modal** answer | 1,358 (**89%**) |
| store **disagrees** with the mode | **173 (11%)** |

The 11% is not noise at the margins. It contains the protagonist:

```
姜子牙   character 64 · species 20    → stored `species`   (first seen 07:56)
武王     character 30 · species  6    → stored `species`
哪吒     character 70 · species 20    → stored `character` ✓
風火輪   item 40 · terminology 7      → stored `terminology` + a duplicate `item`
西岐     organization 52 · location 38 → genuinely both
```

> **The store answers a question the model answered 84 times by keeping the answer it gave
> first.** That is the worst available estimator: one draw instead of the argmax over all of
> them. Every kind-accuracy number this project has published measures **arrival order**.

### What the 173 are made of

| pair | n | nature | fixed by |
|---|---|---|---|
| species ↔ character | 48 | **orthogonal axes** — an individual vs a type of being | multi-label |
| item ↔ terminology | 50 | mutually exclusive by definition; the model wavers | vote |
| organization ↔ location | 30 | **missing entity** (`BTG-A28`) — 西岐 is a place *and* a polity | multi-label |
| terminology → technique / power_system | ~15 | **granularity** | hierarchy |
| remainder | ~30 | assorted | vote |

Three different diseases. A vote fixes the symptom in all of them *today*; the hierarchy and
the labels fix the two that will keep recurring.

## 2. Constraint that shapes everything

`glossary_entities.kind_id` is a **single non-null FK** read by ~470 sites in glossary-service
alone, mirrored as `kind_code TEXT NOT NULL` in knowledge-service's own table, projected into
Neo4j, and assumed scalar by the wiki and every frontend feature folder.

**So the scalar stays.** It becomes a *derived* value rather than a frozen first write.
Everything else is additive, and nothing that reads `kind_id` today has to change.

## 3. Design

### 3.1 One ledger, two jobs

```sql
CREATE TABLE entity_kind_votes (
  entity_id  UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  kind_id    UUID NOT NULL REFERENCES book_kinds(book_kind_id) ON DELETE CASCADE,
  votes      INT  NOT NULL DEFAULT 0,
  first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_id, kind_id)
);
```

The same rows answer both questions, and the difference is a threshold:

- **primary kind** = the resolved argmax (§3.3) → written back to `glossary_entities.kind_id`
- **secondary labels (facets)** = every other kind whose share clears a floor → 西岐 keeps
  `organization` as primary *and* carries `location`, instead of one of them being erased

That unification is the reason all three chosen directions fit one schema. Multi-label is not
a second mechanism; it is the ledger read with a looser threshold.

**Tenancy.** `entity_id` scopes to a book, `kind_id` to `book_kinds` — both already
book-scoped, so the table inherits the scope key and adds no new tenancy surface.

### 3.2 Hierarchy

```sql
ALTER TABLE system_kinds ADD COLUMN parent_kind_id UUID REFERENCES system_kinds(kind_id);
-- and the user_ / book_ tiers, each self-referencing within its own tier
```

Declared parents, from what the data shows the model actually does:

```
terminology            the generic bucket, and the model already uses it as one
  ├─ technique         a named art someone performs
  └─ power_system      a graded ladder
```

This is **describing observed behaviour, not inventing a taxonomy**: `terminology` collected
崑崙之妙術, 土遁, 五行方位, 八九變化 because it was the nearest generic home. Making that
official is what lets a later, more specific answer *refine* rather than *contradict*.

`terminology`'s description gains one line: **when a child kind fits, use the child.**

### 3.3 Resolution

```
resolve(entity):
    v ← votes(entity)                       # {kind: n}
    v ← roll_up(v)                          # a vote for a child is also a vote for its ancestors
    challenger ← argmax(v)
    incumbent  ← entity.kind_id

    if challenger == incumbent:                    keep
    if challenger is a DESCENDANT of incumbent:    take it        # refinement, no threshold
    if v[challenger] ≥ MIN_VOTES
       and v[challenger] > v[incumbent] × SWITCH_RATIO:  take it  # hysteresis
    otherwise:                                      keep, and record a CONFLICT
```

- `MIN_VOTES = 2`, `SWITCH_RATIO = 1.5`. One stray observation never re-kinds anything; a
  consistent majority does. Without hysteresis the kind flips on ties and the KG re-syncs
  forever.
- **Refinement is exempt from the threshold** — `terminology → technique` is strictly more
  specific and loses no information, so it needs no majority. The reverse (child → parent) is
  a normal challenge and does face the threshold.
- A challenger that leads but fails the threshold is not discarded: it is recorded, so the
  disagreement is visible instead of silently dropped (the `updated`-never-`conflict` gap).

### 3.4 Where votes come from

The extraction writeback (`extraction_handler.go`), at exactly the site that today throws the
incoming kind away. It records a vote, re-resolves, and — when the primary moves — journals
the change and emits the outbox event, so knowledge-service re-syncs through the existing
path rather than a new one.

### 3.5 The 173 existing rows

The observation history lives in **translation-service**'s `extraction_raw_outputs`, a
different service and a different database. A backfill script reads it, aggregates votes per
name, and posts them to a glossary internal route, which then resolves normally. Same shape
as `scripts/backfill-terminology-names.py`: **dry-run by default**, and the re-kind rides the
ordinary journal + outbox so it is reviewable and reversible.

## 4. Milestones

| | scope | risk boundary |
|---|---|---|
| **M1** | the ledger, the resolution, the writeback recording votes, journal + outbox on a primary change | DB migration + a behaviour change in the writeback |
| **M2** | `parent_kind_id`, the declared hierarchy, roll-up + refinement rule | ontology change, adopt/sync propagation |
| **M3** | the backfill of the 173 | a data mutation |
| **M4** | secondary labels surfaced — API, FE badge, KG mirror | cross-service contract |

## 5. What this deliberately does NOT do

- **Does not make `kind_id` nullable or multi-valued.** The scalar is the compatibility
  surface for ~470 call sites, KG and Neo4j; multi-label rides alongside it.
- **Does not re-open `BTG-A28`** (西岐 as one entity vs two linked ones). Multi-label makes the
  case *visible* rather than lossy; splitting into linked entities remains its own decision.
- **Does not touch the extraction prompt.** The model's answers are already good enough — the
  mode is right 89% of the time and it is the store, not the model, that loses them.
