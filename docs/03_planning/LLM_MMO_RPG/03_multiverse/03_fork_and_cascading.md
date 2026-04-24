<!-- CHUNK-META
source: 03_MULTIVERSE_MODEL.ARCHIVED.md
chunk: 03_fork_and_cascading.md
byte_range: 13379-16089
sha256: 613963b1ac4f5eddeec61319fbb29afc8090a4bdb4996c0ca36ad8a4952486dc
generated_by: scripts/chunk_doc.py
-->

## 6. Snapshot fork semantics (locked decision)

Fork is always snapshot. Repeated from [02 §4](02_STORAGE_ARCHITECTURE.md) for self-containment:

- Child reality inherits events from parent's chain **up to and including `fork_point_event_id`**
- Events in parent after fork point are **not visible** to child
- Events in child are **not visible** to parent
- No merging between peer realities
- Replay of child is deterministic: same events chain → same state, always

For the full tradeoff analysis vs live fork, see the conversation log; live fork was rejected.

### One exception: read-through to book

The book layer (L1 + L2 canon) is not a reality and not subject to snapshot fork. Book updates are read-through to all realities. This is NOT live fork between realities — it is cascading read to the immutable canon layer.

- If the author edits an L1 axiom after a reality was created, that reality sees the new axiom on next read.
- If the author edits an L2 seeded fact, realities that have not written a conflicting L3 event see the new L2 value; realities that have overridden see their own L3.

This follows from the cascade read rule in §3: L3 > L2 > L1. Updates to L1 or L2 propagate only where L3 has not already overridden.

## 7. Cascading read

Reading the state of an aggregate (PC, NPC, region, KV) in reality R:

```python
def load_aggregate_state(aggregate_id, reality_id):
    # 1. Walk ancestry backward, collecting (reality_id, effective_cutoff)
    chain = []
    r = reality_id
    cutoff = None  # no cutoff for self — see all own events
    while r is not None:
        chain.append((r, cutoff))
        parent = lookup_parent(r)
        if parent is None:
            break
        cutoff = lookup_fork_point(r)  # see parent events only up to here
        r = parent

    # 2. Load events from each link with its cutoff
    events = []
    for (r_id, cut) in chain:
        if cut is None:
            events += select_events(reality_id=r_id, aggregate_id=aggregate_id)
        else:
            events += select_events(reality_id=r_id, aggregate_id=aggregate_id,
                                     event_id__lte=cut)

    # 3. Order by (chain_depth_descending, aggregate_version) and fold
    events.sort(key=lambda e: (e.chain_depth, e.aggregate_version))

    # 4. If L1/L2 values exist, use them as base; else default empty
    base = load_canon_defaults(aggregate_id)
    return fold(base, events)
```

Optimization: projections collapse this cascade into per-reality flat rows (see [02 §5](02_STORAGE_ARCHITECTURE.md)). The cascade above is the semantic model; the physical read hits a projection row.

