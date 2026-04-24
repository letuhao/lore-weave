<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: C01_severance_orphan_worlds.md
byte_range: 139622-147656
sha256: d0af551dc1885a47fb28129d1c095edfe86fd7394e43f870bf31df2daa6ee3aa
generated_by: scripts/chunk_doc.py
-->

## 12M. Reality Ancestry Severance — Orphan Worlds (C1 resolution)

**Origin:** SA+DE adversarial review 2026-04-24 surfaced C1 — cascade read broken when ancestor reality is archived/dropped. User proposed reframing as **gameplay feature**: "orphan worlds" — realities whose ancestry has faded from memory. Elegant resolution: turn tech constraint into in-world mystery.

### 12M.1 The problem C1 identified

Snapshot-fork cascade (§6, §7) lets descendants inherit events from ancestors up to fork point. When an ancestor reality closes per R9 (§12I) and its DB is dropped:
- Descendants' projection tables stay intact
- BUT cascade read into ancestor events fails
- Projection rebuild fails
- Cold aggregate load fails

The R9 120-day close floor doesn't help — descendants may live far longer than their ancestors.

### 12M.2 The solution — auto-severance at freeze

When an ancestor reality transitions `pending_close → frozen` in R9 state machine, **automatically sever all live descendants** before allowing ancestor to proceed to `archived`:

```
For each live descendant D where cascade_ancestors(D) contains frozen_reality_id:
  1. Force snapshot all D's aggregates at current version
     (ensures full state captured before ancestor vanishes)
  2. Store snapshots as D's "ancestry_severance_baseline"
  3. Update D's registry: ancestry_status='severed', severed_ancestor_reality_id,
       ancestry_severance_baseline_event_id
  4. Append to D's ancestry_fragment_trail (lore record)
  5. Emit event: reality.ancestry_severed (scope='reality', propagates to all D's sessions)
  6. Only after ALL descendants severed → ancestor proceeds to archived
```

Technically identical to MV9 auto-rebase but preserves descendant's reality_id + adds narrative framing.

### 12M.3 Schema

```sql
ALTER TABLE reality_registry
  ADD COLUMN ancestry_status TEXT NOT NULL DEFAULT 'intact',
    -- 'intact' | 'severed' | 'genesis' (no ancestor by design)
  ADD COLUMN ancestry_severed_at TIMESTAMPTZ,
  ADD COLUMN severed_ancestor_reality_id UUID,
  ADD COLUMN ancestry_severance_baseline_event_id BIGINT,
  ADD COLUMN ancestry_fragment_trail JSONB;
    -- Append-only. Array of severed ancestor references for lore display.
    -- e.g., [
    --   {"reality_id": "...", "severed_at": "2028-03-15",
    --    "narrative_name": "The First Age", "baseline_event_id": 1234567}
    -- ]
```

New event type: `reality.ancestry_severed`
```json
{
  "scope": "reality",
  "payload": {
    "severed_ancestor_id": "uuid",
    "severance_reason": "ancestor_closed",   // 'ancestor_closed' | 'user_requested'
    "baseline_event_id": 1234567,
    "narrative_text": "The Old Age has passed beyond memory..."
  }
}
```

### 12M.4 Cascade read — stops at severance

```python
def load_aggregate_state(aggregate_id, reality_id):
    r = lookup_reality(reality_id)

    if r.ancestry_status == 'severed':
        # Load baseline snapshot captured at severance
        base = load_baseline_snapshot(r.reality_id, r.ancestry_severance_baseline_event_id)
        # Apply only own events after severance point
        own_events = select_events(reality_id=r.reality_id,
                                    aggregate_id=aggregate_id,
                                    event_id__gt=r.ancestry_severance_baseline_event_id)
        return fold(base, own_events)
    else:
        # Standard cascade, stopping at first severed ancestor
        chain = walk_ancestors(r, stop_at_severance=True)
        events = collect_events_along_chain(chain, aggregate_id)
        return fold(events)
```

Severance is terminal — cascade never walks past a severed marker.

### 12M.5 Player notification cascade (extends R9-L5)

When ancestor enters `pending_close` (R9 state), notification fans out to descendant owners:

| Timing | Message |
|---|---|
| T-30d (ancestor enters pending_close) | "Reality <A> is scheduled for closure on YYYY-MM-DD. Your reality <D> will have its ancestry severed — events before that date will become unreadable. Current state is preserved. [Export event log] [View lore summary]" |
| T-7d | Reminder |
| T-1d | Final reminder |
| T=0 (ancestor reaches `frozen`, severance fires) | In-world narrative event in D: "The Old Age has passed beyond memory..." |

Owners cannot prevent (ancestor owner's right). They can export/document anything they want to preserve externally.

### 12M.6 Narrative framing — in-world event

The `reality.ancestry_severed` event is **user-visible** via DF5 session stream. Example narrator copy (configurable, localized):

- Short: "The Old Age has passed beyond memory."
- Poetic: "A profound quiet settles over the world. Ancient memories, once whispered among the oldest, fade into myth. What came before... is no longer known."
- Technical mode (admin/debug): "Reality <R_id> severed from ancestor <A_id> at event <E_id>."

Session LLM can elaborate: NPCs may react ("something feels different... like a dream I can't recall"), historian NPCs lose references, artifacts become mysterious.

### 12M.7 Discovery UI — ancestry fragment trail

Reality's "lore page" shows severance history:

```
The history of this world:
  🌀 The First Age    — severed 2028-03-15
  🌀 The Forgotten Era — severed 2030-01-10
  ⏳ The Current Age  — ongoing since 2030-01-10
```

Each entry has `narrative_name` (author-authored or LLM-generated). Clicking shows baseline snapshot fact summary but not event-level history (which is gone).

Reality browser filter: "Show worlds with severed ancestry" for players who want that narrative tone.

### 12M.8 Reversibility

- **During ancestor R9 cooling period** (`pending_close`, T≤30d): ancestor cancel → severance never fires. Safe.
- **After severance fired** (`frozen` state reached, descendants severed): **one-way operation.** Even if ancestor is restored via R9 emergency cancel, descendants remain severed.
  - Rationale: narrative event already broadcast to players. Reversing creates continuity mess. Cheaper to accept severance is final.
- Document as irreversible in DF9/DF11 admin UI.

### 12M.9 Interaction with MV9 auto-rebase

Both mechanisms produce similar technical state (flatten + detach). Difference:
- **MV9 auto-rebase**: triggers at fork depth > 5; creates new reality_id; no narrative framing; silent
- **12M severance**: triggers at ancestor close; preserves reality_id; narrative event + UX; gameplay layer

MV9 is a pure ops mechanism; §12M is a product mechanism. Both coexist. If a reality hits MV9 rebase first, its ancestry_fragment_trail gets `severance_reason='auto_rebase'` entry.

### 12M.10 Config

```
reality.severance.auto_trigger_on_ancestor_freeze = true
reality.severance.notification_advance_days = 30
reality.severance.narrative_event_enabled = true
reality.severance.baseline_snapshot_required = true   # hard invariant
reality.severance.narrative_text_mode = "poetic"      # 'short' | 'poetic' | 'technical'
```

### 12M.11 Implementation ordering

- **V1 launch**: L1 trigger mechanism + L2 schema + L3 baseline snapshot on severance + L4 cascade-read-with-severance logic + L7 minimal ancestry_fragment_trail
- **V1 + 30 days**: L5 player notification + L6 narrative event + UX
- **V2+**: Discovery UI (L7), filter in reality browser, lore page polish
- **V3+**: **DF14 Vanish Reality Mystery System** — pre-severance breadcrumb generation (see DF14)

### 12M.12 What this resolves

- **C1 cascade read into dropped ancestor**: MITIGATED. Cascade stops at severance.
- **R9 ancestor close blocked by descendants**: RESOLVED. Severance unblocks.
- **Cascade depth unbounded over time**: BOUNDED. Every severance truncates.
- **Simplifies M5 fork-depth concerns** (§12 previous): natural upper bound via severance lifecycle.

Gameplay bonus: "ancient worlds" become narratively richer. Mysteries naturally emerge (see DF14).

