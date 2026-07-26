# WS-D5 — Track D follow-ups (post-WS-D4)

Three workstreams remain after the capability sweep, WS-D4, and the step-5 selection
signal. This spec triages each into *do-now* / *tracked-defer* / *won't-do*, with the gate
reason, so none silently rots and none is busy-worked past its value.

Status source: `docs/sessions/SESSION_HANDOFF.md`. Evidence:
`docs/eval/tool-liveness/2026-07-11-selection-quality.md` (the 36 misses),
`docs/eval/tool-liveness/2026-07-10-capability-sweep.md` (the residue).

---

## WS-D5a — Tool description disambiguation (the 36 selection misses)

The step-5 proxy found 36 tools a model can't pick from their own synonym with every
sibling present. Not all 36 are description bugs; triaged:

### (A) Fixable — an over-generic SYNONYM claims a common word (do now)

The synonym, not the description, is wrong: a broad word ("remember", "search") is claimed
by a tool that isn't the obvious home for it, so it loses to the tool that *is*.

| tool | offending synonym | collides with | fix |
|---|---|---|---|
| `book_steering_set` | "remember this rule" | `memory_remember` | → "remember this steering rule" |
| `registry_propose_skill` | "remember this as a skill" | `memory_remember` | → drop; keep skill-specific phrasings |
| `book_search` | "where does it say" | `story_search` | → "where in the book does it say" |

**Rule this encodes:** a synonym must be *specific to its tool's domain*. A bare common verb
("remember", "search", "delete") is a synonym bug — it advertises a claim the tool can't win.

### (B) Fixable — the DESCRIPTION doesn't state the surface up front (do now, focused)

`book_*` and `composition_*` are **two parallel chapter surfaces**: the *saved book* (reader
-facing, canonical) vs. the *authoring workspace* (drafting, an authoring run). The
descriptions carry the distinction but bury it, so a generic ask picks by surface-level
similarity. Fix: **lead** each colliding description with its surface, in brackets.

| tool | lead with | (was picked instead) |
|---|---|---|
| `composition_get_prose` | "[Authoring workspace] …" | `book_get_chapter` |
| `composition_write_prose` | "[Authoring workspace] …" | (already says "NOT publish") |
| `composition_create_work` | "[Authoring workspace] …" | `book_create` |
| `composition_get_work` | "[Authoring workspace] …" | `book_list` |
| `book_get_chapter` | "[Saved book] …" | (wins some, loses "chapter text") |
| `book_chapter_save_draft` | "[Saved book] …" | `composition_write_prose` |

### (C) Won't-fix now — INHERENT product ambiguity (record, re-check after B)

Some asks map to two *genuinely valid* tools (two real surfaces both edit a chapter). No
description edit makes "edit chapter text" unambiguous when two surfaces both do it. These
are re-measured after (B); a residue is expected and acceptable.
- "edit chapter text" (save_draft vs write_prose), "make canon" (chapter_publish vs
  composition_publish), "rename/archive chapter" (book meta vs outline node).
- Intra-family sibling blur (`arc_get`/`arc_list`, `settings model_set_default`/`get_defaults`,
  `translation coverage`/`job_status`, `jobs_cancel`/`jobs_pause`): the tools are legitimately
  adjacent; leading each with its distinguishing verb helps but won't fully separate them.

**Gate:** (A)+(B) are fix-now (cheap, in-scope, root-cause-clear). (C) is a **conscious
won't-fix** (gate #5) — recorded so it stops re-surfacing; re-run `selection.py` after (B) to
confirm the count dropped and (C) is the floor.

### Verified outcome (2026-07-11, in-memory override of the edits)

Applied and re-classified the affected tools with the edited text (the live catalog is
stale until the containers rebuild — see below):

- **(A) synonym fixes confirmed:** "remember this steering rule" → `book_steering_set` ✅,
  "author a reusable skill" → `registry_propose_skill` ✅. The over-generic word was the bug.
- **(B) surface tags help where the ask isn't inherently ambiguous:** "read chapter text" →
  `book_get_chapter` ✅ (the `[Saved book]` tag).
- **(C) confirmed inherent (the floor):** "chapter text", "new writing project", "edit
  chapter text" still split between `book_*` and `composition_*` — because a book genuinely
  *is* a writing project and both surfaces edit a chapter. No prefix disambiguates a
  genuinely two-home request. This is the expected, accepted residue.

**Deploy note (done 2026-07-11):** a tool-description/synonym change reaches the live
federated catalog only after BOTH steps, in order:
1. **Rebuild + restart the owning MCP-server container** (here: book / composition /
   agent-registry) — recompiles the description into the server.
2. **Restart `ai-gateway`** — it CACHES the federated `tools/list`; after only step 1 the
   catalog still served the old text (verified). This is the gotcha: a description deploy is
   not live until the gateway's cache is cleared.

Both done; the edits are confirmed live in the catalog. Full `selection.py` re-run against
the live catalog records the post-fix miss count (see `docs/eval/tool-liveness/selection/`).

---

## WS-D5b — Capability-sweep residue (84 `executes: null`) — tracked defer

None block anything (`null` ≠ broken). Each clears a defer gate:

| cluster | n | gate | reason |
|---|---|---|---|
| authoring-run family | ~14 | #4 blocked | a real run needs a **paid** confirm (`budget_usd`) + a model plan for `arc_id` |
| `job_id` consumers (`jobs_*`, `composition_get_*_job`) | 7 | #4 blocked | needs a real async job → **spend** |
| kg graph-state (`kg_build_graph`, `kg_sync_apply`, `kg_triage_*`, `kg_world_query`) | ~9 | #2 structural | needs an adopted ontology + a built graph — a deeper fixture |
| glossary `items`/`ops`/`kinds` batch | ~8 | #2 structural | authored structured payloads (a real proposal batch) |
| long tail (translation versions, glossary merge, kg template/edge) | ~35 | #2/#4 | bespoke creator chains or genuinely-external deps |

The **cheaply-seedable** clusters (credential, registry-slug) are already done. The above are
NOT — fixing them manufactures reachability that doesn't model production (spend a real
budget, or seed graph state a user never has at $0). Revisit if a paid-eval budget or a
graph-fixture is stood up.

---

## WS-D5c — Hard-reject → `proven` gate tightening — **won't-do** (recorded)

CD4's headline hints at eventually rejecting a workflow unless every tool is `proven`
(G1–G4). **Decision (2026-07-11): do not.** `proven` includes G1 — "can a model pick this
tool from its description?" — which is a **chat-surface** property (WS-D5a), *irrelevant* to
a curated workflow that names its tool directly. Tightening the reject gate to `proven`
would reject legitimate workflows for a property they don't use, and cost ~199 NL probes to
do it. The workflow reject gate stays `executes: false` (+ the WS-D4 critical-effect fold).
`proven`/selection lives as a description-quality dashboard, not a gate. This closes the
"WS-D4 tightening" open item.
