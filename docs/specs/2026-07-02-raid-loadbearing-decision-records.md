# RAID load-bearing items — Decision Records (autonomous run)

**Purpose:** the user-mandated autonomous run builds the load-bearing RAID items
(C1 steering, C2 HITL, C6 checkpoints, Wave D dial) without a human POST-REVIEW in
the loop. Each gets a Decision Record here — schema, scope keys, who-writes-what,
reversibility — so the human can veto/redirect *after the fact* without archaeology.
Everything is additive + flag-safe; nothing rewrites an existing contract.

---

## DR-C1 — Steering store (07S §1a) · 2026-07-02

**What:** per-book author-written rules (story-bible-as-steering; the Cursor-rules /
Kiro-steering analog) rendered into every matching chat turn as the `steering` bucket.

**Owner service: book-service.** Steering is *authored book content* whose write
authority is exactly the book grant model — and book-service IS the E0 grant
authority (`getBookAccess` is the single resolver every service calls). Placing the
table next to the authority avoids a second tenancy implementation. (Considered:
chat-service — wrong owner, it consumes; knowledge-service — steering is authored
SSOT, not derived knowledge; glossary — lore entities, not authoring rules.)

**Schema (tenancy per CLAUDE.md checklist):**
```sql
CREATE TABLE book_steering (
  id              UUID PK DEFAULT uuidv7(),
  book_id         UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,  -- scope key
  name            TEXT NOT NULL,            -- slug-ish, #name manual trigger
  body            TEXT NOT NULL,            -- CHECK char cap 8000 (taxed every turn)
  inclusion_mode  TEXT NOT NULL DEFAULT 'always'
      CHECK (inclusion_mode IN ('always','scene_match','manual','auto')),
  match_pattern   TEXT,                     -- scene_match: case-insensitive substring/regex vs active chapter/scene title
  enabled         BOOLEAN NOT NULL DEFAULT true,
  author_user_id  UUID NOT NULL,            -- who wrote it (audit)
  created_at/updated_at TIMESTAMPTZ,
  UNIQUE (book_id, name)                    -- scoped unique — NEVER UNIQUE(name)
);
```
- **Write tier:** book owner + E0 EDIT grantees (edge #13: an edit-collaborator CAN
  author steering — same tier as editing chapters; a VIEW grantee cannot).
- **Read tier:** VIEW grant (steering renders into any collaborator's chat on that book).
- **Row caps:** ≤ 20 entries/book (soft, 422 over), body ≤ 8000 chars — steering is
  taxed every turn; keep tight (07S §1).

**Render path (chat-service):** on a book-scoped turn, fetch via internal
`GET /internal/books/{book_id}/steering` (book-service; internal token), select:
`always` ∪ (`manual` whose `#name` appears in the user message) ∪ (`scene_match`
whose pattern matches the active chapter/scene title from editor_context). Rendered
as a `<steering>` system part right after the system prompt (pinned — never compacted,
per compaction's pinned rule). Soft cap: if the selected set estimates > 2000 tokens,
log + truncate lowest-priority (manual < scene_match < always keeps).
**v1 honesty:** `auto` mode (model pulls by name) is NOT yet model-driven — v1 treats
`auto` as `manual` (trigger by #name only); the pull-tool is a follow-up. Documented
in the API description so authors aren't misled.

**Reversibility:** additive table + one fetch/render block in chat-service guarded by
"book-scoped session AND fetch succeeded" (failure → skip, turn unaffected). Dropping
the feature = dropping the render block; no data migration risk.

**FE:** deferred ONE step (a steering editor panel touches the dock catalog, which the
concurrent dockable-migration track owns right now — collision risk). The REST API is
the contract the panel will consume; tracked as `D-RAID-C1-FE-PANEL`.
