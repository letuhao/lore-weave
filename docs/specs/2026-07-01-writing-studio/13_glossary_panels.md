# 13 · Glossary Dockable Migration — shared foundation + fanout

> **Status:** 📐 specced 2026-07-04 · branch `feat/context-budget-law` (studio track resumes here)
> Cycle queue position: [`12_json_document_standard.md`](12_json_document_standard.md) queues **Glossary** immediately after Chapter editor (cycle 1, shipped). This spec covers ALL of Glossary's dock-panel work, split into a **serial shared-foundation phase** and a **parallel fanout phase**, per [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md).

## Why a two-phase shape (not one flat cycle, not a straight fanout)

Scoping investigation (2026-07-04) found Glossary is NOT a single-page migration like Trash/Settings (wave 1) — it's **~10,800 lines across 4 directories**, 7 distinct sub-features, with three DOCK-standard violations:

- **DOCK-8** — `GlossaryTab.tsx` (802 lines) internally swaps its ENTIRE subtree by a `view` state switch (`entities`/`ontology`/`unknown`/`ai_suggestions`/`merge_candidates`) instead of each capability being its own catalog entry.
- **DOCK-9** — six hand-rolled `fixed inset-0` modals (`EntityEditorModal`, `CreateEntityModal`, `ExtractionWizard`, `GlossaryTranslateWizard`, `BatchTranslateDialog`, `ResolveKindModal`) instead of the shared `FormDialog`/`ConfirmDialog`.
- **DOCK-10** — no Tier-4 hoist for entity edits; `EntityEditorModal` fetches/saves via component-local `useState`, not a reusable hook (unlike chapter editor, which already had `useManuscriptUnit` for cycle 1 to wrap).

Every one of these three fixes is **shared surface** — the same file (`GlossaryTab.tsx`, `catalog.ts`) or the same missing hook that every future panel would otherwise duplicate. Per [[fanout-independent-slices-parallel-build-serial-integrate]] (fan-out only works on genuinely disjoint files), these must land **serially first** (Phase A). Once they exist, the remaining 4 ontology/unknown/suggestions/merge panels + 4 remaining modals are **provably disjoint files** and fan out safely (Phase B).

## Locked decisions (this session)

| # | Decision | Why |
|---|---|---|
| G1 | **Entity editor + translate wizard stay `FormDialog` modals — NOT dock panels.** | Matches VS Code precedent (rename-symbol/quick-edit doesn't dock); a focused CRUD form has no benefit from being a dock tab; keeps catalog/enum scope smaller. |
| G2 | **`registerJsonDocumentProvider('loreweave.glossary-entity.v1')` ships in Phase A**, wrapping a NEW `useGlossaryEntity(bookId, entityId)` hook extracted FROM `EntityEditorModal`'s inline state — not deferred like cycle-1's scene-prose-anchoring was. | User call; unlike manuscript-unit there is no pre-existing hoist to wrap (`EntityEditorModal` owns `entity`/`pendingChanges` as local `useState`), so the hook extraction is real Phase-A work, not a thin wrapper. |
| G3 | **Two-phase shape: Phase A (shared, serial) gates Phase B (fanout, parallel).** | The DOCK-8/9/10 fixes are the shared surface every panel would otherwise touch; building them once, then fanning out, avoids N agents colliding on `GlossaryTab.tsx`/`catalog.ts`/the entity hook. |
| G4 | **`EntityEditorModal`'s hook-extraction and its `FormDialog` adoption land in the SAME Phase-A change** (not split across phases) | It's one file either way — touching it twice (once to extract state, once to swap the modal shell) is pure churn. `ResolveKindModal` (not `EntityEditorModal`) is the DOCK-9 **precedent** example instead, since it's small (173 lines) and untangled from the hook-extraction work. |

## Phase A — shared foundation (serial, build first)

| # | Task | File(s) | Why it must be serial |
|---|---|---|---|
| A1 | Extract `useGlossaryEntity(bookId, entityId)` — load/save/pendingChanges/isDirty/status/genre — from `EntityEditorModal.tsx`'s inline state. Byte-preserving refactor; existing entity-editor tests stay green. Adopt `FormDialog` (`size="3xl"`) in the same pass (G4). | `components/entity-editor/EntityEditorModal.tsx`, new `features/glossary/hooks/useGlossaryEntity.ts` | The hook is the thing BOTH the modal AND the JSON provider (A2) wrap — must exist once, not be duplicated per-consumer. |
| A2 | `registerJsonDocumentProvider('loreweave.glossary-entity.v1')` wrapping `useGlossaryEntity` (A1). `save()` wraps the existing `glossaryApi.patchAttributeValue`/`patchEntity` — OCC via the `base_version` contract already fixed repo-wide (W0/W1, `docs/sessions/SESSION_HANDOFF.md`), never a new write path. Mirrors `manuscriptUnitDocument.ts`. | new `features/studio/glossary/entityDocument.ts` (or co-located under `features/glossary/`) | Registry is a single shared array; the provider needs A1's hook to exist first. |
| A3 | Extract the **entity list/search/filter/bulk-actions** portion of `GlossaryTab.tsx` into its own component + the `glossary` dock panel (catalog entry, `useRegisterStudioTool`, bus, self-title, params-seeded from F1, zero `useNavigate`/`<Link>` per DOCK-7). This is the FIRST full panel and doubles as this cycle's live-gate proof (spec-12 gate item 6). | `pages/book-tabs/GlossaryTab.tsx` (shrinks — becomes a thin router redirect to the panel or is retired per-route), new `features/studio/panels/GlossaryPanel.tsx` + `catalog.ts` row | The other 4 view-swap branches (ontology/unknown/ai_suggestions/merge_candidates) each already own a self-contained hook (`useMergeCandidates`, `useUnknownReview`, `useAiSuggestions`, ontology's own tree) — no extraction needed there. Only the entity-list portion was entangled with `GlossaryTab`'s state, and it's the piece every other capability's "back to list" affordance points at. |
| A4 | Migrate `ResolveKindModal` (173 lines) to `FormDialog` — the DOCK-9 adoption **precedent** the 4 remaining Phase-B modals copy. | `features/glossary/components/ResolveKindModal.tsx` | One worked example de-risks the pattern (dialog width, close/cancel wiring) before 4 parallel agents repeat it. |
| A5 | Verify/wire the Lane-B effect handler family for `glossary_*` MCP tool results → invalidate the `glossary` panel's query keys (entity list, counts). Extend if a `book_*`/existing handler doesn't already cover it. | `features/studio/host/*` (effect registry) | Shared registry; every Phase-B panel's LIVE gate depends on this existing before it can prove agent→MCP→DB→panel-realtime. |
| A6 | Fix the DOCK-7 route defect: `features/glossary-translate/StepConfig.tsx`'s `<Link to="/settings?tab=ai-models">` → `host.openPanel('settings', { params: { tab: 'providers' } })`. | `features/glossary-translate/StepConfig.tsx` | Small, but the translate wizard is invoked from multiple future panels — fix once at the root. |

**Phase A gate (must ALL pass before Phase B starts):** `glossary` panel is DOCK-1..11 compliant end-to-end (catalog+register+bus+self-title+route-decoupled+tests); JSON provider (A2) live-tested (open→edit→save round-trips through the real domain API); `ResolveKindModal` demonstrates the `FormDialog` adoption pattern; Lane-B wired; the one route defect fixed; `/review-impl` clean.

**✅ Phase A COMPLETE (2026-07-04).** A1 `useGlossaryEntity` hook extracted + `EntityEditorModal` migrated to raw `Dialog.*` (DOCK-9; custom-chrome precedent, documented in dockable-gui.md). A2 `loreweave.glossary-entity.v1` JSON provider (modal-scoped binding bridge, mirrors manuscript-unit's pattern; two-phase save with per-part conflict surfacing). A3 `GlossaryEntityList` extracted (DOCK-2, shared by `GlossaryTab` page + the new `glossary` dock panel); `glossary` panel added to `catalog.ts` **and** the agent `ui_open_studio_panel` enum (panelCatalogContract enforces openable-set == enum — this was NOT optional once the panel went palette-visible; contract regenerated via `WRITE_FRONTEND_CONTRACT=1 pytest`). A4 `ResolveKindModal` → `FormDialog` (the DOCK-9 precedent). A5 `glossaryEffect` Lane-B handler (`GLOSSARY_WRITE_PATTERN` regex, excludes reads) + `reloadBoundGlossaryEntity` (G7-guarded). A6 `StepConfig`'s settings link branches on `useOptionalStudioHost()` (new safe hook on `StudioHostProvider`) — `followStudioLink` inside the studio, plain `<Link>` outside; also fixed the link's stale target (`?tab=ai-models` → `/settings/providers`, matching `AddModelCta`'s pattern).

**⚠ NEW DEFERRED (found during A6, gate #1 — out of scope for this glossary effort):** `AddModelCta.tsx` (and its ~14 consumers incl. `PlannerPanel`, `CompositionPanel`, `ModelPicker`/`EmbeddingModelPicker`/`RerankModelPicker`) hand-rolls a plain `<Link>` to `/settings/providers` with NO studio-awareness — the exact DOCK-7 defect A6 just fixed locally, but already shipped inside at least the `planner` dock panel. Needs the same `useOptionalStudioHost()` + `followStudioLink` branch, applied once at the shared `AddModelCta` component (fixes all consumers in one place — do NOT patch each call site). Tracked here per the No-Defer-Drift gate (structural — touches a widely-adopted shared component, deserves its own scoped pass, not a piecemeal fix inside Phase A).

**Verify (2026-07-04):** full FE suite 524 files / 3628 tests green; `tsc --noEmit` clean; chat-service `test_frontend_tools_contract.py` 21/21 (contract regenerated + verified in both write and check mode); i18n parity clean for the new `glossary` keys across en/vi/ja/zh-TW (pre-existing unrelated gaps in other namespaces untouched). New test files: `useGlossaryEntity.test.tsx` (12), `entityDocument.test.ts` (15, incl. `reloadBoundGlossaryEntity`), `EntityEditorModal.test.tsx` (5), `GlossaryEntityList.test.tsx` (8), `GlossaryPanel.test.tsx` (4), `ResolveKindModal.test.tsx` (4), `glossaryEffects.test.ts` (22), `StepConfig.test.tsx` (2), `FormDialog.test.tsx` (+2), `dockablePanelHygiene.test.ts` (recursive scan + order-independent DOCK-9 check, /review-impl-fixed).

## Phase B — fanout (parallel, disjoint once Phase A lands)

| Slice | File(s) | Depends on Phase A |
|---|---|---|
| Panel: ontology management | `features/glossary/components/tiering/**` (ManageWorkspace + friends) → new `GlossaryOntologyPanel.tsx` + catalog row | A3's catalog-entry pattern; A5's Lane-B family |
| Panel: unknown-entity triage | `UnknownEntitiesPanel.tsx` + `useUnknownReview.ts` → new dock panel + catalog row | same |
| Panel: AI-suggestions inbox | `AiSuggestionsPanel.tsx` + `useAiSuggestions.ts` → new dock panel + catalog row | same |
| Panel: merge-candidate review | `MergeCandidatePanel.tsx` + `useMergeCandidates.ts` → new dock panel + catalog row | same |
| Modal → `FormDialog`: create-entity | `features/glossary/components/tiering/CreateEntityModal.tsx` | A4's precedent |
| Modal → `FormDialog`: extraction wizard (glossary invocation only) | `features/extraction/ExtractionWizard.tsx` (glossary call site) | A4's precedent |
| Modal → `FormDialog`: translate wizard | `features/glossary-translate/GlossaryTranslateWizard.tsx` | A4's precedent + A6 (Link fix already landed) |
| Modal → `FormDialog`: batch-translate | `features/glossary/components/BatchTranslateDialog.tsx` | A4's precedent |

Each slice gates independently per spec-12's 6-point cycle gate (catalog+register/bus, MCP audit — already satisfied per the earlier tool-inventory, Lane-B handler reuse from A5, realtime data layer, LIVE gate). **ONE combined verify + `/review-impl`** at Phase-B integration, per [[fanout-independent-slices-parallel-build-serial-integrate]] — not per-slice sign-off in isolation.

Entity revision history (`EntityHistoryPanel.tsx`) stays a tab inside the `EntityEditorModal` (already wired that way) — not promoted to its own panel this cycle; revisit only if a standalone use case appears.

**✅ Phase B COMPLETE (2026-07-04).** All 8 slices fanned out in parallel (8 subagents, genuinely disjoint files — 4 new panel files, 4 existing modal files, zero collisions), then integrated serially (this session, not the fanout agents): `GlossaryOntologyPanel`/`GlossaryUnknownPanel`/`GlossaryAiSuggestionsPanel`/`GlossaryMergeCandidatesPanel` added to `catalog.ts` + all 4 locale `studio.json` files + the `ui_open_studio_panel` BE enum (contract regenerated) — palette + agent openable, matching the `glossary` panel precedent. `CreateEntityModal`/`BatchTranslateDialog` migrated to `FormDialog` (simple template fit); `GlossaryTranslateWizard`/`ExtractionWizard` migrated to raw `Dialog.*` (both have a pinned step-indicator row FormDialog's template can't hold — the `EntityEditorModal` custom-chrome precedent). `GlossaryPanel`'s temporary internal view-switch (the Phase-A DOCK-8 exception) is GONE — `onOpenView` now calls `host.openPanel('glossary-ontology'|'glossary-unknown'|'glossary-ai-suggestions'|'glossary-merge-candidates')`, a real cross-panel jump, type-checked exhaustive via `Record<OtherGlossaryView, string>`.

**Integration fixes applied** (beyond the 8 agents' own scope, done during the serial integration pass): a small `mcpToolPrefixes` inconsistency on `GlossaryOntologyPanel` (missing vs. the other 3 siblings); `GlossaryPanel.test.tsx` rewritten (the 2 Phase-A tests asserting the temporary view-swap no longer apply — replaced with an `it.each` proving all 4 launchers call `host.openPanel` with the correct sibling id).

**Verify:** full FE suite 545 files / 3768 tests (1 unrelated failure in another track's uncommitted WIP — `VersionsPanel.test.tsx`, not part of this effort); `tsc --noEmit` clean; the 14 Phase-B-touched test files run in isolation: 112/112; BE `test_frontend_tools.py` + `test_frontend_tools_contract.py` + `test_agent_surface.py`: 74/74 (checked BOTH known snapshot locations this time, learning from the Phase-A gap where one was missed); i18n parity clean for the 4 new `glossary-*` key sets across en/vi/ja/zh-TW.

## Out of scope

- Relationships graph — lives in the Knowledge/KG-ontology tab, not glossary.
- Wiki pages — separate feature/route, only loosely related via shared entities.
- The extraction engine itself (shared with other entry points) — only the glossary invocation's modal shell is in scope, not `useExtractionState`/the wizard's shared step machinery.
- Server-sync of any new panel's layout (existing D6 localStorage convention applies).

## Testing discipline

Per [`00_OVERVIEW.md`](00_OVERVIEW.md): unit + E2E per panel/hook, `/review-impl` at Phase A close and at Phase B integration close. Phase B's cross-panel E2E (e.g. "back to list" from ontology) may defer to the debt stack until ≥2 Phase-B panels exist.
