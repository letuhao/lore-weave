# S-12 · Workflows + workflow-proposals GUI (G-WORKFLOWS)

> **PO decided (2026-07-17): build in THIS track.** `registry_propose_workflow`'s description says it
> "records a proposal the user must approve **in the UI**" — and there is no UI, so an agent calling it
> today writes a row no human can ever approve. **Service:** agent-registry-service (Go) + FE.
> **CLARIFY-verify correction:** the audit called the workflows public surface "completely empty" — **stale**.
> The proposals half + a workflows LIST already ship; the gap is 3 backend verbs + the entire FE.

## 1. Current state (verified, corrects the audit)
Public routes that EXIST (`server.go:295-300`):
```
GET  /workflows                                    (list — System + own + granted)
GET  /workflow-proposals                           (list)
GET  /workflow-proposals/{id}                       (get-one)
PUT  /workflow-proposals/{id}/approve
POST /workflow-proposals/{id}/reject
```
Compared to the **complete** `skills` surface (the reference, `server.go:236-245`: list/create/import/get-one/
delete/export/revisions/**enablement**), workflows is MISSING:
```
GET    /workflows/{id}                (get-one)            ❌
DELETE /workflows/{id}                                     ❌
PUT    /workflows/{id}/enablement     (enable/disable)     ❌
```
FE: **zero consumers** — no `workflowApi`, no `WorkflowsPanel`, no `WorkflowProposalsPanel` (grep empty).
`mode_bindings.go` exists but is labelled in code "a USER setting" with **no settings surface** (SET-1..8
write-only-behavior).

## 2. Backend — 3 routes mirroring skills (S)
- `GET /v1/workflows/{id}` → `getWorkflow` (mirror `getSkill`; System/own/granted visibility).
- `DELETE /v1/workflows/{id}` → `deleteWorkflow` (mirror `deleteSkill`; owner-scoped; System-tier =
  admin-only, a regular user cannot delete a System workflow — User-Boundaries).
- `PUT /v1/workflows/{id}/enablement` → `setWorkflowEnabled` (mirror `setSkillEnabled`).
Create stays via the **propose → approve** flow (the workflow authoring model — no direct POST create, by
design; the approve route already mints the workflow from the proposal).

## 3. FE — two panels off the skill-panel spine (near-clones)
`ExtensionsPanel` (skills) and `enrichment/ProposalsPanel` are the spine to reuse (DOCK-2, don't fork):
- **`workflows`** panel (category — same as `ExtensionsPanel`'s): lists the user's visible workflows
  (System badged read-only, own editable), enable/disable toggle (→ enablement route), delete (own),
  view-one. GG-8 shape.
- **`workflow-proposals`** panel: the pending inbox — list + get-one + **approve / reject** (the routes
  exist; this is the UI the tool's own description promises). Near-clone of `ProposalsPanel`. Approving here
  is what closes the "an agent writes a proposal no human can approve" hole.
- **mode-binding control** in `settings`: surface `mode_bindings` as a real user setting (effective value +
  source tier, SET-1..8) — it is currently write-only-behavior (stored, no surface). Small.

## 4. Tenancy (User-Boundaries)
Workflows are 3-tier like skills: **System** (admin-seeded, read-only to users), **own** (user), **book-
granted**. `getWorkflow`/`delete`/`enablement` gate writes on ownership; a regular user cannot delete/disable
a System workflow. Proposals are owner-scoped. Reuse the skills visibility helper — do not invent a second.

## 5. MCP
`registry_propose_workflow` (agent) already exists. The human approve/reject is the GUI (this spec). Add MCP
`registry_workflow_{delete,set_enabled}` only if agent parity on those admin-ish verbs is wanted — **defer**
(the human GUI is the driver; agents propose, humans dispose). Record as conscious.

## 6. Tests
- backend: get-one/delete/enablement mirror the skill routes; System-tier delete/disable by a regular user →
  403; owner-scope isolation.
- FE: the proposals panel lists pending + approve mints a workflow (the row leaves pending, appears in
  workflows); reject removes it; the workflows panel enable/disable round-trips; a System workflow shows
  read-only.
- the tool loop: `registry_propose_workflow` → the proposal appears in the panel → a human approves → the
  workflow is enabled. (The end-to-end the tool's description promised.)
- `panelCatalogContract` covers both new panels; mode-binding shows effective value + tier.

## 7. Out of scope
- The workflow RUNNER (`/internal/workflows` step-runner) — exists, untouched.
- No direct POST-create workflow (propose→approve is the model, by design).
