# S-03 · References edit (the UPDATE the corpus never had)

> **Tier A — DATA-layer build (port surface).** `ReferencesRepo` = create/list/get/delete/search — **no
> `update`**; the router is GET/POST/DELETE. Fixing a typo means delete + re-add, which **re-embeds the
> whole content** and loses ordering. **No HTML draft** — `ReferencesPanel` (legacy) is the design
> reference; the reference-shelf port (S-10) carries the panel, this spec adds the verb + edit affordance.
> **Service:** composition-service.

## 1. The design axis — metadata vs content (this is the whole spec)

```
reference_source (migrate.py:576)
  METADATA (no embedding impact):  title · author · source_url
  CONTENT  (drives the embedding): content · embedding · embedding_model · embedding_dim
  scope:   project_id · book_id (tenancy)   actor: created_by
```
Editing `title`/`author`/`source_url` must **NOT** re-embed — it is a cheap column write. Editing `content`
**MUST** re-embed (re-run the embed path `create` uses). A single naive PATCH that always re-embeds would
make fixing a typo in an author's name pay for a full re-embed. So UPDATE splits by what changed.

## 2. Repository methods (new)

- `update_metadata(project_id, reference_id, *, title?, author?, source_url?) -> ReferenceSource | None` —
  `UPDATE reference_source SET <provided cols> WHERE id = $ AND project_id = $` (book scope already fixed at
  create; the row can't cross projects). No embedding touched. Returns None if not found in this project.
- `update_content(project_id, reference_id, *, content, embedding, embedding_model, embedding_dim)` —
  `UPDATE … SET content, embedding, embedding_model, embedding_dim WHERE id AND project_id`. The **caller
  (service layer) runs the embed** before calling this, exactly as the create route does — the repo never
  embeds (provider-gateway invariant: embedding resolves through provider-registry via the service, not the
  repo).

No OCC column exists on `reference_source` and references are low-contention single-author corpus rows;
last-write-wins is acceptable — **decision: no OCC** (recorded, not an omission).

## 3. REST routes

```
PATCH /v1/composition/works/{project_id}/references/{reference_id}
      body: { title?, author?, source_url? }                      → update_metadata (no re-embed)
PUT   /v1/composition/works/{project_id}/references/{reference_id}/content
      body: { content }                                           → embed + update_content (re-embeds)
```
Separate paths make the cost explicit at the API: PATCH is cheap, PUT-content is a priced embed. The
content route resolves the project's `reference_embed_model_ref` (the same model create uses) through
provider-registry — **it does not accept a model in the body** (one embedding space per Work, the OQ-9 pin).

## 4. MCP tool (agent parity)

`composition_reference_update` — metadata-only args (title/author/source_url). **Content edit via MCP is
out of scope** (an agent re-authoring a whole reference corpus is not a wanted capability; agents add
references via the existing create path). State this so the asymmetry is intentional, not an omission.

## 5. Frontend (affordance on the ported reference-shelf, S-10)

On each reference row in `reference-shelf`: an inline edit for title/author/source_url (→ PATCH, optimistic)
and a separate "Edit content…" action that opens the content editor and, on save, shows a "re-embedding…"
state (→ PUT-content). The metadata edit must feel instant; the content edit must signal it costs an embed.
No new panel — this is why S-03 has no draft.

## 6. Tests

- **metadata PATCH does not touch the embedding** — assert `embedding`/`embedding_model`/`embedding_dim`
  unchanged after a title edit (the bug this spec prevents).
- **content PUT re-embeds** — assert a new embedding is written and the model is the project's pinned one.
- **tenancy** — a reference in project A cannot be PATCHed via project B's path (404); the row's `book_id`
  is immutable through both routes.
- **MCP** — `composition_reference_update` round-trips metadata; rejects a content field (out of scope).

## 7. Out of scope / by-design

- References restore: none — hard-delete is by design (module docstring: "no critic-calibration history to
  preserve"). Not a gap; do not add.
- The `reference_embed_model_ref` surfacing leg (LIST returns only `embed_model_set: bool`) is a separate,
  unbacked BE slice — not this spec.
