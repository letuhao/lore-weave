# Plan — KG-Build Embedding-Benchmark UX Fix (batch R1–R6)

**Date:** 2026-06-22 · **Branch:** `feat/knowledge-graph-ontology` · **Status:** DESIGN + PLAN (ready to BUILD)
**Analysis:** [`2026-06-22-kg-benchmark-ux-gap-analysis.md`](../specs/2026-06-22-kg-benchmark-ux-gap-analysis.md) · **Deferred row:** `D-JOURNEY-KG-BENCHMARK-UX`
**Surfaced by:** live drive of the worldbuilder journey on the Dracula book — `Build KG` 409'd `benchmark_missing`, and a `runs=1` benchmark reported `passed:false` at `recall@3=1.0`.

## 1. Goal

Fix, in ONE coherent effort, the design contradiction + the implementation gaps that make "Build KG" a dead-end. After this, the journey "tell the agent / click Build KG" clears the benchmark gate without a structural impossibility, without a misleading "low-quality" message, without polluting the real project, and with an agent-accessible remedy.

The six findings (analysis §5) collapse into **one backend re-keying** (R1) that also dissolves the pollution (R1c), plus four small surface fixes (R2 labelling, R3 clamp, R4 MCP tool, R5 FE checklist, R6 swap warning).

## 2. Root cause (one line)

The gate demands a passing benchmark **for the build project** (`extraction.py:696` keys `(user, project, embedding_model)`), the runner **refuses to run on a project with content** (`runner.py:223-227` `not_benchmark_project`), and the FE's only "Run benchmark" button sits **on that same real project** — three constraints that cannot co-hold once a project has passages. Underneath: `min_runs=3` reports a perfect `runs=1` as `passed:false` with no reason.

## 3. Design decisions

### D1 — Re-key the benchmark to `(user, embedding_model)`, run it on an auto-provisioned sandbox (R1 Option A)
The benchmark answers *"is this **model** good enough for my entities?"* — that's a per-**model** property, not per-project. So:

- **Gate lookup** becomes model-scoped: a new `BenchmarkRunsRepo.get_latest_for_model(user_id, embedding_model)` drops the `b.project_id = $1` filter from the existing 3-column query ([benchmark_runs.py:45-94](../../services/knowledge-service/app/db/repositories/benchmark_runs.py)), keeping `p.user_id = $2 AND b.embedding_model = $3 ORDER BY created_at DESC`. The extraction gate ([extraction.py:696](../../services/knowledge-service/app/routers/public/extraction.py)) calls it instead of the project-scoped one. ⇒ a passing run for model X on ANY of the user's projects (incl. the sandbox) unlocks every project using X. **Back-compat:** existing per-project passing runs still satisfy it (same table, looser filter).
- **The run itself routes to a hidden sandbox project** keyed to `(user, embedding_model)`, resolve-or-create. The sandbox always has zero real passages, so `not_benchmark_project` can never fire, and the ~10 synthetic `benchmark_entity` fixtures land in the sandbox's vector space — **never in the real project** (this is the whole of R1c, for free).
- **Contract stays stable:** the FE keeps calling `POST /projects/{id}/benchmark-run`. The handler resolves the project's embedding model, gets-or-creates the sandbox for `(user, that model)`, and runs there. The `project_id` in the path now identifies *the user + the model to benchmark*, not the run target. (No FE call-site change needed for the run; only the badge copy in R2/M4.)

**Rejected — Option B** (keep per-project, make the runner tolerate real passages + clean up fixtures): leaves a pollution-cleanup `finally` that can leak on crash, and keeps the conceptually-wrong per-project keying. Not chosen.

### D2 — Sandbox project model
- A new boolean `knowledge_projects.is_benchmark_sandbox NOT NULL DEFAULT false` (migration). The sandbox is owner-scoped, `book_id = NULL`, `name = "__benchmark__:<embedding_model>"`, `is_benchmark_sandbox = true`.
- **Excluded from every user-facing project list** (`ProjectsRepo.list_*` adds `AND NOT is_benchmark_sandbox`) so it never shows in the UI/agent project pickers.
- One sandbox per `(user, embedding_model)` (its vector space = that model's dimension). Reused across re-benchmarks; the existing per-project `benchmark_already_running` sentinel keys on it.

### D3 — Make `passed:false` self-explaining (R2)
- `passes_thresholds()` ([core.py:157-174](../../services/knowledge-service/app/benchmark/core.py)) returns `gate_failures: list[str]` alongside the bool — named codes: `insufficient_runs`, `low_recall`, `low_mrr`, `low_avg_score`, `negative_control_too_high`, `unstable`.
- `BenchmarkRunResponse` ([extraction.py:1658-1676](../../services/knowledge-service/app/routers/public/extraction.py)) + the persisted `raw_report` carry `gate_failures`.
- FE `BenchmarkBadge` ([EmbeddingModelPicker.tsx:219-227](../../frontend/src/.../EmbeddingModelPicker.tsx)): when `gate_failures == ["insufficient_runs"]`, render *"benchmark inconclusive — needs ≥3 passes"*; render the quality copy ONLY for an actual metric failure. Never say "low-quality results" when `recall@3 ≥ threshold`.

### D4 — Clamp `runs` up to `min_runs` on the interactive endpoint (R3)
The benchmark-run handler clamps the effective run count up to `min_runs` (so `runs=1 → 3`) and notes `runs_clamped_to: 3` in the response. The benchmark is embeddings-only (~$0), so 3 runs is cheap and is the only way to a valid pass. (FE already pins `runs:3`; this closes the trap for API/agent callers.) Rejected: a hard `409 runs_below_min_runs` (worse UX than just running enough).

### D5 — `kg_run_benchmark` MCP tool (R4, MCP-first)
A domain-owned tool ([build_tools.py](../../services/knowledge-service/app/tools/build_tools.py) neighbourhood) that runs the benchmark for the caller's project's embedding model (→ sandbox via D1), owner-only, idempotent. Direct (no cost-confirm — it's ~$0 and read-shaped on the real graph). Wired into the executor + `TOOL_DEFINITIONS` + the `@mcp_server.tool` shim. The `kg_build_graph` preview already shows `⚠ benchmark not passing` ([build_graph_effect.py:132-136](../../services/knowledge-service/app/ontology/build_graph_effect.py)); now the agent has the remedy in-flow.

### D6 — FE prerequisite checklist + swap warning (R5, R6)
- `BuildGraphDialog` shows the chain up front: **LLM model → embedding model → passing benchmark → (optional rerank)**, each with a ✓/✗ + inline action — not just a disabled-Confirm reason at the bottom (P0 KN-1/BL-16).
- `PUT /embedding-model` warning copy ([extraction.py:1308-1315](../../services/knowledge-service/app/routers/public/extraction.py)) adds: *"the new model has no passing benchmark — you'll need to re-run it before building."*

## 4. Contract changes
- `BenchmarkRunResponse` gains `gate_failures: string[]` + `runs_clamped_to?: int` (additive, back-compat).
- New MCP tool `kg_run_benchmark` in the knowledge MCP catalogue.
- Gate semantics change (project-scoped → model-scoped) is **internal** — no public request/response shape change on `extraction/start`.
- Update the knowledge OpenAPI/contract doc for the benchmark response + tool catalogue.

## 5. Build plan — milestones

**M1 — backend, R1 core (the root-cause re-key + sandbox).** ~L.
- Migration: `is_benchmark_sandbox` on `knowledge_projects` (+ partial index for list-exclusion).
- `get_latest_for_model(user, embedding_model)` repo method; gate ([extraction.py:696](../../services/knowledge-service/app/routers/public/extraction.py)) uses it.
- `benchmark-run` handler: resolve project's embedding model → get-or-create sandbox `(user, model)` → run there; `ProjectsRepo` get-or-create-sandbox + list-exclusion.
- Tests: unit (2-col lookup; sandbox naming/idempotency), **integration real-PG** (benchmark on sandbox → `extraction/start` on a DIFFERENT content-bearing project PASSES; fixtures land only in sandbox; sandbox absent from list).

**M2 — backend, R2 + R3 (labelling + clamp).** ~S.
- `passes_thresholds → (bool, gate_failures)`; thread into `BenchmarkRunResponse` + `raw_report`.
- Clamp `runs` up to `min_runs` in the interactive handler; response notes it.
- Tests: `runs=1` → clamped → passes; a real metric fail names the right `gate_failures`; an `insufficient_runs`-only fail is distinguishable.

**M3 — backend, R4 (`kg_run_benchmark` MCP tool).** ~S/M.
- Tool + arg model + executor + `TOOL_DEFINITIONS` + `@mcp_server.tool` shim; owner-gated; runs via D1.
- Tests: catalogue includes it; owner-gate; runs→passing; **live MCP smoke** over the wire (tools/list shows it; call → sandbox benchmark passes).

**M4 — frontend, R2 + R5 + R6.** ~M.
- `BenchmarkBadge` reason-aware copy (insufficient_runs ≠ low-quality).
- `BuildGraphDialog` leading prerequisite checklist.
- `EmbeddingModelPicker` "Run benchmark" now always succeeds (sandbox) — drop/adjust the `not_benchmark_project` toast path; swap-warning copy.
- Tests: badge renders the right copy per `gate_failures`; checklist gating; `tsc --noEmit` clean.

**M5 — contract + docs.** ~XS.
- OpenAPI/contract for `gate_failures`/`runs_clamped_to` + the tool; clear the `D-JOURNEY-KG-BENCHMARK-UX` row.

### Sequencing
M1 → M2 (M2's fail_reason feeds M4) → M3 (needs M1 sandbox) → M4 (needs M2 field) → M5 alongside. M1 is the load-bearing risk boundary (gate + migration) — checkpoint/commit there before M3/M4.

## 6. Verify / live-smoke (the gate this whole effort is about)
Re-drive the **real Dracula build through the fixed flow** on the running stack: (a) a fresh content-bearing project gets `benchmark_missing` → run benchmark (sandbox) → `extraction/start` now passes with NO `not_benchmark_project`, NO fixtures in the real project; (b) `runs=1` via API now clamps and passes (no "low-quality" lie); (c) `kg_run_benchmark` over the wire clears the gate for an agent. Rebuild knowledge-service + (for M4) frontend images first (stale-image false-greens, per `live-smoke-rebuild-stale-images-first`).

## 7. Risks / migration / rollback
- **Migration** (`is_benchmark_sandbox`) is additive + defaulted — safe; the shared-DB suite is Python/asyncpg here (no Go DDL-deadlock concern).
- **Back-compat:** the looser gate lookup still honours existing per-project passing runs, so already-built projects keep working; no re-benchmark forced.
- **Sandbox accumulation:** one per `(user, model)`; bounded, hidden, cheap. Optional later GC if a user churns models.
- **Rollback:** the gate change is one repo call; revert restores per-project keying. The migration column can stay (unused) on rollback.
- **Cross-service:** knowledge-service only (gate/runner/repo/tool) + frontend; no other service's contract moves. `extraction/start`'s public shape is unchanged.

## 8. Size
**XL** (backend re-key + migration + MCP tool + FE + contract, across knowledge-service + frontend; load-bearing gate on the headline journey). Subagent-assisted build recommended; M1 is the spine, M2–M6 are independent surfaces that can fan out after M1 lands.
