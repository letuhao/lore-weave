# C-merge Design — unify manuscript Parts ⇄ plan Arcs into one structure

**Status:** `DESIGN — awaiting PO sign-off.` No data touched. This is the gate the spec mandates before
any Part-C build. Grounded in three parallel blast-radius maps (book-service · composition · frontend),
2026-07-18.

**Decision requested:** approve the **SSOT choice** (§2) and the **cutover sequence** (§5), or redirect.

---

## 1. What exists today (the two systems, from the maps)

| | **Parts** (manuscript acts) | **Arcs** (plan spec) |
|---|---|---|
| Service / lang | `book-service` (Go, domain) | `composition-service` (Python, AI/plan) |
| Table | `parts` (`migrate.go:273`) | `structure_node` (`migrate.py:1171`) |
| Scope key | `book_id` | `book_id` (Work-agnostic) |
| Shape | **flat**, `sort_order`, `UNIQUE(book_id,sort_order)` | **tree** saga→arc→sub-arc, `parent_id`+`depth` (DB trigger), LexoRank |
| Concurrency | last-write-wins | **OCC** (`version` + If-Match) |
| Chapter link | `chapters.part_id` (book-service FK, `ON DELETE SET NULL`) | `outline_node.structure_node_id` (composition, **project_id-scoped**) |
| Richness | title + lifecycle only | `tracks`/`roster`/`roster_bindings` JSONB, template + plan provenance, conformance state |
| Surfaces | 7 REST + 6 MCP tools, **no OpenAPI contract, no events** | ~12 REST + ~15 MCP tools, engine/packer/conformance deeply bound |
| Tests | `parts_db_test`, `mcp_tools_parts_db_test`, `migrate_test` (string-match DDL asserts) | ~10 unit + ~15 integration-DB (incl. the `arc_lift` precedent) |

**The single bridge between the two worlds:** `outline_node.structure_node_id` — the only place the
book-scoped arc layer meets the project-scoped outline (chapter/scene) layer.

**The asymmetry that dominates this design:** arcs are `book_id`-only and Work-agnostic; every table they
link *downstream* (`outline_node`, `motif_application`, `decompose_commit`, conformance) is
`project_id`-scoped. Parts, by contrast, group **book-service chapters** (`chapters.part_id`), which are a
*different* chapter representation than composition's `outline_node`. **There are two chapter models**, and
the merge must reconcile which one structure groups.

---

## 2. SSOT decision — **Arcs win** (structure SSOT → `structure_node` in composition)

**Recommended:** `structure_node` becomes the single structure hierarchy; `parts` is migrated into it and
retired.

**Why arcs, not parts:**
- **Richness + integration:** a part is trivially expressible as a depth-0 `structure_node` (a title + an
  order). The reverse is false — rebuilding arcs (tree, OCC, LexoRank, tracks/roster, template/plan
  provenance, conformance) on top of the flat `parts` table would be a full re-implementation, and would
  force composition's engine/packer/conformance (all keyed on `structure_node_id`) to read structure
  cross-service from book-service on every generation. That inverts the AI-service's ownership of its own
  plan spec.
- **Blast-radius math:** arcs-win migrates **one simple table (7 routes/6 tools, no contract, no events)**
  into an existing rich one. Parts-win rewrites **the entire composition structure layer** + every engine
  consumer. Arcs-win is strictly the smaller, safer destruction.

**The boundary reframe this commits to (and the PO must accept):**
> `book-service` owns **prose containers** (chapters, files, scenes-as-text). `composition` owns
> **structure** (how chapters are grouped/ordered/planned). "Grouping chapters into acts" is reclassified
> from a book-service domain concern to a composition/plan concern.

This is defensible — F6's whole finding is that Parts and Arcs *are* the same concept — and it respects I3
(structure is plan ⇒ Python/composition; raw prose stays Go/book-service). But it is a **real boundary
shift**: the Manuscript rail's act-grouping will read `structure_node` from composition, not `parts` from
book-service. `structure_node` being `book_id`-scoped and Work-agnostic means this works even for a
prose-first, un-planned book (no Work required) — so it does **not** force planning on drafters.

**What must be added to `structure_node` to absorb parts:** a depth-0 grouping that is not necessarily a
generation "arc". Proposal: reuse `kind` with a new value **`'part'`** (or treat existing `kind='arc'` at
depth 0 as the group) so a manuscript grouping and a plan arc can coexist in one tree without forcing a
prose-first writer's "Part One" to carry generation semantics. **← key sub-decision for the PO** (a new
`kind='part'` vs. overloading depth-0 `arc`).

---

## 3. The chapter-link reconciliation (the hard part)

Today: `chapters.part_id` (book-service) and `outline_node.structure_node_id` (composition, project-scoped)
are **two independent chapter→group links on two chapter models**. Arcs-win must make **one** link authoritative.

- Book-service `chapters` is the SSOT for a chapter's existence/prose. Composition `outline_node` is the
  chapter's *plan projection* (project-scoped, exists once there's a Work).
- **Proposal:** the chapter→structure link becomes `structure_node_id`, stored on the **book-service
  chapter** (rename/replace `chapters.part_id` → `chapters.structure_node_id`, a book-scoped id pointing at
  composition's `structure_node`). Composition's `outline_node.structure_node_id` stays as the plan-side
  mirror. A cross-service read (gateway) resolves a chapter's group for the Manuscript rail.
- **Un-planned books:** `structure_node` is book-scoped, so a drafter's chapters can be grouped by a
  `kind='part'` node with **no Work and no outline_node** — exactly today's "parts without a plan" case,
  now expressed in the unified model.

This is the riskiest reconciliation and where §5's additive-first sequence matters most.

---

## 4. Blast radius to touch (from the maps)

**book-service (retire parts):** `parts` table + `storeCreatePart…` (`parts.go`), 7 routes
(`server.go:323-328,358`), 6 MCP tools (`mcp_tools_parts.go`), `chapters.part_id` + `structural_path`
(`migrate.go:305-307`), `idx_chapters_part`, the `hierarchy.go` JOIN + `uuidv5` synthetic-part fallback
(`:231`), the `migrate_test.go` string-match DDL asserts (`:12-27,66-76,78`), `parse.go` importer writes.

**composition (extend arcs):** `structure_node` DDL + depth trigger (`migrate.py:1171-1253`), `StructureRepo`
(add `kind='part'` handling), `arc.py` routes, arc MCP tools, the `arc_lift` migration precedent to mirror.

**gateway:** a cross-service resolve so the Manuscript rail reads structure from composition.

**frontend (unify the two rails):** the 9 breakage points from the FE map — `partsApi.ts` → composition
arc routes; `partsTree.ts`/`buildPartsTree` flat model → arc tree; `useManuscriptTree.partsMode`
(`:90`, the no-Work either/or) collapses; `ManuscriptNavigator` part affordances → OCC-aware arc writes
(rename/reorder now need `If-Match`); `ManuscriptRowKind` union; the two click contracts in `StudioSideBar`
(`:61-90`); the `partVsArc` tooltip + `actShort`/`actTag`/`statActs` i18n across 18 locales; and all parts
+ arc test suites.

**contracts:** book-service parts are *undocumented* today (no gate to satisfy), but the composition arc
routes that absorb them ARE contract-bound — additions go through the contract-first flow.

---

## 5. Cutover sequence (additive → migrate → cutover → remove — each a slice)

Never a big-bang. Each step is independently shippable, reversible until the last, and cross-service
live-smoked + `/review-impl`'d.

1. **C1 · Additive model** — add `kind='part'` (or the chosen grouping) to `structure_node`; add a
   book-scoped `chapters.structure_node_id` to book-service **alongside** the existing `part_id` (nullable,
   no backfill). Nothing reads it yet. *Reversible.*
2. **C2 · Dual-write** — parts mutations (create/rename/reorder/assign) also write the mirrored
   `structure_node`/`structure_node_id`. Reads still come from `parts`. Backfill existing parts →
   `structure_node`. *Reversible; data now consistent in both models.*
3. **C3 · Read cutover** — the Manuscript rail + hierarchy JOIN read `structure_node` (via gateway) instead
   of `parts`. `partsMode` collapses; the two rails unify their click contract. FE flips behind this.
   *Reversible by flipping reads back.*
4. **C4 · Retire parts** — drop the parts routes/tools/table + `chapters.part_id`; delete the parts FE +
   tests; update the `migrate_test` asserts + i18n. *The point of no return — only after C3 soaks.*

Rollback: any step before C4 reverts by pointing reads back at `parts` (still dual-written through C3).

---

## 6. Risks (honest)
- **Two chapter models** (`chapters` vs `outline_node`) is the deepest hazard — §3's link reconciliation
  can strand a chapter's grouping if the book-side and plan-side links disagree (cf. the memory lesson
  "two anchor-writers disagreed"). C2 dual-write + a consistency check gate this.
- **OCC introduction** to the Manuscript rail: part rename/reorder becomes version-checked; the FE must
  handle 412s it never saw before.
- **Boundary shift** (structure → composition) is architecturally load-bearing; if the PO rejects the
  reframe in §2, the whole design changes (parts-win, far larger) — hence this sign-off.
- **Cross-service migration + LOCKED I3** ⇒ `/review-impl` on every C-slice, mandatory cross-service
  live-smoke, and the DEFERRED/gate discipline for anything that can't land in a slice.

## 7. Sign-off asks (PO)
1. **SSOT = arcs-win** + the boundary reframe (structure is a composition concern)? [Y/redirect]
2. **Grouping kind:** new `structure_node.kind='part'`, or overload depth-0 `arc`? [choice]
3. **Cutover sequence** C1→C4 as staged (additive/dual-write/read-cutover/retire)? [Y/redirect]
4. Confirm this runs with **`/review-impl` on every C-slice + cross-service live-smoke** (given I3 + a
   destructive migration).

**Until sign-off: no Part-C code, no schema change, no data touched.** Part B (the small "Set up this book"
primitive) can proceed independently in the meantime.
