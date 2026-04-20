# Knowledge Service — Track 3 Implementation Plan

> **Status:** Implementation plan, ready to execute after Track 2 ships
> **Created:** 2026-04-13 (session 34)
> **Scope:** Track 3 (K19–K22 from [KNOWLEDGE_SERVICE_ARCHITECTURE.md §9](KNOWLEDGE_SERVICE_ARCHITECTURE.md))
> **Goal:** Power-user polish — Memory UI, tool calling, summary regeneration, privacy
>
> **Prerequisites:** Tracks 1 and 2 complete and stable.
> See [KNOWLEDGE_SERVICE_TRACK1_IMPLEMENTATION.md](KNOWLEDGE_SERVICE_TRACK1_IMPLEMENTATION.md)
> and [KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md](KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md).

---

## 1. Executive Summary

### What Track 3 delivers

Polish and power-user features on top of the working Track 1 + Track 2 system:

- **Full Memory UI** — power-user browser for every fact, entity, event, drawer
  with edit/delete/pin/trust actions
- **Extraction Jobs UI** — visual job management with progress, cost, history
- **Timeline view** — temporal browser for events and facts
- **Entities browser** — table view with drill-down and manual editing
- **Summary regeneration** — scheduled job that refreshes L0/L1 using recent
  content, with drift prevention rules
- **Tool calling integration** — LLMs can actively query the knowledge graph via
  `memory_search`, `memory_recall_entity`, `memory_timeline`, `memory_remember`,
  `memory_forget` tools during chat
- **Honest Privacy Model UI** — dedicated page explaining what's stored, where,
  and what users can do about it. Export/delete buttons.
- **Inline fact correction** — users can edit wrong facts without full rebuild

### What Track 3 explicitly does NOT include

| Out of scope | Why / Where |
|---|---|
| Wiki generation (D4-03) | Separate project — "Wiki" is its own feature, not memory |
| Timeline visualization as a standalone page | Track 3 has Timeline tab inside memory; a full standalone page is a Wiki/Story feature |
| Shared/collaborative memory between users | Never (hobby scope per KSA §7.7) |
| Memory across languages with auto-translation | Future; current design is per-language extraction |
| Fine-tuning extraction on user's own writing | Future enhancement, not core |
| AI-driven fact relationship discovery | Use LLM extractor (already in Track 2) |
| Graph visualization (force-directed network graph) | Aesthetic, not functional. Defer to future. |
| Cross-project entity "tunnels" | Open question — defer until needed |
| Memory quota per user for the instance | Phase 2 sharing concern, not hobby scope |

### Prerequisites before starting Track 3

- **Track 1 complete and stable** (K0-K9)
- **Track 2 complete and stable** (K10-K18)
- At least **2 weeks of real usage** on your own writing (validates that you
  actually want Track 3 features)
- Track 2 gates all passed (especially Gate 13 — Mode 3 end-to-end)

### What "done" looks like for Track 3

Ticking all boxes below means Track 3 is complete:

- [ ] User can open /knowledge page and see all 6 tabs
- [ ] Projects tab shows all 13 memory states (§8.4 state machine)
- [ ] Extraction Jobs tab shows running/paused/complete/failed jobs
- [ ] Global tab allows editing L0 identity with regenerate button
- [ ] Entities tab lists all entities with drill-down
- [ ] Timeline tab shows events chronologically with filters
- [ ] Raw drawers tab supports vector search + delete
- [ ] Mobile Memory UI works (simplified, read-mostly)
- [ ] Summary regeneration runs on schedule without drift
- [ ] Tool calling: LLM can call `memory_search` during chat and use results
- [ ] Privacy page shows honest model from KSA §7.7
- [ ] Export user data endpoint returns full JSON
- [ ] Delete user data endpoint cascades cleanly (Postgres + Neo4j + MinIO)
- [ ] Inline fact correction works (PATCH /v1/knowledge/facts/{id})
- [ ] All Track 3 integration tests pass

### Honest effort estimate

Track 3 is **mostly frontend** — big by volume but less risky than Track 2.
Tool calling and regeneration are the two backend touches.

| Phase | Effort | Why |
|---|---|---|
| K19a Projects tab + state cards | 8–12 hours | State machine UI, most important tab |
| K19b Extraction Jobs tab | 6–10 hours | Job list + detail + progress polling |
| K19c Global tab (L0 editor) | 4–6 hours | Simple textarea + regenerate button |
| K19d Entities tab | 10–15 hours | Table + drill-down + inline edit |
| K19e Timeline + Raw drawers | 12–18 hours | Two tabs, filtering, vector search UI |
| K19f Mobile Memory UI | 6–8 hours | Simplified variants of above |
| K20 Summary regeneration | 8–12 hours | Scheduled job + drift prevention rules |
| K21 Tool calling integration | 15–20 hours | Tool definitions + chat-service loop changes |
| K22 Privacy page + export/delete | 6–10 hours | Static content + wire up existing endpoints |
| **Integration + QC** | 10–15 hours | End-to-end UI tests, polish |
| **Total realistic** | **85–126 hours** | 4–6 weeks of evenings |

Less than Track 2, but more than Track 1. The biggest hidden cost is the
UI polish — making every state look good on desktop and mobile takes time.

---

## 2. Architecture Recap (Track 3 additions)

Track 3 doesn't add new services or databases. It adds:

- **Frontend feature expansion** — 6 tabs, extraction jobs page, mobile variants
- **Scheduled job** — summary regeneration (runs hourly/daily)
- **Tool calling loop in chat-service** — new flow where LLM can call memory tools mid-response
- **Dedicated privacy page** — static content from KSA §7.7

No new containers. No new databases. No new cross-service calls beyond what
Tracks 1/2 already established.

```
┌─────────────────────────────────────────────────────────┐
│ Frontend (Track 3 additions)                            │
│                                                         │
│  /knowledge page (Track 1 had just Projects list)       │
│   ├── Projects tab (K19a) — full state machine          │
│   ├── Extraction Jobs tab (K19b)                        │
│   ├── Global tab (K19c)                                 │
│   ├── Entities tab (K19d)                               │
│   ├── Timeline tab (K19e)                               │
│   ├── Raw drawers tab (K19e)                            │
│   └── Mobile variants (K19f)                            │
│                                                         │
│  /privacy page (K22) — honest model + data controls     │
└─────────┬───────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│ knowledge-service (Track 3 additions)                   │
│                                                         │
│  Existing endpoints (from Tracks 1+2)                   │
│                                                         │
│  + Scheduled job (K20): summary regeneration            │
│  + Fact correction endpoints (K22)                      │
│  + Tool endpoints for chat-service                      │
│    (memory_search, recall, timeline, remember, forget)  │
└─────────┬───────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│ chat-service (Track 3 additions)                        │
│                                                         │
│  K5 integration (Track 1) augmented with:               │
│  + Tool calling loop (K21)                              │
│    - LLM returns tool_calls in response                 │
│    - chat-service executes memory tool via              │
│      knowledge-service internal API                     │
│    - Tool result added to conversation                  │
│    - LLM continues generation                           │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Phase K19a — Projects Tab with State Cards

**Goal:** The most important memory UI tab — users see their projects with
clear state, can create/edit/delete, and trigger extraction jobs.

### Session 48 progress (2026-04-19)

| Sub-task | Status | Commit | Notes |
|---|---|---|---|
| K19a.1 route + page scaffold | ✅ | d14d71b | `/memory` → `/knowledge` end-to-end rename (URL + page + i18n namespace). Plan originally said NEW; actual work was rename of Track 1's MemoryPage to KnowledgePage. |
| K19a.1-placeholders (split from K19a.1) | ✅ | bab8829 | 4 placeholder tabs: Jobs / Entities / Timeline / Raw. Each renders a localized "Coming soon" card. 7-tab shell complete (incl. Projects / Global / Privacy). |
| K19a.2 TS discriminated union | ✅ | 70a3136 | `ProjectStateKind`, `ProjectMemoryState`, `VALID_TRANSITIONS`, `canTransition` in `features/knowledge/types/projectState.ts`. 22 tests including exhaustive edge-diff against KSA §8.4. BE-aligned supporting types (CostEstimate mirrors `EstimateResponse`, ExtractionJobSummary mirrors BE subset, etc.). |
| K19a.7 i18n labels skeleton (batched with K19a.2) | ✅ | 70a3136 | All 13 state labels + 14 action-button labels × 4 locales (en / ja / vi / zh-TW). Runtime coverage tests iterate every key path × every locale (192 assertions) — closes the vitest-mock bypass for this namespace. |
| K19a.3 ProjectStateCard + 13 subcomponents | ✅ | af4cefa | Dispatcher with exhaustive `never`-default switch; each card's own minimal typed Props; callback-prop pattern. 26 component tests (13 dispatcher variants + 13 behavior assertions incl. 8 callback-click tests, progressbar ARIA, canRetry toggle). Shared `StateCardShell`, `StateActionButton`, `ProgressBar`, `Spinner`. |
| K19a.4 useProjectState hook + graph-stats BE | ✅ | 5a726be | First Track 3 FS cycle. New `GET /v1/knowledge/projects/{id}/graph-stats` BE endpoint (Cypher UNION-ALL counting :Entity/:Fact/:Event/:Passage × 6 tests). Hook: derives state from `(Project, jobs, stats)`, polls `/extraction/jobs` at 2s while active, wires 11 of 14 callbacks; 3 toast-stubs pointing to K19a.5, 3 toast-stubs pointing to K19a.6. `ProjectCard.tsx` deleted, replaced by `ProjectRow.tsx`. 23 tests (15 `deriveState` + 8 `scopeOfJob`). |
| K19a.5 BuildGraphDialog + error viewer | ✅ | session 49 | Shipped: BuildGraphDialog (scope/llm/embedding/maxSpend form + debounced estimate + benchmark pre-flight gate + BE-detail error extractor) + ErrorViewerDialog (shared Failed/PausedError). 3 stubs replaced via ProjectRow dialog-state lift + actions merge. 100 FE tests (+25). 7 review-impl findings fixed in-cycle. 7 new D-K19a.5-* deferrals logged. |
| K19a.6 ProjectEditor extension | ✅ | session 49 | FS cycle. Shipped: NEW BE `POST /extraction/disable` (preserves graph, 5 tests) + ChangeModelDialog (destructive-warning + benchmark badge + same-model gate + cross-device no-op detection) + ConfirmDialog wraps for Delete (single) / Rebuild (double-confirm) / Disable (single). Fixed `updateEmbeddingModel` wrapper (confirm query param + typed response union). 2 stubs cleared (onChangeModel, onDisable). 114 FE + 5 BE tests. 7 review-impl findings fixed in-cycle (1 MED + 4 LOW + 2 COSMETIC). Monthly budget field stays deferred as D-K19a.5-03 (K19b.6). |
| K19a.7 i18n polish (remaining) | tail | — | Per-feature string review once K19a.5/6 land. |
| K19a.8 Storybook | optional | — | Plan says optional; skip unless state-machine bugs need visual debugging. |

**Deferred from session-48 review-impl (K19a.4 F4/F7/F8):**
- Polling scale — 2 queries × N projects, bounded by the 100-item pagination cap; consider an aggregator endpoint if pagination is ever removed.
- Multi-device race on paused/complete states — polling stops; external state changes on another client aren't auto-refreshed. Future: always-on low-cadence poll or SSE.
- Hook action-API test gap — the 11 real-action callbacks have no hook-level tests (`renderHook` + mocked `knowledgeApi` needed); only pure `deriveState` + `scopeOfJob` covered.

### Tasks

```
[ ] K19a.1 Route + page scaffold
    Files:
      - frontend/src/features/knowledge/pages/KnowledgePage.tsx (NEW)
      - frontend/src/routes.tsx (MODIFY — add /knowledge route)
    Description:
      Create /knowledge route with tabbed interface. Tabs: Projects,
      Extraction Jobs, Global, Entities, Timeline, Raw.
      Projects tab is default. Each tab lazy-loads (React.lazy).
    Acceptance criteria:
      - /knowledge renders with Projects tab active
      - Tab navigation works
      - Other tabs show "Coming soon" placeholder until K19b-e
    Test:
      - Manual: visit /knowledge
    Dependencies: Track 1 complete
    Est: S
    Notes:
      Keep this minimal. All the complexity is in the tab components.
```

```
[ ] K19a.2 Project state machine TypeScript types
    Files:
      - frontend/src/features/knowledge/types/projectState.ts (NEW)
    Description:
      Per KSA §8.4 — discriminated union type for all 13 project memory states.
      Include state transition helper functions (which states can transition to which).
    Acceptance criteria:
      - Type covers all 13 states
      - Transition function enforces valid moves
      - TypeScript compiler catches invalid transitions
    Test:
      - Type-check only
    Dependencies: K19a.1
    Est: M
    Notes:
      Reference KSA §8.4 state diagram. Don't skip states just because
      some are rare — all 13 can happen in practice.
```

```
[ ] K19a.3 ProjectStateCard component
    Files:
      - frontend/src/features/knowledge/components/ProjectStateCard.tsx (NEW)
      - frontend/src/features/knowledge/components/state_cards/*.tsx (NEW — one per state)
    Description:
      Main card component that renders different UI per state. Dispatches to
      a state-specific subcomponent:
        - DisabledCard (default, with "Build knowledge graph" button)
        - EstimatingCard (loading spinner)
        - ReadyToBuildCard (shows cost, confirm button)
        - BuildingRunningCard (progress bar, pause button)
        - BuildingPausedCard (resume/cancel buttons)
        - CompleteCard (stats, extract new / rebuild / disable buttons)
        - StaleCard ("new chapters pending, extract now")
        - FailedCard (error message, retry / delete buttons)
        - ModelChangePendingCard (warning + confirm)
        - CancellingCard / DeletingCard (spinner)
    Acceptance criteria:
      - Each state renders correct UI per KSA §8.4b examples
      - Buttons trigger correct API calls
      - Optimistic UI updates
    Test:
      - Visual/manual across all states (use Storybook or dev mock)
    Dependencies: K19a.2
    Est: L
    Notes:
      This is the biggest visual component in Track 3. Use shadcn/ui or
      the existing LoreWeave component library for consistency.
```

```
[ ] K19a.4 Projects list with state detection
    Files:
      - frontend/src/features/knowledge/components/ProjectsTab.tsx (NEW)
      - frontend/src/features/knowledge/hooks/useProjectState.ts (NEW)
    Description:
      Hook that fetches project + any active extraction job, derives the
      memory state (which of 13). Projects list renders ProjectStateCard
      for each, plus "Create new project" button.
    Acceptance criteria:
      - State detection accurate for all variations
      - Polling on running jobs (2s interval per KSA §6.3)
      - Loading state while fetching
    Test:
      - Manual with various project states
    Dependencies: K19a.3
    Est: M
```

```
[ ] K19a.5 Build knowledge graph dialog
    Files:
      - frontend/src/features/knowledge/components/BuildGraphDialog.tsx (NEW)
    Description:
      Modal triggered from DisabledCard. Contains:
        1. Scope selector (chapters / chat / all)
        2. LLM model dropdown (from provider-registry)
        3. Embedding model dropdown (curated list, bge-m3 default)
        4. Max spend input (with budget context: "You have $X monthly remaining")
        5. Cost estimate preview (calls /extraction/estimate)
        6. Confirm button → calls /extraction/start
    Acceptance criteria:
      - Dialog validates inputs
      - Cost estimate updates when scope or model changes
      - Confirm creates job and closes dialog
      - Error states handled gracefully
    Test:
      - Manual: trigger build, verify job appears in jobs tab
    Dependencies: K19a.4
    Est: L
```

```
[ ] K19a.6 Project edit panel
    Files:
      - frontend/src/features/knowledge/components/ProjectEditor.tsx (MODIFY from Track 1)
    Description:
      Extend Track 1 K8.5 editor with Track 2 fields:
        - Monthly budget field (optional)
        - Change embedding model (with warning dialog)
        - Delete graph (with confirm)
        - Rebuild from scratch (with double confirm)
    Acceptance criteria:
      - All actions wired to correct API endpoints
      - Destructive actions require confirmation
    Test:
      - Manual
    Dependencies: K19a.4
    Est: M
```

```
[ ] K19a.7 i18n strings
    Files:
      - frontend/public/locales/*/knowledge-projects-tab.json (NEW)
    Description:
      All strings for Projects tab + state cards + Build dialog.
      Plain-language labels per KSA §8.7 rules ("Static memory", not "Mode 2").
    Acceptance criteria:
      - No hardcoded strings
      - 4 languages translated
    Test:
      - Manual language switch
    Dependencies: K19a.3-K19a.6
    Est: M
```

```
[ ] K19a.8 Visual regression / Storybook (optional)
    Files:
      - frontend/src/features/knowledge/components/*.stories.tsx (NEW, optional)
    Description:
      Storybook entries for ProjectStateCard variants. Lets you visually
      verify all 13 states without having to reproduce each in the app.
    Acceptance criteria:
      - Each state has a Story
      - `npm run storybook` works
    Test:
      - Visual review
    Dependencies: K19a.3
    Est: M
    Notes:
      Optional. Only do this if the state machine has subtle bugs that
      need visual debugging. Otherwise skip.
```

### Gate 14 — Projects Tab Works

- [ ] All 13 project states render correctly
- [ ] Can create project via dialog
- [ ] Can trigger extraction from disabled state → runs end-to-end
- [ ] Progress updates in real time (polling)
- [ ] Pause/resume/cancel work from UI
- [ ] Rebuild from scratch works with confirmation
- [ ] Embedding model change shows warning
- [ ] Mobile view doesn't explode (even if simplified)

---

## 4. Phase K19b — Extraction Jobs Tab

**Goal:** Dedicated browser for all extraction jobs across all projects.
Shows running jobs prominently, history below.

### Tasks

```
[ ] K19b.1 Job list hook + API calls
    Files:
      - frontend/src/features/knowledge/hooks/useExtractionJobs.ts (NEW)
      - frontend/src/features/knowledge/api.ts (MODIFY — add listJobs)
    Description:
      Fetches all jobs for the user, grouped by status (running / paused /
      complete / failed). Running jobs poll at 2s, others at 10s.
    Acceptance criteria:
      - Returns grouped job list
      - Adaptive polling
      - React Query keys stable
    Test:
      - Manual
    Dependencies: Track 2 K16.5
    Est: S
```

```
[ ] K19b.2 ExtractionJobsTab layout
    Files:
      - frontend/src/features/knowledge/components/ExtractionJobsTab.tsx (NEW)
    Description:
      Layout per KSA §8.5:
        - Running section (highlighted, with progress bars)
        - Paused section (collapsed by default)
        - Complete section (collapsed, show last 10)
        - Failed section (highlighted if any)
        - Total cost summary (this month, all-time)
    Acceptance criteria:
      - Sections render correctly
      - Empty states when no jobs
      - Cost summary accurate
    Test:
      - Manual
    Dependencies: K19b.1
    Est: M
```

```
[ ] K19b.3 Job detail panel
    Files:
      - frontend/src/features/knowledge/components/JobDetailPanel.tsx (NEW)
    Description:
      Slide-over panel showing full job details when user clicks a row:
        - Full progress (items processed / total)
        - Cost breakdown
        - Current item being processed
        - Error message if failed
        - Cancel/pause/resume buttons
        - Log viewer (fetched on demand)
    Acceptance criteria:
      - Panel opens on click
      - All details visible
      - Actions work
    Test:
      - Manual
    Dependencies: K19b.2
    Est: M
```

```
[ ] K19b.4 Job progress bar component
    Files:
      - frontend/src/features/knowledge/components/JobProgressBar.tsx (NEW)
    Description:
      Reusable progress bar showing:
        - Percentage
        - Items processed
        - Cost spent / max
        - Estimated time remaining
    Acceptance criteria:
      - Animates smoothly on updates
      - Shows "paused" vs "running" state clearly
    Test:
      - Visual
    Dependencies: K19b.1
    Est: S
```

```
[ ] K19b.5 Retry failed job
    Files:
      - frontend/src/features/knowledge/components/JobDetailPanel.tsx (MODIFY)
    Description:
      For failed jobs, show "Retry with different settings" button that
      opens BuildGraphDialog pre-filled with the failed job's scope.
    Acceptance criteria:
      - Retry creates new job (doesn't modify old one)
      - Old failed job remains in history
    Test:
      - Manual
    Dependencies: K19b.3, K19a.5
    Est: S
```

```
[ ] K19b.6 Total cost widget
    Files:
      - frontend/src/features/knowledge/components/CostSummary.tsx (NEW)
    Description:
      Displays user's total AI spending:
        - This month: $X.XX
        - All time: $Y.YY
        - Budget: $Z.ZZ (if set) — with progress bar
        - Button to edit monthly budget
    Acceptance criteria:
      - Numbers match backend
      - Budget edit updates in real time
    Test:
      - Manual
    Dependencies: Track 2 K16.12
    Est: S
```

```
[ ] K19b.7 i18n strings
    Files:
      - frontend/public/locales/*/knowledge-jobs-tab.json (NEW)
    Description:
      All strings for jobs tab.
    Acceptance criteria:
      - 4 languages
    Test:
      - Manual
    Dependencies: K19b.2-K19b.6
    Est: S
```

### Gate 15 — Extraction Jobs Tab Works

- [ ] All job statuses visible
- [ ] Progress updates in real time
- [ ] Cost widget shows accurate figures
- [ ] Retry failed job works
- [ ] Job detail panel displays all info
- [ ] Mobile view doesn't break

---

## 5. Phase K19c — Global Tab (L0 Identity)

**Goal:** Simple editor for the user's global bio. Power-user-accessible
regenerate button (Track 3 K20 makes this work).

### Tasks

```
[ ] K19c.1 Global tab layout
    Files:
      - frontend/src/features/knowledge/components/GlobalTab.tsx (NEW)
    Description:
      Layout with:
        - Current bio display (read-only preview)
        - Large textarea for editing
        - Character count + token estimate
        - Save button (disabled if no changes)
        - Regenerate button (calls K20 endpoint)
        - Reset button (clears to empty, with confirm)
    Acceptance criteria:
      - Load current bio
      - Save updates backend + refreshes
      - Regenerate triggers job + shows progress
      - Reset confirms before acting
    Test:
      - Manual
    Dependencies: Track 1 K8.6
    Est: M
    Notes:
      Most of this exists from Track 1 K8.6. Track 3 adds regenerate + reset.
```

```
[ ] K19c.2 Regenerate button + modal
    Files:
      - frontend/src/features/knowledge/components/RegenerateBioDialog.tsx (NEW)
    Description:
      Clicking regenerate opens a dialog:
        - "This will analyze your recent chats and update your global bio."
        - "Estimated cost: $X.XX (small)"
        - "Will NOT override any manual edits within 30 days."
        - Confirm / cancel buttons
        - After confirm: calls POST /internal/summarize (K20)
        - Shows spinner while running
        - Updates bio field with new content
    Acceptance criteria:
      - Dialog renders
      - Cost estimate shown
      - User edit lock respected
      - New content displayed after regen
    Test:
      - Manual
    Dependencies: K20.x endpoints
    Est: M
```

```
[ ] K19c.3 Version history viewer
    Files:
      - frontend/src/features/knowledge/components/SummaryVersionHistory.tsx (NEW)
    Description:
      Shows previous versions of the bio (from knowledge_summaries.version column).
      User can view diff and rollback to a previous version.
    Acceptance criteria:
      - List versions with timestamps
      - Diff viewer (react-diff-viewer or similar)
      - Rollback updates current version
    Test:
      - Manual
    Dependencies: K19c.1
    Est: M
    Notes:
      The knowledge_summaries table already tracks version. Track 1 had
      the field but no UI for it.
```

```
[ ] K19c.4 Preferences section
    Files:
      - frontend/src/features/knowledge/components/GlobalTab.tsx (MODIFY)
    Description:
      Below the bio, show extracted preferences (from knowledge_entities
      where scope is global):
        - "You prefer formal prose"
        - "You write in Vietnamese"
        - Each with edit / delete action
    Acceptance criteria:
      - Loads user's global entities
      - Edit in place
      - Delete with confirm
    Test:
      - Manual
    Dependencies: Track 2 K18
    Est: M
    Notes:
      Only works once Track 2 is extracting facts. Without Track 2, this
      section is empty.
```

```
[ ] K19c.5 i18n
    Files:
      - frontend/public/locales/*/knowledge-global-tab.json (NEW)
    Est: S
```

### Gate 16 — Global Tab Works

- [ ] Bio loads, edits, saves
- [ ] Regenerate triggers K20 and shows new content
- [ ] Version history works
- [ ] Preferences section populated from Track 2 data

---

## 6. Phase K19d — Entities Tab

**Goal:** Browse and manage all extracted entities. Power-user feature for
fixing wrong extractions.

### Tasks

```
[ ] K19d.1 Entities table component
    Files:
      - frontend/src/features/knowledge/components/EntitiesTab.tsx (NEW)
      - frontend/src/features/knowledge/components/EntitiesTable.tsx (NEW)
    Description:
      Filterable, sortable table of entities:
        - Columns: Name, Kind, Project, Mention count, Confidence, Last seen
        - Filter by project dropdown
        - Filter by kind (character / location / concept / ...)
        - Search box (FTS on name + aliases)
        - Sort by column
        - Row click → opens detail panel
    Acceptance criteria:
      - Loads entities from new API endpoint
      - Filters + sort work server-side
      - Handles 1000+ rows without lag (virtualized)
    Test:
      - Manual with large fixture
    Dependencies: Track 2
    Est: L
```

```
[ ] K19d.2 New API endpoint: GET /v1/knowledge/entities
    Files:
      - services/knowledge-service/app/api/public/entities.py (NEW)
    Description:
      Public API for listing entities with filters. Query params:
        - project_id (optional)
        - kind (optional)
        - search (optional, FTS)
        - limit, offset (pagination)
      Returns: {entities: [EntityRow], total: int}
    Acceptance criteria:
      - JWT-authed
      - user_id filter enforced
      - Efficient paging
    Test:
      - Integration
    Dependencies: Track 2 K11.5
    Est: M
```

```
[ ] K19d.3 Entity detail panel
    Files:
      - frontend/src/features/knowledge/components/EntityDetailPanel.tsx (NEW)
    Description:
      Slide-over panel with:
        - Name, kind, aliases
        - Full description
        - All relations (subject/object) — list view
        - All facts mentioning this entity
        - All drawers (verbatim passages)
        - Provenance: which chapters / chat turns mention this
        - Edit buttons for name, kind, aliases
        - Delete button (with cascade warning)
    Acceptance criteria:
      - Lazy-loads relations/facts/drawers on open
      - Edits save to backend
      - Delete cascades correctly
    Test:
      - Manual
    Dependencies: K19d.2
    Est: L
```

```
[ ] K19d.4 New API: GET /v1/knowledge/entities/{id}
    Files:
      - services/knowledge-service/app/api/public/entities.py (MODIFY)
    Description:
      Returns full entity detail including:
        - Base entity fields
        - Relations (1-hop)
        - Facts (negative + positive)
        - Drawers (verbatim text)
        - Provenance (source chapters + chat turns)
      Uses Neo4j queries.
    Acceptance criteria:
      - Returns structured detail
      - Parameterized Cypher
    Test:
      - Integration
    Dependencies: Track 2 K11
    Est: M
```

```
[ ] K19d.5 Inline entity editing
    Files:
      - services/knowledge-service/app/api/public/entities.py (MODIFY)
    Description:
      - PATCH /v1/knowledge/entities/{id} — update name, kind, aliases, description
      - Marks entity as `user_edited = true` so extraction never overrides
    Acceptance criteria:
      - Updates Neo4j + Postgres cached stats
      - Future extractions respect user_edited flag
    Test:
      - Integration: edit entity, run extraction, verify edit preserved
    Dependencies: K19d.4
    Est: M
```

```
[ ] K19d.6 Entity merge (combine duplicates)
    Files:
      - services/knowledge-service/app/api/public/entities.py (MODIFY)
    Description:
      - POST /v1/knowledge/entities/{id}/merge-into/{other_id}
      - Merges relations and provenance from source into target
      - Deletes source entity
      - Target gets all source aliases
    Acceptance criteria:
      - No data lost (all relations preserved)
      - Canonical ID of target unchanged
      - UI updates after merge
    Test:
      - Integration: create 2 entities for same person, merge, verify
    Dependencies: K19d.5
    Est: M
    Notes:
      Common when extraction creates "Kai" and "Master Kai" as separate
      entities. User can fix with merge.
```

```
[ ] K19d.7 i18n
    Est: S
```

```
[ ] K19d.8 Entity visualization (optional, stretch)
    Files:
      - frontend/src/features/knowledge/components/EntityRelationsGraph.tsx (NEW)
    Description:
      Visual graph of entity's 1-hop and 2-hop relations using a lightweight
      lib like react-force-graph or vis.js. Read-only.
    Acceptance criteria:
      - Renders for main characters
      - Click on node → navigates to that entity
    Test:
      - Visual
    Dependencies: K19d.4
    Est: L
    Notes:
      Optional. Cool but not essential. Skip if time is tight.
```

### Gate 17 — Entities Tab Works

- [ ] Table loads entities with filtering/sorting
- [ ] Detail panel shows full entity info
- [ ] Inline edit updates data
- [ ] Merge combines duplicates
- [ ] Delete cascades correctly
- [ ] Mobile view handles list (details may be truncated)

---

## 7. Phase K19e — Timeline + Raw Drawers Tabs

**Goal:** Temporal browsing and verbatim text search.

### Tasks

```
[ ] K19e.1 Timeline tab layout
    Files:
      - frontend/src/features/knowledge/components/TimelineTab.tsx (NEW)
    Description:
      Per KSA §8.3. Shows events in chronological order, grouped by chapter:
        - Filters: project, entity, date range
        - Each event shows: description, source chapter, linked entities
        - Click event → navigates to source chapter in the editor
    Acceptance criteria:
      - Loads events from Neo4j
      - Filtering works
      - Navigation to source works
    Test:
      - Manual
    Dependencies: Track 2 K11.7
    Est: L
```

```
[ ] K19e.2 Timeline API endpoint
    Files:
      - services/knowledge-service/app/api/public/timeline.py (NEW)
    Description:
      GET /v1/knowledge/timeline?project_id=X&entity_id=Y&from=Z&to=W
      Returns: {events: [TimelineEvent], total: int}
      Events sorted by narrative_order (or chronological_order for time-based view).
    Acceptance criteria:
      - Filtering works
      - Pagination for long timelines (5000+ events)
      - User-scoped
    Test:
      - Integration
    Dependencies: Track 2 K11.7
    Est: M
```

```
[ ] K19e.3 Timeline visualization
    Files:
      - frontend/src/features/knowledge/components/TimelineView.tsx (NEW)
    Description:
      Vertical timeline with:
        - Date/chapter markers
        - Event cards
        - Color-coded by event type (action, dialogue, revelation)
      Keeps it simple — no interactive timeline visualizations like d3.
    Acceptance criteria:
      - Renders clearly
      - Scrollable for long timelines
      - Click expands event for more detail
    Test:
      - Manual
    Dependencies: K19e.1
    Est: M
```

```
[ ] K19e.4 Raw drawers tab layout
    Files:
      - frontend/src/features/knowledge/components/RawDrawersTab.tsx (NEW)
    Description:
      Shows verbatim text drawers (chunks) with:
        - Search box (semantic search via Track 2 embeddings)
        - Filter by project / source type (chapter / chat / glossary)
        - Each drawer shows: content preview, source, creation date
        - Click → full content in slide-over
    Acceptance criteria:
      - Search returns relevant drawers
      - Filtering works
      - Content preview readable
    Test:
      - Manual
    Dependencies: Track 2 K18
    Est: M
```

```
[ ] K19e.5 Drawer search API
    Files:
      - services/knowledge-service/app/api/public/drawers.py (NEW)
    Description:
      GET /v1/knowledge/drawers/search?project_id=X&query=Y&limit=Z
      Uses the same vector search as Track 2 L3. Query is embedded server-side.
    Acceptance criteria:
      - Returns ranked drawers
      - User-scoped
      - Respects project's embedding model
    Test:
      - Integration
    Dependencies: Track 2 K12.6, K18.3
    Est: M
```

```
[ ] K19e.6 Delete drawer
    Files:
      - services/knowledge-service/app/api/public/drawers.py (MODIFY)
    Description:
      DELETE /v1/knowledge/drawers/{id} — removes drawer + updates entity evidence counts
    Acceptance criteria:
      - Drawer deleted
      - Evidence count decremented
      - Entities with zero evidence cleaned up
    Test:
      - Integration
    Dependencies: Track 2 K11.8
    Est: S
```

```
[ ] K19e.7 Fact list (bonus — for Raw tab or new subtab)
    Files:
      - frontend/src/features/knowledge/components/FactsList.tsx (NEW)
    Description:
      Table of all facts (not drawers) with inline edit and delete.
      Per KSA §6.2 inline fact correction endpoints.
    Acceptance criteria:
      - Edit fact → marks user_edited
      - Delete fact → removes from Neo4j
      - Trust fact → bumps confidence to 1.0
    Test:
      - Manual
    Dependencies: Track 2 K17
    Est: M
```

```
[ ] K19e.8 Inline fact correction endpoints
    Files:
      - services/knowledge-service/app/api/public/facts.py (NEW)
    Description:
      Per KSA §6.2:
        - GET /v1/knowledge/facts/{id}
        - PATCH /v1/knowledge/facts/{id}
        - DELETE /v1/knowledge/facts/{id}
        - POST /v1/knowledge/facts/{id}/trust
        - POST /v1/knowledge/facts/{id}/never-extract
    Acceptance criteria:
      - All endpoints work
      - user_edited flag prevents future overrides
      - never-extract list respected by pattern + LLM extractors
    Test:
      - Integration
    Dependencies: Track 2 K11.7
    Est: M
```

```
[ ] K19e.9 i18n
    Est: S
```

```
[ ] K19e.10 Empty states + loading states
    Files:
      - All K19e components (MODIFY)
    Description:
      Polish: loading skeletons while fetching, empty states when no data,
      error states on fetch failure.
    Acceptance criteria:
      - Every async UI element has a loading + empty + error state
    Test:
      - Visual manual
    Dependencies: K19e.1-K19e.9
    Est: M
    Notes:
      Easy to skip but really important for UX polish.
```

### Gate 18 — Timeline + Raw Tabs Work

- [ ] Timeline loads events in order
- [ ] Filtering by project/entity/date works
- [ ] Raw drawers search returns relevant results
- [ ] Inline fact correction works (edit, delete, trust, never-extract)
- [ ] Entity merge combines duplicates correctly

---

## 8. Phase K19f — Mobile Memory UI

**Goal:** Simplified memory UI for phones. Read-heavy, simple edits only.

### Tasks

```
[ ] K19f.1 Mobile detection + responsive routing
    Files:
      - frontend/src/features/knowledge/pages/KnowledgePage.tsx (MODIFY)
    Description:
      At mobile breakpoint (<768px), render a simplified version:
        - No tabs — single-column scroll
        - Only Global + Projects + Extraction Jobs sections
        - Entity / Timeline / Raw tabs hidden (show "Use desktop for full features")
    Acceptance criteria:
      - Detects viewport width
      - Switches layout at breakpoint
    Test:
      - Manual on phone + DevTools mobile view
    Dependencies: K19a-K19e
    Est: M
```

```
[ ] K19f.2 Mobile Projects list
    Files:
      - frontend/src/features/knowledge/components/mobile/ProjectsMobile.tsx (NEW)
    Description:
      Stacked cards, one per project. Each shows:
        - Name, type, state badge
        - Build graph / view details buttons
      Tapping a project opens a full-screen detail page (not slide-over).
    Acceptance criteria:
      - Vertical card list scrolls well
      - Tap targets are 44px+ (per mobile cloud readiness rules)
    Test:
      - Manual
    Dependencies: K19f.1
    Est: M
```

```
[ ] K19f.3 Mobile Jobs list
    Files:
      - frontend/src/features/knowledge/components/mobile/JobsMobile.tsx (NEW)
    Description:
      Simplified job list. Running jobs on top with progress. Tap for details.
      No actions beyond pause/cancel (no retry with new settings — use desktop).
    Acceptance criteria:
      - Readable on phone
      - Actions work
    Test:
      - Manual
    Dependencies: K19f.1
    Est: M
```

```
[ ] K19f.4 Mobile Global bio editor
    Files:
      - frontend/src/features/knowledge/components/mobile/GlobalMobile.tsx (NEW)
    Description:
      Just the L0 bio textarea + save button. No regenerate, no version history
      (keep those on desktop for complex interactions).
    Acceptance criteria:
      - Textarea full-width
      - Save button visible without scrolling
    Test:
      - Manual
    Dependencies: K19f.1
    Est: S
```

```
[ ] K19f.5 Tap-target audit
    Files:
      - All mobile components (MODIFY)
    Description:
      Verify all interactive elements meet 44px minimum tap target. Use
      utility class .touch-target or equivalent.
    Acceptance criteria:
      - All buttons ≥44px
      - Adequate spacing between tappable elements
    Test:
      - Manual on phone
    Dependencies: K19f.2-K19f.4
    Est: S
```

### Gate 19 — Mobile UI Works

- [ ] Memory page readable on phone
- [ ] Core actions work (view, edit bio, trigger build, view jobs)
- [ ] No horizontal scrolling
- [ ] Tap targets adequate

---

## 9. Phase K20 — Summary Regeneration

**Goal:** Scheduled job that regenerates L0 (global) and L1 (project) summaries
using recent content, with drift prevention rules.

### Tasks

```
[ ] K20.1 Regeneration logic per KSA §7.6
    Files:
      - services/knowledge-service/app/jobs/regenerate_summaries.py (NEW)
    Description:
      Per KSA §7.6 — drift prevention rules. Main function:
        async def regenerate_project_summary(user_id, project_id):
          1. Check if user recently edited (<30 days) → skip
          2. Fetch recent chapters (last 10) + recent chat turns (last 50)
          3. Build LLM prompt asking for pure project summary
             (no preference inference)
          4. Call user's BYOK model via provider-registry
          5. Compute similarity with existing summary → if >95% similar, skip (no-op)
          6. Write new version with incremented version number
    Acceptance criteria:
      - User edit lock respected
      - Diversity check prevents redundant regens
      - Summary written as new version (old preserved)
      - Metrics: summary_regen_count, summary_regen_no_op, summary_user_override_respected
    Test:
      - Integration with mocked LLM
    Dependencies: Track 2
    Est: L
```

```
[ ] K20.2 Global L0 regeneration
    Files:
      - services/knowledge-service/app/jobs/regenerate_summaries.py (MODIFY)
    Description:
      Similar to K20.1 but for global scope:
        - Uses all recent chat turns (across all projects, last 100)
        - Different prompt focusing on user identity, not project
        - Same drift prevention rules
    Acceptance criteria:
      - Global vs project summaries don't mix
      - User preferences extracted conservatively (3+ instances required)
    Test:
      - Integration
    Dependencies: K20.1
    Est: M
```

```
[ ] K20.3 Scheduled job runner
    Files:
      - services/knowledge-service/app/jobs/scheduler.py (NEW)
    Description:
      APScheduler or similar. Runs:
        - Project summary regeneration: every 24 hours for projects with
          recent activity (20+ new turns since last regen)
        - Global summary regeneration: weekly for active users
      Skips inactive projects/users (no need to regen).
    Acceptance criteria:
      - Cron-like schedule works
      - Handles worker restart (picks up missed runs)
      - Logs all runs
    Test:
      - Integration with fake clock
    Dependencies: K20.1, K20.2
    Est: M
```

```
[ ] K20.4 Internal API: POST /internal/summarize
    Files:
      - services/knowledge-service/app/api/internal/summarize.py (NEW)
    Description:
      Per KSA §6.1 — allows manually triggering regeneration for a scope.
      Called by frontend "Regenerate" button (K19c.2).
    Acceptance criteria:
      - Body: {user_id, scope_type, scope_id, model_source, model_ref}
      - Returns new summary on success
      - Handles user_edit lock (returns 409 if recent edit)
    Test:
      - Integration
    Dependencies: K20.1, K20.2
    Est: S
```

```
[ ] K20.5 Version history support
    Files:
      - services/knowledge-service/app/db/repositories/summaries.py (MODIFY)
    Description:
      Extend summaries repo with:
        - list_versions(user_id, scope_type, scope_id) → all past versions
        - rollback_to_version(user_id, scope_type, scope_id, version_id)
    Acceptance criteria:
      - Past versions accessible
      - Rollback creates new version with old content (doesn't delete)
    Test:
      - Integration
    Dependencies: K20.1
    Est: S
    Notes:
      Frontend K19c.3 depends on this.
```

```
[ ] K20.6 Summary quality guardrails
    Files:
      - services/knowledge-service/app/jobs/regenerate_summaries.py (MODIFY)
    Description:
      Validate LLM output before accepting:
        - Must be plain text (no JSON, no markdown artifacts)
        - Must be within token budget (≤500 tokens)
        - Must not contain injection patterns (K15.6 neutralize)
        - Must not be identical to an existing past version
    Acceptance criteria:
      - Invalid outputs rejected, logged, retried once
      - After 2 failures, summary is not updated (keeps old)
    Test:
      - Unit with bad LLM outputs
    Dependencies: K20.1, K15.6
    Est: M
```

```
[ ] K20.7 Observability
    Files:
      - services/knowledge-service/app/jobs/regenerate_summaries.py (MODIFY)
    Description:
      All metrics from KSA §7.6:
        - summary_regen_count{scope_type}
        - summary_regen_no_op{scope_type}
        - summary_user_override_respected{scope_type}
        - summary_regen_duration_seconds
        - summary_regen_cost_usd (tracks BYOK cost)
    Acceptance criteria:
      - Metrics exposed via /metrics
      - Cost recorded per job
    Test:
      - Check /metrics output
    Dependencies: K20.1
    Est: S
```

```
[ ] K20.8 Integration test: drift scenario
    Files:
      - services/knowledge-service/tests/integration/test_summary_drift.py (NEW)
    Description:
      Validates the KSA §7.6 echo chamber prevention:
        1. Seed L1 summary "User prefers formal prose"
        2. Seed 20 chat turns in formal prose (reinforcing)
        3. Seed 1 chat turn in modern prose (user experimenting)
        4. Run regeneration
        5. Assert new summary is NOT more extreme (doesn't say "user exclusively writes formal")
        6. Assert that if user manually edits to "experimenting with modern", auto-regen is skipped for 30 days
    Acceptance criteria:
      - Drift prevented
      - User edit lock works
    Test:
      - This IS the test
    Dependencies: K20.1
    Est: M
```

### Gate 20 — Summary Regeneration Works

- [ ] Scheduled job runs on cron
- [ ] Drift scenario test passes
- [ ] User edit lock respected
- [ ] Diversity check prevents no-op writes
- [ ] Cost tracked per regeneration
- [ ] Version history accessible via API

---

## 10. Phase K21 — Tool Calling Integration

**Goal:** LLMs can actively call memory tools during a chat response (not just
receive context upfront). Enables queries like "Let me check what we know
about Kai first..." with the LLM autonomously searching memory.

### Tasks

```
[ ] K21.1 Tool definitions (OpenAI function-calling format)
    Files:
      - services/knowledge-service/app/tools/definitions.py (NEW)
    Description:
      Define tool schemas:
        - memory_search: {query, project_id, limit, types} → list of results
        - memory_recall_entity: {entity_name, project_id} → entity detail
        - memory_timeline: {project_id, from_date, to_date, entity_id} → events
        - memory_remember: {user_id, project_id, fact_text, fact_type} → fact stored
        - memory_forget: {fact_id} → invalidates fact
      Each tool has:
        - name (for LLM)
        - description (for LLM to know when to call)
        - parameters (JSON schema)
    Acceptance criteria:
      - Valid OpenAI tool schema
      - Descriptions are clear (helps LLM choose the right tool)
    Test:
      - Unit: validate schema with jsonschema
    Dependencies: Track 2 K11, K18
    Est: M
```

```
[ ] K21.2 Tool executor (calls knowledge-service functions)
    Files:
      - services/knowledge-service/app/tools/executor.py (NEW)
    Description:
      Given a tool_call from the LLM, execute the corresponding function:
        - memory_search → vector search + keyword match
        - memory_recall_entity → get_entity + relations
        - memory_timeline → list events with filters
        - memory_remember → write fact (user-confirmed)
        - memory_forget → invalidate fact
      Return result as JSON suitable for feeding back to the LLM.
    Acceptance criteria:
      - Each tool executes correctly
      - Results capped in size (don't overflow context)
      - Errors wrapped (tool failure doesn't crash chat)
    Test:
      - Integration: each tool in isolation
    Dependencies: K21.1, Track 2 repos
    Est: L
```

```
[ ] K21.3 Internal API: /internal/tools/execute
    Files:
      - services/knowledge-service/app/api/internal/tools.py (NEW)
    Description:
      POST /internal/tools/execute
      Body: {user_id, project_id, tool_name, tool_args}
      Returns: {success, result, error?}
      Called by chat-service when LLM returns a tool_call.
    Acceptance criteria:
      - Internal-only (X-Internal-Token)
      - user_id derived from authenticated context (not from body)
      - All tools accessible
    Test:
      - Integration
    Dependencies: K21.2
    Est: M
```

```
[ ] K21.4 chat-service: tool calling loop
    Files:
      - services/chat-service/app/services/stream_service.py (MODIFY)
    Description:
      Update the LLM invocation to support tool calling:
        1. Include memory tool definitions in request to LLM
        2. When LLM returns tool_calls in response:
           a. Execute each via K21.3
           b. Add tool_call + tool_result to message history
           c. Re-invoke LLM with updated history
        3. Loop until LLM returns a text-only response
        4. Max iterations: 5 (prevent infinite loops)
        5. Stream the final text response to user (tool calls happen
           behind the scenes; user sees "thinking" indicator)
    Acceptance criteria:
      - Tool calling loop works for 1-5 tool calls
      - Max iteration limit enforced
      - Streaming resumes after tool execution
      - Errors during tool execution don't crash chat
    Test:
      - Integration: prompt that triggers a tool call, verify end-to-end
    Dependencies: K21.3
    Est: L
    Notes:
      Not all LLMs support tool calling. Check model capability before
      including tools in request. Use LiteLLM's function_calling support.
```

```
[ ] K21.5 Tool call UI indicator
    Files:
      - frontend/src/features/chat/components/ChatMessage.tsx (MODIFY)
    Description:
      When a message contained tool calls, show a subtle indicator:
        - "🔍 Searched memory"
        - "📚 Recalled 3 entities"
        - "📅 Viewed timeline"
      Clicking shows details (which tool, what args, what result).
    Acceptance criteria:
      - Indicator visible but not distracting
      - Details panel shows tool call history
    Test:
      - Manual
    Dependencies: K21.4
    Est: M
```

```
[ ] K21.6 Tool call persistence in chat_messages
    Files:
      - services/chat-service/app/migrations/NNN_tool_calls.py (NEW)
      - services/chat-service/app/services/stream_service.py (MODIFY)
    Description:
      Add column to chat_messages: tool_calls JSONB.
      Stores the tool call history for UI replay.
    Acceptance criteria:
      - Migration applies
      - Tool calls saved with message
      - UI can replay them
    Test:
      - Integration
    Dependencies: K21.4
    Est: S
```

```
[ ] K21.7 Guardrails on memory_remember
    Files:
      - services/knowledge-service/app/tools/executor.py (MODIFY)
    Description:
      LLM calling memory_remember can inject arbitrary facts. Safeguards:
        1. Marked as confidence=0.7 (below Pass 2's 0.9)
        2. Marked as source_type='llm_tool_call'
        3. Rate limited: max 10 facts per chat session
        4. User confirmation optional (opt-in per project setting)
    Acceptance criteria:
      - LLM can remember facts but they're clearly marked
      - Rate limit enforced
      - Facts appear in Entities tab with source_type visible
    Test:
      - Integration
    Dependencies: K21.2
    Est: M
    Notes:
      Prevents a chatty LLM from polluting memory. User can review in
      Entities tab and clean up.
```

```
[ ] K21.8 Tool call metrics
    Files:
      - services/knowledge-service/app/tools/executor.py (MODIFY)
    Description:
      Metrics:
        - tool_calls_total{tool_name}
        - tool_call_duration_seconds{tool_name}
        - tool_call_result_size_bytes{tool_name}
        - memory_remember_rate_limited_total
    Acceptance criteria:
      - All metrics exposed
    Test:
      - Manual /metrics check
    Dependencies: K21.2
    Est: S
```

```
[ ] K21.9 Integration test: tool calling loop
    Files:
      - services/knowledge-service/tests/integration/test_tool_calling.py (NEW)
    Description:
      End-to-end test:
        1. Create project with extracted data (from Track 2)
        2. Send a chat message that should trigger memory_search
           (e.g., "What do we know about Kai?")
        3. Mock LLM to return a tool_call for memory_search
        4. Execute tool, feed result back
        5. Mock LLM to return final text response
        6. Verify: tool was called, result was used, final message streamed
    Acceptance criteria:
      - Full flow works
      - Tool calls persisted in chat_messages
      - UI indicator shows
    Test:
      - This IS the test
    Dependencies: K21.4-K21.8
    Est: L
```

```
[ ] K21.10 Max iteration safety
    Files:
      - services/chat-service/app/services/stream_service.py (MODIFY)
    Description:
      Enforce max 5 tool-calling iterations per chat turn. After 5, if LLM
      still wants to call tools, force it to stop and return a text response
      with a note: "I hit my tool call limit. Here's what I found so far..."
    Acceptance criteria:
      - Limit enforced
      - User sees helpful message
      - No infinite loops
    Test:
      - Integration with mock LLM that always returns tool_calls
    Dependencies: K21.4
    Est: S
```

```
[ ] K21.11 Provider capability check
    Files:
      - services/chat-service/app/clients/provider_client.py (MODIFY)
    Description:
      Before including tool definitions in LLM request, check if the
      provider/model supports tool calling. LiteLLM has this info.
      If not supported, skip tools (model uses upfront memory only).
    Acceptance criteria:
      - Non-tool-capable models don't crash
      - Log which models don't support tools
    Test:
      - Manual with different providers
    Dependencies: K21.4
    Est: S
```

```
[ ] K21.12 Tool calling opt-out (user preference)
    Files:
      - services/knowledge-service/app/api/public/projects.py (MODIFY)
    Description:
      Add project setting: `tool_calling_enabled: bool = true`
      User can disable per project if they don't want the LLM autonomously
      calling memory (e.g., for deterministic output, or cost control).
    Acceptance criteria:
      - Toggle in project settings
      - chat-service respects the flag
    Test:
      - Integration
    Dependencies: K21.4
    Est: S
```

### Gate 21 — Tool Calling Works

- [ ] LLM can call memory_search and get results
- [ ] memory_recall_entity returns entity detail
- [ ] memory_timeline returns events
- [ ] memory_remember writes rate-limited facts
- [ ] memory_forget invalidates facts
- [ ] Chat shows tool call indicator
- [ ] Max iteration safety enforced
- [ ] Non-tool-capable models fall back gracefully

---

## 11. Phase K22 — Privacy Page + Export/Delete Polish

**Goal:** User-facing privacy content with actual working data controls.

### Tasks

```
[ ] K22.1 Privacy page route + layout
    Files:
      - frontend/src/pages/PrivacyPage.tsx (NEW)
      - frontend/src/routes.tsx (MODIFY — add /privacy)
    Description:
      Static content derived from KSA §7.7 "Trust Me" model. Sections:
        - The Commitment (honest statement)
        - What Actually Happens to Your Content (data flow)
        - Data Flow Diagram (visual)
        - Your Rights (export, delete, inspect, edit)
        - What We Don't Do (no SOC 2, no BAA, etc.)
        - What We Do Instead (open source, self-hostable, BYOK)
        - Sharing with Friends (Phase 2 notes)
    Acceptance criteria:
      - All KSA §7.7 content present
      - Clean, readable layout
      - Diagram renders (can be SVG or mermaid-rendered)
    Test:
      - Visual
    Dependencies: none
    Est: M
```

```
[ ] K22.2 Export My Data button
    Files:
      - frontend/src/pages/PrivacyPage.tsx (MODIFY)
      - frontend/src/features/knowledge/api.ts (MODIFY — add exportUserData)
    Description:
      Button triggers:
        1. Confirmation dialog: "This will download all your LoreWeave data as JSON. May take a minute."
        2. Calls GET /v1/knowledge/user-data/export (from Track 1 K7.5)
        3. Shows progress / spinner
        4. Offers download when ready
    Acceptance criteria:
      - Download triggers browser save
      - Large exports don't crash browser (stream if possible)
      - Handles errors (network timeout, etc.)
    Test:
      - Manual
    Dependencies: Track 1 K7.5
    Est: M
```

```
[ ] K22.3 Delete My Data button
    Files:
      - frontend/src/pages/PrivacyPage.tsx (MODIFY)
    Description:
      Button triggers:
        1. Warning dialog with double-confirm (type "DELETE" to proceed)
        2. Calls DELETE /v1/knowledge/user-data (Track 1 K7.6)
        3. Shows deletion progress
        4. Logs out user after completion
    Acceptance criteria:
      - Double-confirm prevents accidents
      - Deletion cascade works (Track 1 K7.6 + Track 2 additions)
      - User logged out
    Test:
      - Manual (use a test account!)
    Dependencies: Track 1 K7.6
    Est: M
```

```
[ ] K22.4 Enhanced delete cascade (Track 3 additions)
    Files:
      - services/knowledge-service/app/api/public/user_data.py (MODIFY)
    Description:
      Track 1's delete cascade only covered knowledge-service data. Track 3
      extends it to delete:
        - All Neo4j data (entities, events, facts, drawers, sources)
        - All MinIO audio segments
        - All extraction_jobs history
        - BYOK credentials in provider-registry (via internal call)
        - Chat sessions + messages (via internal call to chat-service)
        - Book content + chapters (via internal call to book-service)
        - Glossary entries owned by user (via internal call to glossary-service)
        - Auth/user row (via internal call to auth-service)
      This is TRUE GDPR erasure.
    Acceptance criteria:
      - All services report successful deletion
      - Verification endpoint confirms no orphaned data
      - Transactional if possible, idempotent otherwise
    Test:
      - Integration: create user with full data, delete, verify all services
        report zero rows for that user_id
    Dependencies: All previous tracks
    Est: L
    Notes:
      This is a cross-service operation. Use a distributed transaction
      pattern or a compensating workflow. Don't let a failure in one
      service leave partial data.
```

```
[ ] K22.5 Deletion verification endpoint
    Files:
      - services/knowledge-service/app/api/public/user_data.py (MODIFY)
    Description:
      GET /v1/knowledge/user-data/deletion-status
      After calling DELETE /user-data, user can call this to verify all
      services report zero data for them.
    Acceptance criteria:
      - Queries each service's internal "count user data" endpoint
      - Returns {service: count} map
      - Non-zero counts indicate incomplete deletion
    Test:
      - Integration
    Dependencies: K22.4
    Est: M
```

```
[ ] K22.6 Privacy page i18n
    Files:
      - frontend/public/locales/*/privacy.json (NEW)
    Description:
      Translate all privacy page content. This is a lot of text —
      carefully translated for legal clarity.
    Acceptance criteria:
      - All 4 languages
      - Legal meaning preserved (review manually)
    Test:
      - Manual review by someone fluent in each language (or careful MT)
    Dependencies: K22.1
    Est: L
```

### Gate 22 — Privacy Page Works

- [ ] /privacy page accessible and readable
- [ ] Export downloads full user data
- [ ] Delete cascades across all services
- [ ] Deletion verification confirms completeness
- [ ] Mobile version readable
- [ ] Translated to 4 languages

---

## 12. Integration Test Scenarios (Track 3)

Track 3 specific tests. Many leverage existing UI testing infra.

```
T21: Projects tab renders all 13 states
    Tool: Storybook or visual regression test
    Steps:
      1. Seed project in each of 13 states
      2. Visit /knowledge → Projects tab
      3. Screenshot each card
      4. Compare to expected images
    [ ] Pass

T22: Extraction Jobs tab shows running + completed jobs
    Steps:
      1. Start one extraction job (running)
      2. Complete one previous job
      3. Visit /knowledge → Extraction Jobs tab
      4. Assert both visible in correct sections
      5. Assert progress updates in real time
    [ ] Pass

T23: Global bio regeneration respects user edit lock
    Steps:
      1. User edits bio manually, saves
      2. Try to trigger auto-regen → should skip (user_edit_lock active)
      3. Wait 30 days (fake clock) → auto-regen allowed
      4. Verify user edit is respected for 30 days
    [ ] Pass

T24: Entity merge combines duplicates
    Steps:
      1. Create 2 entities: "Kai" and "Master Kai"
      2. POST /v1/knowledge/entities/{kai_id}/merge-into/{master_kai_id}
      3. Assert: Kai's relations now on Master Kai
      4. Assert: Kai's aliases on Master Kai
      5. Assert: Kai entity deleted
    [ ] Pass

T25: Tool calling loop: memory_search → response
    Steps:
      1. Create project with extracted data
      2. Send chat: "What do we know about Kai?"
      3. Mock LLM to return tool_call for memory_search({query: "Kai"})
      4. Chat-service executes, gets results
      5. Mock LLM to return text response incorporating results
      6. Assert: final text response contains entity info
      7. Assert: chat_messages row has tool_calls field populated
    [ ] Pass

T26: Tool call max iteration safety
    Steps:
      1. Mock LLM to always return tool_calls (infinite loop)
      2. Send chat message
      3. Assert: chat-service stops after 5 iterations
      4. Assert: user sees "hit my tool call limit" message
      5. Assert: no actual infinite loop
    [ ] Pass

T27: Export user data contains all content
    Steps:
      1. User has projects, chats, extracted entities
      2. GET /v1/knowledge/user-data/export
      3. Parse returned JSON
      4. Assert: contains projects, summaries, entities, facts, events
    [ ] Pass

T28: Delete cascade across services
    Steps:
      1. Create user with data in all services
      2. DELETE /v1/knowledge/user-data
      3. Assert: all services report 0 rows for this user
      4. Assert: Neo4j has 0 nodes for this user
      5. Assert: MinIO has 0 objects for this user
    [ ] Pass

T29: Fact edit marked as user_edited
    Steps:
      1. Pass 2 extraction creates a fact
      2. PATCH /v1/knowledge/facts/{id}
      3. Re-run Pass 2 extraction on same source
      4. Assert: user-edited fact is preserved, not overridden
    [ ] Pass

T30: Timeline filters work
    Steps:
      1. Seed events across 5 chapters
      2. GET /v1/knowledge/timeline?project_id=X&from=ch3&to=ch5
      3. Assert: only events from ch3-5 returned
      4. Assert: sorted by narrative_order
    [ ] Pass
```

### Smoke tests (manual)

```
S01: Power user workflow
  1. Open /knowledge
  2. Create project, build knowledge graph, wait for extraction
  3. Open Entities tab, find a miscategorized entity
  4. Edit kind from "character" to "location"
  5. Open chat with that project
  6. Ask about the entity
  7. Verify the edit is reflected in the response
  [ ] Pass

S02: Mobile memory workflow
  1. Open /knowledge on phone
  2. View projects list
  3. Tap a project → detail page
  4. Trigger extraction (with desktop for config)
  5. Check progress from phone
  [ ] Pass

S03: Privacy workflow
  1. Open /privacy
  2. Read through all content
  3. Export data → download works
  4. (On test account) delete data → logged out, data gone
  [ ] Pass
```

---

## 13. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Tool calling loops run up BYOK costs | Medium | High | Max 5 iterations (K21.10), rate limit on memory_remember (K21.7) |
| Entity merge loses data | Low | Medium | Transactional merge, test T24 |
| Delete cascade leaves orphans | Medium | High | Verification endpoint (K22.5), compensating logic (K22.4) |
| Summary regen contradicts user's intent | Medium | Medium | Drift prevention rules (K20.1), user edit lock, diversity check |
| Mobile UI unusable on small phones | Medium | Low | 44px tap targets, simplified layout |
| LLM ignores tool call results | Low | Medium | Test T25, prompt engineering |
| Version history table grows unbounded | Low | Low | Add retention policy (keep last 20 versions) |
| Tool call results too large for context | Medium | Medium | Cap result size in K21.2, paginate |
| Non-tool-capable models crash | Low | Medium | Capability check (K21.11) |
| User accidentally deletes all data | Medium | Critical | Double-confirm (K22.3), export reminder before delete |
| Privacy page translations lose legal meaning | Medium | Low | Manual review per language |

---

## 14. Phase Dependencies

```
Prerequisites:
  Track 1 complete ──────────────┐
  Track 2 complete ──────────────┤
                                 ▼

Frontend (can run in parallel after Track 2):
  K19a Projects tab ─────────────┐
  K19b Jobs tab ──────────────────┤
  K19c Global tab ────────────────┤
  K19d Entities tab ──────────────┤
  K19e Timeline + Raw tab ────────┤
  K19f Mobile ────────────────────┤
                                  │
Backend (some parallel):         │
  K20 Summary regeneration ───────┤
  K22 Privacy + Delete cascade ───┤
                                  │
  K21 Tool calling ───────────────┤  (depends on Track 2 data)
                                  ▼
                            Gate 22 — Ship Track 3
```

Most Track 3 phases are independent and can ship incrementally. Unlike
Track 2, there's no strict serial order — ship what's ready.

---

## 15. Getting Started Checklist (Day 1 of Track 3)

- [ ] Confirm Tracks 1 + 2 fully shipped and stable
- [ ] Confirm you've used Track 2 in real writing for 2+ weeks
- [ ] Re-read KSA §7.6 (regeneration), §8 (UI), KSA open questions
- [ ] Pick ONE phase to start (recommend K19a Projects tab for highest user value)
- [ ] Create branch: `git checkout -b feature/knowledge-service-track3`
- [ ] Update SESSION_PATCH.md
- [ ] Start with K19a.1

---

## 16. Progress Tracking

```
K19a Projects tab         [ / 8  tasks]  Gate 14: [ ]
K19b Extraction Jobs tab  [ / 7  tasks]  Gate 15: [ ]
K19c Global tab           [ / 5  tasks]  Gate 16: [ ]
K19d Entities tab         [ / 8  tasks]  Gate 17: [ ]
K19e Timeline + Raw       [ / 10 tasks]  Gate 18: [ ]
K19f Mobile               [ / 5  tasks]  Gate 19: [ ]
K20 Summary regeneration  [ / 8  tasks]  Gate 20: [ ]
K21 Tool calling          [ / 12 tasks]  Gate 21: [ ]
K22 Privacy + delete      [ / 6  tasks]  Gate 22: [ ]

Integration tests         [ / 10 tests]  (T21-T30)
Smoke tests               [ / 3  tests]  (S01-S03)

Total Track 3 tasks: 69
```

---

## 17. After Track 3 Ships

When all gates pass and tests are green:

1. **Commit final state:** "feat(knowledge): Track 3 complete — power-user UI + tool calling + regeneration + privacy"
2. **Write retrospective:** `docs/sessions/TRACK3_RETRO.md`
3. **Consider what's next.** Track 3 completes the KSA roadmap. Options:
   - **Use it.** Write novels. Let the system work. You're done.
   - **Wiki generation.** A standalone "Wiki" feature that reads the knowledge
     graph and produces browsable entity pages. This is KSA D4-03 territory
     and would be a new document + phase plan.
   - **Timeline visualization as its own page.** Extract the Timeline tab
     into a dedicated story-view feature.
   - **Cross-project entities.** Solve the open question from KSA §12.
   - **Open source release.** Clean up the repo, write a proper README,
     publish. Your architecture docs become its technical foundation.

**Remember:** Track 3 is polish, not core capability. Many users may stop
at Track 2 and never need Track 3. The fact that Track 3 exists means the
architecture is **complete**.

---

## 18. Out of Scope — Track 3 Non-Goals

Things you'll be tempted to build but should NOT in Track 3:

- **Wiki generation** — separate feature, separate design doc, separate phase
- **Force-directed entity network visualization** — cool but not core; skip
- **Real-time collaboration** — never, per hobby scope
- **AI agent workflows** (LangGraph-style multi-step agents) — way out of scope
- **Plugin / extension system for custom tools** — future, if there's demand
- **LLM-based prose quality analysis** — separate writing assistant feature
- **"Chat with your book"** as a standalone page — this IS chat + memory; no standalone needed
- **Auto-generation of chapter outlines from memory** — writing assistant territory
- **Cross-book entity linking** — open question, defer until needed
- **Memory quota enforcement for shared instance** — Phase 2 sharing concern, not hobby

If you find yourself building any of these, STOP. They deserve their own
design documents and implementation plans.

---

## 19. When You Hit a Dead End

**"State machine bugs in Projects tab."**
- Add logging at every state transition
- Use TypeScript discriminated unions — compiler catches invalid states
- Storybook helps isolate the issue visually

**"Tool calling infinite loops."**
- Max iteration limit (K21.10) — verify it's wired
- Check LLM's tool_use output for stop_reason
- Provider-specific quirks — log the full response

**"Summary regeneration keeps contradicting user."**
- Debug the prompt — is it inferring preferences?
- Increase diversity threshold (95% → 99%)
- Extend user edit lock duration

**"Entity merge breaks relations."**
- Test with single relation first
- Check provenance edges — are they moved or recreated?
- Use transaction to atomic the merge

**"Delete cascade fails halfway."**
- Log each service's deletion result
- Add retry logic for transient failures
- Provide manual cleanup script for emergencies

**"Mobile UI looks terrible."**
- Use Tailwind responsive utilities consistently
- Test on real devices, not just DevTools
- Simplify rather than squeeze — hide features rather than shrink them

---

## 20. The Big Picture

### After Track 3 is done, you have:

- **A complete memory system** for a novel-writing AI platform
- **Per-project opt-in extraction** with full cost control
- **Knowledge graph** that scales to 5000-chapter novels
- **Power-user browser** for every fact, entity, event
- **Tool calling** so LLMs can actively query memory
- **Honest privacy model** with working export/delete
- **Three shipment milestones** (Tracks 1, 2, 3) each independently usable
- **~150 concrete tasks** executed (64 + 81 + 69 ≈ 214)
- **~22 QC gates** passed
- **~30 integration tests** green
- **10,000+ lines of architecture documentation** describing every decision
- **A hobby project that does what Mem0, MemPalace, and Claude Projects each
  do partially — all in one integrated system, self-hosted, free, private**

### What you built is actually impressive

Not many hobby projects reach this level of completeness. Most stop at "chat
with AI" and never get to "AI knows my characters, edits, and intentions over
5000 chapters of novel." You built the infrastructure for genuinely
state-of-the-art single-user AI memory for creative writing.

Whether you ship Track 3 or stop at Track 2 (both are legitimate choices),
you should be proud of the design and the discipline to document it at
this level.

---

*Created: 2026-04-13 (session 34) — PM implementation plan for KSA Track 3*
*Total tasks: 69 + 10 integration tests + 3 smoke tests*
*Target: complete the full knowledge service roadmap*
*Prerequisite: Tracks 1 and 2 complete and stable*
