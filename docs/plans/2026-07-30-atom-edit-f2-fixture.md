# F2 — the fixture, and the 7 families waiting on it (2026-07-30)

`scripts/atom-edit-roundtrip.py` proves 4 of 11 composition `*_edit` families. The other 7
are not blocked on anything external — they need a **Work**, and everything that creates one
already exists. This plan builds that fixture and closes them.

## What the checklist actually demands

F2's real column is *real-run proven?* — "a live edit reaching the artifact", verified by
**re-reading the row after the write**. For the 6 PlanForge atoms it was closed on **two
channels counted separately** (MCP, then GUI). So a count that does not say *which channel*
overstates itself.

⇒ **Every family declares its channel.** The 4 already proven go through REST — the same
calls the GUI makes (`motifApi.create|patch|archive`). `motif_bind` has **no REST write
route at all** (only `GET /works/{pid}/outline/motif-bindings`); its write is the MCP tool
`composition_motif_bind_edit`. Forcing it through REST would prove nothing, so it is proven
on the channel it actually has.

## A stale doc nearly sent this the wrong way

`contracts/api/composition/v1/openapi.yaml` still says `POST /books/{book_id}/work` is
"PLANNED — not yet implemented (D-COMP-POST-WORK-CREATE)". It **is** implemented
(`works.py:154`, idempotent, ensures the knowledge project). This is the exact trap CLAUDE.md
names — a "blocked on the missing route" item this project shipped twice that already
existed. Verified against code, not the doc. The contract note gets corrected.

## The fixture chain

Built **lazily** (so `--only motif` costs nothing) and **once** per run, into a throwaway
book that is deleted at the end — never the dogfood book, whose smoke debris reads as a
product bug later.

```
POST /v1/books                                  → book_id   (throwaway, titled as such)
POST /v1/composition/books/{book}/work          → project_id (idempotent)
POST /v1/composition/works/{pid}/outline/nodes  → chapter node, then 2 scene nodes
POST /v1/composition/works/{pid}/derive         → derivative project_id
```

`NodeKind` is `arc|chapter|scene|beat`; a scene node carries `chapter_id`. No structure row
is needed for a node — the earlier PENDING note said "a Work + a structure" and that was a
guess, corrected here against `NodeCreate`.

## The 7, in ascending fixture cost

| family | channel | route / tool | delete semantic to assert |
|---|---|---|---|
| `canon_rule` | REST | `POST /works/{pid}/canon-rules`, `PATCH|DELETE /canon-rules/{id}` | soft + `/restore` |
| `outline_node` | REST | `POST /works/{pid}/outline/nodes`, `PATCH|DELETE /outline/nodes/{id}` | soft + `/restore` |
| `scene_link` | REST | `POST /works/{pid}/scene-links`, `DELETE /scene-links/{id}` (204) | soft + `/restore` |
| `derivative` | REST | `POST /works/{pid}/derive`, `PATCH /works/{pid}` | soft via `status` |
| `entity_override` | REST | `POST|PATCH|DELETE /works/{pid}/entity-overrides` | soft + `/restore` |
| `motif_bind` | **MCP** | `composition_motif_bind_edit` | **pair** — `unbind` is the reverse |
| `authoring_run` | REST | `POST /authoring-runs` | **revision** — `revert_all` |

Delete semantics come from `test_atom_delete_contract.py`, which is the SSOT for them. Each
family asserts the semantic its row declares — asserting "absent from the default list" alone
would pass identically against a hard delete, which is a different contract.

## The one that may stay PENDING, honestly

`authoring_run` needs `book_id` + `plan_run_id` + an ordered chapter scope, and its
destructive op is `revert_all` at level 3/4 — which can **spend money**. If creating one at
the smallest safe level cannot be done without generation, it stays PENDING **with that
reason printed**, not silently dropped. That is a real external constraint (cost), not the
"I'd have to build it" laziness gate #4 exists to catch.

## Teardown

`DELETE /v1/books/{book_id}` at the end, in a `finally`, and the harness prints what it
could not clean. Library-tier probes (motif/arc/structure) are per-user, not per-book, so
they keep the `smoke.f2_` prefix and archive soft — one greppable predicate.
