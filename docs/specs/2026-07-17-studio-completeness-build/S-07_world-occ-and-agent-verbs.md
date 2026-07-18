# S-07 · world-maps OCC consistency + missing agent verbs

> **Tier B — backend-only (no draft).** Three narrow book-service gaps the world/book audit surfaced. None
> need UI; all are consistency/parity fixes over shipped engines. **Service:** book-service (Go).

## 1. world_maps OCC is enforced on REST but bypassed on MCP + image upload

**Verified:** `patchMapREST` gates on `AND version = $expected` (`worlds_maps_write_rest.go:135`, 412 on
mismatch), but `world_map_update` (`mcp_maps.go:521`) and the image upload (`maps_image.go:124`) **bump
`version` without the `AND version = $expected` predicate** → blind last-write-wins. An agent rename or an
image repoint silently clobbers a concurrent human rename the human's own PATCH would have 412'd.

**Fix:** thread the OCC predicate through both write paths. The MCP tool takes an optional `expected_version`
(when the agent read a version, it must pass it; the tool 412s on mismatch like REST). The image upload is
trickier — it is not a semantic edit of the name, so **scope its version bump to the image columns only** (or
use a separate `image_version`) so uploading an image does not race a rename at all. **Decision:** give the
map an `image_version` distinct from the metadata `version`; the image upload bumps `image_version`, never
the metadata `version` — the two concerns stop colliding. Records the reasoning so this isn't re-litigated.

## 2. No MCP `world_update` / `world_delete`

**Verified:** `mcp_worlds.go:294` registers only list/get/create/move; REST UPDATE/DELETE already exist
(`worlds.go:293`, `:319`). An agent that creates a mis-named world can't rename or clean it up, and the
file's own "reversible" claim is unbacked.

**Fix:** add `world_update` + `world_delete` MCP tools wrapping the existing REST handlers/store methods.
Grant-gated identically (the tool resolves the same `owner_user_id` scope). Thin wrappers, no new logic.

## 3. No MCP chapter-reorder tool

**Verified:** reorder is REST-only (`POST /chapters/reorder`); an agent driving the manuscript can
create/delete/save chapters but not reorder them.

**Fix:** `book_chapter_reorder` MCP tool wrapping the existing two-phase `reorderChapters` engine. Body =
ordered chapter ids for the book; same grant + book-scope. (This pairs with the S-02 `book_chapter_set_part`
tool — together they give the agent full manuscript-structure parity with the human.)

## 4. Tests
- OCC: an MCP `world_map_update` with a stale `expected_version` → 412 (matches REST); an image upload does
  NOT 412 a concurrent rename (separate `image_version`) and does not clobber the name.
- world verbs: `world_update`/`world_delete` round-trip, grant-gated, owner-scoped; a non-owner is refused.
- reorder: `book_chapter_reorder` respects `UNIQUE(book_id, sort_order)` with no transient collision; the
  flat order matches what the REST route produces.

## 5. Out of scope
- Marker/region last-write-wins (vs the map's OCC) is a documented, conscious choice — not touched here.
