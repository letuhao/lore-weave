# Plan — Studio v2 "Quality" tab (fill the stub)

Status: PLAN (size XL — full scope incl. new canon-issues backend, per user decision 2026-07-06)
Related: `docs/standards/dockable-gui.md` (DOCK-1..11), `docs/specs/2026-07-01-writing-studio/08_studio_state_architecture.md`

## 1. Problem

`ActivityView='quality'` in Writing Studio v2 is a type slot only — `StudioSideBar.tsx` renders a generic
"Coming soon" stub (`navStub.quality`). The Command Palette already advertises `palette.cmd.showQuality`
("Critic, promises & canon") with no backing command. Three of the four underlying capabilities already exist
as **working backend + frontend code** in the OLD composition workspace (a separate React tree Studio v2 cannot
reach); the fourth (itemized, book-wide canon issues) does not exist anywhere yet.

## 2. Scope decision (user, 2026-07-06)

Full build, all 4 capabilities, including new canon-issues backend work. Not phased.

## 3. Reality map (from CLARIFY research)

| Capability | Backend | Persisted & book-wide? | Existing FE (old workspace) |
|---|---|---|---|
| Promise ledger | `narrative_thread` table, `GET /works/{id}/narrative-threads` | Yes | `ThreadsPanel.tsx`, `useNarrativeThreads.ts` |
| Critic scores | `judge_prose`, `POST /works/{id}/quality-report` | No — per-chapter on-demand only | `QualityReportSection.tsx`, `useQualityReport.ts` |
| Promise coverage | `promise_audit.py` v2, `POST /works/{id}/promise-coverage` | No — book-wide on-demand | `BookPromiseCoverageSection.tsx`, `useBookPromiseCoverage.ts` |
| Canon issues (composition) | `canon_check.py`, result in `generation_job.result->canon`; `chapter_scene_gate` aggregates to COUNTS only | No itemized list | `CanonGatePanel.tsx` (transient, per-scene) |
| Canon issues (KG extraction) | `pass2_orchestrator.py` emits `job_logs` rows (`context->>'event'='pass2_canon_flag'`) | No itemized list (deferred `D-KG-CANON-FLAG-REVIEW-UI`) | none |

Key resolver already exists and is reusable as-is (DOCK-2): `useWorkResolution(bookId, token)`
(`frontend/src/features/composition/hooks/useWork.ts:7-13`) → `WorkResolution` (found/candidates/none +
`project_id`). Composition's `project_id` is a DISTINCT id from `book_id` (own `composition_work` row); this
hook is the ONLY sanctioned way to go bookId→projectId. `useBookKnowledgeProject(bookId)` is the equivalent
resolver for the knowledge-service `project_id` (already used by `KgOverviewPanel.tsx`).

## 4. Architecture

**Hub + sibling panels** (DOCK-8 — matches the Knowledge/Glossary precedent, not a monolithic tabbed panel):

- `quality` (hub, launcher only) — 4 static cards (Promises / Critic / Coverage / Canon), each
  `host.openPanel('quality-<x>')`. Resolves `useWorkResolution(host.bookId, token)` once to show a shared
  "no composition work for this book yet" empty state (mirroring `KgNoProjectState`) when `status !== 'found'`.
  Registers `useStudioPanel('quality', props.api)`.
- `quality-promises` — wraps a decoupled promise-list view over `useNarrativeThreads(projectId, token, status)`.
- `quality-critic` — wraps `QualityReportSection` (already decoupled) + a chapter picker (reuse the existing
  chapter-list source the Manuscript tree already has — do not invent a second one) + model resolution via the
  existing Chat/AI settings cascade (`[[chat-ai-settings-unify-cascade]]`), never a new ad hoc picker.
- `quality-coverage` — wraps `BookPromiseCoverageSection` (already decoupled) over `useBookPromiseCoverage`.
- `quality-canon` — NEW component, merges 2 NEW backend sources (below) into one list, grouped by source
  (Composition / Extraction), each row showing chapter/scene + violation text + a jump-to-chapter action.

**Bus/interaction**: clicking a canon violation or promise row that resolves to a chapter/scene calls
`host.focusManuscriptUnit(chapterId)` (existing action, `StudioFrame.tsx:121-127`) — no new bus event type
needed, this action already exists and does exactly "open this chapter in the editor".

**State tier**: Tier-5 (TanStack Query) only for all 5 panels — every data source here is read-only/diagnostic
("no accept/apply", confirmed in the source components' own comments), so no Tier-4 domain hoist is needed
despite `08_studio_state_architecture.md`'s `Quality scope (future) | (bookId, promiseId) | TBD` placeholder row.
That row can be resolved to "not needed" once this ships.

## 5. New backend work (the genuinely new part)

### 5a. composition-service — itemized canon issues

New repo method + router endpoint mirroring `outline.py::chapter_scene_gate`'s join (same base tables:
`generation_job` DISTINCT ON latest-per-scene JOIN `outline_node`) but returning ROWS instead of COUNTS:

`GET /works/{project_id}/canon-issues` → `{items: [{chapter_id, chapter_title, scene_id, scene_title, status,
violations: [...], resolved, iterations, job_id, created_at}]}`, filtered to jobs whose
`result->'canon'->>'status'` indicates unresolved/violated (mirror whatever enum `chapter_scene_gate` already
checks for "unresolved" — reuse its predicate, don't invent a new one).

### 5b. knowledge-service — itemized canon flags (closes `D-KG-CANON-FLAG-REVIEW-UI`)

New endpoint: `GET /internal/projects/{project_id}/canon-flags` (or a `/v1/...` public route behind
book-grant auth, matching this service's existing convention — check a sibling read endpoint before deciding)
→ `job_logs JOIN extraction_jobs ON job_logs.job_id = extraction_jobs.job_id WHERE extraction_jobs.project_id =
$1 AND job_logs.context->>'event' = 'pass2_canon_flag' ORDER BY job_logs.created_at DESC` → itemized
`{message, context: {source_type, source_id, entity_id, name, span, why}, created_at}` rows.

Both endpoints are pure new READ queries over EXISTING data — no new tables, no migration, no write path
changes. `quality-canon`'s frontend merges both lists.

## 6. Frontend wiring checklist (DOCK-1..11)

- [ ] 5 new catalog rows in `frontend/src/features/studio/panels/catalog.ts` (`quality`, `quality-promises`,
      `quality-critic`, `quality-coverage`, `quality-canon`) — id/component/titleKey/descKey/category/guideBodyKey.
- [ ] i18n: real `panels.quality*.title/desc/guideBody` keys (en authored; other 17 locales via the ML-7
      `scripts/i18n_translate.py` tool, never hand-edited) — replace/retire the now-obsolete `navStub.quality`
      placeholder copy once the hub is real, and wire `palette.cmd.showQuality` to actually open `quality`.
- [ ] `StudioSideBar.tsx`'s `quality` branch: replace the generic stub body with either (a) the same generic
      stub PLUS an "Open Quality" button calling `host.openPanel('quality')`, or (b) skip the sidebar rail
      entirely for Quality and only reach it via Command Palette/dock — confirm with a quick look at how
      `bible`/`search` behave today before deciding (don't invent inconsistent rail behavior across the 3 stub
      tabs without checking if they're being addressed too).
- [ ] Each sibling panel: `useStudioPanel(id, props.api, {...})` registration, `useWorkResolution`/
      `useBookKnowledgeProject` empty-state handling, thin wrapper over the reused hook/section (DOCK-2).
- [ ] DOCK-6: if any panel should be agent-openable via `ui_open_studio_panel`, add to
      `contracts/frontend-tools.contract.json` + `CLOSED_SET_ARGS`.
- [ ] DOCK-7 compliance: no `useParams`/`useNavigate`/`<Link>` in any new panel — `host.bookId` +
      `props.params` only.

## 7. Test plan

- Backend: unit tests for both new endpoints (empty/populated/tenancy-scoped), reusing the existing
  `chapter_scene_gate` test fixtures as a base for 5a.
- Frontend: one test per new panel (loading/empty/populated/error), `KnowledgeHubPanel.test.tsx`-style for the
  hub, `panelCatalogContract.test.ts` picks up the 5 new catalog rows automatically.
- Live E2E: open Quality hub → each sibling panel renders real data for a book with actual narrative_thread
  rows / a real canon flag in job_logs (use an existing dev-DB book/job rather than fabricating from empty).

## 8. Order of work

1. Backend 5a (composition-service) — new endpoint + tests.
2. Backend 5b (knowledge-service) — new endpoint + tests, closes `D-KG-CANON-FLAG-REVIEW-UI`.
3. Frontend: catalog + i18n scaffolding for all 5 panels (empty shells first, so the dock/palette wiring is
   provably correct before porting real content).
4. Frontend: `quality-promises`, `quality-coverage`, `quality-critic` (all pure ports, no new backend).
5. Frontend: `quality-canon` (new component, consumes 1+2).
6. `StudioSideBar` quality-branch decision + wiring.
7. Tests + live E2E + `/review-impl`.

Checkpoint at the end of each numbered step (risk boundary: new contract / new cross-service read / new panel
category) per the budget-driven cadence — not per sub-task.
