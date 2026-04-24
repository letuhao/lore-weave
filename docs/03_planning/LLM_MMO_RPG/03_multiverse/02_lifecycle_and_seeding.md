<!-- CHUNK-META
source: 03_MULTIVERSE_MODEL.ARCHIVED.md
chunk: 02_lifecycle_and_seeding.md
byte_range: 10619-13379
sha256: 8d47276f2298c29e4f373b79ea7c249627c15f2e256f37468be68bd3f3ba5047
generated_by: scripts/chunk_doc.py
-->

## 4. Reality lifecycle

```
              ┌─────────────┐
              │  CREATED    │  metadata only, no events yet
              └──────┬──────┘
                     │ seed initial state
                     ▼
              ┌─────────────┐
              │  ACTIVE     │  players join, events happen
              └──────┬──────┘
                     │
           ┌─────────┼─────────┐
           ▼         ▼         ▼
      ┌──────┐  ┌──────┐  ┌──────────┐
      │FROZEN│  │FORKED│  │  CLOSED  │
      │(maint│  │(child│  │ (archived│
      │ ro)  │  │exists│  │   , DB   │
      │      │  │paren)│  │  dropped)│
      └──┬───┘  └──────┘  └──────────┘
         │        │
         └───►back to ACTIVE (thaw)
```

- **Created** — metadata row exists, seed process pending
- **Active** — live, accepting writes
- **Frozen** — no new writes, reads OK (maintenance, projection rebuild, admin review)
- **Forked** — normal state; existence of a child fork doesn't change parent's status (parent keeps running)
- **Closed** — events + snapshots archived to MinIO, DB dropped, registry row retained for audit

## 5. Seeding modes

When creating a reality, the creator specifies **where it starts**:

### 5.1 From book — fresh universe

```sql
INSERT INTO reality_registry (
  reality_id, book_id, seeded_from, parent_reality_id, fork_point_event_id, ...
) VALUES (
  'uuid', 'book-uuid', 'book', NULL, NULL, ...
);
```

- Starts from book's initial state (L1 + L2 canon)
- No L3 history yet — a blank page
- Entry point for players who want "start from the beginning"

### 5.2 From another reality — snapshot fork

```sql
INSERT INTO reality_registry (
  reality_id, book_id, seeded_from, parent_reality_id, fork_point_event_id, ...
) VALUES (
  'uuid-child', 'book-uuid', 'reality', 'uuid-parent', 12345, ...
);
```

- Inherits parent's event chain up to `fork_point_event_id` (event_id 12345)
- Cascades through ancestors recursively
- After fork point, parent and child are independent
- Entry point for "what-if" branches, capacity overflow splits, private sessions

### 5.3 Seeding is permanent

Once created, a reality's seeding mode + fork point are immutable. They define "what history do I inherit." Changing them later would invalidate every projection. If a different seed is wanted, create a different reality.

