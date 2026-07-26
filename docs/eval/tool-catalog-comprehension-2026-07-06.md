# Eval: tool-catalog-simplification comprehension check — 2026-07-06

**Spec:** `docs/specs/2026-07-06-tool-catalog-simplification.md` §10 step 0 · **Model:** Gemma-4 26B-A4B QAT (200K), `user_model_id=019ebb72-27a2-72f3-a42d-d2d0e0ded179`, `tool_calling:true` · **Method:** real target model, real provider-registry streaming endpoint (`loreweave_llm.Client.stream`, the same path `stream_service.py` uses in production), real `search_catalog()` (unmodified, imported from `app.services.tool_discovery`). Stub backend — no tool actually executed, only selection + argument construction inspected. Script: `services/chat-service/eval/run_tool_catalog_eval.py`.

**Scope, honestly:** this tests schema comprehension + argument construction + discovery-ranking. It does **not** simulate the full two-turn `find_tools`→activate loop, does not hit a real glossary-service backend, and does not exercise the confirm-token flow. Per the spec, this precedes — not replaces — the full mechanism build + cross-service live-smoke.

## Result: 12/12 PASS on live-model argument construction

Every §8 edge case that's model-facing was covered. All 12 scenarios passed on the first run, no retries, `temperature=0.0`, `reasoning_effort="none"`:

| Scenario | Edge case | Verdict |
|---|---|---|
| S1 happy create | create via base_version absence | PASS |
| S2 happy update | update via base_version presence | PASS |
| S3 batch create (N=3) | §8.7 batch size | PASS |
| S4 mixed batch (create+update in one call) | §8.1 mixed batch | PASS |
| S5 user scope, no book_id | §8.5 harmless-extra / omission | PASS |
| S6 delete, book scope | §8.8/8.9 confirm-gated branch | PASS |
| S7 delete, user scope | §8.8/8.9 direct/reversible branch | PASS |
| S8 batch delete (N=3) | §8.8 one-token-covers-batch | PASS |
| S9 "create" phrasing, old tool NOT offered | §8.10 no hallucinated legacy call | PASS |
| S10 attribute with `fields.field_type` | §8.6 open `fields` bag | PASS |
| S11 genre level | level selection | PASS |
| S12 larger batch (N=5) | §8.7 batch-size quality at 5 | PASS |

Notably: **S4 (mixed batch)** — the model produced one item with no `base_version` (the new "Bard" kind) and one item with `base_version:"v2"` (the existing "Wizard" kind) in the *same* `items[]` array, unprompted about how to structure it — the upsert-by-presence discriminator (§3.1/§6) worked exactly as designed, no explicit instruction needed beyond the tool description. **S9** confirms the model didn't invent a call to `glossary_book_create` (not in its tool list at all) when given "create"-flavored phrasing — it correctly used `glossary_ontology_upsert` instead, supporting the CAT-4 legacy-visibility design (§7): removing the old tool from the model's option set, not just from search, is sufficient to prevent the old name from being called.

## Finding: discovery ranking needs CAT-4 filtering — description/synonym tuning alone is insufficient

The offline `search_catalog()` check (real algorithm, no model call — deterministic token-overlap/fuzzy match) tells a different story than the live-call test:

| Query | Top-3 **with legacy tools present** (today) | Top-3 **after CAT-4 filter** (simulated) |
|---|---|---|
| "add a new kind to the book" | `glossary_book_create`, `glossary_user_create`, **`glossary_ontology_upsert` (3rd)** | **`glossary_ontology_upsert` (1st)**, composition_list_outline, translation_start_job |
| "create a genre" | same ordering — new tool 3rd | new tool 1st |
| "make a new attribute type" | same ordering — new tool 3rd | new tool 1st |

**With the old tools still in the catalog, `glossary_ontology_upsert` loses the ranking race every time** — despite carrying `_meta.synonyms: ["add a kind", "add a genre", "add an attribute", ...]` specifically added for this. The old tools' short, punchy descriptions ("Create a book-native genre, kind, or attribute row") score higher on raw token overlap against these queries than the new tool's longer, more precise description (which spends tokens on `base_version`/optimistic-locking/batch semantics that don't share vocabulary with a simple "add a kind" ask).

**This upgrades §8.13 from "worth tuning" to confirmed-necessary**: CAT-4 (excluding `legacy`-tagged tools from `search_catalog` entirely) is not a nice-to-have alongside better descriptions — synonym tuning alone was tried here and still lost 2-of-3 head-to-head against the old tools. The mechanism, not just the wording, is what makes the new tool discoverable. The "after CAT-4 filter" column confirms the fix works once applied: the new tool ranks unambiguously first with the legacy tools removed from the search space.

(Minor, non-blocking: the script logged a benign `asyncgen: aclose() already running` warning during its own async cleanup between iterations — a wart in the throwaway eval script's client lifecycle, not a finding about the production stream endpoint; all 12 scenario results were unaffected and scored cleanly.)

## Conclusion — go/no-go for BUILD

**Go**, with one confirmed requirement: build CAT-4 (the `_meta.visibility` filter in both `tool_discovery.py` and `find-tools.ts`) as part of this pass, not as an optional follow-on — the eval shows the new tool's discoverability depends on it, not on description quality alone. Argument construction (upsert discriminator, batch, scope selection, delete branching) is solid at 12/12 with zero schema changes needed.
