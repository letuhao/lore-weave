# S-05 · KG fact authoring/invalidation + the triage queue panel

> **Tier B — two related gaps.** (a) **Fact authoring/invalidation** is a route wire-up: a human can
> confirm/reject facts the agent proposed but cannot AUTHOR one (no POST) nor INVALIDATE one (relations have
> `/relations/{id}/invalidate`, facts don't, though `invalidate_fact` exists). (b) **The triage queue** is
> agent-only in the GUI: the routes are public and complete (`routers/public/triage.py`), the FE api
> functions exist with **zero callers** — no panel consumes them. **HTML draft:** ✅ net-new triage
> (`screen-kg-triage.html`). **Service:** knowledge-service.

## Part A — fact authoring + invalidation (backend + affordance, no draft)

### A.1 Current state (verified)
```
knowledge_pending_facts → PendingFact { pending_fact_id, user_id, project_id, session_id,
  fact_type: FactType(6-value enum), fact_text, subject/predicate/object?, event_date? }
routers/public/pending_facts.py : GET "" · POST /{id}/confirm · POST /{id}/reject   — NO create
invalidate_fact  (facts.py:764)  exists; exposed for relations (/relations/{id}/invalidate), NOT facts
merge_fact       (facts.py:270)  the direct-write path, MCP-only via memory_remember
```
By design, in-place fact UPDATE does **not** exist (bitemporal — correct = invalidate + re-assert). So the
gap is exactly **author** and **invalidate**, not update.

### A.2 Routes (new)
```
POST /v1/knowledge/pending-facts                       (author → queue a pending fact for own review)
  body: { project_id, fact_type, fact_text, subject?, predicate?, object?, event_date? }
POST /v1/knowledge/facts/{fact_id}/invalidate          (mark a committed fact wrong)
```
- **Author queues to `knowledge_pending_facts`** rather than merging straight to the graph — a
  human-authored fact enters the SAME review lane as an agent-proposed one (symmetry; the human then
  confirms it via the existing `/confirm`). This keeps one write path into `:Fact` and reuses the
  confirm-promotion that already exists. `fact_type` is the 6-value `FactType` enum — validate on write
  (closed set; a bad value must 422, never reach the CHECK and 500 — the
  `enum-backfill-all-CHECK-blocks` lesson).
- **Invalidate** wraps `invalidate_fact` (already used by relations); emit a `fact_corrected` event to match
  the relation-correction pattern so downstream stays consistent.
- Tenancy: owner-scoped (`user_id` = the caller); a fact/pending-fact is only authorable/invalidatable by
  its owner within a project they can access.

### A.3 MCP — SEALED (no new tool)
`memory_remember` already authors (agent side); **`memory_forget` already = invalidate** — CLARIFY-verified:
`_handle_memory_forget` (`executor.py:726`) calls `invalidate_fact` (owner-keyed). So agent parity on BOTH
verbs already exists. **This spec adds the HUMAN routes only** (`POST /pending-facts`, `/facts/{id}/invalidate`)
— no new MCP tool, no duplicate.

### A.4 FE affordance (on the existing EntityDetailPanel fact list — no new panel)
`/entities/{id}/facts` already renders a fact list. Add: an "＋ Add fact" row (opens a small s/p/o + type
form → POST pending-facts, lands in the review inbox with a "pending your review" chip) and, on each
committed fact, a "mark wrong" action (→ invalidate, mirrors the relation "mark wrong" the panel already
has). This closes the asymmetry the audit named: facts become as correctable as relations.

## Part B — the triage queue panel (FE wire-up → HTML draft)

### B.1 Current state (verified)
```
routers/public/triage.py (PUBLIC JWT, mounted main.py:784) — COMPLETE backend:
  GET  /v1/kg/projects/{id}/triage                  (grouped queue)
  POST /v1/kg/projects/{id}/triage/{signature}/resolve   { action: TriageAction }
  POST /v1/kg/projects/{id}/triage/{triage_id}/dismiss
TriageAction (closed set): map · add_to_vocab · add_to_schema · re_target · widen_target_kinds ·
  drop_edge · close_previous · set_multi_active · promote_to_glossary_kind · demote_to_attribute · dismiss
  (each item_type permits a SUBSET — the item carries `suggested_actions`; the router rejects a
   non-permitted action, s11.2)
FE: ontologyApi.listTriage / resolveTriage / dismissTriageItem — DEFINED, ZERO callers.
```
So Part B is **pure FE**: a panel that lists the queue and drives the existing routes. No backend.

### B.2 The panel — `kg-triage` (category `storyBible`), GG-8 shape
- catalog row + `panel_id` enum + contract + i18n `guideBodyKey` + `CATEGORY_ORDER` + a Lane-B
  `triageEffects` handler (an agent resolving a triage item refreshes the panel).
- **The load-bearing UX decision (the draft settles it):** each triage item shows its `suggested_actions`
  as the ONLY offered buttons — a closed set the backend will accept — so the human never picks an action
  the item's type forbids (the router would 400). This is the Frontend-Tool-Contract discipline applied to a
  human surface: offer only the enum values the server permits for THIS item.
- Grouped by `item_type` (unknown edge-type / unknown node-kind / off-schema attribute / multi-active
  conflict …); each row: the offending element + evidence snippet + the permitted-action buttons + dismiss.
- Deep-link IN from the empty-graph state and from the KG panels ("N items need triage →").

### B.3 Tests
- **Part A:** author → row appears in the pending inbox (owner-scoped); confirm promotes to `:Fact`;
  invalidate flips a committed fact + emits `fact_corrected`; a bad `fact_type` → 422 (not 500); another
  user cannot author into your project / invalidate your fact.
- **Part B:** the panel lists the queue; only `suggested_actions` render as buttons; resolving with a
  permitted action succeeds and the row leaves; a Lane-B agent resolve refreshes the list; dismiss removes.
- **contract:** `TriageAction` is a closed-set arg both sides (the panel offers only server-permitted values).

### B.4 Out of scope / by-design
- In-place fact UPDATE — by design (bitemporal). Do not build.
- The triage backend — already complete; do not touch it, only consume it.
