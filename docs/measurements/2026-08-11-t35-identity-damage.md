# T35 — what the derived entity id actually costs — 2026-08-11

> **Result: the plan (and my own re-measurement) were counting the wrong thing.** The headline
> number — 2819 of 6297 nodes whose `Entity.id` disagrees with a recompute — is **mostly
> benign**, and the real damage is **17 duplicate groups** with a cause that belongs to a
> different debt.

## The defect that IS real, and is now fixed

`Entity.id` is `entity_canonical_id(user, project, name, kind)` — a hash of the canonicalised
name and kind — and `merge_entity` MERGEs on it. The glossary rename path (`link_to_glossary`)
correctly updates the node in place and leaves `e.id` alone; its own docstring says so:

> *"The id stays stable post-rename — it no longer matches `entity_canonical_id(new_name,
> kind)`, but that's fine: future lookups go through `glossary_entity_id` or by name."*

Fine for that function. **Not fine for the extraction writer**, which does neither: it computes
a fresh hash from the new name, finds nothing at that id, and mints a SECOND node for the same
character. Nothing raises. Both nodes are well-formed.

Proven as a test before it was fixed (`tests/integration/db/test_t35_identity_rename.py`):
rename → duplicate, re-kind → duplicate, with two controls (distinct entities stay distinct,
projects stay isolated) that a collapse-everything "fix" would fail.

The fix resolves an existing node by what it currently SAYS it is — `(user, project,
canonical_name, kind)` — before minting. **The sort is the safety property:**

```cypher
WITH prior ORDER BY (prior.id = $id) DESC, prior.created_at ASC
```

A node already at the derived id still wins, so the change is a strict no-op for every write
that works today. Resolution decides something only when nothing sits at the derived id —
exactly the rename/re-kind case. A fifth test pins that, and it is the one that matters most.

## Why "2819 stale ids" is the wrong number

Under **opaque identity** — the direction the register seals — an id that survives a rename
*is supposed to* stop matching a recompute. That divergence is the design working, not damage.
A stale id only hurts if something recomputes and joins on the result, and after the fix the
one writer that did no longer does.

So `QC-6`'s stated criterion — *"a Cypher count of nodes whose `e.id` disagrees with a
recomputed hash — must be 0"* — is measuring a quantity that opaque identity guarantees will
be **non-zero forever**. It cannot pass, and passing it would mean the derived id is still
live. The criterion that carries the same intent and can actually be met:

```cypher
// no two nodes may share (user, project, canonical_name, kind)
MATCH (e:Entity) WHERE e.canonical_name IS NOT NULL AND e.kind IS NOT NULL
WITH e.user_id AS u, e.project_id AS p, e.canonical_name AS cn, e.kind AS k, count(*) AS n
WHERE n > 1 RETURN count(*) AS duplicate_groups
```

## The real damage, measured

```
duplicate_groups   17
nodes_in_groups    34
redundant_nodes    17
```

And the classification is unambiguous — **all 17 groups are multi-ANCHORED**:

```
anchored_plus_minted  0
none_anchored         0
multi_anchored       17
```

Every node in every group carries a `glossary_entity_id`. So these are **not** rename-minted
extraction duplicates. They are two distinct glossary entities faithfully mirrored to two
nodes, and the KG is reporting a glossary problem accurately. Two causes, both visible in the
raw names:

```
筋骨断续膏 / 筋骨斷續膏     ← simplified vs traditional, folded together by ML-2's
林家演武场 / 林家演武場        T2S normalisation AFTER both nodes already existed
祭祀大典 / 祭祀大典          ← identical raw names, two glossary entries
```
<!-- doc-language-gate: ok -- stored entity names from the corpus; the traditional/simplified pairing IS the evidence and cannot be shown in translation -->

The first class is **retroactive**: the canonicalisation rules changed under nodes that were
distinct when they were written. The second is a plain authoring duplicate.

## Who owns the 17

Not T35. Both classes are glossary-level, and the remediation already exists:
`POST /internal/books/{book_id}/dedup-name-variants` (`D-GLOSSARY-ST-DEDUP` M3b) groups by the
folded key and merges each group into one winner, dry-run unless `?apply=true`.

It was **not run here.** Merging entities is destructive — it moves edges and deletes nodes —
and the graph in question holds real books. Tracked as `D-T35-COLLISION-GROUPS-ARE-GLOSSARY-DEBT`.

## Reproducing

```
# the benign number
MATCH (e:Entity) WHERE e.id IS NOT NULL RETURN count(e)          → 6297
# the number that means something
MATCH (e:Entity) WHERE e.canonical_name IS NOT NULL AND e.kind IS NOT NULL
WITH e.user_id AS u, e.project_id AS p, e.canonical_name AS cn, e.kind AS k, count(*) AS n
WHERE n > 1 RETURN count(*), sum(n-1)                            → 17, 17
```
