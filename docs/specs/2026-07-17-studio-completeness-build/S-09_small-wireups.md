# S-09 · Small wire-ups (repo/route exists — expose it)

> **Tier B — a basket of XS–S wire-ups (no draft).** Each is a route over an existing repo method or a FE
> caller over an existing public route. Grouped because none warrants its own spec; each cites its evidence.

## W1 · Corrections `list_for_job` route (XS) — composition
`generation_corrections.py:280 list_for_job` is defined with **zero callers**; only the aggregate
`GET /works/{pid}/correction-stats` is exposed. **Add** `GET /v1/composition/jobs/{job_id}/corrections`
mirroring the method (owner/grant-gated). Consequence closed: a user can enumerate the individual corrections
on a job (what a human actually changed), not just accept-rate charts. Update/delete stay absent —
append-only preference log, by design.

## W2 · glossary→graph seed route (S) — knowledge
`kg_project_entities_to_nodes` (MCP) has no REST twin; `POST /entities` is single-node. **Add**
`POST /v1/knowledge/projects/{id}/entities/from-glossary` wrapping the existing `entities_to_nodes` engine
(`anchor_loader.py:194`). Consequence closed: "seed the graph from my glossary without writing prose" becomes
a GUI one-click, not an agent-only capability. Grant-gated on the project's book.

## W3 · View-aware graph reader in the panel (S) — knowledge FE (this is F-12)
`GET /v1/kg/projects/{id}/graph?view=&as_of_chapter=` (`graph_views.py:597`) is public + complete but has
**zero FE callers**; `KgGraphPanel`→`ProjectGraphView` uses `/subgraph` (params `center/hops/limit` only).
**Fix:** point `ProjectGraphView` at the view-aware reader (or add a "view" + "as-of chapter" control that
switches to it). Consequence closed: a human can APPLY a saved lens and view the graph as-of a chapter — the
lens they can already build (`ViewBuilder`) stops being un-lookable-through. Pure FE.

## W4 · Derivative LIST-of-a-book route (XS) — composition
`derivatives`/works has MCP `list_derivatives` but no REST list of a book's derivative Works. **Add**
`GET /v1/composition/books/{book_id}/derivatives` (the `DivergenceManagerView` already wants it). Grant-gated.
(Complements S-04, which mutates the deltas; this lists the derivatives themselves.)

## W5 · Wiki suggestion withdraw + status (XS) — glossary
`submitWikiSuggestion` (`wiki_handler.go:1708`) is INSERT-only; only owner-facing `listWikiSuggestions`
(GrantView). **Add** `DELETE /v1/glossary/wiki/suggestions/{id}` (submitter withdraws own) + include the
accept/reject `status` in the submitter's read. Consequence closed: a contributor who mis-files can retract
and see the outcome, instead of INSERT-and-blind.

## Tests (per item)
- W1: the list returns a job's corrections; grant-gated; empty for a job with none.
- W2: seeds nodes from glossary anchors; idempotent-ish (re-seed doesn't duplicate); grant-gated.
- W3: the panel renders the graph filtered by a saved view + as-of a chapter; no view = current behaviour.
- W4: lists a book's derivatives; grant-gated; a non-grantee sees none.
- W5: submitter withdraws own suggestion (not another's); status visible to the submitter.

## Out of scope
- Fact author/invalidate — in S-05. Restores — in S-08. World verbs — in S-07.
