# Spec — Pass2 precision filter (30B recall → claude-4.7-opus precision filter)

**Cycle:** 2026-05-29 (post-cycle-71+71-bis pivot)
**Size:** XL (~8-10 files, 6 logic blocks, 1 side effect — `JobOperation` enum extension + downstream allowlists)
**Driver:** Cycles 71 + 71-bis closed as NEGATIVE — three distinct event-prompt variants all regressed (regurgitation, asymmetric multilingual drift, English-prose CJK drift). Empirical lesson: prompt-side improvements on `event_extraction_system.md` have a diminishing-returns ceiling around the current c70a baseline (P=0.96/R=0.92 ensemble median, gemma macro 0.81/0.92). Pivot to a structural lever: chain a precision filter behind the existing recall extractor instead of asking the recall extractor to be more precise.

## Goals

1. **Lift ensemble F1 toward ~0.88** by running each Pass2 candidate through a precision-only LLM filter (`huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated`) that votes `supported / partial / unsupported` against the source text — dropping unsupported items, keeping supported, configurable handling for partial.
2. **No new prompt files.** Reuse the existing `_PRECISION_SYSTEM` prompt shape from `services/knowledge-service/tests/quality/llm_judge.py` — it already does exactly this verdict shape against the same dump format. Promote it from eval-only to a library-level utility.
3. **Production-wire it** under an explicit kwarg (`precision_filter: PrecisionFilterConfig | None = None`) on `extract_pass2`. Default `None` = current behavior (zero regression). Worker-ai and knowledge-service callers opt in per-call.
4. **Validate via ensemble re-judge** — produce a c72 dump with filter applied, run the same 3-judge ensemble that locked c70a baseline, compare macro P / macro R / F1 / Fleiss κ. Ship if ensemble F1 lifts ≥ +3pp without κ regression below 0.60 (still "substantial").

## Non-goals (out of scope this cycle)

- **Cloud Claude judge as filter.** Per memory `local-llm-first-cloud-is-fallback`, all iteration runs against LM Studio local. Cloud claude-haiku-4-5 calibration is a separate follow-up cycle.
- **Filter result caching.** First validation cycle uses no cache; if F1 lifts and we promote filter to default-on, a future cycle adds a `(text_hash, model_ref, item_canonical) → verdict` cache.
- **Per-user / per-project filter toggle in the UI.** Filter is opt-in at the SDK boundary; service-level config is hardcoded behind a single env (`KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF`). Per-user surfacing is a Product-track follow-up.
- **Runtime feature flag (per-request override via header).** Hardcoded env-only this cycle.
- **Filter for entity kind / event participants.** Filter votes on the WHOLE item shape (entity name+kind, full triple, full event summary+participants). Sub-attribute partial-credit is out of scope.
- **Replacing the eval-side ensemble judge.** Filter LIVES inside `pass2.py`; the ensemble judge stays as the measurement system. Filter is the change-under-test; ensemble is the ground truth.

## Architecture decisions

### D1 — Filter as SDK module, library-side, opt-in kwarg

**Decision.** New module `sdks/python/loreweave_extraction/pass2_filter.py`. Exposes one async function `apply_precision_filter(candidates, *, text, ...) -> Pass2Candidates`. `extract_pass2` accepts a new optional kwarg `precision_filter: PrecisionFilterConfig | None = None`; when non-None, calls `apply_precision_filter` after extractor results are gathered, before returning.

**Rationale.** Library-level keeps the contract testable in `sdks/python/tests/test_extraction/test_pass2_filter.py` without service infrastructure. Opt-in kwarg = zero risk to existing callers; worker-ai + knowledge-service pass `precision_filter=PrecisionFilterConfig(...)` only when their service env enables it.

**Rejected alternative.** Eval-side post-process (mutate dump `actual.json` from a CLI tool). Cheaper to build but doesn't ship; user explicitly chose full production wiring.

### D2 — Filter scope: all three LLM categories (entity, relation, event)

**Decision.** Filter votes on all three category lists. Facts are NOT filtered (Pass2 facts are a Phase-4a-β extractor that produces summary-level statements; filter shape doesn't apply cleanly — defer to a Pass2Facts-specific cycle if facts ever go production).

**Rationale.** c70a baseline shows the ensemble F1 weakness is distributed across all three: entity P=0.95 (acceptable but room for +2pp), relation P=0.97 (best), event ensemble macro skewed by ch14 0/6 TP (event is the worst per-chapter axis). Filtering only one category leaves measurement noise from the unfiltered ones.

**Implementation.** One filter call per category per chapter (not one combined call). Reason: the prompt for entity vs relation vs event differs in item-format — the existing `format_items_for_judge` in `llm_judge.py` already encodes this split, reuse it.

### D3 — Filter judge model: `huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated` (UUID `019e5650-eca7-78c2-985d-465aa3bce1ce`)

**Decision.** Use Judge C from the existing ensemble as the filter model. UUID-pinned via `precision_filter_model_uuid` config field (canonical identifier per cycle 69 D3 — names are prose only).

**Rationale.**
- Per cycle 70 c70a empirical: claude-4.7-opus is the **high-precision judge** in the ensemble (macro P 0.955, highest of three).
- Per the memory `claude-4.7-opus is the high-recall barometer` from cycle 70 — its R lifted +4.5pp when c70a added predicate-learning. Translation: it has the strictest precision verdicts AND accepts paraphrase well. Exactly the contract we want for a filter (strict on "is this supported" without rejecting paraphrase as unsupported).
- Per memory `local-llm-first-cloud-is-fallback`: cloud claude is out-of-scope.
- The model is already loaded in LM Studio for ensemble runs — zero new infra.

**Risk:** filter and one of the eval judges are the SAME model. Self-reinforcement bias — the filter's "supported" verdict during extraction will ~match what claude-4.7-opus says during ensemble judging. **Mitigation:** the c70a baseline is also being re-judged by gemma + qwen-30b in the same ensemble; if filter-vs-baseline gain shows up ONLY on the claude judge and not on gemma + qwen, that's the self-reinforcement signature and we reject the cycle. **D11 makes this explicit.**

### D4 — Verdict policy: drop `unsupported`, keep `supported`, configurable for `partial`

**Decision.** Three options exposed via `PrecisionFilterConfig.partial_policy: Literal["keep", "drop", "demote"]`:

| Policy | Behavior on `partial` |
|---|---|
| `keep` (default) | Treat as supported (preserve recall) |
| `drop` | Treat as unsupported (max precision) |
| `demote` | Keep but tag in metadata for downstream weighting |

**Rationale.** `partial` is ambiguous — per `llm_judge.py` doc: "partially correct — e.g. right entity but wrong kind, right relation but wrong direction, or only weakly implied." For an extraction pipeline we prefer recall-leaning defaults (`keep`) because downstream consumers (Neo4j writer, glossary merge) can still benefit. For high-precision use cases (e.g. citation generation) callers can opt into `drop`.

`demote` requires a new field on `LLMRelationCandidate` etc. (`confidence: Literal["full","partial"]`). **MED-1 risk:** that field cascades to Neo4j schema. Reserve the policy value in this cycle but BUILD only the `keep`/`drop` paths; `demote` is deferred to a follow-up cycle.

### D5 — Empty / failure / coverage policy

**Decision.** Three boundary cases:

1. **Filter returns 0 supported across a category** → return empty list for that category (no error). Pass A's candidates are simply dropped. Caller sees the empty list and decides (knowledge-service writer is already empty-safe — Pass A returning empty already happens for short text).
2. **Filter LLM call FAILS** (`LLMError` / `ExtractionError` from the judge call) → log + return Pass A candidates UNFILTERED (degrade-to-recall, never lose data). Mirrors `llm_judge.py` `judge_status="failed"` semantics. **MED-2 risk:** caller doesn't know the filter degraded — surface via `Pass2Candidates.filter_status: Literal["applied", "degraded", "skipped"]` (new field).
3. **Filter returns a verdict for SOME but not all items** (coverage < 1.0, observed in llm_judge.py during gemma reasoning-token bursts) → for items without a verdict, default to `partial_policy` semantics. Coverage statistic also surfaced via `Pass2Candidates.filter_coverage: dict[Category, float]`.

**Rationale.** Per memory `cross-store-best-effort-writes-need-try-except` — the filter is a best-effort enhancer over Pass A; it must NEVER cause data loss in the existing extraction path. Plus per memory `llm-schemas-tolerate-at-validation-filter-at-postprocess` — same pattern applies here.

### D6 — `JobOperation` enum reservation

**Decision.** Add `"extraction_filter"` to the `JobOperation` Literal in `sdks/python/loreweave_llm/models.py`. Same shape as `entity_extraction` / `relation_extraction` etc. Reserve immediately; this cycle USES it for the filter call.

**Rationale.** Per memory `reserve-operation-names-early-in-unified-apis` — adding the name at first-design-time means no migration when activation extends. Filter call needs an operation label for telemetry (Prometheus counters, usage logs, billing) and for gateway routing of any future operation-specific config.

**Side effect cascade** (per memory `new-error-code-cross-cutting-registration`):
- Update gateway whitelist if there's an operation allowlist
- Update `usage_logs.operation` CHECK constraint (Postgres migration) if it exists
- Update worker-ai / provider-registry op routing
- Update OpenAPI specs that enumerate operations

**Audit in DESIGN.** Grep `"entity_extraction"` to find all sync points. If <5 hits, the operation is loosely-coupled and migration is trivial. If ≥5, plan a separate "op-reservation" sub-step.

### D7 — Telemetry: per-category dropped counter

**Decision.** New Prometheus counter (knowledge-service side):
```
knowledge_extraction_filter_decisions_total{category, verdict}
```
Labels: `category ∈ {entity, relation, event}`, `verdict ∈ {supported, partial, unsupported, unjudged, failed}`.

**Plus** `knowledge_extraction_filter_coverage_ratio{category}` gauge for the per-run coverage signal.

Worker-ai is allowed to NOT emit (matches existing `on_dropped: DroppedHandler | None`). Filter library accepts an optional `on_filter_decision` callback with the same shape.

### D8 — Caller integration: feature env on each service

**Decision.** Two service-level envs (one per caller):
- `WORKER_AI_PRECISION_FILTER_MODEL_REF` — when set, `worker-ai/runner.py` calls `extract_pass2(..., precision_filter=PrecisionFilterConfig(model_ref=ENV))`.
- `KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF` — when set, `knowledge-service/extraction/pass2_orchestrator.py` (currently directly calls extractors, NOT `extract_pass2`) does ONE of:
  - **Option A:** refactor `extract_pass2_chapter` / `extract_pass2_chat_turn` to call the SDK `extract_pass2` instead of per-extractor calls. ← chosen at DESIGN.
  - **Option B:** add a separate filter call after gather.

Decided in **DESIGN** based on the refactor cost. CLARIFY just reserves both possibilities.

**Default unset = current behavior, current latency, current F1.**

### D9 — Latency budget

**Decision.** Filter adds ~30-90s per chapter (claude-4.7-opus inference). 10-chapter fixture run: +5-15 min vs no-filter baseline. Production worker-ai SLA: no change to the existing per-item budget (worker-ai bounds via spend caps + state-machine, not wall-clock). Knowledge-service `/extract-item` legacy endpoint NOT touched (filter only on the new persist-pass2 path).

**Risk:** in production with a many-chapter book, filter doubles total extraction wall-clock. **Mitigation:** since it's opt-in per service env, prod can ship with filter off; we only enable it after the eval cycle proves F1 lift justifies the latency cost.

### D10 — Validation methodology (the locked test)

**Decision.** Three runs, same fixtures (10 golden chapters), same extractor model (`huihui-qwen3-30b-instruct`), same prompts (c70a relation prompt locked + un-reverted c69 event prompt at 4522 chars):

| Run | Filter | Expected outcome |
|---|---|---|
| **A — c72a-baseline** | None (current behavior) | Re-locks c70a numbers — sanity check |
| **B — c72b-filter-keep-partial** | `claude-4.7-opus`, `partial_policy="keep"` | Recall-preserving filter — target: P +3pp, R within −1pp |
| **C — c72c-filter-drop-partial** | `claude-4.7-opus`, `partial_policy="drop"` | Precision-max filter — target: P +5pp, R within −3pp |

All three judged by the SAME locked 3-judge ensemble (gemma + qwen-30b + claude-4.7-opus). Ship the variant with higher ensemble F1, no drop in Fleiss κ below 0.60, AND no self-reinforcement signature (D3 guard).

**Self-reinforcement guard (D3 mitigation):** ship criteria explicitly require the gain to appear on gemma+qwen-30b's verdicts, NOT only on claude-4.7-opus's. Acceptance:
- gemma macro F1 lift ≥ +1pp **AND** qwen-30b macro F1 lift ≥ +1pp **AND** claude-4.7-opus macro F1 lift ≥ +2pp.

If only claude lifts → reject (self-reinforcement). If gemma+qwen lift but claude regresses → ship anyway (anti-reinforcement, suggests genuine signal).

### D11 — Ensemble decision rule preservation

The cycle 69 D9 ensemble decision rule (median over 3 judges = canonical macro) STAYS canonical for c72 baseline lock. F1 quoted in ship criteria is median(F1_gemma, F1_qwen, F1_claude).

### D12 — Run artifacts + revert path

**Artifacts to capture (per run, in `tests/quality/eval_runs/c72/`):**
- `extraction_dump_<variant>/` — c72a/c72b/c72c each
- `judge_ensemble_report_<variant>.json`
- `c72_compare.md` — narrative comparison vs c70a

**Revert path:** filter is opt-in via env unset → revert = unset envs. The new SDK module stays in place (kwarg defaults to None = no behavior change). If c72 ships, the new `extraction_filter` JobOperation enum entry STAYS reserved regardless of revert.

## Risks (gradient by severity)

| ID | Risk | Mitigation |
|---|---|---|
| HIGH-1 | Self-reinforcement: filter judge = ensemble judge C | D3 explicit cross-judge agreement gate in D10 |
| HIGH-2 | Filter doubles wall-clock latency on production books | D8 opt-in env per service; default off |
| MED-1 | `partial_policy="demote"` requires schema change on `LLMRelationCandidate` | Reserve enum value only; BUILD `keep`/`drop` paths only |
| MED-2 | Filter degradation invisible to caller | D5 new `Pass2Candidates.filter_status` field |
| MED-3 | `JobOperation` enum addition cascades to N hidden allowlists | D6 grep audit at DESIGN |
| MED-4 | `knowledge-service/pass2_orchestrator.py` bypasses `extract_pass2` | D8 Option A: refactor to use SDK orchestrator |
| MED-5 | Filter LLM call cost not metered in usage_billing | New `extraction_filter` op enum should auto-route through existing usage-billing on first call — verify in DESIGN |
| LOW-1 | Filter coverage < 1.0 silently underapplied | D5 coverage field on Pass2Candidates + D7 metric |
| LOW-2 | Existing eval tests assume Pass A only (no filter) | Filter defaults to None in all existing call sites; new test file covers filter path |

## Test plan (executes in BUILD + VERIFY)

### Unit tests — new module
- `test_pass2_filter_unit.py` — verdict-policy combinations (keep/drop on partial), empty-pass-A short-circuit, failed-filter-degrades-to-Pass-A, coverage-metric correctness, per-category list independence

### Unit tests — orchestrator
- `test_pass2.py` (additions) — `precision_filter=None` keeps current contract (no behavior change), `precision_filter=PrecisionFilterConfig(...)` chains the call, filter_status field populated correctly

### Integration tests
- `test_pass2_filter_live.py` (new, `--run-quality` opt-in) — real claude-4.7-opus call on one short fixture (alice_ch01), assert Pass2Candidates returned with filter_status="applied"

### Eval verification (the ship test)
- 3-run protocol D10 — produce c72a / c72b / c72c dumps, run ensemble judge, compare macro F1, gate on D10 acceptance.

### Regression-lock tests (per memory `audit-all-callsites-when-adding-optional-kwarg`)
- `test_runner.py` (worker-ai) — env unset case (current behavior preserved), env set case (filter applied)
- `test_internal_extraction.py` (knowledge-service) — same shape for both env cases
- Cross-grep `extract_pass2(` to ensure no caller silently bypasses filter

## Acceptance criteria

1. SDK module `pass2_filter.py` ships with full unit coverage
2. `extract_pass2` accepts `precision_filter` kwarg, default `None` = zero behavior change (verified by re-running existing `sdks/python/tests/test_extraction/test_pass2.py` suite — all pass unchanged)
3. Worker-ai + knowledge-service callers opt in via env without code changes to extractor logic
4. `JobOperation` enum has `"extraction_filter"` reserved + all downstream allowlists updated (D6 audit zero hits orphan)
5. Three eval runs (c72a/b/c) complete, ensemble-judged, results captured in `c72_compare.md`
6. EITHER ship c72b or c72c per D10 acceptance, OR document NEGATIVE cycle with revert clean (same shape as cycle 71)
7. Live-smoke evidence at VERIFY: `live smoke: c72b filter end-to-end on alice_ch01 via worker-ai+knowledge-service+gateway+lm-studio, filter_status=applied` (cross-service: worker-ai + knowledge-service + provider-registry)

## Open questions (resolved in DESIGN)

- **OQ-1:** Should the filter accept a separate `model_source` from extraction's model_source? (E.g., extraction = `user_model`, filter = `platform_model`?) — likely yes for cost/SLO isolation; resolve in DESIGN.
- **OQ-2:** Knowledge-service orchestrator refactor — Option A (use SDK extract_pass2) vs Option B (keep current direct-extractor pattern + bolt on filter)? Cost of Option A: ~50-line refactor + test fixture rewrite. Option B: cleaner separation but duplicates orchestration.
- **OQ-3:** Should filter-degraded candidates be flagged at Neo4j write time (e.g., `(:Entity {filter_status: "degraded"})`)? — adds debug signal but cascades schema. Default: NO, filter_status is in-memory only.

---

**Spec status:** CLARIFY complete; DESIGN section appended below.

---

# Design (resolved 2026-05-29)

## D6 revision (cascade audit changed scope)

**Empirical** (grep audit `entity_extraction` against repo):
- `JobOperation` is reserved in **10+ sync points**: OpenAPI spec, provider-registry migration #2/3/4 + handler + worker + aggregator + billing + 5+ test files, knowledge-service metrics label.
- Adding `extraction_filter` cascades to a Postgres migration (#5: drop+recreate `operations` CHECK) plus 9 code touchpoints + ~12 test rewrites.

**Empirical** (read `llm_judge.py`): the existing precision-judge call uses `operation="chat"`. Per OpenAPI line 844-849, `chat`/`completion`/`*_extraction` ALL share the OpenAI chat-completion wire shape; the operation enum picks the per-op AGGREGATOR + CHUNKER, not the input schema. For the filter, we parse JSON in the caller (same as `llm_judge.py` does) → we don't need the per-op aggregator.

**Revised D6.** Filter calls the gateway with `operation="chat"`. **No new JobOperation enum value, no migration, no allowlist updates.** MED-3 risk **removed** from the risk table.

**Cost.** Lose: distinguished billing/telemetry label per filter call (only `chat` shows in usage logs). **Mitigation:** filter caller passes `job_meta={"extractor": "pass2_filter"}` — provider-registry already surfaces `job_meta` in its job audit (cycle 4a-α). FUTURE cycle can promote to dedicated op when usage warrants.

**Files removed from D6 cascade list** (vs CLARIFY estimate): `sdks/python/loreweave_llm/models.py`, `contracts/api/llm-gateway/v1/openapi.yaml`, `services/provider-registry-service/internal/migrate/migrate.go` (no migration #5), 5+ provider-registry test files, `services/notification-service/internal/consumer/consumer.go`, `services/knowledge-service/app/metrics.py` (op-label tweak avoided).

## OQ-1 resolution — filter model_source

**Decision.** Filter accepts its own `model_source` in `PrecisionFilterConfig` independent from extraction's `model_source`. Default `"user_model"`.

**Rationale.** This lets a user run extraction on their BYOK and filter on a platform model (or vice versa). The cost/SLO isolation is real — filter latency is the dominant cost; platform-model filter caps it. No additional implementation cost (already a kwarg to `client.submit_and_wait`).

## OQ-2 resolution — knowledge-service orchestrator integration

**Decision.** **Option B** — keep `extract_pass2_chapter` / `extract_pass2_chat_turn` calling per-extractor directly (current shape). Filter integrates as a new post-gather step in the orchestrator, BEFORE `write_pass2_extraction` is called.

**Rationale.** The orchestrator does work the SDK `extract_pass2` does NOT do:
- Per-leaf P2 cache (`_p2_cache_wrap`) keyed on extractor_version per op
- Model-aware concurrency semaphore (tight-context fallback to 1-2 parallel slots vs unbounded)
- Stage-by-stage `_emit_log` to `job_logs` for FE progress display
- Anchor loading + glossary integration

Option A (refactor orchestrator to use SDK `extract_pass2`) would REGRESS all four. The SDK orchestrator is for the LIGHTWEIGHT path (worker-ai); knowledge-service has the HEAVY path. They are intentionally divergent.

**Implementation.** New module-level helper `_maybe_apply_precision_filter(candidates, *, text, env_model_ref, ...)`. Called from BOTH `extract_pass2_chapter` and `extract_pass2_chat_turn` right after the gather, before write. Reads `KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF` env; when unset → returns `candidates` untouched; when set → calls `apply_precision_filter` from `pass2_filter`.

## OQ-3 resolution — Neo4j filter_status flag

**Decision.** **NO.** `filter_status` and `filter_coverage` stay in-memory on `Pass2Candidates`. Not persisted to Neo4j.

**Rationale.** Adding a property to Neo4j nodes cascades to writer + indexer + reader schemas + RAG selector. The signal is debug-grade — not worth the schema delta. Surfaced via Prometheus + job_logs only.

## Module map

```
sdks/python/loreweave_extraction/
├── pass2.py                          (MODIFIED)
│     adds: precision_filter kwarg (PrecisionFilterConfig | None = None)
│            return-shape: Pass2Candidates now carries filter_status + filter_coverage
├── pass2_filter.py                   (NEW, ~280 lines)
│     exports:
│       - PrecisionFilterConfig (dataclass)
│       - FilterStatus = Literal["applied", "degraded", "skipped"]
│       - apply_precision_filter(candidates, *, text, config, llm_client, ...) -> Pass2Candidates
│       - PrecisionFilterError (extends ExtractionError)
│       - DecisionHandler = Callable[[Category, Verdict], None]  (telemetry hook)
├── __init__.py                       (MODIFIED)
│     re-exports PrecisionFilterConfig, FilterStatus

sdks/python/tests/test_extraction/
├── test_pass2.py                     (MODIFIED, additions)
│     test_precision_filter_none_keeps_current_behavior
│     test_precision_filter_set_chains_call
│     test_filter_status_field_populated
├── test_pass2_filter_unit.py         (NEW, ~280 lines)
│     unit coverage of verdict policies, empty-pass-A short-circuit, failed-filter degrade

services/worker-ai/
├── app/runner.py                     (MODIFIED)
│     reads WORKER_AI_PRECISION_FILTER_MODEL_REF env
│     when set → passes precision_filter=PrecisionFilterConfig(...) to extract_pass2
├── tests/test_runner.py              (MODIFIED, regression-lock)
│     env-unset case (current contract preserved)
│     env-set case (filter applied, persist-pass2 receives filtered candidates)

services/knowledge-service/
├── app/extraction/pass2_orchestrator.py   (MODIFIED)
│     reads KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF env
│     adds _maybe_apply_precision_filter helper called post-gather pre-write
│     emits stage log "precision_filter applied: X→Y entities, ..." when applied
├── tests/unit/test_pass2_orchestrator.py  (MODIFIED, regression-lock)
│     env-unset: current pipeline shape (cache + gather + write)
│     env-set: filter call lands between gather and write
├── app/metrics.py                          (MODIFIED, new counter)
│     knowledge_extraction_filter_decisions_total{category, verdict}
│     knowledge_extraction_filter_coverage_ratio{category}
├── tests/quality/test_pass2_filter_live.py (NEW, --run-quality opt-in)
│     real claude-4.7-opus call on alice_ch01 with stub gold;
│     asserts filter_status="applied" + filter_coverage > 0.8

docs/
├── specs/2026-05-29-pass2-precision-filter.md   (THIS FILE)
├── plans/2026-05-29-pass2-precision-filter.md   (NEXT — PLAN phase)
```

**File count summary:** 4 NEW, 7 MODIFIED = 11 files. **XL classification holds.** (Drops from initial 13-file estimate after D6 revision removed gateway/migration files.)

## Interfaces

### PrecisionFilterConfig

```python
from dataclasses import dataclass, field
from typing import Literal

PartialPolicy = Literal["keep", "drop", "demote"]  # "demote" reserved, BUILD blocks if used

@dataclass(frozen=True)
class PrecisionFilterConfig:
    """Config for the Pass2 precision filter pass. None = filter disabled."""

    model_ref: str                             # e.g. "huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated"
    model_source: Literal["user_model", "platform_model"] = "user_model"   # OQ-1
    partial_policy: PartialPolicy = "keep"     # D4
    categories: tuple[Literal["entity", "relation", "event"], ...] = ("entity", "relation", "event")  # D2 — subset for ops that filter only some
    max_items_per_batch: int = 3               # mirrors llm_judge.py batch size; calibrated for reasoning-token bursts
    transient_retry_budget: int = 1            # same as extractor budget

    def __post_init__(self) -> None:
        if self.partial_policy == "demote":
            raise NotImplementedError("partial_policy='demote' reserved for follow-up cycle; use 'keep' or 'drop'")
```

### FilterStatus + Pass2Candidates extension

```python
FilterStatus = Literal["applied", "degraded", "skipped"]

@dataclass
class Pass2Candidates:  # MODIFIED
    entities: list[LLMEntityCandidate] = field(default_factory=list)
    relations: list[LLMRelationCandidate] = field(default_factory=list)
    events: list[LLMEventCandidate] = field(default_factory=list)
    facts: list[LLMFactCandidate] = field(default_factory=list)

    # NEW (default values match current contract — no filter applied)
    filter_status: FilterStatus = "skipped"
    filter_coverage: dict[str, float] = field(default_factory=dict)  # {"entity": 1.0, ...}

    def is_empty(self) -> bool:
        return not (self.entities or self.relations or self.events or self.facts)
```

### apply_precision_filter

```python
async def apply_precision_filter(
    candidates: Pass2Candidates,
    *,
    text: str,
    config: PrecisionFilterConfig,
    user_id: str,
    llm_client: LLMClientProtocol,
    on_decision: DecisionHandler | None = None,
) -> Pass2Candidates:
    """Apply the precision filter pass to existing Pass2 candidates.

    Empty input → returns candidates unchanged with filter_status="skipped".
    LLM error → returns candidates unchanged with filter_status="degraded"
      (NEVER raises; caller's existing pipeline must survive filter failure).
    Success → returns filtered candidates with filter_status="applied" +
      filter_coverage per category.
    """
```

### extract_pass2 signature change

```python
async def extract_pass2(
    *,
    text: str,
    known_entities: list[str],
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    llm_client: LLMClientProtocol,
    on_dropped: DroppedHandler | None = None,
    precision_filter: PrecisionFilterConfig | None = None,   # NEW
    on_filter_decision: DecisionHandler | None = None,        # NEW (optional)
) -> Pass2Candidates:
    ...
```

**Backwards-compat invariant:** every existing caller passing the current kwarg set MUST get the current behavior unchanged. Verified by `sdks/python/tests/test_extraction/test_pass2.py` suite running unchanged.

### Filter prompt — promote `_PRECISION_SYSTEM` from `llm_judge.py`

The filter promotes the existing `_PRECISION_SYSTEM` prompt (currently in `services/knowledge-service/tests/quality/llm_judge.py`) into `sdks/python/loreweave_extraction/prompts/precision_filter_system.md`. The eval-side `llm_judge.py` REIMPORTS from the SDK going forward (1-line change).

**Rationale.** Single source of truth. If we later iterate the precision prompt (a future cycle), one file changes, both filter + judge benefit. Per memory `prompt-example-text-must-not-overlap-eval-fixtures`, the prompt has no example text (rule-only) — safe for both filter and judge use.

### Caller envs

```bash
# worker-ai/runner.py:
WORKER_AI_PRECISION_FILTER_MODEL_REF=huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated
WORKER_AI_PRECISION_FILTER_PARTIAL_POLICY=keep   # default; "drop" available

# knowledge-service/pass2_orchestrator.py:
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF=huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated
KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY=keep
```

Both envs unset = current behavior. Both envs set + non-identical = each service files its own filter call with its own policy (allowed; might happen if worker-ai prefers `keep` and knowledge-service prefers `drop` for downstream-citation reasons).

## Validation methodology refinement (D10 update)

**Run A — c72a-baseline** = re-extract on current locked prompts, no filter. Should re-produce c70a's ensemble macro (P=0.96/R=0.92, F1≈0.94, κ=0.671). If c72a diverges from c70a by ≥1pp, **STOP**: there's drift not from the filter — investigate before proceeding.

**Run B — c72b-filter-keep** = same extract pass + filter with `partial_policy="keep"`.

**Run C — c72c-filter-drop** = same extract pass + filter with `partial_policy="drop"`.

Each judged by the same locked 3-judge ensemble.

**Locked ship table** (per D10, repeated for clarity):

| Variant | gemma F1 lift | qwen-30b F1 lift | claude F1 lift | κ delta | Verdict |
|---|---|---|---|---|---|
| c72b | ≥ +1pp | ≥ +1pp | ≥ +2pp | ≥ -0.05 | SHIP |
| c72b | < +1pp on gemma OR qwen | — | ≥ +2pp | — | REJECT (self-reinforcement) |
| c72b | regression on gemma+qwen | — | regression | — | REJECT |
| c72c | same shape as c72b | — | — | — | same shape |

Both c72b and c72c pass acceptance → ship whichever has higher median F1 (D11 rule).
Neither passes → cycle is NEGATIVE, revert. Same shape as cycle 71.

## Risks (revised)

| ID | Risk | Mitigation | Change vs CLARIFY |
|---|---|---|---|
| HIGH-1 | Self-reinforcement: filter judge = ensemble judge C | D3 explicit cross-judge agreement gate in D10 | unchanged |
| HIGH-2 | Filter doubles wall-clock latency on production books | D8 opt-in env per service; default off | unchanged |
| MED-1 | `partial_policy="demote"` requires schema change | Reserve enum value only; BUILD `keep`/`drop` paths only; `__post_init__` raises | unchanged |
| MED-2 | Filter degradation invisible to caller | D5 new `Pass2Candidates.filter_status` field | unchanged |
| ~~MED-3~~ | ~~JobOperation enum cascade~~ | **REMOVED** — use `operation="chat"` per `llm_judge.py` precedent | **removed** |
| MED-4 | knowledge-service orchestrator bypasses `extract_pass2` | OQ-2 resolved: Option B — filter as post-gather step in orchestrator (orchestrator KEEPS its direct-extractor pattern) | resolved |
| ~~MED-5~~ | ~~Filter LLM call cost not metered in usage_billing~~ | **RESOLVED** — `chat` op already metered | **removed** |
| MED-6 (new) | Existing `llm_judge.py` and filter share `_PRECISION_SYSTEM` — change to filter's copy silently changes eval | **MITIGATION:** promote to single SDK source of truth (`prompts/precision_filter_system.md`); `llm_judge.py` imports it; regression-lock test asserts the imported text matches expected hash | new |
| MED-7 (new) | Filter is called per-category per-chapter — N chapters × 3 categories × ~30s/call = N×90s wall-clock | **MITIGATION:** library-side ALL 3 categories batched into ONE `asyncio.gather` per chapter (3 concurrent calls, not serial); ~30s/chapter actual added wall-clock | new |
| LOW-1 | Filter coverage < 1.0 silently underapplied | D5 coverage field on Pass2Candidates + D7 metric | unchanged |
| LOW-2 | Existing eval tests assume Pass A only (no filter) | Filter defaults to None in all existing call sites; new test file covers filter path | unchanged |
| LOW-3 (new) | Filter could be applied to a category list that contains 0 items (gate at orchestrator) | Library-side: filter for category returns empty input unchanged with coverage=1.0 (vacuous) | new |

## Test plan (BUILD + VERIFY check-list — per memory `design-test-plan-is-a-checklist`)

### SDK unit tests
- [ ] `test_pass2_filter_unit.py::test_keep_partial_treats_partial_as_supported`
- [ ] `test_pass2_filter_unit.py::test_drop_partial_treats_partial_as_unsupported`
- [ ] `test_pass2_filter_unit.py::test_demote_raises_not_implemented_in_post_init`
- [ ] `test_pass2_filter_unit.py::test_empty_input_short_circuits_with_coverage_1`
- [ ] `test_pass2_filter_unit.py::test_filter_failure_degrades_to_pass_a_unchanged`
- [ ] `test_pass2_filter_unit.py::test_per_category_filter_independence`
- [ ] `test_pass2_filter_unit.py::test_coverage_lt_1_partial_policy_applied_to_unjudged`
- [ ] `test_pass2_filter_unit.py::test_three_categories_run_concurrently_in_gather` (MED-7 mitigation)
- [ ] `test_pass2_filter_unit.py::test_categories_subset_respected_unselected_pass_through`

### SDK pass2.py extension tests
- [ ] `test_pass2.py::test_precision_filter_none_zero_behavior_change` (regression-lock)
- [ ] `test_pass2.py::test_precision_filter_set_chains_filter_call`
- [ ] `test_pass2.py::test_filter_status_field_populated_correctly_per_status`
- [ ] `test_pass2.py::test_filter_coverage_populated_per_category`

### worker-ai integration
- [ ] `test_runner.py::test_runner_env_unset_skips_filter` (regression-lock per memory `audit-all-callsites-when-adding-optional-kwarg`)
- [ ] `test_runner.py::test_runner_env_set_passes_filter_config_to_extract_pass2`
- [ ] `test_runner.py::test_runner_filter_degraded_status_still_persists_pass_a`

### knowledge-service orchestrator integration
- [ ] `test_pass2_orchestrator.py::test_orchestrator_env_unset_skips_filter_call`
- [ ] `test_pass2_orchestrator.py::test_orchestrator_env_set_calls_filter_post_gather_pre_write`
- [ ] `test_pass2_orchestrator.py::test_orchestrator_filter_failure_logs_warning_continues_write`
- [ ] `test_pass2_orchestrator.py::test_orchestrator_emits_filter_applied_stage_log`

### Prompt-source regression lock
- [ ] `test_precision_filter_prompt.py::test_sdk_prompt_matches_llm_judge_import` (single SOT)

### Eval verification (the SHIP test)
- [ ] c72a baseline run reproduces c70a within 1pp ensemble macro
- [ ] c72b run completes + ensemble report captured
- [ ] c72c run completes + ensemble report captured
- [ ] `c72_compare.md` written with all three runs side-by-side
- [ ] D10 cross-judge acceptance gate evaluated explicitly
- [ ] Live-smoke evidence captured

## Acceptance criteria (revised — explicit per-check version)

1. ✅ SDK module `pass2_filter.py` ships with all unit tests above passing
2. ✅ `extract_pass2` `precision_filter=None` path tests unchanged (regression-lock)
3. ✅ Worker-ai + knowledge-service env-unset cases preserve current behavior (regression-lock)
4. ✅ Worker-ai + knowledge-service env-set cases apply filter end-to-end
5. ~~JobOperation enum~~ — **removed** per D6 revision
6. ✅ Three eval runs (c72a/b/c) complete, ensemble-judged
7. ✅ EITHER ship c72b or c72c per D10 acceptance, OR document NEGATIVE cycle
8. ✅ Live-smoke evidence at VERIFY: `live smoke: c72b filter end-to-end on alice_ch01 via worker-ai+knowledge-service+gateway+lm-studio, filter_status=applied`

---

**Design status:** /review-impl round 1 complete; 7 findings folded below; ready for PLAN.

---

# Round 1 fixes folded (2026-05-29)

7 findings (2 HIGH, 4 MED, 3 LOW). All folded into spec; no findings deferred to BUILD.

## HIGH-1 fold: c70a dump fixture, not re-extraction

**Was:** D10 Run A "c72a-baseline" = re-extract on current locked prompts.
**Now:** D10 Run A is REMOVED. Pass A source for filter is the SAVED `eval_dump_cycle70` from session 70 (commit `1c0b2a08`). Copied as repo fixture under `services/knowledge-service/tests/quality/eval_runs/c70a/` containing the 9-chapter `actual.json`/`expected.json` + the already-locked 3-judge ensemble report (`judge_ensemble_report.json` + per-judge verdicts).

**Empirical validation** (this cycle): `docker exec infra-knowledge-service-1 ls /tmp/eval_dump_cycle70/` returned all 9 chapter directories + 3 per-judge verdict files + `judge_ensemble_report.json` — the fixture is recoverable.

**Implication for SDK design:** `apply_precision_filter` MUST be callable from a script with `Pass2Candidates` reconstructed from dump JSON, not just inline inside `extract_pass2`. Add:
```python
# pass2_filter.py
def load_candidates_from_dump(dump_dir: Path) -> Pass2Candidates:
    """Reconstruct Pass2Candidates from a saved actual.json dump."""
```
This unlocks both: (a) the c72 validation harness that runs filter on c70a fixture, (b) ad-hoc precision audits on any saved dump.

**D10 revised ship table:**

| Variant | Pass A source | Filter | Judged by |
|---|---|---|---|
| **c70a-saved** (reference) | `tests/quality/eval_runs/c70a/` | None | Already done (saved ensemble report) |
| **c72b** | same fixture (load + filter) | claude-4.7-opus, `partial_policy="keep"` | Fresh ensemble run |
| **c72c** | same fixture (load + filter) | claude-4.7-opus, `partial_policy="drop"` | Fresh ensemble run |

Same Pass A → only filter is the changing variable. Filter F1 lift is now attribution-clean.

**c72_compare.md format change:** No re-baseline step. Directly diffs c72b/c against the saved c70a ensemble report.

## HIGH-2 fold: Promote both `_NO_THINK_PREFIX` and `_PRECISION_SYSTEM` via builder helper

**Was:** "promote `_PRECISION_SYSTEM` from `llm_judge.py` to SDK"
**Now:** Promote BOTH constants. The SDK exposes a single helper:

```python
# sdks/python/loreweave_extraction/prompts/precision_filter_system.md  — body only
# sdks/python/loreweave_extraction/extractors/precision_filter_prompts.py
NO_THINK_PREFIX = "RESPOND DIRECTLY. Do NOT think aloud, ..."
PRECISION_SYSTEM_BODY = open(... .md).read()  # loaded once at import

def build_precision_prompt(*, suppress_thinking: bool = True) -> str:
    """Single SOT for the precision filter / judge prompt.
    `suppress_thinking=True` (default) prepends the NO_THINK_PREFIX —
    required for thinking-tuned judges like claude-4.7-opus or
    gemma-4-26b reasoning variant.
    """
    return (NO_THINK_PREFIX + PRECISION_SYSTEM_BODY) if suppress_thinking else PRECISION_SYSTEM_BODY
```

`llm_judge.py` becomes:
```python
from loreweave_extraction.extractors.precision_filter_prompts import build_precision_prompt
_PRECISION_SYSTEM = build_precision_prompt(suppress_thinking=True)
```

Filter calls `build_precision_prompt(suppress_thinking=True)` (default).

## MED-1 fold: Pydantic → dict adapter at filter boundary

**Was:** Unspecified.
**Now:** Spec pins: `apply_precision_filter` calls `[c.model_dump(mode="json") for c in candidates.entities]` (and same for relations/events) before invoking the formatter. The formatter (`format_items_for_judge`) signature is unchanged (still takes `list[dict]`).

Test plan **adds**:
- `test_pass2_filter_unit.py::test_pydantic_model_to_judge_format_adapter` — assert filter accepts `LLMEntityCandidate(...)` instances and forms correct numbered prompt without `AttributeError`.

## MED-2 fold: Cross-judge gate revised

**Was:**
```
gemma F1 lift ≥ +1pp AND qwen-30b F1 lift ≥ +1pp AND claude F1 lift ≥ +2pp
```

**Now (replaces D10 acceptance):**
```
SHIP requires ALL of:
  (a) median(F1_lift) over [gemma, qwen-30b, claude] ≥ +1.5pp
  (b) min(F1_lift) over the 3 judges ≥ -0.5pp  (no judge regressed materially)
  (c) claude F1_lift ≤ 2 × median(F1_lift)     (anti-self-reinforcement bound)
  (d) Fleiss κ on filtered dump ≥ 0.60 (still "substantial")
```

Symmetric: (c) catches "only claude lifts" (self-reinforcement); (b) catches "claude lifts but gemma regresses" (precision win paid for by recall loss); (a) requires consensus on direction; (d) catches "judges disagree more after filter" (degraded reliability).

Test in c72_compare must explicitly print all 4 gates with PASS/FAIL.

## MED-3 fold: Measurement validity caveat

**Spec gains a new "Measurement validity caveat" subsection:**

> The c72 ship table reports FILTER-OUTPUT F1 (what `apply_precision_filter` returns), not Neo4j-realized F1 (what `pass2_writer` actually persists). These diverge because the writer enforces relation referential integrity ([services/knowledge-service/app/extraction/pass2_writer.py:204](services/knowledge-service/app/extraction/pass2_writer.py#L204)) — relations whose subject/object entity isn't merged get auto-skipped.
>
> **Implications:**
> - Filter dropping entity X → writer auto-skips relations involving X → "relation precision lift" measured by the filter judge is PARTLY a cascade from entity filter, not a pure relation-prompt effect.
> - Events do NOT cascade: filter-dropped entity X stays as a STRING in event `participants` array (untyped, no FK). Net effect: precision filter on entity creates a small orphan-participant signal on events. Measured by filter judge as supported (the participant string is still in the text); user-visible as Neo4j Event nodes with participants that don't link to any :Entity node.
> - Facts have no entity reference at all (per [services/knowledge-service/app/extraction/pass2_writer.py:282](services/knowledge-service/app/extraction/pass2_writer.py#L282) — subject is intentionally dropped). Filter on facts is moot anyway (D2 excludes facts).
>
> **Decision:** filter-output F1 is the canonical c72 metric. A Neo4j-realized re-judge is documented as **D-PASS2-FILTER-NEO4J-REALIZED-F1** in deferred items; not blocking c72 ship.

## MED-4 fold: Immutability contract on `apply_precision_filter`

**Spec gains explicit:**

> `apply_precision_filter` MUST NEVER mutate input. Returns a NEW `Pass2Candidates` via `dataclasses.replace(candidates, entities=[...], filter_status=..., filter_coverage=...)`. Input instance remains exactly as caller passed it.

**Pass2Candidates dataclass extension** updated to add `__post_init__` defensive copy of list fields (optional belt-and-suspenders):
```python
@dataclass
class Pass2Candidates:
    entities: list[LLMEntityCandidate] = field(default_factory=list)
    # ... etc
    filter_status: FilterStatus = "skipped"
    filter_coverage: dict[str, float] = field(default_factory=dict)
```
Note: NOT `frozen=True` — preserves backwards-compat with any existing call site that mutates candidates post-construction. Filter contract is the only place immutability is asserted (via test).

Test plan **adds**:
- `test_pass2_filter_unit.py::test_filter_never_mutates_input_instance` — `input is not output`, `input.filter_status == "skipped"` after `apply_precision_filter(input, ...)`, `id(input.entities) != id(output.entities)`.
- `test_pass2_filter_unit.py::test_filter_degraded_returns_new_instance_with_pass_a_lists` — even on degradation, output is a new instance.

## LOW-1 fold: Batch size calibration as BUILD-time CALIBRATE

**Defer to BUILD.** First c72b run captures `filter_coverage` per category. If aggregate coverage < 0.9, retune `max_items_per_batch` (try 2, then 1) + token budget. PLAN documents this as a BUILD-time calibration step (with explicit log-line check) — no DESIGN change.

## LOW-2 fold: Facts filter as deferred row

Add to deferred items in SESSION_HANDOFF on commit:

> **D-PASS2-FILTER-FACTS-SUPPORT** — extend `PrecisionFilterConfig.categories` Literal to include `"fact"`, extend `format_items_for_judge` to handle fact items, extend `_PRECISION_SYSTEM` instructions to describe fact verdict shape. Out of scope for cycle 72 per D2.

## LOW-3 fold: Entity-category default deferred to c72b empirical

**Spec gains:** PLAN includes step "in c72b post-mortem, if per-category lift on entity is < +0.5pp, ship cycle with `categories=("relation","event")` as recommended default; document in c72_compare." No DESIGN change — empirical-driven.

## Updated test plan (incremental from base)

**Added** (4 new test cases on top of the original 19):
- `test_pass2_filter_unit.py::test_pydantic_model_to_judge_format_adapter` (MED-1)
- `test_pass2_filter_unit.py::test_filter_never_mutates_input_instance` (MED-4)
- `test_pass2_filter_unit.py::test_filter_degraded_returns_new_instance_with_pass_a_lists` (MED-4)
- `test_pass2_filter_unit.py::test_load_candidates_from_dump_roundtrips_pass2candidates` (HIGH-1)

**Added** (1 new SDK file):
- `sdks/python/loreweave_extraction/extractors/precision_filter_prompts.py` — single SOT for prompt + builder helper (HIGH-2)

**Added** (1 new repo fixture):
- `services/knowledge-service/tests/quality/eval_runs/c70a/` — copied from container `/tmp/eval_dump_cycle70/` (HIGH-1). Includes all 9 chapter dumps + 3-judge ensemble report + per-judge verdicts. Committed once; future cycles can re-validate against it without re-running extraction.

**Removed:** D10 Run A "c72a baseline re-extract" (HIGH-1 — replaced by saved fixture).

**Module count revised:** 4 NEW + 7 MODIFIED + 1 FIXTURE = 12 files (vs initial 11). XL classification holds.

---

**Round 1 verdict:** all findings folded. No round-2 needed pre-PLAN. Spec status: ready for PLAN.

