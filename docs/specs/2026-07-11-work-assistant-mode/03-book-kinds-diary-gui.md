# 03 · Book Kinds & the Diary GUI — detailed design

**Date:** 2026-07-11 · **Phase:** P1 · **Status:** DESIGN · Implements **D10, D14, D16**.
UI drafts: `design-drafts/work-assistant/diary/`. Register: [`RED-TEAM-2026-07-11.md`](RED-TEAM-2026-07-11.md).

---

## Q1. What is `books.kind` and why is it load-bearing?

A first-class book type — `novel` (default) · `document` · `lore` · `diary` — generalizing the one-off
`is_bible` flag. **It is not cosmetic: `kind='diary'` is the privacy lock.** Every egress guard in
[`09`](09-settings-consent-privacy.md) keys on it, so if `kind` can be changed or missed, the lock opens.

```sql
ALTER TABLE books ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'novel'
  CHECK (kind IN ('novel','document','lore','diary'));
UPDATE books SET kind='lore' WHERE is_bible = true;   -- DEFAULT does NOT revisit existing rows
```

`is_bible` **stays** as the orthogonal hidden-from-counts flag (there is also a `chapters.is_bible` — the
`kind` backfill touches **books only**; do not invent a chapter kind).

## Q2. How is immutability *enforced*? (Not by convention — T29)

The only "enforcement" today would be a convention that nobody adds `kind` to the two dynamic UPDATE
allowlists (`patchBook` server.go:912; MCP `book_update` mcp_tools_write.go:201). That is not a lock.

→ **A DB `BEFORE UPDATE` trigger** raising on `NEW.kind <> OLD.kind` (migrate.go already uses the
`DO $$ … EXCEPTION` idiom). Structural, survives future contributors. Leaving `diary` is **forbidden**
(it would strip the privacy lock); to get a different kind, create a new book.

## Q3. Every book-create path must set `kind` (T30)

**Four** paths, and the world-bible one is the trap:

| Path | Today | Fix |
|---|---|---|
| REST `createBook` (server.go:634) | no `kind` → `'novel'` ✅ correct | — |
| MCP `book_create` (mcp_tools_write.go:100) | no `kind` → `'novel'` ✅ correct | — |
| **World-bible `createWorldCore` (mcp_worlds.go:48)** | inserts `is_bible=true`, **no `kind`** → `'novel'` ❌ | **set `kind='lore'` in the same commit as the backfill** — otherwise pre-migration bibles are `lore` and post-migration ones are `novel` |
| **Diary provisioning** (new) | — | server-set `kind='diary'`; the only writer |

Hygiene test: assert every `INSERT INTO books` sets `kind` explicitly (the "one name for one concept" drift class).

## Q4. What does the diary GUI reuse, and what changes? (D14)

**Reuse the existing book workspace (`/books/:id`), entries list, and chapter editor** — kind-branched. No new
book route. The assistant *chat* is `/assistant`; the diary *book* is browsed through the reused GUI.

| Feature | `novel` | `diary` |
|---|---|---|
| Public sharing / grants | allowed | **hard-blocked** (D10) |
| **Wiki tab / "Generate wiki" / enrichment** | allowed | **hard-blocked** ([`09`](09-settings-consent-privacy.md) §Q3) |
| Chapter "Publish" button | shown | **absent — no publish concept** (D15) |
| KG-extraction trigger | `chapter.published` | **"Keep entry" → `chapter.kg_indexed`** |
| Vocabulary | "Chapter" | **"Entry"** (i18n label by kind) |
| **Library grid / catalog / stats** | listed | **hidden** (D16 — T27: otherwise it sits next to the novels, and appears when the user screen-shares in a meeting) |
| `kind` mutability | immutable | **immutable + un-convertible** |
| Export of own data | allowed | allowed (owner only) |

## Q5. The "Keep entry" action

The diary's flavor of the general **"index / add to knowledge"** action
([publish-independent-kg-indexing](../2026-07-11-publish-independent-kg-indexing.md)):

1. Sets `chapters.diary_kept_at` — an **orthogonal column**, *not* a third `editorial_status` value (which
   would break the reparse sweeper's `editorial_status='published'` gate and contradict "no publish").
2. Sets `kg_indexed_revision_id` → emits **`chapter.kg_indexed`**.
3. Facts divert to the pending-facts inbox (D4).

**Un-keeping** an entry must **retract** (D17/§3.8 of the prereq spec) — `kg_exclude` clears the pointer and
purges the derived facts. A toggle that only stops *future* indexing is a lie.

## Q6. Mobile (PUX-6)

The diary book workspace + editor are the phone's daily surfaces, and the existing writer surfaces are
desktop/dockview-shaped. A **mobile pass on the reused GUI for `kind='diary'`** is real P1/P2 FE work — see
[`13`](13-frontend-shell-mobile.md).

## Q7. Acceptance

- Consumed-by-effect test **per egress path** (grants · sharing PATCH · wiki settings PATCH · generateWikiStubs
  · enrichment · checkWikiPublic · public-MCP · library list · notifications).
- `kind` immutability: an UPDATE attempt **raises at the DB**.
- World-bible created **after** the migration has `kind='lore'`.
- Jargon check: the diary UI never says chapter/publish/entity/kind (S06 rule).
- Mobile viewport: browse entries → open → keep, on a phone.
