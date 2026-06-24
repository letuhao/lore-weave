# Creation-Unblock RAID — Gap Analysis

> **Date:** 2026-06-15 · **Author:** gap audit (3 parallel read-only audits: World/knowledge FE, backend wiring, planned-vs-built docs) · **HEAD:** `b16e670a` (RAID complete)
> **Status:** ANALYSIS ONLY — no design, no implementation. For review + prioritization.

## Scope & boundary

This analysis is **strictly bounded to what the `creation-unblock` RAID delivered** — cycles C0–C28 and milestones M1–M6 (see [CYCLE_LOG.md](../raid/CYCLE_LOG.md), [cycle decomposition](../plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md)). It catalogs gaps, dead-ends, and unwired seams **inside that surface area only**.

**Explicitly OUT of scope** (separate features, not gaps in this RAID — do not pull them in here):
- **World-core foundation** rearchitecture (knowledge-service "god service" refactor)
- **Living Worlds / MMO-RPG** extension ([LLM_MMO_RPG](../03_planning/LLM_MMO_RPG/))
- **Collaboration / multi-user** authoring
- Billing/tier, extraction raw-output cache, platform system-config UI

These are tracked elsewhere and have their own design tracks. This doc does not touch them.

## What the RAID delivered (recap)

| Milestone | Cycles | Capability shipped |
|---|---|---|
| (trio) | C1–C3 | Rerank registration → discovery → connection-test (BYOK via provider-registry) |
| **M1** | C4–C7 | BookPicker; build-graph gates; project-detail shell (G6 IA); projects browser HOME |
| **M2** | C8–C14 | Entities semantic layer · promote→glossary-draft · gap report · proposals inbox · build wizard (targets + pinning) · timeline importance/order |
| **M3** | C15–C17 | Writer unblock — co-write bridge, grounding-optional, guided first-run, continue-from-cursor |
| **M4** | C18–C19 | Graph subgraph endpoint (G5) + explorable graph canvas |
| **M5** | C20–C22 | World container (book-service) + prose-less world FE + intent-branching onboarding |
| **M6** | C23–C28 | dị bản (derivative) system — schema/derive API · divergence wizard · packer base+delta merge · critic override enforcement · delta flywheel + what-if promotion · living-world timeline view |

All 29 cycles DONE; M1–M6 reached. Backend for projects/books/worlds/derivatives is **fully wired end-to-end through the gateway** (verified: `/v1/knowledge/projects`, `/v1/books`, `/v1/worlds`, `/v1/composition/works/{id}/derive` all proxied — [gateway-setup.ts:367,412](../../services/api-gateway-bff/src/gateway-setup.ts)).

## Headline gap — the World workspace is a dead-end

This is the gap surfaced in review: *"World UX cannot be used — no button to add project/book, no picker to browse/pick."* The investigation **partially confirms** it, with one correction:

- ✅ **Real:** After creating a world (M5) you land in [WorldWorkspacePage](../../frontend/src/features/world/pages/WorldWorkspacePage.tsx#L14) on an empty [LivingWorldTree](../../frontend/src/features/world/components/LivingWorldTree.tsx#L81) whose empty-state reads *"No works in this world yet — start a book or a what-if to grow its timeline"* — **with no button to do either.** The user must navigate away to `/books`, create a book, attach it, and come back. The M6 living-world view shipped the *visualization* but not the *populate-it* affordance.
- ❌ **Correction:** It is **not** "backend never wired." C20 shipped the move-book endpoint (`POST /v1/worlds/{id}/books`) and it's proxied. Create-book/create-project/create-world buttons all exist — they're just **siloed** to their home routes ([/books](../../frontend/src/pages/BooksPage.tsx#L123), [/knowledge/projects](../../frontend/src/features/knowledge/components/ProjectsTab.tsx#L181), [/worlds](../../frontend/src/features/world/components/WorldsBrowser.tsx#L46)) and unreachable from the world workspace.

**Net:** a pure FE wiring gap on top of a ready backend. It makes the M5/M6 "build a world" path (which onboarding C22 routes users into) effectively unusable without prior knowledge.

## Gap inventory (in-boundary)

### Tier 1 — Wiring / dead-ends (small; unblock workflows now)

| # | Gap | Where | State | Size |
|---|---|---|---|---|
| G1 | **World workspace has no "create/attach book" or "create what-if" CTA** | [WorldWorkspacePage.tsx](../../frontend/src/features/world/pages/WorldWorkspacePage.tsx), [LivingWorldTree.tsx:81](../../frontend/src/features/world/components/LivingWorldTree.tsx#L81) | empty-state hint only, no action | S (FE; backend ready) |
| G2 | **No reusable ProjectPicker / WorldPicker** | only [BookPicker](../../frontend/src/components/shared/BookPicker.tsx) exists; chat uses a raw `<select>` for projects; no world picker anywhere | partial | S (mirror BookPicker) |
| G3 | **Feature islands don't cross-link** — knowledge ⇄ world ⇄ composition ⇄ chat have no shared entry points; you can only create/select each from its own home route | sidebar routes only | islands | S–M (nav/affordance) |

### Tier 2 — In-boundary feature incompleteness (medium)

| # | Gap | Where | State | Size |
|---|---|---|---|---|
| G4 | **Worlds ↔ knowledge/composition not linked** — a world can hold books but a knowledge project can only bind to a *book*, not a world; composition has no world-awareness | C20/C21 model; [ProjectFormModal](../../frontend/src/features/knowledge/components/ProjectFormModal.tsx) binds book only | decoupled | M (needs design — touches the boundary) |
| G5 | **Onboarding "Build a world" promise unfulfilled** — C22 routes Build-a-world → `/worlds`, which then dead-ends at G1 | [onboarding](../../frontend/src/features/onboarding/) → world workspace | broken-by-G1 | S (resolved once G1 lands) |

### Deferred items originating from this RAID (tracked backlog)

| ID | Origin | Description | State |
|---|---|---|---|
| **D-C16-NULL-WORK-ROUTE** | C16 | A greenfield null-`project_id` Work isn't `{project_id}`-route-addressable until backfill; the BE id-route was left out of C17 (FE-only). **Still OPEN.** | open |
| D-079 (D-C24-ANCHOR-ON-THE-FLY) | C24/C25 | Divergence wizard persists `target_entity_id` as a KNOWLEDGE node id, not the GLOSSARY anchor the present-lens keys on; C25 reconciles at pack time. | LOW (mitigated) |
| D-C26-CRITIC-FN | C26 | 3 advisory false-negative edges in the override-slip detector (broad base lens, substring false-neg, delta_inconsistency rides on bio-slip). Dimension is advisory, never blocks accept. | M0-acceptable |
| D-078 | C12 | Decoupled trio fan-out defaults to unbounded gather (concurrency_level caps the sync path only). | doc-only |
| D-080 | adjust | Compose tab-strip scroll affordance (no fade indicator; keyboard nav works). | COSMETIC |

### Resolved during the adjustment pass (NOT gaps — recorded to prevent re-investigation)

- **C7 client-side search/sort/filter** → server-side filter shipped (`849be75a`); cursor binds full filter set (`b571567c`).
- **KN-7 in-flight cap** → addressed via worker concurrency decoupling (`ca2611fd`).
- **C2/C3 rerank live-smokes** → C3 passed; C2 parser gap found + fixed (`7815acc2`); both green on origin.
- **C11 inbox live-smoke** → RESOLVED 2026-06-15.
- **C26 override gate** (CJK-blind detector + set-but-never-consumed `needs_regeneration`) → fixed `8b34a2a6`; gate now blocks at `/persist` 409.

## What is NOT a gap (corrections to the initial read)

To keep the next pass focused, these were investigated and found **already working**:

1. **Backend wiring** — every project/book/world/derivative create+list endpoint exists and is gateway-proxied. No backend holes. Any missing button is a FE gap.
2. **dị bản creation IS discoverable** — the divergence wizard and what-if-promotion are wired into the composition panel ([CompositionPanel.tsx:307,330](../../frontend/src/features/composition/components/CompositionPanel.tsx#L307)). The dead-end is the *world* side, not the derivative side.
3. **Create buttons exist** for projects, books, and worlds — they're just siloed to their home routes (the G1/G3 discoverability problem, not an absence).

## Recommended remediation order

1. **Tier 1 as one FS batch (G1 → G2 → G3).** Backend is ready; this is the difference between the M5/M6 world feature being usable vs broken, and it directly closes the user-reported dead-end + the onboarding promise (G5). Estimated S–M.
2. **G4 (worlds ↔ knowledge/composition linkage)** as a separate small DESIGN pass — it touches a service boundary, so it earns a short spec rather than ad-hoc wiring.
3. **D-C16-NULL-WORK-ROUTE** — the one genuinely-open BE deferral from the RAID; schedule when the composition/Work routing is next touched.
4. Leave D-079 / D-C26-CRITIC-FN / D-078 / D-080 as tracked (all advisory/cosmetic/M0-acceptable).

Out-of-boundary big features (world-core, MMO, collaboration) are **not** part of this remediation — they remain separate tracks.
