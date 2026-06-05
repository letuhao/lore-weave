# C2 — Grounding rework · build plan · 2026-06-03

> Cycle 2 of [the de-bias decomposition](2026-06-03-debias-cycle-decomposition.md). Slice 0c.
> Design: [spec §2.0/§2.9/§2.10](../specs/2026-06-03-enrichment-debias-book-profile.md) (+ the code-traced verifications). **Size: XL.** Full 12-phase; CLARIFY+DESIGN inherited from the spec.
> Branch `lore-enrichment/foundation`. Depends only on C1 (done).

## Goal
An **extracted** book grounds enrichment **without re-ingesting chapters** — by reusing the digest the platform already has (knowledge `build_context` passages + glossary authored canon + KG facts), composed into the P1 grounding. `source_corpus` stays for DELIBERATE material only (external reference library + author-selected chapters). An **unextracted** book gets a clear "extract first" signal, not a cryptic skip.

**Why (C1 live finding):** the demo 姜子牙 enrich produced honest "故阙如" no-fab content because its only grounding was 1 thin source_corpus chunk (score 0.28). The book's KG/glossary has far more about 姜子牙 — C2 feeds that in, so generation has real evidence.

## Current state (audited)
- `GapPipeline.run_gap` → `RetrievalStrategy.run([gap], ctx)` → grounding ONLY from `source_corpus` (embed search). Empty corpus → no grounding → `GenerationError` → gap skipped.
- `KnowledgeClient.build_context(user_id, project_id, message)` → ONE assembled context STRING (chat-shaped: `<passages>`/`<entities>`), Mode-3 "full" includes L3 passages; (user,project)-scoped; needs `extraction_enabled`; 404 on cross-user.
- `GlossaryClient.list_entities(book_id)` → entity + `short_description` (authored canon).
- No live KG-neighbour reader is wired (fabrication's `neighbor_lookup` defaults to None).

## Design — a `GroundingComposer` with injected providers
Grounding sources, **entity-tight first, breadth last**, deduped + top-K by score:
1. **Glossary canon** — the entity's `short_description` → one `GroundingRef` (`corpus_id='glossary:canon'`, score 1.0). Entity-tight, clean.
2. **KG facts / context (breadth)** — `build_context(message = canonical_name + localized missing-dim labels)` → parse the `<passages>` block → `GroundingRef`s (`corpus_id='knowledge:context'`). Degrade-safe (empty/404 → no refs).
3. **`source_corpus`** — the existing embed search (external reference library + selected chapters).
Composer = union → dedup (by excerpt hash) → top-K. Generation's H0 "refuse if empty" holds; an entity with truly nothing known still skips (correct).

## TDD task order
| T | What | Files | Test-first |
|---|---|---|---|
| **T1** | `GroundingProviderFn` seam + `compose_grounding(providers, top_k)` (union/dedup/top-K, deterministic) | new `app/retrieval/grounding.py` | new `tests/test_grounding_composer.py` — merge/dedup/top-K/empty |
| **T2** | Glossary-canon provider (`list_entities` → entity desc → `GroundingRef`) | `app/retrieval/grounding.py`, `app/clients/glossary.py` (find-by-name) | provider returns a ref for a known entity; `[]` for unknown |
| **T3** | Knowledge-context provider (`build_context` → parse `<passages>`) — **PLAN-verify the exact tag** | `app/retrieval/grounding.py`, `app/clients/knowledge.py` | parse passages from a sample block; empty/404 → `[]` (degrade) |
| **T4** | Wire the composer into the P1 path: `RetrievalStrategy` (or `GapPipeline`) composes corpus ∪ canon ∪ knowledge-context; assembly injects the providers (it has kc + glossary_client) | `app/retrieval/strategy.py` OR `app/jobs/stages.py`, `app/jobs/assembly.py` | a gap with EMPTY source_corpus but canon/KG present now grounds (was skipped) |
| **T5** | Shared reference library: `source_corpus.project_id` nullable; store search scopes `project_id = $proj OR project_id IS NULL`; seed demo PD corpora as shared (optional) | `app/db/migrate.py`, `app/retrieval/store.py` | search returns a NULL-project (library) corpus for any project |
| **T6** | Chapter-**selection** ingest: `POST …/books/{id}/ground {chapter_ids:[...]}` → book-client `get_chapter_text` → `ingest_corpus`; idempotent | new `app/api/grounding.py`, `app/clients/book.py` | selected chapters ingested; re-run no-op; empty selection 400 |
| **T7** | "extract first" signal: detect/enrich on an unextracted book (no glossary entities + empty KG via `build_context` mode) → a clear 409/`needs_extraction` signal, not a silent skip | `app/api/gaps.py` / runner outcome | unextracted book → clear signal |
| **T8** | Test-ripple + suite green | tests | — |
| **T9** | VERIFY live: re-enrich 姜子牙 on the demo → grounding now includes KG/canon → richer (non-"阙如") content; an extracted book grounds with NO source_corpus ingest | — | `live smoke:` token |

## Acceptance
1. `pytest` green incl. composer tests.
2. Live: a gap with empty `source_corpus` but glossary canon / KG context **grounds + generates** (was skipped); demo 姜子牙 re-enrich produces richer content than the C1 "阙如".
3. H0 untouched (grounding is evidence; generation chokepoint + confidence<1.0 unchanged).
4. No re-ingest of chapters for the own-book path.

## Risks / PLAN-verify
- **`build_context` passages format** — confirm the exact `<passages>` tag/structure to parse (read `app/context/modes/full.py` formatter on knowledge-service); if brittle, wrap the whole context block as one ref (coarser but safe).
- **build_context scope** — (user, project), needs `extraction_enabled`; demo `project_id := book_id`. A multi-book project grounds across books (accepted).
- **Cross-service** (lore-enrichment + knowledge + glossary) → VERIFY needs a `live smoke` token.
- **Scope guard:** T5 (shared library) + T6 (selection ingest) are DELIBERATE-ingest features; if the cycle runs long, T1–T4 + T7 + T9 are the headline (own-book grounding) and T5/T6 can split to a C2b. Decide at BUILD.

## Phases
CLARIFY ✅(spec) → DESIGN ✅(spec) → REVIEW(design, this cycle) → PLAN ✅(this file) → BUILD(T1–T8) → VERIFY(T9) → REVIEW(code) → QC → POST-REVIEW → SESSION → COMMIT → RETRO.
