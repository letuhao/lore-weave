# Cycle 10: Strategy (b) retrieval

## 🎯 TL;DR (30 seconds — TOP critical info)
Build the **P1 cultural-retrieval strategy** over OWNED corpora (山海经 + 封神演义). Ingest text into `source_corpus`, chunk it, embed each chunk by **REUSING knowledge-service `/internal/embed` (model_ref)** with a **per-project embedding model resolved from provider-registry** — NO new RAG framework, NO langchain/llamaindex, NO heavy deps. Add a lightweight similarity search that, for a given gap, returns top-K grounded passages and populates `cultural_grounding_ref` on the proposal.
- **This is a strategy plugin** registered into the C8 registry, consuming C9's scaffolds — it does NOT replace the template strategy.
- **Web/internet search is OUT of scope.** Grounding comes only from the two downloaded, public-domain corpora.
- **Embedding model name is NEVER hardcoded** — `text-embedding-bge-m3` resolved via provider-registry / `model_ref`.
- **Acceptance gate:** `scripts/raid/verify-cycle-10.sh` exits 0 (created by this cycle's runner; forward ref OK). Includes a **live-smoke**: seed one 山海经 chunk → embed → retrieve it back via similarity.

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C8, C9
- C8 = `EnrichmentStrategy` interface + registry + feature-flags + cost guardrail + job state machine. C10 registers as a strategy and obeys the cost cap.
- C9 = P1 template strategy (dimension scaffolds). C10's retrieval enriches the same gap→scaffold path with grounded passages.
- Also relies on C2 (`source_corpus`, `cultural_grounding_ref` tables) and C1 (knowledge-service embedding client / `KnowledgeReadPort`) already landed.

## Scope (IN)
- **Corpus ingest:** loader that reads the downloaded 山海经 + 封神演义 public-domain text into `source_corpus` rows: title, corpus_kind, project scope, raw text, license note. CJK-safe (UTF-8, no mojibake).
- **Chunking:** deterministic, CJK-aware chunker (sentence/passage windows with overlap) producing stable chunk ids; re-ingest of identical text is idempotent (no duplicate chunks).
- **Per-project embedding:** call knowledge-service `/internal/embed` with the project's `model_ref` (resolved via provider-registry, e.g. `text-embedding-bge-m3`); store vectors + the resolved `model_ref` alongside each chunk so a model change is detectable.
- **Similarity search:** cosine/inner-product top-K over a project's chunk embeddings (custom lightweight implementation — pgvector if the C2 migration enabled it, else in-process numpy-style scoring). Returns ranked passages with corpus + chunk provenance.
- **Retrieval strategy plugin:** `RetrievalStrategy` implementing the C8 `EnrichmentStrategy` interface; given a gap + C9 scaffold, embeds the gap query, retrieves top-K grounded passages, attaches them, and **populates `cultural_grounding_ref`** (corpus id + chunk ids + similarity scores) on the produced proposal.
- **Cost guardrail integration:** embed calls counted against the C8 per-job cost cap; JIT model-load latency tolerated (call by id, retry once on first-call load).
- `scripts/raid/verify-cycle-10.sh` running unit tests + the live-smoke embed/retrieve check.

## Scope (OUT — explicitly)
- **NO web/internet search** (ddgs/SearXNG/Tavily/SerpAPI/MCP) — owned corpora only. (technique-d sourcing is C16/C17 territory.)
- **NO new RAG framework / heavy deps** — no langchain, no llamaindex, no separate vector-DB service.
- **NO hardcoded model names** — all model ids via provider-registry / `model_ref`.
- **NO generation/normalization-repair or H0 origin-tagging logic** — that is C11.
- **NO canon-verify / anachronism / injection-defense at proposal creation** — that is C12.
- **NO write-back to glossary/KG, NO promotion** — that is C13.
- **NO editing climate/geo eval files**, world-service, game-server, tilemap, or `infra/existing-prod/`.
- **NO P2 fabrication / P3 re-cook** strategies.

## Acceptance criteria (CI gates — exit code 0 = pass)
- `scripts/raid/verify-cycle-10.sh` exits **0**.
- Unit: ingest of fixture corpus is **idempotent** (re-run → same chunk count, no dupes).
- Unit: similarity search returns the seeded chunk as top-1 for its own text query; top-K ordering is by descending score.
- Unit: strategy run on a gap produces a proposal whose `cultural_grounding_ref` references real corpus + chunk ids with scores.
- Unit: embedding client uses a `model_ref` from provider-registry — a grep-style guard test asserts **no literal `bge-m3` / `text-embedding-` model string** in strategy/client source.
- **Cross-service live-smoke (REQUIRED — CLAUDE.md VERIFY rule):** seed one 山海经 chunk → call real knowledge-service `/internal/embed` on a stack-up → retrieve the chunk back via similarity. Evidence string MUST carry a `live smoke: <one-liner>` token; if the stack is not bootable, use `live infra unavailable: <reason>` or `LIVE-SMOKE deferred to D-C10-LIVE-SMOKE` (track the row in SESSION_PATCH). Mock-only green is INSUFFICIENT.

## DPS parallelism plan
- **DPS 2–3 (low, per locked cost posture).** Three weakly-coupled tracks behind shared types:
  1. **Ingest+chunk track** — `source_corpus` loader + idempotent CJK chunker + fixtures.
  2. **Embed+search track** — knowledge-service embed client wrapper (over C1 port) + `model_ref` resolution + similarity scorer.
  3. **Strategy-plugin track** — `RetrievalStrategy` wiring into C8 registry + `cultural_grounding_ref` population + cost-cap hookup.
- Define chunk/embedding/grounding-ref dataclasses FIRST so tracks 2 and 3 code against stable shapes. Live-smoke is single-threaded at the end (needs the stack up + real embed call).

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Mock-only false-green:** does any "passing" retrieval test actually hit the real `/internal/embed`, or is the embedding mocked everywhere? Demand the live-smoke token; a green unit suite alone is the known cross-service trap.
- **Hardcoded model name:** is `text-embedding-bge-m3` (or any embed id) baked into code instead of resolved from provider-registry `model_ref`? Check client + strategy + tests.
- **Idempotency / chunk drift:** re-ingesting the same corpus must not duplicate chunks or silently re-embed; chunk ids must be stable across runs.
- **model_ref drift:** are stored vectors tagged with the resolving `model_ref`? A silent embedding-model change would mix incomparable vector spaces (a real bug class seen on this platform — embedding model-ref UUID drift).
- **Scope leak toward canon (H0 spirit):** does retrieval accidentally write anything to glossary/KG, or mark passages as canon? It must only attach grounding refs to a *proposal*; no `source_type='glossary'`, no promotion.
- **Hidden web-search / heavy dep:** any import of langchain/llamaindex/requests-to-internet/ddgs sneaking in? Must be owned-corpora-only and lightweight.
- **CJK correctness:** chunker on Classical Chinese — does it split mid-character or corrupt UTF-8? Verify byte-safe handling.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR only if ALL hold: (1) no model name hardcoded — embed via `model_ref`; (2) no web search and no new RAG/heavy dep added; (3) no writes to glossary/KG/Neo4j and no canon/promotion logic; (4) only `lore-enrichment-service` + its own DB/tables touched — no edits to world-service/game-server/tilemap/`infra/existing-prod/` or climate/geo eval files; (5) live-smoke token present (or an explicit, tracked deferral). Otherwise BLOCKED with the offending file/line.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- `docs/plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md` — C10 row + parallelism/cost-discipline notes.
- `docs/plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md` — Tooling decisions (REUSE knowledge-service, no framework; web-search OUT), Execution decisions (Qwen/bge-m3 via provider-registry; JIT load), Demo scope (4 locations + public-domain corpora), H0 invariant.
- `docs/03_planning/lore-enrichment/PLAN.md` — overall plan + service boundary.
- `docs/03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md` — code-verified ground truth (knowledge-service `/internal/embed`, glossary SSOT, scoping).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **REUSE knowledge-service `/internal/embed` — do NOT build/import a RAG framework (no langchain/llamaindex, no heavy deps). Web/internet search is OUT of scope; owned corpora (山海经 + 封神演义) only.**
- 🔴 **NO hardcoded model names. Embedding model (`text-embedding-bge-m3`) resolved via provider-registry / `model_ref`; store the resolving `model_ref` with each vector to detect drift.**
- 🔴 **H0 boundary: retrieval ONLY attaches `cultural_grounding_ref` to a PROPOSAL. It NEVER writes glossary/KG, never marks anything `source_type='glossary'`, never promotes. Origin-tagging is C11, write-back/promotion is C13.**
- 🔴 **Acceptance gate = `scripts/raid/verify-cycle-10.sh` exits 0, AND a cross-service live-smoke (seed 山海经 chunk → real embed → retrieve) carries a `live smoke:` token. Mock-only green does NOT pass.**
- 🔴 **DO NOT TOUCH: world-service, game-server, tilemap, `infra/existing-prod/`, or climate/geo eval files. Stay inside `lore-enrichment-service` + its own DB.**
