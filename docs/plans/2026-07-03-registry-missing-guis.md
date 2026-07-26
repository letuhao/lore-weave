# Plan — Registry missing FE GUIs: Subagents + Activity log

**Why:** a design↔shipped reconcile (draft `plugin-register/draft-ui.html` nav ↔ `frontend/src/features/extensions`)
found 2 screens shipped as backend-only. `01_GUI_CHECKLIST.md` listed them but was never used as a gate (273 boxes,
0 ticked). Backends are 100% ready. Clears `D-REG-P5-SUBAGENTS-FE` + `D-REG-P5-ACTIVITY-FE`.

**Governing principle** (memory `checklist-is-self-report-enforce-by-tests`): an item is DONE only when a **test asserts
its EFFECT**. Every GUI here ships with a test that proves the effect (create persona → row appears; audit rows render +
filter), and I tick a GUI-checklist line ONLY when a passing test backs it.

**Size:** M (FE-only, 2 CRUD screens mirroring `SkillsView`/`CommandsHooksView`; no new backend, no contract change).

## Backends (verified, ready)
- Subagents: `GET/POST /v1/agent-registry/subagents`, `PATCH/DELETE /subagents/{id}`. Row: `{subagent_id, tier,
  owner_user_id, book_id, name, description, system_prompt, tool_scope (JSON array of globs), model_ref, enabled, …}`.
  Create validates name (lowercase a-z0-9-, 1-32) + non-empty system_prompt + tool_scope array; user-tier quota 20;
  409 on dup name; System rows read-only for non-admin.
- Activity: `GET /v1/agent-registry/audit?kind=&range=7d|30d&limit=&offset=` → `{items:[{audit_id, at, actor_kind,
  kind, action, target_id, target_name, tier, detail}], total, limit, offset}` (owner-scoped).

## Build (mirror the existing MVC split: hooks own logic, views render-only)
1. **types.ts** — `Subagent`, `SubagentList`, `CreateSubagentReq`, `AuditEntry`, `AuditList`.
2. **api.ts** — `listSubagents/createSubagent/patchSubagent/deleteSubagent` + `listAudit`.
3. **hooks** — `useSubagents.ts` (list/create/toggle/remove, degrade-safe error string like `useCommands`),
   `useAudit.ts` (list + kind/range filter).
4. **SubagentsView.tsx** — create form (name · model_ref · tool_scope comma→globs · system_prompt textarea) + list
   (name, tier badge, scope chips, enable toggle, delete on non-system). Closed-set nothing here (free-form persona), but
   surface the backend `result.error` verbatim on reject (no silent no-op).
5. **ActivityView.tsx** — kind + range (7d/30d) filter + a recent-first table (relative time, actor_kind, kind·action,
   target_name). Read-only.
6. **Mount** in BOTH shells (two-shells, one controller): `ExtensionsPage.tsx` tabs + `ExtensionsPanel.tsx` tabs.
7. **Tests** (`__tests__/subagents.test.tsx`, `activity.test.tsx`) — EFFECT assertions: create→row appears (mocked api),
   reject→error surfaced, toggle calls patch, delete calls delete; audit rows render + a kind filter re-queries.

## Checklist discipline
Update `01_GUI_CHECKLIST.md`: **add the missing `## Subagents` + `## Activity log` sections** (the old checklist under-
specified Subagents as a capability chip only), and tick ONLY the lines a passing test proves. Leave un-tested lines `[ ]`
with a note — never tick from self-report.

## VERIFY
`tsc` clean · new vitest suites green · full FE extensions+studio suites green · a live browser smoke (create a subagent
in the /extensions page → it appears; open Activity → rows render) since this is an agent→GUI surface.

## Milestones / commit boundaries
M1 types+api+hooks (no UI) · M2 the two Views + mount + tests (commit together — the shippable screen) · M3 browser
smoke + checklist tick + SESSION + commit.
