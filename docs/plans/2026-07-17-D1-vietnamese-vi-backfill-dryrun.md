# D-1 · `Vietnamese` → `vi` backfill — DRY-RUN (PO-gated, NOT executed)

> Spec: [29_translation_repair.md](../specs/2026-07-01-writing-studio/29_translation_repair.md) §D12,
> tracked as `D-TRANSL-LANG-BACKFILL`. Run against the live `loreweave_translation` DB
> (`infra-postgres-1`) on 2026-07-17, read-only. **Nothing was written.** The write-side is now
> closed (C1, commit 5edd3a06f): no NEW `Vietnamese` can enter the store, so this set is frozen and
> will not grow.

## Scope — the only non-canonical value is `Vietnamese`

| table | `Vietnamese` rows | (all other values already canonical: en/vi/ja/ko) |
|---|---|---|
| `chapter_translations` | **5** (across 4 chapters) | |
| `active_chapter_translation_versions` | **1** | |
| `translation_chapter_memos` | **1** | |

Total 7 rows, 4 chapters, 1 book (`019eeb09-…` = Dracula).

## Collision analysis (D12) — 3 clean renames + 1 genuine collision

**`chapter_translations`** — `UNIQUE(chapter_id, target_language, version_num)`:

| chapter | Vietnamese version_nums | existing `vi` version_nums | verdict |
|---|---|---|---|
| `019eeb0e-d4fa-…` (Dracula ch.1) | 1, 2 | 1 | **COLLISION** — `Vietnamese v1` clashes with `vi v1`. Needs renumbering. |
| `019eee8d-08dc-…` | 1 | — | clean rename |
| `019eee8d-08fb-…` | 1 | — | clean rename |
| `019eee8d-0911-…` | 1 | — | clean rename |

**`active_chapter_translation_versions`** — `PK(chapter_id, target_language)`:
- `019eeb0e-d4fa-…` has an active version in **both** `Vietnamese` and `vi` → **COLLISION** (two rows collapse to one PK — must choose the winner).

**`translation_chapter_memos`** — `PK(book_id, chapter_index, target_language)`:
- book `019eeb09-…`, chapter_index 0 has a memo in **both** → **COLLISION** (choose the winner).

## 🔴 The PO decision this dry-run STOPS for (the "which-version-wins" rule)

Only chapter `019eeb0e-d4fa-…` (Dracula ch.1) collides. Three coupled choices:

1. **Version renumbering.** `Vietnamese` v1, v2 must be renumbered above the existing `vi` v1.
   Proposal: append in `created_at` order → `Vietnamese v1 → vi v2`, `Vietnamese v2 → vi v3`.
   *(Alternative: interleave by created_at across both languages. Simpler = append.)*
2. **Active version winner.** Both `Vietnamese` and `vi` currently have an active version for this
   chapter. After merge only one `vi` active may exist. Proposal: **keep the most-recently-created
   of the two as active**; the other becomes a non-active version in the merged history.
3. **Memo winner** (book `019eeb09-…` idx 0). Proposal: **keep the `vi` memo** (the canonical one),
   drop the `Vietnamese` memo — memos are regenerable and the `vi` one reflects the current code path.

The 3 clean-rename chapters need no decision — a plain `UPDATE … SET target_language='vi'`.

## Proposed migration shape (for review — NOT run)

```sql
BEGIN;
-- assert the frozen scope before touching anything
DO $$ BEGIN
  IF (SELECT count(*) FROM chapter_translations WHERE target_language='Vietnamese') <> 5
     OR (SELECT count(*) FROM active_chapter_translation_versions WHERE target_language='Vietnamese') <> 1
     OR (SELECT count(*) FROM translation_chapter_memos WHERE target_language='Vietnamese') <> 1
  THEN RAISE EXCEPTION 'D-1 scope changed since dry-run — re-run the dry-run first'; END IF;
END $$;

-- 1) the 3 clean chapters: plain rename
UPDATE chapter_translations SET target_language='vi'
 WHERE target_language='Vietnamese'
   AND chapter_id IN ('019eee8d-08dc-…','019eee8d-08fb-…','019eee8d-0911-…');

-- 2) the collision chapter 019eeb0e-…: renumber THEN rename (order = PO decision #1)
--    e.g. shift Vietnamese v1→v2, v2→v3 (append after vi v1), then set target_language='vi'
--    …exact UPDATEs written once the PO fixes the rule…

-- 3) active-version winner (PO decision #2): delete the losing active row, rename the winner to vi
-- 4) memo winner (PO decision #3): delete the Vietnamese memo (keep vi)

-- post-assert: zero Vietnamese left, no PK/UNIQUE violation (implicit — the tx would have failed)
DO $$ BEGIN
  IF (SELECT count(*) FROM chapter_translations WHERE target_language='Vietnamese') <> 0
  THEN RAISE EXCEPTION 'residual Vietnamese rows'; END IF;
END $$;
COMMIT;  -- (dry-run: ROLLBACK)
```

**Rollback:** the whole migration runs in one transaction; a snapshot of the 7 affected rows
(`\copy (SELECT * FROM … WHERE target_language='Vietnamese') TO …`) is taken first so the
pre-state can be restored even after COMMIT. Because the set is tiny (7 rows) and frozen, the
snapshot is the rollback.

## Status — EXECUTED 2026-07-17 (PO ruled: append + newest + keep-vi)

The PO approved decisions #1–#3 as proposed. Snapshot of the 7 rows taken first (rollback
safety), then the migration ran as ONE transaction with pre/post asserts:

```
BEGIN → DO(pre-assert 5/1/1) → UPDATE 3 (clean renames) → UPDATE 1 (Vn v2→vi v3) →
UPDATE 1 (Vn v1→vi v2) → DELETE 1 (old vi active) → UPDATE 1 (Vn active→vi) →
DELETE 1 (Vn memo) → DO(post-assert: 0 Vietnamese, 3 vi, active=019f0a1a) → COMMIT
```

**Verified end state:**
- `Vietnamese` rows remaining across all 3 tables: **0**.
- Collision chapter `019eeb0e` vi history: v1 completed (non-active), **v2 completed (ACTIVE)**,
  v3 failed (non-active) — the newest active (Vietnamese v1 = `019f0a1a`) won, appended after the
  existing `vi v1`.

`D-TRANSL-LANG-BACKFILL` is CLEARED. The write-side (C1) keeps the set from ever growing again.
