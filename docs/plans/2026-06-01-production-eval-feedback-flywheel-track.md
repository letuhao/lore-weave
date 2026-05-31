# Track Plan — Production Eval + Feedback Flywheel (learning-service quality plane)

**Date:** 2026-06-01 · **Status:** DESIGN-CHECKPOINT (no code yet — design artifact for a multi-session XL track) · **Author:** session 105 ·
**Extends** [`2026-05-31-extraction-accuracy-and-eval-plan.md`](2026-05-31-extraction-accuracy-and-eval-plan.md) (the correction-loop + eval-hygiene plan) and [`2026-05-31-phase-b2-config-telemetry-plan.md`](2026-05-31-phase-b2-config-telemetry-plan.md) (config telemetry, SHIPPED).
**Grounded in** a 6-dimension industry research workflow (OpenAI · Anthropic · Google Vertex · LLM-observability platforms · vendor-neutral ML feedback patterns · LoreWeave codebase audit) + an adversarial critique pass.

---

## 0 · Why this track exists — the gap

LoreWeave's extraction pipeline is **ship-ready** (independent-judge baseline **F1 = 0.869**, 95% CI [0.842, 0.895], measured this session over 9 golden chapters with the disjoint-median metric-of-record). The R&D arc that produced it is **closed**.

But the entire eval apparatus — macro P/R/F1, 3-judge LM-Studio ensembles, Fleiss κ, disjoint-median, bootstrap CI — lives **only** in `services/knowledge-service/tests/quality/`. It is host-run R&D code that **writes nothing to any database**. The live extraction pipeline emits `outcome` + `cost` + `config_hash` and nothing about *quality*. It cannot answer "what was the precision for chapter 3 under model X with filter Y?".

A production AI platform (the way OpenAI/Anthropic/Google operate) closes the **data flywheel**: deploy → collect signal from real usage → persist to DB → eval online → self-improve. LoreWeave has the **run/telemetry half** (`extraction_runs`, `config_registry`, `config_adjustment_events`, `corrections`) but **zero of the quality/eval half**. This track builds that half — the **quality plane** — on top of the existing `learning-service`.

**North star.** Every extraction run and chat turn carries live per-category quality signal (not just outcome/cost); user edits + chat ratings flow through the existing `outbox → relay → Redis-Streams` spine into an append-only score store as gold labels; a sampled online-eval consumer runs the lifted ensemble (host-orchestrated against LM Studio) and persists disjoint-median F1 with bootstrap CI; shadow/champion-challenger replays real chapters through a candidate config and logs structural projections (never raw novel text) for paired A/B; a **Dev Log** ties every config/prompt version to its measured F1 delta; and production failures auto-promote into a versioned eval-case dataset. The whole plane honors **redact-by-default**, **local-LLM-first cost reality**, **multi-tenant isolation**, and **human-gated promotion ("flashlight, not autopilot")**.

---

## 1 · Industry grounding — what we steal, where we diverge

Five load-bearing patterns appear across all sources. We **match** the data models and statistical discipline; we **diverge** on infrastructure for a local-first, single-operator, redact-by-default reality.

| Pattern | Frontier-lab form | LoreWeave form |
|---|---|---|
| **Eval data model** | OpenAI Eval / Run / Output-Item; Vertex `summary_metrics` + `metrics_table`; Langfuse/Phoenix Score entity | `eval_runs` / `eval_results` / `quality_scores` + `score_config` — **item-level** stored so clustered/paired SE is recomputable at query time (Anthropic: never store only the aggregate) |
| **Grader = reward** | One grader serves eval criterion, online monitor, AND the RL reward (OpenAI grader→reward identity) | Lift the existing scorer once; deterministic structural F1 (python-grader analog, no source text) + LLM-judge (score_model analog). Grader→reward identity **preserved** for a possible future local DPO/LoRA, but no RLHF now. |
| **Production tap** | OpenAI `store=True`+metadata→replay; Anthropic **Clio** (cluster prod usage, privacy-first) | `extraction_runs` + content-addressed `config_registry` already ARE the tap; steal the **replay** pattern (re-grade a metadata-filtered slice; A/B a candidate config on the same chapter inputs) |
| **Online eval** | (filter + sampling_rate) → async out-of-band judge → write score back by id, never blocks the request | New `eval-runner` Redis consumer group; **sampling is the cost governor** (local LLM); host-orchestrated judge to dodge container OOM |
| **Feedback loop** | thumbs/regen/**edit** → DPO preference pairs; user edits = (preference + supervision + reward) triple | We **already capture** entity/relation/event correction edits — a latent gold-label goldmine; add the only missing primitive (chat thumbs/regenerate) |

**Deliberate divergences (local-first):** no managed eval service / Vertex Pipelines / ClickHouse — Postgres tables + window functions + the existing Redis-Streams consumer pattern. Sampling + host-orchestrated LM-Studio judging instead of cloud judge-everything (cloud Claude/GPT = periodic calibration only; iterative cloud tuning is prohibitively expensive — the inverse of frontier-lab economics). No raw-content capture — structural projections + content-hashes only, with a **k-anonymity + privacy-auditor gate stricter** than typical observability platforms (which log prompts/completions freely). Promotion stays **human-gated** by design, fitting the no-deadline correctness-over-speed bar. We mirror **OpenTelemetry `gen_ai.*`** attribute names + the `gen_ai.evaluation.result` event *shape* so telemetry stays portable to Phoenix/Grafana later.

---

## 2 · Architecture — the quality plane on learning-service

```
   PRODUCTION                         EVENT SPINE (REUSE)                 QUALITY PLANE (NEW, learning-service)
 ┌──────────────┐  outbox        ┌───────────────────────────┐
 │ worker-ai    │───────────────▶│ worker-infra relay         │  loreweave:events:knowledge
 │ extraction   │  extraction_   │  (XADDs outbox_id — F1/F2) │──────────────┬───────────────────────────────┐
 │ run          │  run_completed │  event_log = durable replay│              │                               │
 └──────────────┘                └───────────────────────────┘   learning-collector            eval-runner (NEW group)
        │                                       ▲                  (corrections,                 sample 5–10%, judge async
        │ writes                                │ outbox           config telemetry)             host→provider-registry→LM Studio
        ▼                                       │                         │                               │
 ┌──────────────┐   knowledge.*_corrected ┌─────┴───────┐                  ▼                               ▼
 │ knowledge-   │────────────────────────▶│ chat-service │           corrections,            eval_runs / eval_results /
 │ service      │   glossary.entity_updated│ message_     │           extraction_runs,        quality_scores  ◀── score_config
 │ (Neo4j SSOT) │   (actor=user)           │ feedback(NEW)│           config_registry         (append-only, dual dedup key)
 └──────────────┘                          └─────────────┘                                            │
        ▲ replay challenger config (shadow, fire-and-forget)                                          ▼
        └───────────────────────────────────────────────────────────── shadow_extraction_runs → shadow_comparisons
                                                                          eval_cases / correction_clusters (k-anon + auditor)
                                                                          Dev Log (config_hash → F1 delta)  ─▶ promotion gate
```

**Reuse (do NOT rebuild):**
1. The **event spine** — KS `outbox_events` → worker-infra relay (already XADDs `outbox_id` as the stable dedup key, verified `outbox_relay.go:49`, test-enforced) → Redis Streams → `learning-collector` with DLQ + `XAUTOCLAIM` PEL-reclaim. New consumer groups attach via **Redis fan-out** without perturbing existing delivery (exactly how `learning-collector` was added beside `knowledge-extractor`).
2. **`event_log`** (worker-infra `loreweave_events`) as the durable replay source for backfill.
3. **`config_registry`** content-addressed snapshots as the "model version" identity every `eval_run` / shadow / rollout / Dev-Log delta keys to — no new versioning.
4. **`extraction_runs` + `corrections` + `config_adjustment_events`** as the telemetry spine the quality tables join to.
5. **`get_outcome_recompute`** (`mining.py:158`) — already written.
6. The mature **3-judge ensemble + Fleiss κ + disjoint-median + bootstrap-CI** logic (`tests/quality/`, cycles 72–74) — gateway-compliant; **lift, don't rewrite**.
7. **`project_embedding_benchmark_runs`** as the DDL house-style template for the new eval tables.
8. The redact-by-default `split_snapshot`/`diff_class` machinery in handlers.
9. The existing **Mining Insights panel** on `KnowledgePage` as the host for the Dev Log view.
10. **MinIO** for dataset/adapter snapshots; **pgvector** for cluster embeddings.

**Build new:** the quality DB schema; `eval-runner` + shadow consumer groups; `online_eval_rule` sampling; chat `message_feedback` (+ `loreweave:events:chat` added to STREAMS); Dev Log read API + FE; promotion gate; Clio clustering + privacy gate.

**Refactor:** Q0 lifts `tests/quality` into a shared package with a `PersistenceAdapter` seam + parameterizes the hardcoded extractor/filter UUIDs (`compute_ensemble_macros.py:48-49`) into a `JudgePanel` config; Q2 threads run provenance so `source_extraction_run_id` stops being NULL; Q8 augments `get_config_quality` to rank by realized eval F1 (additive query, no config-side migration).

---

## 3 · DB schema (extend learning-service)

The backbone = OpenAI's three-object split + a universal append-only Score entity (Langfuse/LangSmith/Phoenix), keyed to the existing `config_registry` + `extraction_runs` spine. **Item-level, never aggregate-only** so paired/clustered SE is recomputable. **Structural + content-hash only** (redact-by-default).

| Table | Purpose | Key columns |
|---|---|---|
| **`eval_runs`** | One row per scored dump (OpenAI Run / Vertex summary_metrics). | `eval_run_id` PK (uuidv7), `user_id`, `project_id`, `book_id`, `source_extraction_run_id`, `config_hash` REFERENCES config_registry, `judge_panel_id`, `dataset_version`, `disjoint_median_f1`, `fleiss_kappa`, `bootstrap_ci` JSONB, `bias_metrics` JSONB, `n_chapters`, `created_at`; **UNIQUE(source_extraction_run_id, judge_panel_id)** |
| **`eval_results`** | Per-row, per-category result (OpenAI Output-Item / Vertex metrics_table). Item-level → clustered SE at query time. | `id` PK, `eval_run_id` FK, `category` (entity\|relation\|event), `chapter_ref` (the **cluster unit** for clustered SE), `precision`, `recall`, `f1`, `input_hash`, `gold_projection` JSONB; INDEX(eval_run_id, category) |
| **`quality_scores`** | Universal append-only Score/Feedback entity. 3-judge ensembles + human corrections + chat ratings coexist without mutating output. | `id` PK, `target_kind` (entity\|relation\|event\|extraction_run\|chat_message), `target_id`, `book_id`, `user_id`, `metric_name`, `value_num`, `value_label`, `data_type`, `source` (human\|llm_judge\|heuristic), `judge_model`, `comment`, `source_eval_run_id`, `origin_service`, `origin_event_id`, `created_at`; **dual dedup — see §9 fix #5** |
| **`score_config`** | Registered versioned metric definition (Langfuse ScoreConfig); validates scores at write time; mirrors OTel `gen_ai.*` naming. | `score_config_id` PK, `name` UNIQUE, `data_type`, `min_value`, `max_value`, `categories` JSONB, `description`, `is_archived`, `created_at` |
| **`judge_panel`** | Single registered judge-ensemble config (UUIDs today scattered across env vars → drift). Records ensemble + which models to exclude as extractor/filter. *(see §9 over-build note — start as a Q0 config object, table only when a 2nd panel exists)* | `judge_panel_id` PK, `judge_model_refs` JSONB, `extractor_exclude_ref`, `filter_exclude_ref`, `rubric_template_hash`, `created_at` |
| **`message_feedback`** *(chat-service)* | The missing chat-turn feedback primitive. Explicit thumbs/rating + implicit regenerate-as-negative; emitted via chat outbox. | `id` PK, `message_id`, `session_id`, `user_id`, `rating` SMALLINT, `reason`, `regenerated_from_message_id`, `created_at` |
| **`online_eval_rule`** | (filter + sampling_rate) automation for `eval-runner`; sampling rate = the local-LLM cost governor. | `rule_id` PK, `user_id`, `filter_jsonb` JSONB, `sampling_rate` CHECK 0..1, `judge_panel_id`, `metric_set` JSONB, `enabled`, `created_at` |
| **`eval_cases`** | Versioned golden set built FROM production failures, frozen fixture snapshots, replacing brittle hand fixtures. | `case_id` PK, `user_id`, `input_hash`, `gold_projection` JSONB, `category`, `source` (correction\|judge_disagreement\|shadow_divergence\|manual), `created_from_run_id`, `fixture_version`, `created_at` |
| **`shadow_extraction_runs`** | Champion-challenger shadow log; a challenger config replayed on real inputs, never served. | `id` PK, `request_id`, `user_id`, `champion_config_hash`, `challenger_config_hash`, `output_projection` JSONB, `eval_run_id`, `latency_ms`, `created_at`; INDEX(challenger_config_hash) |
| **`correction_clusters`** | Clio-style failure-mode clusters over redacted summaries (pgvector) with k-anonymity gate + privacy-auditor score. *(flat k-means — see §9 over-build note)* | `cluster_id` PK, `level`, `parent_id`, `title`, `summary`, `n_owners`, `n_corrections`, `privacy_score`, `embedding` vector, `created_at` |

**Deferred to Track-2 (see §10):** `rollouts`/`rollout_events`/`guardrail_readings` (weighted-canary state machine), `annotation_queue` (active-learning queue → replaced by a filtered view), `training_pairs`/`distillation_runs` (LoRA).

---

## 4 · The phases

Status markers per CLAUDE.md. Each phase ships independently with its own VERIFY + POST-REVIEW + COMMIT. Sizes XS–XL. All six adversarial-critique fixes are **folded into the phase definitions** (traceable in §9).

### Q0 — Lift the eval harness into a shared, DB-capable library · **M** · depends: —
**Goal.** Promote the cycle-72–74-debugged scoring/judging code (`eval_harness.py`, `llm_judge.py`, `judge_ensemble.py`, `compute_ensemble_macros.py`) out of `tests/quality/` into an importable package so a production consumer can call it and write to a DB. **No behavior change.**
**Deliverables.**
- New package `services/learning-service/app/eval/` (or `sdks/python/loreweave_eval/`) with the gateway-compliant call shape preserved (**gateway response is `result["messages"][0]["content"]`, not `result["content"]`** — see [[feedback_gateway_response_messages_array_not_content_string]]).
- A `Scorer` protocol: `score_dump(dump_tree, judge_panel) → EvalResult{per_category P/R/F1, disjoint_median_f1, fleiss_kappa, bias_metrics, bootstrap_ci, per_judge_verdicts}`.
- A `PersistenceAdapter` interface: `FileSink` (current behavior, kept for R&D parity) + `DbSink` (stub, filled in Q1).
- **Split into two commits (critique fix #6):** (0a) **pure move**, regression-locked byte-identical to a saved fixture dump; (0b) parameterize the hardcoded extractor/filter UUIDs (`compute_ensemble_macros.py:48-49`) into an explicit `JudgePanel` config object — behavior-preserving, own targeted test (UUID-resolution change can alter serialization, so it cannot share the byte-identical lock).
**Industry basis.** OpenAI "build the grader once"; observability "scorer + pluggable sink".

### Q1 — Quality DB schema (the three-object model) · **M** · depends: Q0
**Goal.** Add the persisted quality schema — the missing half. Implements requirement **(a) production telemetry of quality**.
**Deliverables.**
- Idempotent migration: `eval_runs`, `eval_results`, `quality_scores`, `score_config` (learning-service house style, modeled on `project_embedding_benchmark_runs`).
- `DbSink` (from Q0) writing one `eval_runs` + N `eval_results` + per-judge `quality_scores` per scored dump.
- `score_config` seed rows for the metric-of-record (P/R/F1 per category, `fleiss_kappa`, `disjoint_median_f1`) with write-time datatype/range validation; **names mirror OTel `gen_ai.*`** (critique fix #4-OTel).
- **Materialize the locked baseline 0.913 AND the clean 0.869 as `eval_runs` rows tied to a real `config_hash`** (critique concern — Q8 needs something to diff against).
- **Dual dedup on `quality_scores`** (critique fix #5): `UNIQUE(origin_service, origin_event_id)` for consumed producer events + a second composite `UNIQUE(source_eval_run_id, target_id, metric_name, judge_model)` for **self-produced** judge verdicts (which have no `outbox_id`).
- Read API `GET /v1/learning/eval-runs` (per-owner isolated, reusing existing `auth.py` owner-scoping).
**Industry basis.** OpenAI three-object model; Vertex summary/metrics split; Langfuse Score/ScoreConfig validated at write time.

### Q2 — Corrections-as-gold: provenance + activate outcome-recompute · **M/L** · depends: Q1
**Goal.** Turn the correction log into per-run quality labels. Implements requirement **(b) extraction edits = gold labels** — the cheapest real online quality signal.
**Re-scoped per critique fix #1 (was mis-sized S).** Verified: graph nodes carry **no** run provenance; `run_id` is a fresh `uuid4` per chapter (`runner.py:440`); the only stable handle is `(book_id, chapter_ref)`. So this is not a 1-line thread-through.
**Deliverables.**
- **Decide + build the provenance path:** EITHER persist a node→run link at extraction-write time (Neo4j property or a `(book_id, chapter_ref) → run_id` resolution table), OR explicitly accept **time-window attribution** (the `get_outcome_recompute` NULL-branch fallback `mining.py:201-202` already does this) and drop the per-node `run_id` claim. Pick one in CLARIFY.
- **Verify current `get_outcome_recompute` output BEFORE claiming it "activates"** (critique: the NULL-branch + time-window means it is likely already non-empty, just coarse — the run_id value is *precision*, not *activation*).
- **Reconcile BOTH correction routes** (critique concern): `knowledge.{entity,relation,event}_corrected` AND `glossary.entity_updated` (filtered `actor_type=='user'`, `handle_glossary_entity_updated`) — the canonical anchored entities flow through the glossary SSOT path with different provenance; the gold-label projection must not double-count or miss attribution.
- `gold_labels` projection: corrections → (target_type, structural before=non_preferred, after=preferred, edit-distance magnitude) — the preference/supervision/reward triple, structural + content-hash only.
**Industry basis.** User-edits-as-triple-signal (OpenAI/Anthropic/vendor-neutral).

### Q3 — Chat-turn feedback capture · **M** · depends: Q1
**Goal.** Add the only absent feedback primitive — chat-service has zero rating column. Implements requirement **(b) chat half**.
**Deliverables.**
- chat-service: `message_feedback` table + `POST /v1/chat/messages/{id}/feedback` + outbox emit `chat.message_feedback` (reuses chat-service's existing outbox + relay).
- **Regeneration-as-negative** on the original message; the new message = candidate-preferred; de-linked from identity before the mining read path. (No-action ≠ negative — implicit-signal noise discipline.)
- learning-service: `handle_chat_feedback` writing `source=human` `quality_scores` rows (`target_kind=chat_message`); register on `learning-collector`; **add `loreweave:events:chat` to STREAMS**.
- Frontend: thumbs/regenerate affordance on chat turns (server is source of truth, no localStorage), via gateway.
**Industry basis.** OpenAI preference-signal flywheel; Anthropic feedback de-linking; observability separate append-only feedback entity.

### Q3.5 — Judge calibration gate (NEW first-class phase) · **S/M** · depends: Q2
**Goal.** Validate the judge ensemble against human corrections BEFORE Q4 trusts online judge scores. **Pulled out of Q5 per critique fix #2 + sequencing** — given the measured ~4-5pp self-reinforcement, this is load-bearing, not a sub-bullet.
**Deliverables.**
- A **judge-vs-human agreement gate** (balanced accuracy + Cohen κ) computed from corrections-as-ground-truth; require **75–90%** before a judge panel is trusted as a metric-of-record source.
- Enforce **disjoint-median (exclude any judge sharing the extractor/filter model) in code** as the metric-of-record — not a manual env step (the primary self-reinforcement defense; see [[project_eval_self_reinforcement_measured]] and [[feedback_anti_self_reinforcement_via_judge_subset_recompute]]).
- Block Q4 online-judge trust until a panel passes calibration.
**Industry basis.** OpenAI "validate the grader before trusting it"; Anthropic grader-reliability holdout; Vertex `evaluate_autorater`.

### Q4 — Online-eval consumer · **L** · depends: Q1, Q3.5
**Goal.** Sample production runs, judge async, persist scores — never block extraction. Implements requirement **(c) online eval**.
**Deliverables.**
- `online_eval_rule` table (filter + sampling_rate + judge_panel + metric_set + enabled).
- New consumer group `eval-runner` on `loreweave:events:knowledge` via **Redis fan-out** (does NOT perturb `learning-collector`/`knowledge-extractor` delivery); replay-from-`event_log` for backfill.
- **DEFAULT = structural-only deterministic re-score** (`eval_harness.py` path, **no source text needed**) for the 99% non-opted case (critique fix #3 + hard-ordering bug). **Full LLM judge only for `save_raw_extraction=true` projects** — the raw-retention opt-in (BE+FE, `D-P2-FE-SAVE-RAW`) is the gated enhancement for the LLM path, NOT a blocker for shipping structural online eval.
- **Judge MODEL runs in LM Studio via provider-registry** (`host → provider-registry:8208 → LM Studio:1234`); the consumer dispatches calls but **never JIT-loads a 26B model in-container** (critique fix #6-deployment; the OOM lesson is about the model host, not the orchestrator — see [[feedback_host_orchestrate_rejudge_to_bypass_container_oom]]).
- **Sampling = cost governor:** default 5–10%; **sampled-out events `XACK` immediately** (critique fix #5 — no PEL/`XAUTOCLAIM` churn since it shares the stream with `learning-collector`). Paced/delayed queue via a **sorted-set** (Redis Streams lack time-based delivery — see [[feedback_redis_streams_no_time_based_delivery]]); **throughput budget + max-in-flight backpressure** deliverable (sequential JIT judges on a 26-35B local model are minutes-per-chapter — quantify steady-state backlog vs extraction throughput).
- DLQ on judge failure.
**Industry basis.** Observability online eval = (filter + sampling_rate) → async → write-score-back-by-id; Vertex continuous-eval; Anthropic cost-aware sampling.

### Q5 — Eval-case dataset built FROM production failures · **M** · depends: Q2
**Goal.** Promote corrections + high-judge-disagreement runs (+ later shadow divergences) into a versioned `eval_cases` table with frozen fixtures, so pre/post-launch eval is directly comparable and the golden set grows continuously. Partially implements **(f) self-improvement**.
**Deliverables.**
- `eval_cases` table (structural + content-hash); curation/dedup + **saved-dump fixture freeze** to kill extraction nondeterminism (see [[feedback_saved_dump_fixture_kills_extraction_nondeterminism]]).
- **Replace the `annotation_queue` state machine with a filtered VIEW** (critique over-build #5): the developer is the single reviewer who already edits entities (that IS the correction signal); surface a low-Fleiss-κ / shadow-divergence view they browse — no assignee/status workforce machinery.
- Acquisition-ranked promotion (low confidence, low κ, divergence) into `eval_cases`.
**Industry basis.** OpenAI evals-as-unit-tests grow-the-set; vendor-neutral auto-generate-cases-from-failures + active-learning acquisition.

### Q6a — Shadow capture · **L→split** · depends: Q4
**Goal.** Replay a challenger `config_hash` on real (sampled) chapter inputs as a pure fire-and-forget side-effect; log the structural projection; never serve it. Implements requirement **(d) shadow / champion-challenger** (capture half).
**Deliverables.**
- `shadow_extraction_runs` table (structural + content-hash, no raw text).
- Shadow trigger: replay a chapter through a challenger `config_registry` snapshot; fire via outbox→relay→Stream; land a row via a shadow consumer — **challenger NEVER blocks/slows champion** (async side-effect; test: champion latency unaffected).
**Industry basis.** AWS SageMaker shadow testing; Vertex AutoSxS.

### Q6b — Paired comparison · **M** · depends: Q6a
**Goal.** Compare challenger vs champion offline, with statistical rigor (shadow analysis half).
**Deliverables.**
- Paired comparison job on identical chapter fixtures (saved-dump makes the pair reproducible): paired diff + **clustered standard error on the chapter unit** + bootstrap CI (Anthropic "Adding Error Bars to Evals").
- **Judge the REALIZED (post-persist) output, not filter output** when supported-cascade rate >5% (see [[feedback_filter_output_f1_overstates_realized_when_writer_cascades]]).
- `shadow_comparisons` materialized view (per challenger: win-rate, paired F1 delta, per-example choice/confidence/disagreement buckets).
**Industry basis.** Vertex AutoSxS (win-rate + per-example confidence); Anthropic paired/clustered SE.

### Q7 — Dev Log: version → measured quality delta · **M** · depends: Q4
**Goal.** Tie every config/prompt version (`config_hash`) to its measured F1 and the paired delta vs the prior shipped version: *"v_A F1=X, v_B F1=Y, impact +Z (paired SE, n chapters)"*. The user's **explicitly named deliverable**. Implements requirement **(e)**.
**Deliverables.**
- `config_quality_log` view joining `config_registry` ← `eval_runs` (offline F1) and `config_adjustment_events` (what changed) into a chronological version-delta timeline, per-category slices.
- `GET /v1/learning/dev-log` returning ordered `{config_hash, base_default_version, prompt_versions, what_changed, f1_per_category, paired_delta_vs_prev, paired_se, n_chapters, kappa, ci}`.
- **STRICTLY per-owner until Q9** (critique sequencing): no cross-tenant rollup before the privacy gate exists.
- Offline↔online correlation rollup: paired (offline F1 delta, online user-correction-rate delta) per shipped change — validate the offline metric empirically predicts the online signal.
- FE Dev Log panel extending the existing Mining Insights panel on `KnowledgePage`.
**Industry basis.** Vertex persisted ModelEvaluation per versioned snapshot; OpenAI eval-run comparison over time; offline↔online metric-correlation validation.

### Q8 — Guarded config promotion gate · **M** · depends: Q6b
**Goal.** A new `config_hash` cannot become the project/global default unless its disjoint-median F1 is non-regressing vs the locked baseline past a threshold. **Human-gated promote** ("flashlight not autopilot"). Implements the ship gate. **depends_on corrected to Q6b** (the candidate-vs-baseline number comes from shadow/paired, not just Q5 — critique sequencing).
**Deliverables.**
- Promotion gate: candidate `config_hash` vs locked baseline `config_hash`, **paired on shared `eval_cases`**, blocks if disjoint-median F1 drop > threshold.
- Optional eval gate wired into `workflow-gate.py`/pre-commit that blocks a config/prompt commit if F1 regresses vs last shipped `config_hash` (evals-as-unit-tests).
- Promote-to-default = **human-confirmed terminal action**; manual revert.
- **CUT (critique over-build #1, #2):** the weighted-canary `rollouts` state machine, CUPED, sequential testing → Track-2 (sample sizes don't justify them at hobby scale; there is no high-QPS peeking problem). Keep paired + clustered SE (Q6b) + bootstrap CI (exists).
**Industry basis.** OpenAI/Vertex evals-as-CI/CD-gate; Anthropic paired/clustered SE; human-gated promotion.

### Q9 — Privacy + multi-tenant aggregation gate (Clio-style) · **M** · depends: Q5; **must precede any cross-tenant surface**
**Goal.** Before any mined insight crosses a single owner's boundary, enforce a k-anonymity minimum-aggregation threshold + an LLM privacy auditor. Formalizes redact-by-default into the cross-tenant safety rule the platform currently lacks.
**Deliverables.**
- Periodic failure-clustering job (Clio bottom-up): embed redacted correction summaries into **pgvector**, **flat k-means** base clusters (critique over-build #6 — NOT a multi-level LLM-named hierarchy at hobby scale), cheap local model per-item + larger model only to name clusters.
- `correction_clusters` with a **k-anonymity WHERE gate**: surface cross-tenant only if `n_owners >= N AND n_corrections >= M`.
- **LLM privacy-auditor** final gate scoring each human-visible cluster title/summary; private-scoring clusters removed before any read API returns them (an LLM-written name can leak a unique plot detail even from hashed inputs).
- Identity-decoupling on the mining read path; prioritize tuning by **convergence across owners**.
- **Sequencing guard:** ship before/with the first cross-tenant read path (Q7's cross-tenant correlation rollup); until then Q7 is strictly per-owner.
**Industry basis.** Anthropic Clio bottom-up clustering + 4-layer privacy (redact → min-aggregation k-threshold → redact → LLM auditor) + prioritize-by-convergence.

---

## 5 · Sequencing & dependency graph (corrected)

```
Q0 ─▶ Q1 ─┬─▶ Q2 ─┬─▶ Q3.5 ─▶ Q4 ─┬─▶ Q6a ─▶ Q6b ─▶ Q8
          │       └─▶ Q5 ─────────┤                  ▲
          ├─▶ Q3 (chat feedback) ─┘   └─▶ Q7 ────────┘ (Q7 per-owner only)
          └─▶ (baseline rows seeded in Q1)
                                   Q5 ─▶ Q9 ─▶ (unlocks Q7 cross-tenant)
```

**Critical path:** Q0 → Q1 → Q2 → Q3.5 → Q4 → Q6a → Q6b → Q8. **Foundation to start BUILD:** Q0 (pure lift) then Q1 (schema) — clean, no upstream dependency, correctly ordered. Q3 (chat feedback) parallelizes off Q1. Q9 must land before Q7 ships any cross-tenant surface.

**Natural session checkpoints** (per [[feedback_xl_cycle_natural_checkpoint_pattern]]): Q0+Q1 = "data-foundation" checkpoint; Q2+Q3+Q3.5 = "signal-capture" checkpoint; Q4 = "online-eval" checkpoint (largest single phase); Q5+Q6a+Q6b = "shadow/dataset"; Q7+Q8+Q9 = "surfaces + gates".

---

## 6 · Privacy & multi-tenant model

- **Redact-by-default everywhere:** quality tables store structural projections + content-hashes; raw novel text only under the per-tenant `save_raw_extraction` opt-in (default OFF; `migrate.py:670`).
- **Q4 default = structural-only** for non-opted projects — degraded-but-real signal that needs no source text; LLM judging is the opted-in enhancement.
- **Cross-tenant insights gated by Q9** — k-anonymity threshold + LLM privacy auditor, stricter than typical observability platforms.
- **Per-owner isolation on every new read API** (`GET /eval-runs`, `GET /dev-log`) via the same `auth.py` owner-scoping the corrections/mining routers use; cross-tenant aggregates are the *only* exception and only behind Q9.

---

## 7 · Local-LLM-first cost model

- **Sampling is the primary cost governor** (5–10% default, per-rule configurable). Judge-everything is economically impossible on local LM Studio.
- **Host-orchestrated judging:** judge model runs in LM Studio fronted by provider-registry; the in-container consumer dispatches, never hosts the heavy model (dodges the OOM-killer — [[feedback_host_orchestrate_rejudge_to_bypass_container_oom]]).
- **Throughput budget (Q4):** sequential JIT-loaded judges on a 26-35B model are minutes-per-chapter; quantify steady-state judge backlog vs extraction throughput and add max-in-flight backpressure, else `eval-runner` permanently lags.
- **Cloud = calibration only:** periodic Claude/GPT runs to calibrate the local judge panel; never the iterative-tuning loop (prohibitive token cost — [[feedback_local_llm_first_cloud_is_fallback]]).

---

## 8 · Risks

1. **Self-reinforcement (~4-5pp).** Extractor self-grades 0.972 vs disjoint 0.869. Disjoint-median-excluding-generator MUST be enforced in code (Q0/Q3.5/Q4); the 75-90% judge-vs-human gate (Q3.5) is the second defense. Skip it → the flywheel optimizes a vanity number.
2. **Local-LLM wall-clock + container OOM.** Q4 must host-orchestrate + sample; naive in-container online eval OOMs and stalls extraction.
3. **Redis Streams lack time-based delivery.** A paced/sampled queue needs a sorted-set, not future `retry_at`; sampled-out events `XACK` immediately.
4. **Raw-text retention default OFF.** Q4 LLM judging is limited to opted-in projects; structural-only is the default. Organic raw gold-set building is blocked by design until the opt-in ships (honor redact-by-default).
5. **Extraction nondeterminism confounds A/B** (alice_ch01 P swung 0.385→0.250 with zero fixture change). Q5/Q6 MUST freeze saved-dump fixtures as the A/B substrate.
6. **Filter-output F1 over-states realized quality** when the writer cascades (FK/schema drops). Q6b/Q8 judge realized post-persist output when cascade rate >5%.
7. **Multi-tenant leakage via LLM-written cluster names.** Q9's k-anonymity + auditor are mandatory before any cross-tenant surface.
8. **Offline F1 may not predict the online signal.** Q7 runs offline+online in parallel and correlates; if weak, prefer the behavioral online metric (edit-effort) for promotion.
9. **Promotion automation overreach.** Auto-rollback fine; promote-to-default stays human-confirmed (Q8). Fully-automated promotion on a small noisy local sample risks shipping self-reinforced regressions.

---

## 9 · Adversarial-critique fixes folded (traceability)

The raw synthesis was stress-tested; these six corrections are already folded into §3/§4 above:

1. **Q2 re-sized S → M/L.** Graph nodes carry no run provenance (`run_id` is fresh `uuid4`, `runner.py:440`); needs a node→run link OR explicit time-window attribution. The "activates the recompute query" premise is wrong — the NULL-branch (`mining.py:201-202`) already attributes by time-window; run_id adds *precision*. → folded into Q2.
2. **Judge calibration → its own phase Q3.5**, between Q2 and Q4 (was a buried Q5 bullet). → new phase.
3. **Hard ordering bug: Q4 needs source text but `save_raw_extraction` defaults OFF.** Q4 default scoped to structural-only deterministic re-score; LLM judge is the opted-in enhancement. → folded into Q4.
4. **Idempotency:** dual dedup key on `quality_scores` (self-produced judge verdicts have no `outbox_id`); sampled-out events `XACK` immediately. **OTel `gen_ai.*`** naming made a concrete Q1 deliverable. → folded into Q1/Q4.
5. **`Q8 depends_on` corrected Q5 → Q6b** (candidate-vs-baseline number comes from shadow/paired). **Q9 moved before any cross-tenant Q7 surface.** → folded into §5 graph.
6. **Deployment clarification:** judge model in LM Studio via provider-registry, never JIT-loaded in the learning-service container. **Q0 split** into pure-move + parameterize commits. → folded into Q0/Q4.

**Scope cuts for a local-first one-operator platform** (from critique over-engineering): weighted-canary `rollouts` state machine, CUPED, sequential testing → Track-2; `annotation_queue` → filtered view; Clio multi-level hierarchy → flat k-means + privacy gate; `judge_panel` table → start as a Q0 config object, table only when a 2nd panel exists.

---

## 10 · Deferred → Track-2 (documented, not in this track's BUILD)

| Item | Why deferred | Trigger to revisit |
|---|---|---|
| **LoRA distillation of the local extractor** (was Q10, XL) | No GPU-training story established; folding it in invites scope/fatigue. `training_pairs` export + `distillation_runs` + drift-triggered tuning belong in a dedicated track, shadow→gate-validated before serving. | When correction/gold volume + a GPU-training path justify it |
| **Weighted-canary rollout state machine** (`rollouts`/`rollout_events`/`guardrail_readings`) | Frontier-lab high-QPS serving infra; LoreWeave extraction is batch-per-chapter. Shadow (Q6) + human-confirmed promote + `config_adjustment_events` log give the same safety. | If live traffic-splitting ever becomes a real need |
| **CUPED + sequential testing** | Statistical machinery for continuous high-volume experiments; marginal at n=tens of chapters. | When A/B sample sizes justify the variance reduction |
| **`annotation_queue` with assignee/acquisition state machine** | Product-grade HITL for a one-person review loop; the developer's edits ARE the signal. | If a multi-reviewer labeling workforce appears |
| **ClickHouse for score volume** | Postgres + window functions suffice at hobby scale. | Only if score volume ever dwarfs Postgres |

---

## 11 · PO decisions (resolved — session 105)

All four resolved by PO at design-checkpoint approval (recommendations accepted):

1. **Q2 provenance → time-window FIRST.** Start with the existing `get_outcome_recompute` time-window attribution (`mining.py:201-202`); build the node→run link only if attribution noise measurably hurts the Dev Log. Q2 BUILD does NOT block on the Neo4j provenance link.
2. **Raw-retention opt-in → structural-only FIRST.** Q4 ships with the structural-only deterministic re-score default; the `save_raw_extraction` BE+FE opt-in (LLM online judge) is a fast-follow, not a Q4 blocker.
3. **Baseline of record → 0.869 (clean disjoint).** Materialize 0.869 as THE promotion baseline (Q1 deliverable); retire the self-inflated 0.913 from gate use (keep it only as a historical/full-panel comparison row).
4. **Track home → `docs/plans/` for now; promote to a numbered `docs/03_planning/<TRACK>/` module set IF BUILD spans >5 sessions.** Re-evaluate after the Q0+Q1 foundation checkpoint.

---

*This is a design-checkpoint artifact (no code). BUILD starts at Q0 in a future session, inheriting the interfaces locked here. Per [[feedback_design_checkpoint_commit_separates_design_from_implementation]], commit this discretely so future BUILD sessions don't re-litigate the decisions.*
