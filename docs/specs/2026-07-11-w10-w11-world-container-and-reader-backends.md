# W10 World-Container + W11 Reader/Lore-Seeker — Track B backend design

**Status:** BUILT (2026-07-15). W10 maps — 8 `world_map_*` MCP tools + 3 tables + MinIO base image + the `/v1/worlds/{id}/maps` read REST + the FE canvas (WorldMapsSection), all browser-proven by effect. W11 reader — the ask-the-lore facade (resolve-to-owner, `before_chapter_id` server-enforced cutoff, fail-closed, canon-only `status='active'` leak-guard), the `story_search` `before_chapter_id` cutoff, and the FE lore-seeker (spoiler-windowed, fail-closed on both facts AND the entity list) — browser-proven. Design below is retained as the build record.
**Track:** B (domain backend). Unblocks Track C's W10/W11 surfaces (`TRACK-C.md` "Consumes: B's backing tools for W2/W4/W10/W11").
**Date:** 2026-07-11 · **Branch:** `feat/context-budget-law`
**Supersedes framing:** the board called W10/W11 "P2, structurally large, biggest structural gap." Grounded research (2026-07-11, three parallel探査 agents) shows both are **largely wiring over substrates that already exist** — plus exactly two genuinely-greenfield pieces (W10 maps; W11 public lore access).

---

## 0. What the research changed

| Assumption (board) | Reality (code, anchored) |
|---|---|
| W10 world container is greenfield | **Substrate already built** — `creation-unblock` C20/C21/C22/C28. book-service `worlds` table, hidden bible-book + `sort_order 0` bible chapter, `knowledge_projects.world_id`, `world_rollup.py`, read-only `kg_world_query`, and a full FE `world/` feature. |
| W11 needs a spoiler engine | **Spoiler engine already exists + battle-tested** — `knowledge-service/app/spoiler_window.py:31` `resolve_before_order`, `before_chapter_id`/`as_of_chapter` params across `entities.py`/`timeline.py`/`graph_views.py`, glossary `before_chapter_index` (`canon_at_chapter_handler.go:36`), two-axis `composition-service/app/packer/spoiler.py`. Reveal-chapter signal exists (`MIN(chapter_entity_links.chapter_index)`, KG `event_order`). Reading position is **stored** (`book-service reading_progress`, `migrate.go:179`). |

**Net remaining scope:** W10 = a world-scoped MCP **write** surface + graph authoring + a **new map primitive**. W11 = a reading-position→cutoff **resolver** + a **reader-scoped ask-the-lore facade** (cutoff server-enforced) + a **RAG cutoff** + **KG-auth unification onto grants** + a **new public/anonymous lore route**.

**Services touched (scope-accuracy note, review-impl 2026-07-11).** TRACK-B.md's "Owns" list names glossary-service, knowledge-service, and chat-service — **not book-service**. But `worlds`, the bible-book/chapter substrate, `reading_progress`, MinIO image storage, and the world MCP write surface all live in **book-service**, so W10/W11 unavoidably extend it (world tools §3.1, reading-position resolver §4.1, maps §3.3). This is a correct follow-the-data extension of Track B's surface, not scope creep — but the owns-list predates this design, so flag it for Track-C coordination and the build plan. Services in play: **book-service (Go), knowledge-service (Py), glossary-service (Go), sharing-service (Go).**

---

## 1. Locked decisions this design honors / overrides

- **G1 additivity (HONORED).** `OPEN_QUESTIONS_LOCKED.md:16-27` — lore stays `book_id`/`chapter_id`-keyed and *rolls up* to a world via its books; **no `world_id` on existing glossary/knowledge/composition rows.** World-native authoring resolves `world_id → bible_book_id → bible_chapter_id` and writes book-keyed, exactly as the FE does today (`frontend/src/features/world/api.ts:87-116`).
- **"Reader/public product" non-goal (DELIBERATELY OVERRIDDEN — user decision 2026-07-11).** `OPEN_QUESTIONS_LOCKED.md:176-178` listed "reader/lore-seeker product beyond read-only graph/wiki" and "world-level sharing" as non-goals of the earlier cycle. The user has explicitly greenlit the **public/anonymous reader** for W11. This design therefore *retires* that non-goal for W11; recorded here so it stops re-surfacing.
- **New map primitive vs. G1 (SURFACED tension — see §3.3).** G1 forbade retrofitting `world_id` onto *existing* lore to avoid a migration. A world map is world-spanning by nature; a *new* `world_id`-scoped map table is additive (no migration of existing rows) and does not violate G1's letter. This design scopes maps **world-first** and explains the boundary.

---

## 2. Invariants every deliverable must satisfy

- **MCP-first** — all agent-facing capabilities (world create, lore/graph authoring, map authoring, ask-the-lore) are **MCP tools** through ai-gateway, not bespoke HTTP+prompt endpoints. Non-agentic reads (a FE fetching a map) can be plain REST.
- **Provider-gateway** — any LLM/embedding/rerank in the reader "ask" path resolves through `provider-registry-service` (the RAG `raw_search` already does; the answer-composition step, if any, must too).
- **Tenancy / anti-oracle** — every new read/write declares a scope tier + grant check; cross-tenant without a grant returns a **uniform 404/empty** (no existence leak). Spoiler cutoff is **fail-closed** everywhere (unknown position ⇒ nothing passes), mirroring `spoiler_window.py:28`.
- **Tiering** — every new MCP tool declares `_meta.tier` (R/A/W) + `scope`; a `tools/list` gate rejects an untiered tool (Track A precedent, `D-KNOWLEDGE-META-ADOPTION`).

---

## 3. W10 — World-container backend

### 3.1 World-scoped MCP write surface

**Problem.** World CRUD is HTTP/JWT-only today (`book-service/internal/api/worlds.go`); no MCP tool creates a world or authors world lore world-natively. Glossary propose/confirm are `ScopeBook` — an agent must be hand-fed `bible_book_id`. The FE hides this (`world/api.ts`); the agent surface must too.

**Design.** book-service already exposes a full MCP surface — **reads** (`mcp_tools_read.go`) *and* **TierW/TierA writes** (`mcp_actions.go`: `book_chapter_publish`, `book_delete`, `book_set_cover` via `addTool(srv, …, NewToolMeta(TierW, ScopeBook, …))`). [verified review-impl 2026-07-11] So world tools mirror the existing `mcp_actions.go` pattern:

| Tool | Tier · Scope | Behavior |
|---|---|---|
| `world_create(name, description?)` | **A · none** | Runs the existing `createWorld` transaction (`worlds.go:54`): world + hidden bible book (`is_bible`) + `provisionBibleChapter`. Returns `{world_id, bible_book_id, bible_chapter_id}`. |
| `world_list()` / `world_get(world_id)` | **R · none** | Wrap `listWorlds`/`getWorldByID`; returns `book_count`, `bible_book_id`, `bible_chapter_id`. |
| `world_move_book(world_id, book_id)` | **A · book** | Wrap `moveBookIntoWorld` (guards `is_bible=false`). |

**Scope decision (build):** existing book-service MCP tools are `ScopeBook`; a world is not a book. World tools need either a new `ScopeWorld` in the shared `lwmcp` kit (cleaner, but a kit change other services inherit) or `ScopeNone` with an in-handler owner check (`requireWorldOwner`, `worlds.go:353`). Decide at build; `ScopeNone` + explicit owner check is the lower-blast-radius default.

**World-native lore authoring (hide the bible-book mechanic).** Rather than force agents to juggle `bible_book_id`, the design adds a **world-resolution helper** consumed by glossary/knowledge authoring tools: an optional `world_id` arg that resolves to the world's `bible_book_id` (glossary) / world KG project (knowledge) via a book-service internal route, then authors book-keyed per G1. Storage is unchanged; only the tool ergonomics improve.
- New internal route (book-service): `GET /internal/worlds/{world_id}/bible` → `{bible_book_id, bible_chapter_id}` (owner/grant-checked). Analogous to the existing `/internal/worlds/{id}/books` (`server.go:198`).

### 3.2 Graph authoring tools

Most of this shipped in WS-4B (`kg_project_entities_to_nodes`, `kg_propose_edge`, read `kg_world_query`). Two gaps for world graph authoring:
1. **Manual single-node create** — the known W4 blocker ("no manual node tool; `kg_propose_edge` parks edges whose endpoints aren't nodes yet"). Add `kg_create_node(project_id|world_id, name, kind, ...)` (**Tier-A**). *Build-time verify this doesn't already exist* (anti-laziness rule — the earlier "blocked on missing route" items were often already present).
2. **World-native resolution** — graph tools accept `world_id` and resolve to the world KG project (the bible-book project stamped with `world_id`, `knowledge_projects.world_id`, `migrate.py:978`), so an agent authors "the world's graph" without knowing the project id.

### 3.3 Maps — the greenfield spatial primitive (user chose IN scope)

**Not** the LLM_MMO_RPG procedural tile kernel (`crates/world-gen`, `tilemap-service`, `world-service` — a separate game-runtime stack, downstream-only). This is a **worldbuilder's reference map** (World-Anvil/Inkarnate-lite): a base image with placed pins/regions linked to `location` glossary entities.

**Home service: book-service (Go). [REVISED — review-impl 2026-07-11]** The first draft put maps in glossary-service; that was wrong on two counts the review caught: (1) **glossary-service has no MinIO/blob infra** (verified — nor does knowledge-service), so it could not store a map image without new infra, whereas **book-service already has MinIO and an image precedent** (`book_set_cover`, cover art); (2) **G1 forbids `world_id` on glossary** — `world_id` legitimately lives in book-service, which owns the `worlds` table. The original rationale ("keep marker→entity FK intra-service") rested on a false premise: glossary is a **separate database**, so a marker's `entity_id` is a **cross-service soft UUID reference no matter where the map lives** — there is no intra-service FK to preserve. book-service already owns the world container + world_id + image storage, so it is the correct home; the marker→entity reference is soft (optionally validated best-effort via a book-service→glossary internal call at write, never a hard FK).

**Scope: world-first.** A world map spans a world's books, so it carries `world_id` — clean in book-service (where `world_id` already lives; G1-consistent). Markers bridge world↔book: a marker references a glossary `location` entity that is itself book-keyed (in one of the world's books).

**Data model (new, book-service):**
```
world_maps(id, owner_user_id, world_id, name, image_object_key, image_w, image_h,
           created_at, updated_at)              -- image blob in MinIO (book-service already has it)
map_markers(id, map_id, entity_id NULLABLE, label, x REAL, y REAL,   -- x,y ∈ [0,1] relative
            marker_type, created_at)            -- entity_id = SOFT cross-service ref → glossary location entity
map_regions(id, map_id, name, polygon JSONB, entity_id NULLABLE, created_at)  -- polygon overlay (full, per sign-off)
```
Scope key `world_id` + `owner_user_id`; every query filters by both; `world_id` re-checked as the owner's world; grant-gated for collaborators (mirrors `worlds.go requireWorldOwner`).

**MCP tools (book-service — mirror the existing `mcp_actions.go` TierW/TierA write surface, `book_set_cover`/`book_chapter_publish` etc.):**

| Tool | Tier · Scope | Behavior |
|---|---|---|
| `world_map_create(world_id, name, image_ref?)` | **A · none** | Create a map (scope `none`, not `book` — a map is world-, not book-scoped; needs a `ScopeWorld` addition or `ScopeNone`, decide at build). Image via presigned MinIO PUT (reuse the cover-image path). |
| `world_map_add_marker(map_id, label, x, y, entity_id?, marker_type?)` | **A · none** | Place a pin; optionally bind to a `location` entity (soft ref, best-effort existence check). |
| `world_map_add_region(map_id, name, polygon, entity_id?)` | **A · none** | Add a polygon overlay. |
| `world_map_get(map_id)` / `world_map_list(world_id)` | **R · none** | Read markers + regions + presigned image URL. |

**REST (for the FE canvas — Track C):** `POST/GET /v1/worlds/{world_id}/maps`, `.../maps/{map_id}/markers`, image presign route (reuse book-service's cover presign). FE map canvas is Track C.

**Effort flag:** the bulk of W10's new work — new tables + migration, MinIO image handling (reusing the cover path), 4 MCP tools + REST, and (Track C) a canvas. Its own build milestone.

---

## 4. W11 — Reader / lore-seeker backend

### 4.1 Reading-position → cutoff resolver

`reading_progress` stores per-chapter rows (`book-service migrate.go:179`), not a single "furthest-read" pointer, but `getReadingHistory` already joins `chapters.sort_order` (`analytics.go:248`).

**Design (book-service):** `GET /internal/books/{book_id}/reading-position?user_id=` → `{furthest_chapter_id, furthest_sort_order}` = `MAX(ch.sort_order)` over the user's `reading_progress` rows LEFT-JOINed to `chapters` (the `getReadingHistory` join, `analytics.go:251`). Small derivation, no schema change. The reader facade (§4.2) calls it to obtain `before_chapter_id`, then `resolve_before_order` (`spoiler_window.py:31`) turns it into the `before_order` ceiling.
- **Edge (review-impl 2026-07-11):** a read chapter that was later **deleted** LEFT-JOINs to `NULL sort_order`; SQL `MAX` ignores NULLs, so the furthest *surviving* chapter wins — correct. If **every** read chapter is deleted (or the user has no rows), `MAX → NULL → no position →` the facade **fails closed** (nothing passes), consistent with `spoiler_window.py:28`. Both cases need an explicit test — a fresh/empty reader must not accidentally see the whole book.

### 4.2 Reader-scoped ask-the-lore facade (cutoff SERVER-enforced)

**Core security property.** In reader mode the spoiler cutoff must be **injected server-side from the reader's own position — never a tool argument the LLM controls.** An agent must not be able to widen its window by omitting/altering `before_chapter_id`.

**Design (knowledge-service — owns "reader backends", `TRACK-B.md:10`):** a **reader context** that wraps the lore reads so `before_chapter_id` is forced to the reader's furthest position (fail-closed if unresolved). Exposed as MCP tools for the reader's chat agent (MCP-first):

| Tool | Tier | Behavior |
|---|---|---|
| `lore_ask(book_id, question)` | **R** | The composite "ask the lore": resolves reader position → cutoff → spoiler-windowed glossary known-entities + KG facts/timeline + RAG `raw_search`, returns a spoiler-safe evidence bundle for the agent to answer from. |
| `lore_browse_entities(book_id)` / `lore_entity(book_id, entity_id)` | **R** | Windowed entity list / detail (wrap glossary `before_chapter_index`, KG `before_chapter_id`). |
| `lore_timeline(book_id)` | **R** | Windowed events (wrap `timeline.py before_order`). |

All are **Tier-R**, scope **`project`** (the session carries `project_id`; the grant derives `book_id` from it — corrected from "book" at build), cutoff auto-injected. The reader's chat agent runs with only these + no write tools.

**▶ BUILD RECIPE (grounded 2026-07-11, ready to execute — `get_reading_position` + its tests already shipped in the M2-groundwork commit).** Net-new = a new MCP tool family `app/tools/reader_tools.py` exporting `READER_TOOL_{ARG_MODELS,HANDLERS,DEFINITIONS}`, merged like `project_tools.py`.

- **Handler scaffold (shared by all 4; mirror `_handle_kg_graph_query`):**
  1. `owner = await _resolve_project_owner(ctx, GrantLevel.VIEW)` (`graph_schema_tools.py:1019` — grant-gates the reader on `book_id≥VIEW`, anti-oracle "project not found"; OD-8 rejects public `mcp_key_id`).
  2. `project = await ctx.projects_repo.get(owner, ctx.project_id)`; `book_id = project.book_id`.
  3. **reader position (the caller's own — never an LLM arg):** `chapter_id = await ctx.book_client.get_reading_position(book_id, ctx.user_id)` → `None` fail-closed.
  4. **three axes from the one position:** `before_order, avail = await resolve_before_order(ctx.book_client, chapter_id)` (KG event axis, inclusive-through-N); `before_sort_order, _ = await resolve_before_sort_order(ctx.book_client, chapter_id)` (RAG passage axis, inclusive N). Both `-1` when `chapter_id is None`.
- **Per-read wiring (all run as `user_id=str(owner)`):**
  - **Glossary canon** — `get_glossary_client().list_known_entities_for_chapter(book_id, before_chapter_index=before_sort_order + 1, ...)`. **OFF-BY-ONE (verified):** glossary is **exclusive** (`chapter_index < before_chapter_index`, `canon_at_chapter_handler.go:81`) while the axes are inclusive-through-N, so pass `before_sort_order + 1` to include the reader's current chapter. **Fail-closed:** if `before_sort_order < 0`, DON'T call glossary → empty canon. Wrap `GlossaryAnchorUnavailable/Malformed` → empty + degraded marker (never raise).
  - **RAG passages** — `run_hybrid_search(user_id=owner, book_id, project, ..., before_sort_order=before_sort_order)` (already windowed per M1).
  - **KG facts** — `list_facts_for_entity(session, user_id=owner, entity_id, before_order=before_order)` (`facts.py:529`). **KG status** — `statuses_detail_at_order(session, user_id=owner, project_id, entity_ids, at_order=before_order)` (`entity_status.py:226`; `-1`=fail-closed). **KG timeline** — `list_events_filtered(session, user_id=owner, project_id, before_order=before_order, after_order=None)` (`events.py:1166`). One `async with neo4j_session() as session:` per call.
  - **Cast list** — `list_entities_filtered` (`entities.py:1957`) has **NO window** (returns the FULL cast by name). **MANDATORY windowing (review-impl 2026-07-11 — do NOT skip):** `lore_browse_entities` must NOT return the raw cast, or a **null-position reader** (`before_order = -1`, hasn't started) sees the ENTIRE cast — a full-corpus leak, the exact fail-open the feature prevents. Instead: fetch the cast, then `statuses_detail_at_order(..., at_order=before_order)` for those ids, and **drop every entity whose windowed status is absent or whose `from_order > before_order`** (an entity not yet introduced by the reader's chapter). Null position ⇒ `before_order = -1` ⇒ `at_order = -1` ⇒ every entity dropped ⇒ **empty cast** (fail-closed). Add a red-first test: a reader with null position gets an EMPTY cast, not the full one.
- **The 4 tools:** `lore_ask(query)` → composite **evidence bundle** `{entities, facts, passages, window_available}` (per sign-off: evidence-only, caller's agent composes on its BYOK model; NO server LLM). `lore_browse_entities(kind?, limit?)` → windowed cast + statuses. `lore_entity(entity_id)` → windowed facts + status for one entity. `lore_timeline(limit?)` → windowed events.
- **Register in the THREE lockstep sources (FastMCP strips missing args — update all):** shims in `mcp/server.py` (copy `story_search` at :385, `meta=require_meta("R","project",tool_name=...)`, first param `ctx: MCPContext`, body `return await _dispatch(ctx, name, args)`); `READER_TOOL_ARG_MODELS` into `ARG_MODELS` (`definitions.py:186`) + `READER_TOOL_TOOL_DEFINITIONS` into `TOOL_DEFINITIONS` (`definitions.py:385` area); `READER_TOOL_HANDLERS` into `_HANDLERS` (`executor.py:724` area). Arg models subclass `ProjectScopedArgs` (`argbase.py:29`).
- **Tests (red-first):** fail-closed (None position → empty windowed reads, NOT full); anti-oracle (non-grantee → tool error "project not found"); resolve-to-owner (reads run as owner not caller); the glossary `+1` inclusion (reader AT ch N sees ch N's canon, not ch N+1's); each axis windows. **Then the mandatory adversarial `/review-impl` (this is the security-sensitive milestone: cutoff-server-enforced + anti-oracle + resolve-to-owner + fail-closed) — the M1 review caught a real HIGH fail-open, so run it.**

### 4.3 RAG cutoff on `raw_search` / `story_search`

The one "ask" surface missing a window (`raw_search.py:100-171` has ownership/language logic but no `before_chapter_id`). Passages carry `chapter_index` (`drawers.py:81`, `raw_search.py:253`), so:
**Design:** add optional `before_chapter_id` to `raw_search` (+ `story_search`); post-filter hits by `chapter_index ≤ cutoff`, **fail-closed** on unknown `chapter_index` (drop + count, mirroring `packer/spoiler.py`). The reader facade always passes it; author callers keep today's behavior when omitted.

### 4.4 KG read-auth unification onto grants

Today KG `entities.py` facts/statuses/timeline are **owner-`user_id`-scoped** (`entities.py:552,655`) — a VIEW-granted reader can hit glossary + `raw_search` (grant-gated) but **not** KG facts. Inconsistent.

**Design [refined at build 2026-07-11 — moved to M2].** `list_entity_facts`/`get_entity_detail` are keyed by `entity_id` with **no book context**, so a per-endpoint grant check has nothing to check `book_id` against without a new param. Rather than widen every author endpoint (and complicate `entity_id → book` resolution), reader KG access is delivered **inside the M2 facade**: it grant-checks `book_id ≥ VIEW` once (the `grant_client` shim to `loreweave_grants`, as `raw_search.py:117`), resolves the project **owner**, and calls the KG **repos** (`list_entities_filtered`/`list_facts_for_entity`/`statuses_detail_at_order`) as owner with the server-enforced `before_order` — the same resolve-to-owner identity `raw_search` uses. `entities.py`'s HTTP endpoints **stay owner-scoped** (the author/composition inspector is the owner); readers never hit them directly. Anti-oracle: no grant ⇒ the facade 404s uniformly. Red-first tenancy tests live with M2.

### 4.5 Public / anonymous spoiler-windowed lore route (user chose IN scope)

**Access boundary.** Only books with `sharing_policies.visibility='public'` (`sharing-service migrate.go:14`). Non-public ⇒ 404 (anti-oracle). Analogous to the existing unlisted-token chapter reads (`sharing-service server.go:108-110`) but for lore, not text.

**Anonymous cutoff = self-declared.** An anonymous reader has no `reading_progress` (no account), so their spoiler cutoff is **client-declared** ("I've read up to chapter N") — a weaker guarantee than the server-enforced grant-holder path (§4.2), acceptable for public exploration. Logged-in grant-holders always get the server-enforced position.

**Data-exposure guard (critical) — VERIFIED MECHANISM, 2026-07-11.** The public route exposes **confirmed canon only** — never `ai-suggested`/draft glossary entries, never owner-private KG scratch.
- **How canon-only holds today (verified against code):** `glossary_entities.status` defaults `'draft'` (`glossary migrate.go:74`); WS-4C canon-capture writes AI-suggested entities as **`status='draft'` + `[ai-suggested, assistant]` tags, never canon** (`capture_canon_handler.go:8`). The `known-entities` query (`extraction_handler.go:259+`) applies **no status filter by default** (`:277`, "only filter when explicitly asked") and `alive=true` does NOT exclude drafts (they default alive). Canon-only holds **only IMPLICITLY**: capture creates **no `chapter_entity_links`** for its drafts (grep-verified), so the `COUNT(cl.link_id) >= min_frequency` HAVING clause drops them whenever `min_frequency ≥ 1`. **M2's facade relies on this implicit guarantee** (it passes `min_frequency=1`) — acceptable for grant-gated collaborators.
- **M3 MANDATE (public surface — do NOT rely on the implicit guarantee):** the public route MUST pass an **explicit status filter** to `known-entities` — `status='active'` (the confirmed-canon value; DEFAULT is `'draft'`, so a draft is NEVER `'active'`). Belt-and-suspenders: also keep `min_frequency ≥ 1`. Rationale: if any future path ever creates a `chapter_entity_link` for a draft (or `min_frequency` is lowered), the implicit guarantee silently breaks and **leaks unreviewed AI guesses to the public** — the single highest-risk line in the whole design. Confirm `'active'` is the promote-path's canon value at build (candidate strongly supported: `alive`/attr reads use `status='active'`), then add a red-first test: a `status='draft'` + `ai-suggested` entity WITH a chapter link is EXCLUDED from the public route.
- **KG facts on the public route:** if the public route also serves KG facts (not just glossary canon), apply `review_status='promoted'` (facts) — but the leanest M3 is **glossary canon-cast only** (no KG), which sidesteps the KG-fact review-status question entirely; add KG later if needed.

**Design (sharing-service or a knowledge public route behind the public-visibility gate):** `GET /v1/public/books/{book_id}/lore?before_chapter=N&query=...` → windowed, canon-only glossary + KG + RAG. No JWT; rate-limited at the gateway edge.

---

## 5. Contracts & discoverability touched

- **New MCP tools** auto-appear in `tool_list` after registration (N1 mechanism, live). Each declares `_meta.tier`+`scope`.
- **C1 category enum** — the new tools are `book`/`glossary`/`knowledge` domain; no new category needed (unlike Track D's `research`). Verify at build that `world_*`/`lore_*`/`world_map_*` prefixes map to an existing `GROUP_DIRECTORY` home, else add the mapping lockstep (the Track-D `web→research` precedent).
- **Track C consumes:** world write tools + `kg_create_node` + map tools (W10 surface); `lore_ask`/`lore_*` + the public route (W11 reader surface). Coordinate signatures with Track C before freezing.

---

## 6. Proposed build milestones (order decided at sign-off)

**W11 (smaller — mostly wiring):**
- **W11-M1** — reading-position resolver (§4.1) + RAG cutoff (§4.3). *The two genuinely-standalone pieces; pure wiring over existing engines; red-first spoiler + fail-closed tests.*
- **W11-M2** — reader ask-the-lore facade + MCP tools, cutoff server-enforced (§4.2), **INCLUDING the KG grant-access (§4.4).** *[build refinement 2026-07-11]* `list_entity_facts`/`get_entity_detail` are keyed by `entity_id` with no book context, so they can't grant-check the way `raw_search` (which has `book_id`) does. So reader KG access is not a per-endpoint widening of `entities.py` (which stays owner-scoped for the author/composition inspector); it is **resolve-to-owner inside the facade after one `book_id` grant check** — the facade grant-checks `book_id ≥ VIEW`, resolves the project owner, and calls the KG repos (`list_entities_filtered`/`list_facts_for_entity`/`statuses_detail_at_order`) as owner with the server-enforced `before_order`. A reader "browse the cast/timeline" view (structured, not chat) is served the same way through the facade. Author endpoints are unchanged.
- **W11-M3** — public/anonymous canon-only windowed lore route (§4.5). *Public data surface ⇒ mandatory `/review-impl`.*

**W10 (write surface small; maps large):**
- **W10-M1** — world MCP write surface + world→bible/project resolution + `kg_create_node` (§3.1–3.2).
- **W10-M2** — maps primitive: tables + migration + MinIO image + 4 MCP tools + REST (§3.3). *The greenfield bulk; own milestone.*

**Cross-cutting DoD:** each milestone unit + a live cross-service smoke (≥2 services), MCP tools proven effectful (not just tools/list), spoiler fail-closed proven, anti-oracle proven.

---

## 7. Resolved decisions (signed off 2026-07-11)

1. **Map fidelity — FULL.** Ship all three tables in W10-M2: `world_maps` + `map_markers` + `map_regions` (polygon overlays), markers/regions optionally bound to `location` entities. No region deferral.
2. **`lore_ask` composition — evidence-bundle default, BYOK-only compose.** `lore_ask` returns a spoiler-windowed **evidence bundle** (entities/facts/passages); the caller's agent composes the answer on **its own BYOK model** (provider-gateway-clean, no platform spend). An *optional* server-side compose mode is allowed **only** when it resolves a **BYOK model through provider-registry** (the reader's own) — never a platform/hardcoded model. **The anonymous/public path is evidence-bundle-ONLY** (no server LLM): an unlisted-token reader has no BYOK, and the book owner must not be billed for strangers' queries. So server-compose is a logged-in-reader-only convenience over their own model.
3. **Public reader — unlisted-token gated.** Public lore is reached via a shareable **unlisted token** (mirrors sharing-service's public chapter reads, `server.go:108-110`), not fully open by `book_id`. Canon-only + self-declared spoiler cutoff + gateway rate-limit. Non-public / bad token ⇒ 404 (anti-oracle).
4. **Build order — W11 first.** W11-M1 → M2 → M3, then W10-M1 → M2. (§6 milestones.)

**One decision propagates into §4.2/§4.5:** the reader facade's return shape is the evidence bundle; server-compose is a logged-in-only flag gated on a provider-registry BYOK resolve; the public route (§4.5) never composes server-side.
