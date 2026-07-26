# Spec — Unified Manuscript-Structure MCP Tool

- **Date:** 2026-07-22
- **Branch:** `feat/frontend-tools-mcp-migration`
- **Status:** BUILT + VERIFIED + MEASURED (commit `b1eb36225`). Results: [`docs/eval/tool-liveness/manuscript-structure/RESULTS.md`](../eval/tool-liveness/manuscript-structure/RESULTS.md) — gemma-4 A/B fragmented 4/6 vs unified 5/6; the 2 previously-impossible part-authoring ops went 0/2→2/2 (10/10 across N=5 repeats, DB-verified). The design below is as-shipped.
- **Size:** XL (cross-service: book-service ↔ composition-service; new internal routes; new MCP surface)
- **Follows:** [`2026-07-22-book-tools-redesign.md`](2026-07-22-book-tools-redesign.md) (the book-tools content/lifecycle split). This is the *structure-graph* follow-on the redesign flagged.
- **Governs (standards):** [`docs/standards/mcp-tool-io.md`](../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6 / CAT-1..4), MCP-first invariant, Provider-gateway (N/A here), User Boundaries & Tenancy, Gateway invariant.

---

## 1. Problem

To organize a manuscript's structure, an agent must today juggle **3 tool families across 2 services** over **two different node trees** whose kind-names overlap — and one core operation is **not reachable by MCP at all**.

### 1.1 The actual graph (verified against code)

| Node | Service | Kinds | DB |
|---|---|---|---|
| `structure_node` | composition | `saga`, `arc`, **`part`** | one table, `kind` discriminator (`models.py:225` `StructureNodeKind = Literal["saga","arc","part"]`; "part" = depth-0 manuscript grouping) |
| `outline_node` | composition | `chapter`, `scene` | separate outline tree |
| `chapters` (prose) | book | — | links into the structure tree via `chapters.structure_node_id` (its part home) |

Cross-links / overloads that trip a weak model:
- **"chapter" means two things**: a prose row in book (`chapters`) *and* an `outline_node` kind in composition.
- **"part" and "arc" are the same table** (`structure_node`), different `kind`.
- A **chapter's home** is `chapters.structure_node_id` → a `kind='part'` node (or null = flat/unassigned).

### 1.2 Tool reachability today (the gap)

| Operation | MCP tool | Reachable by agent? |
|---|---|---|
| Read manuscript graph | `/structure` resolver ([`book_structure.go`](../../services/book-service/internal/api/book_structure.go)) | ✅ (book owns the read) |
| Home a chapter into a part | `book_chapter_set_part` | ✅ |
| Reorder chapters | `book_chapter_reorder` | ✅ |
| **Create a part** | — | ❌ HTTP-only (`arc.py:642` `create_part`) |
| **Rename a part** | — | ❌ HTTP-only (`arc.py:654` `rename_part`) |
| **Reorder parts** | — | ❌ HTTP-only (`arc.py:669` `reorder_parts`) |
| **Delete/archive a part** | — | ❌ HTTP-only (`arc.py:684` `archive_part`) |
| Arc/saga (spec layer) | `composition_arc_create` (`Literal["saga","arc"]`) | ✅ but **refuses `part`** |
| Outline chapter/scene | `composition_outline_node_*` (`Literal["chapter","scene"]`) | ✅ |

**Consequence:** an agent can file a chapter into a part it has no way to create. "Make a Part and put the last 3 chapters in it" is impossible via MCP. This is the primary bug this spec closes; the tool-count reduction / anti-fragmentation is secondary.

### 1.3 Why the fragmentation is intentional (do NOT undo it)

The `structure_node` (saga/arc/part) vs `outline_node` (chapter/scene) split, and the closed `Literal` on each kind, are **deliberate** (BPS-4 / F6, `server.py:948`): a closed enum turns a mid-tier model's `kind:"Arc"` into a clean 422 instead of a DB `CheckViolation` 5xx (mcp-tool-io IN-2, the `panel_id` bug class). **This spec keeps the DB model and the low-level tools exactly as they are.** It adds ONE manuscript-facing surface *over* them — it does not merge the entities or the underlying tools.

---

## 2. Goals / Non-goals

**Goals**
- G1. Close the gap: an agent can create / rename / reorder a manuscript **part** via MCP.
- G2. One coherent **read** of the manuscript graph (parts → chapter groupings → unassigned) — reference-first, paged, with an explicit stop-signal (OUT-1/2, the book-redesign output contract).
- G3. One coherent **write** surface over the manuscript structure ops the agent needs, with a closed `op`×`kind` enum, per-op Undo, and no silent seam on cross-service failure.
- G4. Empirically measure whether a weak local model (gemma-4) navigates the graph *better* with the unified surface than with the fragmented one (A/B), with DB verification after every mutation.

**Non-goals**
- N1. Do NOT touch the `structure_node`/`outline_node` DB model or the existing low-level tools (`composition_arc_*`, `composition_outline_node_*`, `book_chapter_set_part`, `book_chapter_reorder`) — they stay; the unified tool *orchestrates* them.
- N2. Do NOT expose arc/saga (the spec layer) through the manuscript tool. Manuscript-facing = **part + chapter** only. Arcs remain `composition_arc_*`.
- N3. No destructive part-delete on the auto-write surface (CAT-2). Part archive/delete stays a separate legacy/manual tool, consistent with the book-tools redesign's "human owns lifecycle/destructive."
- N4. No outline-tree (scene) writes here. Scenes live under chapters in the outline tree; that is `composition_outline_node_*`'s job.

---

## 3. Design

### 3.1 Ownership — book-service owns the unified tool

- The manuscript **read** already lives in book-service and is *documented as book-owned* (`book_structure.go`: "book-service OWNS this read: it holds the chapter SSOT + the `structure_node_id` join key"). Parts are always read (Work-independent).
- The manuscript **writes** split: chapter-homing/reorder are already book MCP tools; part-writes are composition HTTP. `book_chapter_set_part` **already** reaches into composition via an **internal** route (`X-Internal-Token` + acting `user_id`) because the MCP path has no user bearer.
- ⇒ **book-service owns the unified tool** and orchestrates composition for part-writes over internal routes — the exact established pattern. One manuscript-facing surface, consistent with the read's ownership. (MCP-first: the tool lives on the owning domain service; ai-gateway federates.)

### 3.2 The two tools

#### `book_structure_read` (Tier: read)
Returns the manuscript graph as a reference-first, paged skeleton — reuse `buildBookStructure` (the LEFT-JOIN-safe grouping; chapter-conservation invariant `sum(part counts)+unassigned==len(chapters)`).

Output contract (OUT-1/2 + book-redesign envelope):
- **L1 reference-first:** parts (`part_id`, `title`, `sort_order`, `chapter_count`) + `unassigned_count` + `kinds_present` + `sources` (`ok|unavailable` — no silent seam) — NOT inline chapters.
- **L2 detail on request:** `part_id` (or `unassigned`) drills into that group's chapters, paged (`returned/total/offset/next_offset/has_more/is_complete`), reusing the existing chapter pagination.
- **Stop-signal:** structured `is_complete: bool` **and** prose `guidance` (both, per PO decision 2026-07-22) so the model stops paging when the group is exhausted.
- Never truncate silently (OUT-5: report the cap).

#### `book_structure_edit` (Tier: A — auto-write + Undo, EDIT-gated)
One write tool. Closed enums (IN-2 / Frontend-Tool-Contract closed-set ⇒ `enum`; register in `CLOSED_SET_ARGS` where applicable). Routes by `op`:

| `op` (enum) | Args | Routes to | Undo |
|---|---|---|---|
| `create_part` | `title` | composition **internal** `POST /parts` (NEW route) | archive the created part |
| `rename_part` | `part_id`, `title` | composition **internal** `PATCH /parts/{id}` (NEW) | restore prior title |
| `reorder_parts` | `ordered_part_ids[]` | composition **internal** `POST /parts/reorder` (NEW) | restore prior order |
| `home_chapter` | `chapter_id`, `part_id`\|null | existing `moveChapterToPart` (book) | restore prior `structure_node_id` (already implemented) |
| `reorder_chapters` | `part_id`\|null, `ordered_chapter_ids[]` | existing `book_chapter_reorder` path | restore prior order |

- **Destructive split (CAT-2):** `delete_part` / `archive_part` is **NOT** an `op` here — it is a separate `book_structure_part_archive` tagged `visibility:legacy` (human-owned lifecycle). Undoing a `create_part` archives (reversible), which is fine; a *user-intended* delete is the legacy tool.
- **Validation (no silent seam, mirrors `book_chapter_set_part`):** a non-null `part_id` target for `home_chapter` must be a LIVE `kind='part'` of THIS book (existing `validatePartTargetInternal`); `create_part`/`rename_part`/`reorder_parts` gate EDIT on the book and surface a composition outage as a clean "try again shortly," never a fabricated success.
- **Bare-payload success / `{success:false,error}` on failure** (OUT-4). Errors are uniform not-accessible (no existence oracle, matching the rest of the book/parts surface).

### 3.3 New internal composition routes (the real cross-service work)

The public part routes (`arc.py` 642/654/669) are **bearer-gated**; the MCP agent path has only `X-Internal-Token` + `user_id`. So book needs **internal** counterparts, mirroring the existing internal `GET /internal/composition/books/{id}/parts?caller_user_id=` used by `validatePartTargetInternal`:

- `POST /internal/composition/books/{book_id}/parts` (`caller_user_id`, `title`)
- `PATCH /internal/composition/parts/{node_id}` (`caller_user_id`, `title`)
- `POST /internal/composition/books/{book_id}/parts/reorder` (`caller_user_id`, `ordered_ids`)

Each: resolve node → assert `kind='part'` (never touch an arc, per `_gate_part`) → gate the owning book's grant for `caller_user_id` → write. Uniform 404 for missing/not-a-part/not-a-grantee (no existence oracle). Tenancy: book-scoped, per User Boundaries.

### 3.4 Discovery / hot-set

`book_structure_read` + `book_structure_edit` are book-surface tools → hot-set for the book/editor surface (prefix `book_*` already hot per `surface_hot_domains`). Legacy `book_structure_part_archive` is `visibility:legacy` (excluded from `tool_list`/hot set, reachable only via explicit pin) — same mechanism as the 15 tools deprecated in the book redesign.

---

## 4. Measurement plan (the "does the agent understand the graph" test)

Per the measure-first discipline: build → then A/B the fragmented surface vs the unified surface on the SAME scenarios, weak model, DB-verified.

**Model:** gemma-4 local (lm_studio, $0) — the target weak model. Test account `019d5e3c-…` (has BYOK). Resolve `model_ref` live.

**Protocol per scenario:** real MCP calls through ai-gateway → after every mutation, **query Postgres directly** to confirm the DB actually changed (the user's rule: "nhiều khi có bug không update vào db"). Log: turns, tokens (in/out/cached), tool-calls made, success (DB-verified) / failure / wrong-tool / gave-up.

**Scenario set (escalating graph reasoning):**
1. **Navigate** — "Where does chapter X sit — which part, or is it unassigned?" (read + traverse)
2. **Create + multi-hop** — "Make a Part 'Act II' and move the last 3 chapters into it." (⚠ impossible on the fragmented surface today — expect baseline FAIL, unified PASS — this is G1's proof)
3. **Reorder** — "Put chapter 5 first within its part."
4. **Traversal query** — "Which chapters have no part?"
5. **Trap / refusal** — "Move a scene into a part." (should refuse cleanly — scenes live under chapters in the outline tree, not the structure tree; measures whether the closed enums keep the model honest)
6. **Reorder parts** — "Swap the order of Part 1 and Part 2."

**Metrics:** per-scenario success rate (DB-verified), tokens, wrong-tool rate, refusal-correctness on #5. **A/B:** fragmented (current tools) vs unified (this spec). Success bar: unified ≥ fragmented on success-rate with ≤ tokens, and #2 goes FAIL→PASS.

---

## 5. Risks / open questions

- **R1.** Internal part-write routes duplicate the public ones' logic — factor the core into a shared repo method both call (public bearer handler + internal token handler), don't fork the logic.
- **R2.** `reorder_parts` / `reorder_chapters` take an ordered id list — a partial/foreign id must fail-closed (reject the whole op), not silently drop. Mirror the dual-axis ordinal lockstep lesson.
- **R3.** Undo for `reorder_*` must snapshot the FULL prior order, not just the moved id.
- **R4.** The unified read must keep chapter-conservation (`buildBookStructure`) — reuse it, don't reimplement.
- **Q1 — RESOLVED (PO 2026-07-22): FOLD IN.** `home_chapter`/`reorder_chapters` become `op`s on `book_structure_edit` (owning the concept). The existing standalones `book_chapter_set_part` / `book_chapter_reorder` are tagged `visibility:legacy` (one name per concept, smallest agent-facing surface). Their handlers are REUSED by the new ops — the legacy tag hides them from discovery, it does not delete the code path (`moveChapterToPart`, the reorder path stay). Migration cost: two more `visibility:legacy` tags + a contract/visibility test, same mechanism as the 15 book-redesign deprecations.

## 6. Build slices (when approved)

1. **BE composition:** 3 internal part-write routes + shared repo methods (R1). Tests: gate/tenancy/not-a-part 404.
2. **BE book:** `book_structure_read` (reuse resolver, add L2 paging + is_complete/guidance) + `book_structure_edit` (op router, Undo per op, validation). Tests: op routing, undo round-trip, fail-closed reorder (R2/R3).
3. **Register + hot-set + legacy-tag** the archive tool; contract/visibility tests.
4. **Measurement harness** (§4) + run A/B + record results in SESSION_HANDOFF.

---

*Design checkpoint. No code until approved. Then: BUILD → VERIFY (live cross-service smoke, ≥2 services) → REVIEW → the §4 A/B measurement as the effectiveness proof.*
