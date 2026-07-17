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
