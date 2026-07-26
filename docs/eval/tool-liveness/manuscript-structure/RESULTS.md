# Manuscript-structure tool — weak-model graph comprehension eval

- **Date:** 2026-07-22
- **Spec/impl:** [`docs/specs/2026-07-22-manuscript-structure-tool.md`](../../../specs/2026-07-22-manuscript-structure-tool.md) · commit `b1eb36225`
- **Model:** `google/gemma-4-26b-a4b-qat` (local lm_studio, the target weak model), temperature 0
- **Method:** each scenario drives the **real** book-service MCP (`/mcp`, cross-service to composition), the
  emitted tool-calls execute live, and the effect is **DB-verified** in Postgres. State reset between runs.
- **Question:** does a weak agent understand the part/chapter GRAPH, and does the unified tool actually work?

## A/B — fragmented vs unified surface (1 pass, 6 scenarios)

- **FRAGMENTED** = `book_structure_read` + `book_chapter_set_part` + `book_chapter_reorder` (the pre-existing
  surface — NO way to create/rename/reorder a part: the real gap).
- **UNIFIED** = `book_structure_read` + `book_structure_edit`.

| Scenario | Fragmented | Unified | Note |
|---|---|---|---|
| navigate (which part is Ch2 in?) | ✅ | ✅ | read-only, identical tool both arms |
| **create part + move chapter** | ❌ *impossible* | ✅ | **the gap** — fragmented has no create-part tool |
| reorder chapters | ✅ | ✅ | both make the real reorder call |
| traversal (count unassigned) | ✅ | ✅ | read-only (1 stray miscount in an earlier pass — model variance, tool returned the right data) |
| trap: nest a part inside a chapter | ~ | ~ | **not a discriminator** — no op can do it in EITHER surface; verify was a phrasing heuristic |
| **create + rename part** | ❌ *impossible* | ✅ | **the gap** — fragmented has no rename-part tool |
| **total** | **4/6** | **5/6** | the 2 unified wins are the previously-impossible part-authoring ops |

**Token cost:** unified input slightly higher (~14.2k vs ~12.4k over the suite), output **lower**
(~6.9k vs ~9.9k) — on the gap scenarios the fragmented model *flails* (re-reads, long reasoning searching
for a tool that isn't there) and burns output; the unified model is decisive.

## Reliability — the newly-enabled + mutation ops (UNIFIED, N=5 each, DB-verified)

| Scenario | Pass rate | Tool calls | mean tok in/out |
|---|---|---|---|
| create part + move chapter | **5/5** | 2× `book_structure_edit` | 2336 / 479 |
| reorder chapters | **5/5** | 2× read + 1× edit | 3741 / 2370 |
| create + rename part | **5/5** | 2× `book_structure_edit` | 2172 / 536 |

**15/15**, DB-verified. The weak model reliably **chains** the graph — it creates a part, reads back the
returned `part_id`, and homes/renames against it — in exactly the minimum number of decisive calls. No
wrong-tool calls, no loops (the `guidance` + `is_complete` stop-signals hold).

## Conclusion

1. **Yes — gemma-4 understands the graph.** It navigates part↔chapter, chains create→home on a returned id,
   reorders, and counts groupings, using the unified surface correctly and reliably.
2. **The unified tool closes a real capability gap.** Part authoring (create/rename) went **0/2 → 2/2** in
   the A/B and **10/10** across repeats — operations a weak agent literally could not perform before.
3. **It is effective, not just possible.** 15/15 DB-verified on the authoring/mutation scenarios, 2–3
   decisive calls each, decisive stop behavior.

Honest caveats: the `trap_nest` verify is a keyword heuristic and not a meaningful A/B signal (neither
surface can nest, so neither does harm); one traversal miscount in an earlier pass was model variance on a
read the tool answered correctly. Harness: `scratchpad/structure_ab.py` + `reliability.py`.
