# S-08 · Soft-archive RESTORE for motif + arc-template (dead-end soft-delete)

> **Tier B — repo method + route + affordance (no draft).** `motif_repo.archive` and
> `arc_template_repo.archive` soft-set `status='archived'` ("history survives") but **neither repo has a
> `restore`** — verified against canon/plan/structure/outline, which ALL restore. Archived motifs and arc
> templates are fully recoverable data (a status flip; `list` even supports `status=archived`) with **no
> transport to un-archive them** — a dead-end soft-delete, asymmetric with every other archivable domain.
> **Service:** composition-service.

## 1. Current state (verified)
```
motif_repo.py        : archive(441) soft status='archived' · clone · adopt — NO restore
arc_template_repo.py : archive(225) soft status='archived' · clone — NO restore
(control) canon_rules / plan_runs / structure / outline : all have a restore method
```

## 2. Repo methods (new — mirror the canon_rule restore exactly)
- `MotifRepo.restore(user_id, motif_id) -> Motif | None` — `UPDATE motif SET status='active', updated_at=now()
  WHERE id = $ AND owner_user_id = $me AND status='archived'`. Owner-scoped; returns None if not found /
  not-owned / not-archived.
- `ArcTemplateRepo.restore(user_id, template_id) -> ArcTemplate | None` — same shape.
  (Both mirror `canon_rules.restore`, the audit's "complete" reference.)

## 3. Routes
```
POST /v1/composition/motifs/{id}/restore
POST /v1/composition/arc-templates/{id}/restore
```
Owner/grant-gated exactly as the matching archive (DELETE) routes.

## 4. MCP
`composition_motif_restore` + `composition_arc_template_restore` — the archive tools already exist
(`composition_motif_archive`, `composition_arc_template_archive`); this completes the symmetry so an agent
that archived can restore.

## 5. FE (affordance)
In the motif-library / arc-templates panels, an "Archived" filter already lists archived rows (the repos
support `status=archived`); add a "Restore" action on each archived row (→ POST restore, Lane-B refresh).
No new panel.

## 6. Tests
- restore un-archives an archived own-row; a non-archived row → no-op/None; another user's row → not
  found/403.
- the archive→restore round-trip preserves the row id + history (the whole point of soft-delete).
- MCP parity: `composition_motif_restore` / `composition_arc_template_restore` round-trip.

## 7. Note
This is the same shape S-01 builds INTO structure_template from day one (`is_archived` + restore), so all
authorable composition domains end symmetric. Book-shared arc templates (S2's tier) restore the same way —
gate the restore on the row's book for the shared tier.

---

## 8. VERIFICATION + CORRECTION (2026-07-18, investigated against real code before build)

The spec's **diagnosis is right, its mechanism claim is wrong.** Verified against
`motif_repo.py` / `arc_template_repo.py` / their patch args + routers + MCP tools:

- ✅ **Confirmed:** neither repo has a dedicated `restore` method (canon_rules + structure_template do —
  `structure_templates.restore` / `composition_structure_template_restore` are the exact references).
- ⚠️ **CORRECTION — "no transport to un-archive … a dead-end soft-delete" is FALSE at the API layer.**
  Both `MotifPatchArgs` and `ArcTemplatePatchArgs` carry a **`status` field**, and neither repo's `patch`
  guards `status <> 'archived'`. So `composition_motif_patch(status='active', expected_version=N)` (MCP) and
  `PATCH /motifs/{id}` (HTTP) **already un-archive** an owned row today. The `composition_motif_archive` tool
  even documents this ("un-archive is composition_motif_patch(status='active')") and sets its `undo_hint` to
  `None` *because* there is no clean reverse verb.
- ✅ **The real gap is threefold, and the build still stands:**
  1. **No dedicated, idempotent `restore` verb.** The patch path needs a 2-step OCC dance (fetch the archived
     row for its `version`, then patch) and can silently re-arm other fields; `restore` is one call, no
     version, `status`-only — matching every sibling domain.
  2. **No FE affordance.** The libraries have an "Archived" filter but **no Restore button** — from the user's
     seat it *is* a dead-end. This is the primary user-facing fix (mirror `StructureTemplatesPanel`'s restore).
  3. **Dishonest MCP undo.** `composition_motif_archive` / `composition_arc_template_archive` return
     `undo_hint = None`; once `restore` exists they must point at it (an archive you can't cleanly undo).
- **Scope refinement (was under-specified):** motif's shared/book tier needs `restore_shared` (mirroring
  `archive_shared`) and arc-template's `restore(book_id=…)` (mirroring its `archive(book_id=…)`), each
  EDIT-gated on the book — otherwise a *shared* archived row stays a dead-end even after this fix. Restore
  returns the row (RETURNING) so the FE refreshes and the route 404s a not-found/not-owned/not-archived id
  (canon-restore semantics; no cross-tenant oracle since a foreign row simply matches nothing).

## 9. BUILD STATUS (2026-07-18)

- ✅ **BE complete + verified** (commit `fa79e0963`): `MotifRepo.restore`/`restore_shared`,
  `ArcTemplateRepo.restore(book_id)`; routes `POST …/{id}/restore[?book_id=]`; MCP
  `composition_motif_restore` + `composition_arc_template_restore`; archive MCP tools' `undo_hint`
  now point at restore (was `None`). Tests: repo DB round-trip on real PG (id+version preserved,
  foreign/wrong-book/not-archived→None, shared tier), router 404/owner/shared, MCP tool-list parity +
  tier-gate + functional. **220 passed** together; provider-gate clean.
- ✅ **FE arc-templates complete + verified** (commit `005cf6545`): `arcApi.restore` + `motifApi.restore`;
  `useArcTemplates` gained an **Archived tier** (fetches `status='archived'`) + a `restore()` action;
  `ArcTemplatesPanel` shows an **Archived tab** whose rows carry only a **Restore** action. This is what
  makes the soft-delete a non-dead-end — before, archived arcs were never fetched, so nothing could
  surface a Restore. Panel test 10/10, tsc 0.
- ⏭️ **DEFERRED — `D-S08-FE-MOTIF-ARCHIVED-VIEW`** (gate #2 · structural). The **motif library**
  (`MotifLibraryView`) has **no archived-row surface at all** today — the audit's assumption that "an
  Archived filter already lists archived rows" is inaccurate for both panels; arc-templates got its
  archived view built here, but the motif library is a large, tab-heavy component and adding an archived
  view + restore there is its own focused FE pass. `motifApi.restore` (+ shared via `book_id`) is already
  wired and BE-tested, so this is a view-only add, not new capability. Target: a motif-library UX pass.
