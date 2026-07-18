# S-12 · Workflows + workflow-proposals GUI (G-WORKFLOWS) — RUN-STATE

## COMMITMENT
Build S-12 ([spec](../specs/2026-07-17-studio-completeness-build/S-12_workflows.md)): close the
"an agent proposes a workflow no human can approve" hole. **agent-registry-service (Go) + FE.** Finish =
a user can (a) see/approve/reject workflow proposals in a GUI, (b) list/view/enable-disable/delete their
workflows, (c) set mode-bindings as a real setting. Slice-by-slice; review-impl + QC each.

## INVESTIGATION — verified vs code 2026-07-18 (corrects/extends the spec)
- **Routes that EXIST** (`server.go:295-300`): `GET /workflows`, `GET /workflow-proposals`,
  `GET /workflow-proposals/{id}`, `PUT /workflow-proposals/{id}/approve`, `POST …/reject`. Missing:
  `GET/DELETE /workflows/{id}`, `PUT /workflows/{id}/enablement` (spec §2 confirmed).
- **`workflows` table** (migrate.go:395): PK `workflow_id UUID`, tier(system/user/book)+owner_user_id+book_id
  scope_key, slug/title/description/surfaces/inputs/steps/notes_md/status/source. Approve mints a row
  (workflows.go:641 — INSERT source='agent', status='published'); reject/get/list all work.
- **⚠ `workflow_enablement` table does NOT exist** — skills use `skill_enablement (skill_id, owner_user_id,
  enabled, PK(skill_id,owner_user_id))` (migrate.go:158). Mirroring `setSkillEnabled` REQUIRES a new
  `workflow_enablement` migration. (Spec implied via "mirror setSkillEnabled" but didn't spell out.)
- **`listUserWorkflows` (workflows_rest.go) exposes NO workflow_id and NO enabled** — light projection
  (slug/title/desc/tier/status/surfaces), shared struct `workflowMeta` with the MCP tool. FE needs
  workflow_id (to act by id) + effective enabled (toggle state) → add a SEPARATE REST list struct (don't
  touch the MCP `workflowMeta` output contract).
- **Reusable helpers:** `authorizeRowWrite(w,r,tier,owner,book,uid)` is GENERIC (server.go:136 — user=own,
  system=requireAdminScope, book=≥edit grant). `loadVisibleWorkflow(ctx,uid,slug)` exists but keys on SLUG;
  REST routes key on workflow_id → add by-id load. Mirror `getSkill`/`deleteSkill`/`setSkillEnabled`.
- **mode-bindings BACKEND is DONE + SET-1..8 compliant** — `getModeBinding` (server.go:291) returns the
  EFFECTIVE binding + per-tier sources; `putModeBinding` writes. The gap is PURELY the FE surface
  (write-only-behavior = no GUI). No BE work for the setting.

## SEALED DECISIONS
- **SD-1 · setWorkflowEnabled = PER-USER override (mirror setSkillEnabled), allowed for ANY visible
  workflow incl. System.** Resolves the spec §2-vs-§4 tension toward the skill precedent §2 mandates: a
  per-user `workflow_enablement` row is a tenancy-SAFE preference (only that user's view), NOT a System
  mutation. The real System guard is on DELETE (admin-only via authorizeRowWrite). Blocking a per-user
  System-disable would diverge from skills for no tenancy reason + worsen UX. FLAG at POST-REVIEW.
- **SD-2 · getWorkflow/deleteWorkflow key on `workflow_id` (UUID PK), mirroring getSkill/deleteSkill.**
  The MCP get keys on slug (agent-facing); REST keys on id (GUI-facing, from the list's workflow_id).
- **SD-3 · No new MCP tools for delete/enablement (spec §5 defer)** — agents propose, humans dispose via GUI.

## FE STATE — verified 2026-07-18 (corrects the spec's "zero FE / no surface")
Partial FE ALREADY exists, surfaced ONLY in the standalone `/extensions` route (`ExtensionsPage`), NOT in
the studio dock / `catalog.ts` / `ui_open_studio_panel` enum:
- `features/workflows/` — **read-only** `WorkflowRack` (list only; NO enable/disable/delete), `workflowsApi.list()`.
- `features/modeBindings/` — WORKING mode-binding UI (`BindingSettings` veto toggles, effective+tier badges).
- **NO workflow-proposals FE of any kind** (genuine net-new).
Spines to clone: skills `features/extensions/` — `SkillsView` (list+toggle+delete), `ProposalsView`
(approve/reject), `useSkills`/`useProposals`, `extensionsApi`. GG-8 reg: `catalog.ts` STUDIO_PANELS (:262
extensions/proposals entries), `contracts/frontend-tools.contract.json` panel_id enum (:199), i18n `studio`
ns `panels.<id>.*` (guideBodyKey REQUIRED). `platform` category already in CATEGORY_ORDER (no change). Resolver
`studioUiNav.ts` is generic (host.openPanel looks up catalog) — no change. Base path `/v1/agent-registry`.

## SLICE BOARD (each: BUILD → review-impl → QC → evidence)
| slice | user gains | status | evidence |
|---|---|---|---|
| **1 · BE — enablement table + 3 routes + list id/enabled** | get/delete/enable-disable a workflow by id | **DONE** | `workflow_enablement` migration; `getWorkflow`/`deleteWorkflow`/`setWorkflowEnabled` (workflows_rest.go) mirror skills; list exposes workflow_id+effective enabled (separate REST struct, MCP contract untouched). **8 pgxmock route tests: get own/404, delete own-204/other-404/System-blocked, enable disables/404. Full pkg + migrate-lint green; build+vet+provider-gate clean.** review-impl: fixed getWorkflow book READ requiring ≥edit → ≥view (matches list+MCP; a view-grantee could see-but-not-open). |
| **2 · FE — workflow-proposals panel (net-new)** | approve/reject the pending inbox (closes the hole) | **DONE** | `WorkflowProposalsView` + `WorkflowProposalsPanel` (GG-8, panel_id `workflow-proposals`), `useWorkflowProposals`, api list/approve/reject. Approve mints the workflow. |
| **3 · FE — workflows panel (+toggle/delete + GG-8)** | list/view/enable-disable/delete own workflows | **DONE** | `WorkflowsView` + `WorkflowsPanel` (GG-8, panel_id `workflows`), `useWorkflowManage` (optimistic toggle, delete-own), api get/setEnabled/remove. System read-only + per-user toggle (SD-1). |
| **4 · FE — mode-binding setting** | mode_bindings reachable as a real setting | **DONE** | New `workflow-bindings` tab in the settings-tab registry (`tabs.tsx`) mounting the existing `BindingSettingsPanel` → lands on BOTH the /settings page + Studio settings dock (one registry, `settingsTabParity` proves it). No-bookId usage verified correct (getModeBinding treats book_id optional → System+user tiers). QC: settingsTabParity 9/9 + full settings suite 54/54; tsc 0; i18n en `page.tab.workflow-bindings` + 17 locales (gate full parity). |

**Slices 2+3 evidence (committed together — shared GG-8 registration):** catalog.ts +2 entries;
chat-service `panel_id` enum +2 (`workflows`, `workflow-proposals`) + prose; `contracts/frontend-tools.contract.json`
regenerated (`WRITE_FRONTEND_CONTRACT=1 pytest` → 20 passed); i18n en (studio panels.* + extensions workflows.*)
+ 17 locales via i18n_translate (0 failures, gate at full parity). **QC:** panelCatalogContract 9/9; 8 new view
tests (proposals approve/reject/filter/empty, workflows toggle/delete/system-readonly/empty) + existing rack 4 =
21 green; tsc 0; provider-gate clean. review-impl: panels palette-reachable via catalog (extensions/proposals
precedent); optimistic toggle flips only on success (matches useSkills). **Live browser E2E** (agent proposes →
panel → approve → runnable) deferred — full stack/browser MCP not available at dev time; each link proven (BE
pgxmock ↔ FE vitest ↔ contract parity both sides ↔ tsc). `LIVE-SMOKE deferred to D-S12-LIVE-SMOKE`.

## COMPLETENESS AUDIT (2026-07-18) — "is the loop TRULY closed?"
The original hole was "there was no UI." Building the panel makes approval POSSIBLE, not DISCOVERED —
a subtler re-run of the same hole ("invisible UI"). Audit end-to-end found + cleared:
- **GAP-1 · Discoverability (fixed the primary signal).** An agent proposes → the row waits → the user
  (working in the studio) had NO signal where to approve. The agent's tool message said "approve in the UI"
  but didn't NAME the panel. **Fixed:** both `toolProposeWorkflow`/`toolUpdateWorkflow` messages now name the
  "Workflow Proposals" panel + how to open it (⌘K) + nudge the agent to open it via
  `ui_open_studio_panel(panel_id="workflow-proposals")`. (`proposals_pending` already counts workflow
  proposals — verified — but is surfaced ONLY in the /extensions page; a persistent STUDIO badge is deferred,
  see DEBT.)
- **GAP-2 · Approving blind (fixed).** The proposal card showed `notes_md` but not the actual `steps`. **Fixed:**
  the card + type now render the tool sequence (with gate badges) — informed consent for the approve action.
- **GAP-3 · view-one missing (fixed).** Built `getWorkflow`/`api.get`/`WorkflowFull` but `WorkflowsView` had no
  affordance calling them (dead code + spec §3 "view-one" unmet). **Fixed:** an expand/view button lazy-loads the
  full workflow (steps) via the hook (MVC-correct). +2 tests (proposal steps render, view-one).
- **Skills-parity absences are intentional:** no import/export/direct-patch (workflows author via propose→approve
  by design, spec §2/§7); revisions = deferred (below).

## REGISTERS
### DECISIONS — SD-1..SD-3 above.
### DEBT — (all S-12 defers CLEARED, see Recently cleared)

### RECENTLY CLEARED (2026-07-18, spec [`../specs/2026-07-18-S12-deferred-cleanup.md`])
- **D-S12-STUDIO-PROPOSAL-BADGE ✅** — the studio now has a frame-level "pending approvals" badge
  (`ProposalsStatusItem`, registered in `StudioStatusContributions` beside the bell). Polls `/usage`, shows the
  skill+workflow total, click routes to the panel with pending items (workflow-proposals first). BE split the
  count (`skill_proposals_pending` + `workflow_proposals_pending`, `proposals_pending` kept = sum, back-compat).
  Uses the precedented registered-status-item mechanism — no new chrome. 5 badge tests + 1 BE split test.
- **D-S12-WORKFLOW-REVISIONS ✅** — `GET /v1/workflows/{id}/revisions` (`listWorkflowRevisions`) mirrors
  `listSkillRevisions`; reads the rows `snapshotWorkflowRevision` writes. ≥view visibility gate
  (`workflowVisibleToUser`). BE-only (skills' route also has no FE). 2 route tests.
- **D-S12-BINDINGS-I18N ✅** — `BindingSettings` (the settings tab) now uses `useTranslation` (`extensions` ns,
  `bindings.*` keys, 17 locales). `WorkflowRack` verified to have NO visible hardcoded strings (needed no i18n).
- **D-S12-LIVE-SMOKE** — the full agent-loop E2E (registry_propose_workflow → proposal appears in the
  panel → human approves → workflow runnable/enabled) needs a live stack + browser MCP, unavailable at
  dev time. Each link is proven in isolation (BE pgxmock ↔ FE vitest ↔ contract parity ↔ tsc). Trigger:
  next time the full stack + a browser MCP are up.
### DRIFT — (none)

## RESUME
Re-read THIS → `git log --oneline -8` → continue at the first non-DONE slice. FE slices wait on the
FE-map investigation (ExtensionsPanel/ProposalsPanel spine + GG-8 registration points).
