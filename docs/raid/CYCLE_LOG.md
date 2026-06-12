# RAID Cycle Log — creation-unblock

> Task `creation-unblock` (slug `2026-06-13-creation-unblock`). One row per cycle as RAID executes. See [cycle decomposition](../plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md).
>
> **Schema note:** column 1 is the BARE cycle number (0–28) and column 3 is the single-word Status — this is the contract `scripts/raid/coordinator-helper.py` parses (`| <num> | <title> | <status> |`) and that `done-cycle` flips PENDING→DONE. Do not prefix the number with `C` or reorder these three columns.
>
> **C0** is the shared-FE bootstrap; per the /raid contract C0 is built via the default+AMAW workflow (NOT dispatched by the Coordinator) and must be DONE before the loop runs C1+.

| Cycle | Title | Status | BE/FE | Commit | Verify / notes |
|---|---|---|---|---|---|
| 0 | Bootstrap — shared FE foundation | DONE | FE | (this commit) | FormDialog max-h/scroll/pinned-footer + reusable AddModelCta (deep-link+return, ProvidersTab honors ?return=) + rerank/reranker reconcile (canonical RERANK_CAPABILITY, spy-injection wiring test). tsc+eslint clean; 17 vitest green; verify-cycle-0.sh exit 0. Live screenshot deferred to first consumer (C5/C6/C7/C15) — FormDialog/AddModelCta have no live surface yet (D-C0-FOUNDATION-LIVE-SMOKE). Default workflow, not /raid. |
| 1 | Rerank registration (FE) | PENDING | FE | — | add rerank to register form; picker matches; 0-found feedback |
| 2 | Rerank discovery (BE+FE) | PENDING | BE+FE | — | inventory sync parses Cohere-shape /v1/models; live smoke |
| 3 | Rerank connection test (BE+FE) | PENDING | BE+FE | — | rerank-aware verify (real /v1/rerank); live smoke |
| 4 | Book picker (FE) | PENDING | FE | — | reusable BookPicker replaces raw-UUID field |
| 5 | Build-graph gates unblock (FE) | PENDING | FE | — | in-flow AddModelCta + visible benchmark gate |
| 6 | Project detail SHELL (FE — IA backbone G6) | PENDING | FE | — | nested route + project-scoped sub-tabs (no select-box) |
| 7 | Projects browser = HOME + build polish (FE) | PENDING | FE | — | search/sort/filter/paginate; rows route into C6 — M1 |
| 8 | Entities semantic layer (BE+FE) | PENDING | BE+FE | — | status/semantic_query/anchor_score; scoped in C6 shell; live smoke |
| 9 | Promote + entity detail (BE+FE) | PENDING | BE+FE | — | link-to-glossary promote → draft; live smoke |
| 10 | Glossary Gap Report (BE+FE) | PENDING | BE+FE | — | wire find_gap_candidates; bulk-promote |
| 11 | Pending Proposals inbox (FE) | PENDING | FE | — | aggregate 3 sources, deep-link; integrate not duplicate |
| 12 | Build wizard — target-typed extraction + concurrency (BE+FE) | PENDING | BE+FE | — | conditional task-list ~4 sites; live smoke targets=events |
| 13 | Build wizard — glossary pinning (BE+FE) | PENDING | BE+FE | — | pinned→known_entities; worker-ai fetch_by_ids; stats endpoint; live smoke |
| 14 | Timeline narrative-order + importance (BE+FE) | PENDING | BE+FE | — | importance + narrative sort; scoped in C6 shell — M2 |
| 15 | Writer unblock (FE) | PENDING | FE | — | chat-model AddModelCta in Compose; ready-to-draft messaging |
| 16 | Work-setup resilience (BE composition) | PENDING | BE | — | POST /work must not 502 when knowledge down; live smoke |
| 17 | Writer flow polish (FE) | PENDING | FE | — | guided first-run; continue-from-cursor — M3 |
| 18 | Graph subgraph endpoint (BE knowledge) | PENDING | BE | — | GET /projects/{id}/subgraph n-hop node-capped; live smoke |
| 19 | Graph canvas (FE) | PENDING | FE | — | visual network reusing GraphCanvas; read-only — M4 |
| 20 | World container — model + API (book-service) | PENDING | BE | — | worlds table + world_id FK + bible chapter; live smoke |
| 21 | World container — FE | PENDING | FE | — | prose-less worldbuilding against bible chapter — M5 |
| 22 | Intent-branching onboarding (FE) | PENDING | FE | — | 4-intent first-run router |
| 23 | Derivative schema + API (composition) | PENDING | BE | — | source_work_id/branch_point/divergence_spec/entity_override; project_id NOT NULL |
| 24 | Divergence wizard + derivative studio (FE) | PENDING | FE | — | 4-step wizard + 2-layer grounding badges |
| 25 | Packer override-merge (composition) | PENDING | BE | — | base→overrides→delta two-project merge; live smoke |
| 26 | Critic override enforcement (composition) | PENDING | BE | — | derivative critic dimension enforces overrides |
| 27 | Flywheel on delta + what-if→derivative promotion | PENDING | BE+FE | — | approved dị bản chapters extract into delta; live smoke |
| 28 | Living-world view (FE) | PENDING | FE | — | world surfaces canon + derivative branches as timeline tree — M6 |
