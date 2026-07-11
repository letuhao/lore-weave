# Tool description-quality (F5 selection) — 2026-07-11

**Harness:** `scripts/eval/tool_liveness/selection.py` · local gemma-4-26b · $0 · no execution.
**Raw data:** `docs/eval/tool-liveness/selection/selection.json`.

## What this measures (and what it deliberately does not)

This is **not** the workflow ship gate. A curated workflow *names* its tool; nothing selects
it, so `proven`/G1 is irrelevant there (decided 2026-07-11). This is the **chat-surface**
question: *given a tool's description, can a model tell when to use it?* A tool a model can't
pick from its own words is a **description bug** — and hiding it would guarantee it's never
picked.

**Method (a classification proxy).** The model is taken OUT of the agent loop — no lazy
tool-loading, no execution (so a bulk run can't fire a write against the real account). It's
shown the whole 223-tool catalog as `name: description` and asked which ONE tool a
natural-language request maps to. The request is the tool's **own** longest `_meta.synonyms`
entry — the trigger phrase it ships as *"this is what a user would say."* If the model can't
map a tool's own synonym back to it with every sibling present as a distractor, the
description doesn't distinguish it. This is a **hard, honest** isolation of
description-discriminability — a *proxy*, not a reproduction of the lazy-loaded chat
experience (real-loop selection is a stricter, separate bar).

## Headline

**110 / 146 tools discoverable (75%)** · 36 miss · 0 error. (146 of 223 tools carry
synonyms; the other 77 aren't probeable this way.)

75% is a *floor* under the hardest conditions (all 223 siblings present). The 36 misses are
where two tools' descriptions genuinely collide — the actionable output.

## Post-fix live re-run (2026-07-11, after WS-D5a + container/gateway rebuild)

The fixable subset shipped (synonyms specialized, `[Authoring workspace]`/`[Saved book]`
surface tags added) and went live (rebuild the owning MCP server **and** restart `ai-gateway`
— it caches the federated catalog). Live re-run: **112/146 discoverable (76%) · 34 miss.**

- **Synonym fixes confirmed live:** `book_steering_set` and `registry_propose_skill` dropped
  out of the miss list entirely — the over-generic "remember" no longer steals them.
- **Net only 36→34, and that is the honest result:** the residue is dominated by (C)
  inherent ambiguity — `composition_get_prose`/"chapter text", `composition_create_work`/"new
  writing project", `book_chapter_save_draft`/"edit chapter text" still split because a book
  *is* a writing project and both surfaces edit a chapter. Editing one description also shifts
  every other classification slightly, so a few borderline tools surfaced as new misses. **~76%
  is the floor** under the full-catalog stress test, set by genuine product-surface overlap,
  not by bad prose. Driving it lower needs a product decision (merge/clarify the parallel
  book/composition chapter surfaces), not more description tweaks.

## The misses, by pattern (each is a real description collision) — pre-fix snapshot

**1. `book_*` ⇄ `composition_*` — the dominant collision (12).** The book service and the
composition service both own "chapter", "prose", and "structure" concepts, and their
descriptions don't say which is which:

| synonym | should be | model picked |
|---|---|---|
| "make canon" | `book_chapter_publish` | `composition_publish` |
| "edit chapter text" | `book_chapter_save_draft` | `composition_write_prose` |
| "chapter text" | `composition_get_prose` | `book_get_chapter` |
| "new writing project" | `composition_create_work` | `book_create` |
| "rename chapter" | `composition_outline_node_update` | `book_chapter_update_meta` |
| "archive/unarchive chapter" | `composition_outline_node_delete`/`_restore` | `composition_arc_delete`/`_restore` |

→ **Fix:** each description should state its *domain boundary* — e.g. `composition_get_prose`
= "the DRAFTED prose from an authoring run", `book_get_chapter` = "the SAVED chapter body".

**2. Intra-family sibling blur (arc / settings / translation / jobs).** Within one service,
adjacent tools read alike:
- **arc:** `arc_get`↔`arc_list`, `arc_move`↔`arc_apply`, `arc_suggest`↔`arc_list`
- **settings:** `model_set_default`↔`get_defaults`, `model_set_favorite`↔`list_models`, `provider_inventory`↔`list_models`
- **translation:** `coverage`↔`job_status`, `job_status`↔`jobs_list`, `segment_status`↔`retranslate_dirty`, `job_control`↔`retranslate_dirty`
- **jobs:** `jobs_cancel`↔`jobs_pause`, `authoring_run_close`↔`jobs_cancel`

→ **Fix:** lead each sibling's description with the *verb that separates it* (read vs list,
set vs get, cancel vs pause).

**3. Over-generic synonyms that collide across services (a synonym bug, not a description
bug).** `"remember this rule"` → `book_steering_set` and `"remember this as a skill"` →
`registry_propose_skill` both lost to `memory_remember`; `"where does it say"`
(`book_search`) lost to `story_search`. The word "remember"/"search" is claimed by several
tools. → **Fix:** drop the over-broad synonym, or make it specific (`"remember this steering
rule"`).

## What to do with this

- It is a **description-quality backlog**, not a gate. The `book_*`/`composition_*` boundary
  (pattern 1) is the highest-value cleanup — 12 of 36 misses, and the pair most likely to
  bite a real chat user.
- Re-run after description edits: `python -m scripts.eval.tool_liveness.selection`
  (`--limit N` / `--service book_` to scope). The number to move is the 36 → down.
- The signal is intentionally kept OUT of `contracts/tool-liveness.json` (the ship gate) —
  the gate is about *executes* (does the tool work), this is about *discoverability* (is the
  description good). Two different questions, two different homes.
