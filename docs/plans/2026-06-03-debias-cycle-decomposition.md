# De-bias enrichment — cycle decomposition · 2026-06-03

> Design (locked + benchmarked): [docs/specs/2026-06-03-enrichment-debias-book-profile.md](../specs/2026-06-03-enrichment-debias-book-profile.md) (commit `bafafb6a`).
> Branch `lore-enrichment/foundation`. **Each cycle = one full 12-phase v2.2 workflow with human-in-loop** (PO checkpoints at CLARIFY-end + POST-REVIEW). CLARIFY+DESIGN are inherited from the spec (already PO-reviewed + benchmarked), so each cycle opens at a focused DESIGN-review → PLAN.

## Why XL cycles (not the 14 small ones)
The design is locked and benchmarked (6 bias layers, 9 scenarios, 3 code-traced verifications). BUILD does not need to be chopped to "think"; small gates only add overhead. With the 1M context we implement at XL granularity, one coherent concern per cycle.

## The 3 cycles

| Cycle | Slices | Scope | Acceptance | /review-impl |
|---|---|---|---|---|
| **C1 — BE de-bias core** | 0a+0b | profile table/model/reader/seed · thread `StrategyContext.profile` · parameterize 3 prompt builders (worldview/lang/era/voice + kind_label) · profile-driven anachronism · drop enum gating + 5 static kind tables + `resolve_dimensions`/stable-id · de-bias detect-path + **write-back (KB8)** | ① Fengshen **byte-identical** (existing 562+ tests green) ② a CHARACTER + an English-profile book enrich **AND promote** end-to-end with correct kind/language (live smoke on the demo) | ✅ yes (write-back is H0-critical) |
| **C2 — Grounding rework** | 0c | `KnowledgeContextGrounding` (build_context → parse `<passages>`) + glossary-canon + KG-neighbour grounding composed into the P1 path · "extract first" prerequisite signal · shared PD reference library (`project_id` nullable) · chapter-**selection** ingest | an extracted non-Fengshen book grounds with **no re-ingest**; an unextracted book → clear prerequisite signal; a library corpus is reachable cross-project | — |
| **C3 — Profile authoring** | 0d+0e | Profile API GET/PUT/suggest + book-client `list_chapters`/`get_chapter_text` + AI-suggest (chapters + KG summary + 1 LLM call → profile + `dimension_overrides`, server-validated) + FE Settings panel + dimension-override editor + chapter-selection picker + i18n×4 | author can suggest + edit a profile (incl. dimensions) and it round-trips; FE vitest green | — |

## Sequencing + dependencies
- Linear: **C1 → C2 → C3** (C3 depends only on C1's profile model; C2 independent of C3).
- **Minimum to "fix the bug" = C1** (de-biases output for any *already-extracted* book using existing grounding). C2 unblocks brand-new books; C3 is the authoring UX.
- Each cycle self-verifies on the demo (Fengshen book has source_corpus + characters, so C1's CHARACTER path is testable without C2).

## Cross-cycle invariants (hold in every cycle)
- **No-regression:** the Fengshen profile reproduces today's behavior byte-for-byte (golden tests).
- **H0:** enriched ≠ canon — unchanged; C1's write-back de-bias must keep the kind/dimension dynamic WITHOUT loosening any H0 guard.
- **No glossary Go change** (verified: `entity_enrichments.dimension` free-text, kinds pre-seeded by extraction).
- **No new book-service Go endpoint** (verified: chapters + draft-text + projection suffice).
- **Eval-gate de-bias DEFERRED** (`LE-debias-eval-suite`): P1 correct for any book; P2/P3 stay Fengshen-gated.

## Per-cycle plan files
- C1 → [docs/plans/2026-06-03-debias-C1-plan.md](2026-06-03-debias-C1-plan.md)
- C2 / C3 → authored when their cycle opens.
