# 32a · Arc Inspector — structural addendum (the 2 pulled-in defer rows)

> **Status:** S2 detail design, 2026-07-16. Amends [`32_arc_inspector.md`](32_arc_inspector.md).
> **Why this exists:** spec 32 DEFERRED two structural questions (its §11 OQ-2, OQ-8) as gate-#2 work.
> The PO (2026-07-16) pulled them INTO S2 — *no defer* (`D-S2-NO-DEFER`). Deferred = undesigned, so this
> doc is their detail design. Build them WITH B1 (arc-inspector), because both are the honest backing of
> panels the inspector renders (the cascade editor; the Danger/archive zone).
> **Source of truth = code.** Every line/shape below was read from HEAD 2026-07-16, not from a doc note.

---

## A · `D-ARC-TRACKS-ROSTER-SCHEMA` — close the free-blob at both doors

### A.1 The defect (verified)
`tracks`/`roster` are `list[dict[str, Any]]` and `roster_bindings` is `dict[str, Any]` at **every**
door — REST `ArcCreate`/`NodePatch` ([`arc.py:339-341,351-353`](../../../services/composition-service/app/routers/arc.py#L339)),
the MCP arg models ([`server.py` arc create/update]), and the model
([`models.py:232-234`](../../../services/composition-service/app/db/models.py#L232)). The cascade merge
`_merge_by` keys on `it.get(key_field, id(it))`
([`structure.py:639`](../../../services/composition-service/app/db/repositories/structure.py#L639)):
- a **missing** `key` ⇒ the entry falls back to `id(it)` (a Python object id) ⇒ it can **never** be
  shadowed or overridden — permanent un-editable cascade garbage;
- an **empty-string** `key` ⇒ every empty-keyed entry across the whole ancestor chain collides on `""`
  and the leaf silently eats the root's.

Neither door validates it. AI-3 in spec 32 makes the *panel* refuse it — this addendum makes the
*server* refuse it, so the **agent** (which writes the same blobs) cannot corrupt the cascade either.

### A.2 The schema (shapes read from `models.py` comments + `_merge_by`/`resolve_*` usage)
Add typed entry models; the key rule is the load-bearing part.

```python
# arc.py — shared by ArcCreate + ArcPatch; MIRROR into the MCP arg models (server.py)
class ArcTrack(BaseModel):
    model_config = ConfigDict(extra="allow")   # ⬅ ALLOW, not forbid — see note
    key: str = Field(min_length=1)             # required, non-empty — the ONLY hard rule (the shadow key)
    label: str = ""

class ArcRosterSlot(BaseModel):
    model_config = ConfigDict(extra="allow")
    key: str = Field(min_length=1)             # the shadow key (resolve_roster merges on it)
    actant: str | None = None
    label: str | None = None
    constraints: list[str] = Field(default_factory=list)   # shape only — vocabulary stays OPEN (v1)

# tracks: list[ArcTrack] | None ; roster: list[ArcRosterSlot] | None
# roster_bindings unchanged: dict[str, Any] | None  (role_key -> glossary_entity_id)
```

🔴 **`extra="allow"`, NOT `extra="forbid"` — the bug is the KEY, nothing else.** The corruption `_merge_by`
suffers is a **missing/empty/duplicate `key`**; every other field is read leniently by the packer and is
harmless. `forbid` would 422 an agent write carrying a richer object (or a future field), and `ignore`
would silently DROP those fields on `model_dump` (data loss on a round-trip edit). `allow` validates the
one invariant and preserves the rest — non-destructive on re-save of any legacy row whose only sin was a
bad key. We also do NOT cap `label`/`actant` length, for the same re-save-safety reason.

**Unique-key validator** (both lists, both doors) — a `field_validator` that rejects a duplicate `key`
within one node's own list (across-chain shadowing is *intended*; within-node duplicates are the
corruption): **422 `ARC_ENTRY_KEY_DUPLICATE`** with the offending key named.

**`constraints[]` — shape, not vocabulary.** Spec-32 OQ-2 flagged the vocabulary as "unsettled." We do
NOT settle it here: `list[str]` fixes the *shape* (no more `Any`) while leaving the *values* free. A
future vocab spec tightens the enum; this addendum does not block on it.

### A.3 The migration audit (the reason OQ-2 was gate-#2 — handled, non-destructively)
Tightening a write schema can reject writes the **agent already made** into existing rows. So:
- **Read scan first (dry-run, no write):** count `structure_node` rows whose `tracks`/`roster` contain
  an entry with a missing/empty `key`, or a within-node duplicate. **DONE 2026-07-16 — dev DB result:
  `4 nodes, 0 bad/empty/dup keys`. Nothing to repair.**
- **Repair = ALWAYS non-destructive, NEVER a drop** (so the PO-STOP-on-drop default can never fire):
  for a missing/empty `key`, synthesize a **positional** `key = "<track|role>_<ord>"` (stable,
  unique-in-node, editable) rather than dropping the entry; for a genuine within-node duplicate, suffix
  `_2`, `_3`. No entry is ever lost. (Positional over `slug(label)`: robust, always available, and these
  garbage entries were un-shadowable anyway — a stable key is the whole win.)
- **Delivered as an ON-DEMAND idempotent script**, `app/db/repairs/arc_entry_keys.py` (a pure
  `repair_entries()` + a `--scan`/`--apply` CLI), **NOT a boot-time migration**: reads already tolerate
  legacy garbage (`_merge_by`), the write-doors now prevent new garbage, and a heavy JSONB backfill on
  every service boot would be waste for a case that is empty today. Ops runs it once if a real deployment
  ever scans dirty. The pure function is unit-tested (garbage→valid, idempotent).
- Validation is live at both doors now; a legacy garbage row still **reads**, and the only edit it would
  block (a re-save) is unblocked by running the script — which on the current DB has nothing to do.

### A.4 Files
`arc.py` (models + validator) · `server.py` (mirror the models — **3-schema-source FastMCP caveat**:
docstring + arg model + any inline schema) · a data migration (`db/migrate.py` + a one-shot repair
script) · tests: within-node duplicate → 422 both doors; missing/empty key → 422 both doors; a legacy
row with garbage still **reads** (via `_merge_by`) but a re-save is rejected until repaired; the repair
migration backfills a slug and reports drops. Regenerate the MCP contract if the tool schema is asserted.

---

## B · `D-ARC-ARCHIVE-CHAPTER-STRANDING` — archive returns chapters to the pool; restore puts them back

### B.1 The defect (verified)
`archive()` ([`structure.py:448`](../../../services/composition-service/app/db/repositories/structure.py#L448))
flips `is_archived` on the `structure_node` **subtree only**. It never touches
`outline_node.structure_node_id`. `?unassigned=true` is `structure_node_id IS NULL`
([`plan-hub/api.ts:35`](../../../frontend/src/features/plan-hub/api.ts#L35)). So an archived arc's member
chapters sit in **neither** the (archived) arc lane **nor** the unassigned tray — invisible, unreachable.
Spec 32 §3.4 shipped the *honest-message* stopgap ("18 chapters stay bound; unassign first"); the PO
pulled in the real fix.

### B.2 The fix — record-and-reattach (symmetric, race-safe)
The concern OQ-8 named is *"restore could not put them back."* Solve it by recording the severed binding.

- **Migration:** `ALTER TABLE outline_node ADD COLUMN archived_from_structure_node_id UUID NULL;`
  (nullable, no default, no backfill needed — a fresh recovery slot).
- **`archive()` — one extra UPDATE in the SAME path, over the archived subtree's members:**
  ```sql
  UPDATE outline_node
     SET archived_from_structure_node_id = structure_node_id,
         structure_node_id = NULL, updated_at = now()
   WHERE structure_node_id IN (SELECT id FROM subtree)   -- the arcs just archived
     AND kind = 'chapter' AND NOT is_archived
     AND structure_node_id IS NOT NULL;
  ```
  ⇒ the chapters return to the unassigned pool immediately (visible, re-assignable), and the arc remembers
  which chapters were its own.
- **`restore()` — the inverse, over the restored subtree, GUARDED:**
  ```sql
  UPDATE outline_node
     SET structure_node_id = archived_from_structure_node_id,
         archived_from_structure_node_id = NULL, updated_at = now()
   WHERE archived_from_structure_node_id IN (SELECT id FROM <restored subtree>)
     AND structure_node_id IS NULL;   -- ⬅ race guard: do NOT clobber a chapter the user
                                       --    manually re-assigned to another arc while archived
  ```
  A chapter re-homed while the arc was archived keeps its new home (its `archived_from_*` is cleared only
  when reattached; a manual re-assign via BE-A3 must also clear it — see B.3).

### B.3 Interplay with BE-A3 (unassign) — one recovery slot, kept clean
BE-A3 lets a chapter be assigned to `NULL` (manual unassign) or to another arc. Either manual re-home
must **clear `archived_from_structure_node_id`** so a later restore of the old arc does not yank the
chapter back. ⇒ `assign_chapters` sets `archived_from_structure_node_id = NULL` whenever it writes
`structure_node_id` (both the assign and the unassign branch). One line; keeps the recovery slot honest.

### B.4 The confirm copy is now TRUE
Spec 32 §3.4's archive confirm changes from *"18 chapters stay bound to the archived arc; unassign them
first"* to *"Archiving returns its 18 chapters to the unplanned tray; restoring the arc re-attaches
them."* The blast-radius sub-arc count stays client-derived (§3.4). The panel proves the reattach by
effect (restore → the chapters reappear under the arc), not by trusting a response.

### B.5 Files
`db/migrate.py` (the column) · `structure.py` (`archive`/`restore`/`assign_chapters` — 3 SQL edits) ·
`arc.py` (the archive-confirm copy is FE; the DELETE route is unchanged) · tests: archive an arc → its
chapters are `structure_node_id IS NULL` AND carry `archived_from_*`; restore → reattached; a chapter
manually re-assigned while archived is NOT clobbered by restore; archiving a saga cascades the return
across all sub-arcs' members; the recovery slot is cleared on every manual re-home.

---

## C · Sequencing inside B1
`D-ARC-ARCHIVE-CHAPTER-STRANDING` **depends on BE-A3** (it reuses the unassign primitive's null-write
path) → build **BE-A3 first**, then B. `D-ARC-TRACKS-ROSTER-SCHEMA` is independent (do it with BE-A2, the
other write-door tightening). Both migrations run before their door-validation goes live. All of it is
composition-service; the FE arc-inspector (spec 32 §6) consumes the results. One cross-service
live-smoke at B1 close covers the lot.

## D · Compliance
- **Tenancy:** unchanged — both operate on rows already grant-gated by `_gate_arc` (book-derived-from-row).
- **No silent success:** the migration reports every repaired/dropped entry; the archive reattach is
  proven by effect; the `assigned`-count discipline (spec 34 AT-6) is mirrored where counts are returned.
- **Reversibility:** archive/restore stay inverses (the whole point of B); the schema migration is
  report-backed and hand-revertible.
- **New deferred rows raised:** NONE (the `constraints[]` vocabulary is left OPEN by shape, not deferred
  as a tracked row — a future vocab spec tightens it if a consumer appears).
