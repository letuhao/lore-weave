# Plan — Raw-Search E5: recall + calibrated score + golden expansion

Branch `raw-search/foundation` · **L** · v2.2 (no /amaw) · cross-service (book + knowledge → live-smoke required).
Findings driving this: P3-EVAL → lexical oracle-recall **0.63** (flat block `LIMIT` under-covers wide terms) + score = positional RRF floor **0.0164** (non-calibrated, negatives leak).

## Design decisions (PO-locked)
1. **`granularity=chapter|block`** — `chapter` = best block per chapter (max distinct-chapter recall → navigate); `block` = all matching blocks (exhaustive mine).
2. **Score:** keep RRF for *ordering*, add per-hit **`relevance`** (native lexical similarity / semantic cosine, 0–1) + a **score-floor** (`min_relevance`) to drop junk.
3. **Golden:** +~15 oracle-mined queries (phrase / multi-term / paraphrase / typo / more negatives) → ~33 total.

## Root cause (confirmed)
`lexicalSearchSQL` returns a flat `LIMIT $4` of **blocks**; for a term in 11 chapters the 10 block-slots cluster into fewer distinct chapters; orchestrator `cap_per_chapter(3)` + `[:limit]` compounds it. Fix = best-block-per-chapter SQL for the navigate path; high-limit all-blocks for mine.

## BUILD (TDD where pure)

### B1 — book-service lexical leg ([search.go](../../services/book-service/internal/api/search.go))
- Add `lexicalSearchChapterSQL` — window-function variant: `ROW_NUMBER() OVER (PARTITION BY cb.chapter_id ORDER BY (ILIKE $3) DESC, similarity DESC, block_index)`, keep `rn=1`, outer `ORDER BY exact DESC, sim DESC, sort_order LIMIT $4`. One best block per chapter → up to `limit` distinct chapters.
- `runLexicalSearch(ctx, bookID, q, limit, granularity)` — branch SQL on granularity (`block` = existing flat SQL).
- Add **`relevance`** to each hit map: `exact ? 1.0 : sim` (0–1); keep `score` (= `1+sim`/`sim`) for back-compat ordering.
- External `searchChapterText` + internal `searchChapterTextInternal` parse `?granularity=` (default `chapter` — strictly better navigate recall, additive for FE). Validate ∈ {chapter, block}.
- Tests ([search_test.go]): chapter-mode returns ≤1 block/chapter & covers all containing chapters within limit; block-mode unchanged; relevance present + 1.0 on exact; bad granularity → 400.

### B2 — book_client ([book_client.py](../../services/knowledge-service/app/clients/book_client.py))
- `lexical_search(book_id, q, *, limit, granularity="chapter")` → forward `granularity` query param.

### B3 — fusion ([hybrid_fusion.py](../../services/knowledge-service/app/search/hybrid_fusion.py))
- `apply_relevance_floor(hits, min_relevance)` — drop hits with `relevance < floor` (missing relevance treated as pass-through 1.0 to avoid nuking legs that don't set it). Pure, unit-tested.
- `cap_per_chapter` already param'd — caller passes `cap=1` (chapter) / large (block).
- `rrf_fuse` already preserves extra keys (`{**chosen}`) → `relevance` survives. Add a regression test asserting it.

### B4 — orchestrator ([raw_search.py](../../services/knowledge-service/app/routers/public/raw_search.py))
- `+ granularity: Literal["chapter","block"] = "chapter"`, `+ min_relevance: float = MIN_RELEVANCE_DEFAULT` query params.
- Pass `granularity` to `book_client.lexical_search`.
- Semantic `_passage_to_hit`: set `relevance = raw_score` (cosine).
- After fusion: `apply_relevance_floor(..., min_relevance)`; `cap = 1 if granularity=="chapter" else BLOCK_CAP`.
- `MIN_RELEVANCE_DEFAULT` — **calibrate in VERIFY**: measure the cosine the negative queries (封神榜…) get, set the default just above it (so negatives drop, positives survive). Param lets callers override.
- Tests ([test_raw_search_api.py]): granularity forwarded; floor drops a low-relevance hit; relevance present on both legs; default still degrades cleanly.

### B5 — golden expansion ([rawsearch_golden.json](../../services/knowledge-service/app/benchmark/rawsearch_golden.json))
- `scripts/build_rawsearch_golden.py` (new, committed — encodes the anti-cheat oracle-mining; book/project via args, eval defaults) regenerates the set with +~15 queries: phrase (`武市学宫`), multi-term, paraphrase, typo (query mis-spells a real term; expected = correct term's oracle chapters), +2 negatives. ~33 total.

### B6 — runner ([run_rawsearch_eval.py](../../scripts/run_rawsearch_eval.py))
- `+ --granularity` (default chapter) + `--min-relevance`; pass through; report chapter-mode table + the lexical-oracle-recall lift. (Block-mode exhaustive recall optional line.)

## VERIFY (evidence gate — ≥2 services → live-smoke)
- book-service `go test ./internal/api/ -run Search` green; knowledge `pytest tests/unit/test_raw_search_api.py tests/unit/test_rawsearch_metrics.py` green.
- Rebuild book + knowledge images (ship Go SQL + Python). Re-seed not needed (corpus stable).
- **Calibrate** `MIN_RELEVANCE_DEFAULT` from a negatives-cosine probe; set it; re-run.
- Live: `scripts/run_rawsearch_eval.py` → capture new table. Expect **lexical oracle-recall ≫ 0.63** (target ≥0.90), negatives return nothing above floor, hybrid still ≥ legs. Evidence: `live smoke: E5 rawsearch eval, lexical oracle-recall 0.63→X, neg-leak 0`.

## REVIEW(code) 2-stage → QC → POST-REVIEW (STOP; suggest /review-impl — cross-service contract change) → SESSION → COMMIT → RETRO
Deferred after: E6 FE (granularity toggle + relevance display + K-selector), EVAL-CI, 2nd-book golden.
