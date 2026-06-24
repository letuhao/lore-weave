# KG-Build Embedding-Benchmark UX Gap — Analysis

**Date:** 2026-06-22
**Author:** investigation (read-only; no code changed)
**Status:** Analysis — recommendations only
**Trigger:** Live drive of the worldbuilder journey ("create book → ontology → import → glossary → translate → **BUILD KG** → wiki → enrich → write") hit `409 benchmark_missing` on `POST /v1/knowledge/projects/{id}/extraction/start`. The K17.9 embedding benchmark had never been run, and the first attempt to run it (`runs=1`) returned `passed:false` despite `recall@3=1.0` / `mrr=1.0`.

---

## 1. The gate, precisely

`POST /v1/knowledge/projects/{id}/extraction/start` is hard-gated on a passing benchmark for the project's embedding model:

- `services/knowledge-service/app/routers/public/extraction.py:696-711` — `benchmark_repo.get_latest(...)` is `None` ⇒ `409 {error_code: "benchmark_missing"}`.
- `extraction.py:712-726` — latest run exists but `passed=false` ⇒ `409 {error_code: "benchmark_failed"}`.

This gate is the **single chokepoint** for *all* build paths: the REST start route, the rebuild route, the campaign/internal-dispatch path, and the agent `kg_build_graph` path all funnel through `_start_extraction_job_core` (`extraction.py:506`), which contains the gate. The agent confirm-effect `apply_build_graph` (`app/ontology/build_graph_effect.py:56-85`) calls the same core, so the agent cannot bypass it either.

### What "passing" requires

`BenchmarkReport.passes_thresholds()` (`app/benchmark/core.py:157-174`) checks, in order:
1. **`runs >= min_runs`** (default **3**) — *this is checked first, before any metric*.
2. `recall_at_3 >= 0.75`, `mrr >= 0.65`, `avg_score_positive >= 0.60`.
3. `negative_control_max_score <= 0.50` (or `<= 0.70` for dim-1024 / bge-m3, per the `thresholds_by_dimension` override).
4. `max(stddev_recall, stddev_mrr) <= 0.05`.

Thresholds live in `app/benchmark/golden_set.yaml:118-139` (`min_runs: 3`).

**Consequence:** a `runs=1` benchmark fails at step 1 unconditionally — `self.runs (1) < min_runs (3)` returns `False` **before** recall/MRR are ever consulted. A perfect `recall@3=1.0 / mrr=1.0` run with `runs=1` is reported `passed:false`. This is *by design* (stability gate: you can't measure `stddev` across runs with one sample, so a single pass is treated as non-conclusive), but the design is **completely invisible to the user** — see §3b.

### The dedicated-project requirement

`run_project_benchmark` (`app/benchmark/runner.py:223-227`) refuses to run if the project already contains any passage whose `source_type` is in `KNOWN_SOURCE_TYPES` (chapter/chat/glossary) ⇒ `409 {error_code: "not_benchmark_project"}`. The fixture loader tags its synthetic golden-set passages `source_type="benchmark_entity"` and the benchmark scores retrieval against *those*. The documented assumption (`runner.py:9-15`, `:80-84`) is that **benchmarks run on a dedicated, empty project**.

### Changing the embedding model is destructive

`PUT /{project_id}/embedding-model?confirm=true` (`extraction.py:1265-1368`) deletes the entire Neo4j graph, sets `extraction_status='disabled'`, and switches the model. Without `confirm=true` it returns a warning (`:1308-1315`). So a model swap to clear a failed benchmark **also discards any graph already built**.

---

## 2. What the design intended

The design **explicitly chose** a *visible inline* benchmark gate — it is not meant to be silent. Evidence:

- `docs/specs/2026-06-13-knowledge-service-standalone-ux-review.md:46-57` ("Gate B — the benchmark gate, the obscure one") flagged the benchmark as a **"second, non-obvious prerequisite buried in a sub-picker"** and recorded the **corrected prerequisite chain**: *LLM model + embedding model + **passing benchmark (required)** + rerank (optional)*. It calls this out as **P0 KN-1 / BL-16**.
- `docs/raid/cycle_briefs/05_build-graph-gates.md:4,16` mandated: *"promote the golden-set benchmark from a hidden/implicit precondition to a **visible inline gate** — an unbenchmarked project shows a 'Run benchmark' step, and only a passing benchmark enables the Confirm/Build button. **No backend change.**"*

So the design intent was: **benchmark is an explicit, user-visible step with a "Run benchmark" button, gating Confirm.** It was *not* meant to be auto-run, and *not* meant to be silent.

The FE largely implements that intent:
- `EmbeddingModelPicker.tsx:177-187` renders a `BenchmarkBadge` (passed/failed/no-run) + a `RunBenchmarkButton` when not passed.
- `BuildGraphDialog.tsx:265-316` re-fetches the benchmark status and disables Confirm with a named reason (`"Run the golden-set benchmark and pass it to enable extraction (above)."`).
- `useRunBenchmark.ts:283` always posts `runs: 3` — so the FE path never trips the `runs=1` min-runs trap.

---

## 3. Verdict: this is a **DESIGN gap** (a contradiction the spec never reconciled), riding on top of two real implementation gaps

The headline issue is **design-level**, and there are concrete implementation sub-gaps beneath it. Breaking it down:

### (a) The dedicated-project contradiction — **DESIGN gap (the root cause)**

This is the deepest and most damaging problem, and **the design never resolved it**:

- The **backend benchmark runner** requires a *dedicated, empty* project (`runner.py:223-227`; `not_benchmark_project` 409).
- The **frontend** puts the "Run benchmark" button **inside `BuildGraphDialog` / `EmbeddingModelPicker`, on the user's real, content-bearing project** (`EmbeddingModelPicker.tsx:183-185`).
- The **gate** (`extraction.py:696`) keys the benchmark to `(user_id, project_id, embedding_model)` — i.e. it demands a passing run **for the very project you're trying to build**.

These three cannot all be satisfied at once on a real worldbuilder project. The journey is *create book → import → extract glossary → build KG*. By the time the user reaches "Build KG", the project may already hold glossary/chapter passages (or will the instant extraction starts). The benchmark the gate demands is keyed to **this** project, but the runner **refuses to run on this project** the moment it has real passages.

The result the user actually hit (`benchmark_missing`, then a failing run) is the *benign early-state* of this contradiction — the project happened to still be empty of `:Passage` nodes. The moment any real passage exists, the FE's own "Run benchmark" button starts returning `not_benchmark_project` (surfaced as a toast: *"Benchmarks must run on a dedicated project. Create a new project before running."* — `EmbeddingModelPicker.tsx:320-324`), with **no UI anywhere that creates or routes to that dedicated project.** The design produced a gate keyed to project P, a runner that forbids running on project P, and a UI that only offers to run on project P. No spec doc reconciles these.

The RAID brief (`05_build-graph-gates.md:21`) explicitly scoped the cycle **"NO backend changes"** and assumed *"benchmark endpoints already exist"* — so the FE was wired to call a benchmark endpoint that structurally cannot serve the FE's own call site once the project has content. The UX review (`...standalone-ux-review.md`) caught the *visibility* problem (Gate B is buried) but **did not catch the dedicated-vs-real-project contradiction**.

### (b) `min_runs=3` makes a perfect `runs=1` report `passed:false`, surfaced **nowhere** — **IMPLEMENTATION gap**

- `core.py:159` short-circuits on `runs < min_runs` *before* metrics, so `passed=false` with `recall@3=1.0`.
- The `BenchmarkRunResponse` (`extraction.py:1658-1676`) returns `passed`, `recall_at_3`, `mrr`, `runs` — but **no reason for the fail**. The FE `BenchmarkBadge` (`EmbeddingModelPicker.tsx:219-227`) renders `"✗ Benchmark failed (recall@3 1.00) — extraction would produce low-quality results."` — which is **actively misleading**: recall was perfect; the only "failure" was insufficient run count.
- The FE always sends `runs:3`, so a normal FE user never sees this. But (i) any direct API caller, (ii) the agent/MCP surface, and (iii) any future caller that lowers `runs` will get a perfect-but-failed verdict with a wrong explanation. The gap is *"passed:false with a 1.0 metric must be self-explaining."*

### (c) Pollution risk vs the real project — **DESIGN gap (same root as (a))**

The benchmark loads ~10 synthetic golden-set entities as `:Passage` nodes tagged `benchmark_entity` (`fixture_loader.py`, via `runner.py:238-248`). On a dedicated project that's fine. But because the FE invites the user to run it from the real project, on a project that is *still empty* the run **succeeds and leaves 10 `benchmark_entity` passages in the real project's vector space.** There is no documented cleanup of these fixture passages, and `_has_real_passages` deliberately excludes `benchmark_entity` so re-runs don't self-block — meaning the synthetic nodes can accumulate and co-exist with real content. This is a direct consequence of the (a) contradiction.

### (d) Agent path vs FE path — **IMPLEMENTATION gap (asymmetric guidance)**

- **FE path:** handles the gate well *for the empty-project case* — visible badge, "Run benchmark" button, named disabled reason, always `runs:3`.
- **Agent path (`kg_build_graph`):** `app/tools/build_tools.py:68-72` only checks that an embedding model is *configured*; it does **not** check benchmark status. The gate fires later at confirm (`build_graph_effect.py:76`). The preview card (`build_graph_effect.py:118-136`) *does* add a `⚠ benchmark not passing` row — good. **But neither the agent tool nor the confirm card offers any way to RUN the benchmark.** There is no `kg_run_benchmark` MCP tool. So an agent-driven user is told "benchmark not passing, confirm will be rejected" with **no agent-accessible remedy** — they must drop out of the agent flow into the FE dialog. And the FE dialog, on a real project, hits contradiction (a). The agent path is a dead-end on this gate.

---

## 4. Severity for the user journey

**High / journey-blocking.** "Build KG" is a mandatory mid-point of the headline worldbuilder flow. The failure modes compound:

1. First-time user: `benchmark_missing` 409 → must discover the buried "Run benchmark" button (UX review already rated this P0).
2. If they run it wrong (`runs=1` via API/agent): a **perfect** run reports `failed` with a **misleading** "low-quality results" message → user concludes their embedding model is bad and may swap it (destructively).
3. Once their project has any real passage (the normal state at "Build KG" time): the FE's own "Run benchmark" button returns `not_benchmark_project` → **hard dead-end with no in-product path to the required dedicated project.**
4. Agent-driven user: warned but given no tool to clear the gate.

The benign case the live drive hit (empty project, `runs=1` confusion) is the *mildest* manifestation; the contradiction in (a)/(c) is strictly worse for any project that has progressed past import.

---

## 5. Recommendations

Ordered by leverage. References are `file:line` anchors for whoever implements.

### R1 — Resolve the dedicated-vs-real-project contradiction (the root cause) — **DESIGN decision required**
Pick one coherent model and make code + UI agree:

- **Option A (recommended): decouple the benchmark from the build project.** Benchmark per `(user_id, embedding_model)` on an auto-provisioned, hidden "benchmark sandbox" project, not on the user's real project. Change the gate (`extraction.py:696`) to look up the latest passing run **by embedding_model for the user**, independent of `project_id`. This matches the real intent ("is this *model* good enough for *my* entities?") and removes both the `not_benchmark_project` dead-end and the pollution in (c). The FE "Run benchmark" button then transparently runs against the sandbox.
- **Option B: keep per-project, but make the runner tolerate real passages** by scoring only `benchmark_entity` passages and guaranteeing fixture cleanup after the run (delete the 10 synthetic nodes). Removes the `not_benchmark_project` guard (`runner.py:223-227`) and adds a `finally` cleanup. Higher pollution risk; not preferred.

Either way: **the FE call site and the backend runner must stop disagreeing.** This is a backend + contract change — it needs a real plan, not a quick edit (defer-gate reason 2: structural).

### R2 — Make `passed:false` self-explaining; stop mislabelling a perfect short run — **IMPLEMENTATION, fix-now-eligible**
- Add a `fail_reason` (or `gate_failures: string[]`) field to `BenchmarkReport.passes_thresholds` / `BenchmarkRunResponse` (`core.py:157-174`, `extraction.py:1658-1676`) so a fail caused solely by `runs < min_runs` is distinguishable from a metric fail.
- Fix the FE `BenchmarkBadge` (`EmbeddingModelPicker.tsx:219-227`): when the only failing gate is min-runs, render *"benchmark inconclusive — run ≥3 passes"*, **not** *"extraction would produce low-quality results"* (which is false when recall@3=1.0).

### R3 — Default/clamp `runs` to `min_runs` for human-facing callers — **IMPLEMENTATION, fix-now-eligible**
The FE already pins `runs:3` (`useRunBenchmark.ts:283`). Mirror that safety on the BE: in `BenchmarkRunRequest` (`extraction.py:1652-1655`) consider clamping the effective run count up to `min_runs` for the interactive endpoint (or reject `runs < min_runs` with a clear `409 runs_below_min_runs` instead of silently producing a `passed:false`). This closes the "perfect-but-failed" trap for API/agent callers without weakening the stability gate.

### R4 — Give the agent path a way to clear the gate — **IMPLEMENTATION, MCP-first**
Per the MCP-first invariant, add a `kg_run_benchmark` MCP tool (domain-owned, `app/tools/build_tools.py` neighbourhood) so an agent that sees the `⚠ benchmark not passing` preview row (`build_graph_effect.py:132-136`) can actually run it, rather than dead-ending into the FE. Wire it to the same orchestration `run_project_benchmark` uses. (If R1 Option A lands, this tool runs against the sandbox project.)

### R5 — Surface the prerequisite chain up-front in the build flow — **IMPLEMENTATION (already P0 KN-1/BL-16)**
The build flow should state the chain *before* the user reaches a disabled Confirm: *LLM model → embedding model → passing benchmark → (optional rerank)*. The UX review (`...standalone-ux-review.md:53-54,68-72`) already specifies this as KN-1; ensure it's actually shipped as a leading step/checklist in `BuildGraphDialog`, not just a disabled-reason string at the bottom.

### R6 — Make the destructive model-swap path benchmark-aware — **IMPLEMENTATION, small**
When `PUT /embedding-model?confirm=true` (`extraction.py:1265-1368`) switches models, the new model has no passing benchmark, so the *next* build will 409. The warning response (`:1308-1315`) should tell the user "you will need to re-run the benchmark for the new model" so the destructive swap doesn't silently set up the next dead-end.

---

## 6. One-line root cause

The benchmark gate was designed as a *visible per-project prerequisite* and the FE wired it onto the **real build project**, but the benchmark runner was built to require a **dedicated empty project** and the `min_runs=3` stability rule reports a perfect single pass as `failed` with a misleading message — so on any non-trivial project the user's only offered remedy (the in-dialog "Run benchmark" button) structurally cannot clear the gate, and on an empty project it clears only via a confusing `runs`/min-runs dance. The headline is a **DESIGN contradiction** (R1), sitting on top of two **implementation** mislabelling/missing-tool gaps (R2–R4).
