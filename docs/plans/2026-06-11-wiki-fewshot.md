# Plan — D-WIKI-M8-FEWSHOT (gold AI→human pairs as few-shot exemplars)

**Date:** 2026-06-11 · **Branch:** `wiki/phase2-change-control` · **Size:** XL (cross-service, hot-path)

## Goal
Inject gold AI-draft→human-edit pairs as few-shot exemplars into wiki generation so the
model learns the editorial style humans apply. Gated `WIKI_FEWSHOT_ENABLED` (default OFF).
PO: render in the **system message** (explicit framing, not synthetic turns); source via a
**glossary self-contained SQL** (adjacent `ai`→`owner` revisions), no learning dependency.

## The gold pair
An article whose revision history has an `'ai'` revision (the draft) immediately followed
by a later `'owner'` revision (the human correction) — exactly the `wiki.corrected` emit
condition. The bodies live in glossary `wiki_revisions.body_json` (TipTap). There is NO
TipTap→text helper on either side, so the endpoint flattens + truncates server-side.

## Changes

### glossary-service
- `internal/api/wiki_gold_pairs.go` (new): `GET /internal/books/{book_id}/wiki/gold-pairs?limit=N`
  (internal-token). Runs the ai→owner adjacent-pair SQL (DISTINCT ON latest owner per
  article, the latest 'ai' with `version < owner.version`), newest first, `LIMIT min(N, 5)`.
  Flattens each `body_json` (TipTap) → plaintext via a `tiptapPlaintext` walker (~20 lines)
  and **truncates each to ~1500 chars**. Returns `{pairs:[{article_id, entity_id, ai_text,
  human_text}]}`.
- `internal/api/server.go`: register the route under the internal `/internal/books/{book_id}`
  group (next to `/wiki/articles`).

### knowledge-service
- `app/clients/glossary_client.py`: `fetch_wiki_gold_pairs(book_id, *, limit) -> list[dict]`
  — GET the endpoint, best-effort `[]` on any failure (gold pairs missing must never break
  generation; mirrors `fetch_entities_by_ids`).
- `app/wiki/prompt.py`: `build_messages(..., exemplars: list[tuple[str,str]] | None = None)`
  + `_render_exemplars(exemplars)` → appended to the **system** message after the profile
  clauses, before `corrective`. Header: "EXAMPLES OF HUMAN EDITS (learn the editorial style;
  do NOT copy content or cite their labels): --- AI DRAFT --- … --- HUMAN-EDITED --- …".
- `app/wiki/generate.py`: `generate_article(..., exemplars=None)` → thread into the
  `build_messages` call inside the retry loop (loop-invariant; same every attempt).
- `app/wiki/orchestrator.py`: in `run_wiki_gen_job`, beside the `profile` fetch, when
  `settings.wiki_fewshot_enabled` fetch `exemplars` once (book-level) via
  `clients.glossary.fetch_wiki_gold_pairs(job.book_id, limit=settings.wiki_fewshot_max_examples)`
  → `[(p["ai_text"], p["human_text"]) ...]`; thread through `_generate_one` → `generate_article`.
  Off / fetch-fail → `[]` (no exemplars; generation unchanged).
- `app/config.py`: `wiki_fewshot_enabled: bool = False`, `wiki_fewshot_max_examples: int = 3`.

## Tests
- glossary (DB-integration): seed an article with ai(v1)→owner(v2) revisions → the endpoint
  returns the pair (ai_text from v1, human_text from v2); an article with only an ai revision
  → not returned; TipTap flatten + truncation; limit cap. + route-auth (401 w/o token).
- knowledge: `build_messages` with exemplars renders the framing in the SYSTEM message (not
  user), present only when given; `generate_article` threads exemplars; orchestrator fetches
  once + gated off (no fetch when disabled) + degrades to [] on client failure (mock glossary).

## VERIFY
Cross-service (glossary + knowledge). go build/vet + glossary api suite; knowledge wiki
suite + ruff. Live-smoke deferred to D-WIKI-M8-FEWSHOT-LIVE-SMOKE (needs a corrected article
+ a real generation with the flag on).

## Out of scope / follow-ups
Relevance-ranking the exemplars (newest-first only); per-kind exemplars; dynamic token budget
(fixed char-truncation for now); using learning's corrections table as the filter (glossary
SQL is self-contained).
