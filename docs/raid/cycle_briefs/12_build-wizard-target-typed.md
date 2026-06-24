# Cycle 12: Build wizard — target-typed extraction + concurrency

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Let a knowledge build job extract only a **chosen subset of passes** (`targets: [entities|relations|events|facts|summaries]`) instead of always all. De-risked by DESIGN_C12_C13: the SDK already dispatches separable extractors via `asyncio.gather`, so selective invocation is a **conditional task-list at ~4 logic sites** (SDK pass2 entity/trio gather, orchestrator gather, summaries enqueue gate, decoupled trio) + additive threading of a `targets TEXT[]` column (default all; `targets=None` ⇒ all = back-compat). Also threads `concurrency_level` (passthrough cap on parallel LLM calls). Validation: requesting any of {relations,events,facts} auto-includes `entities`; entity recovery/precision-filter auto-disable when entities skipped. FE: 3-step **build-wizard shell** + **Step-1 target picker** (shell is shared with C13 Step-2). Cross-service (knowledge-service start contract + worker-ai runner + decoupled-extract + the `loreweave_extraction` SDK).
- **Acceptance gate:** `scripts/raid/verify-cycle-12.sh` exits 0
- **Top 3 LOCKED decisions consumed:** C12-targets-TEXT[]-default-all, C12-dependent-auto-include-entities, C12-recovery-filter-auto-disable
- **DPS count:** 4
- **Estimated wall time:** 5–7h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C5
- Files expected to exist (grep-able paths): the `BuildGraphDialog` build-gate surface from C5; the existing `loreweave_extraction` SDK package; worker-ai runner + decoupled-extract modules; knowledge-service `extraction.py` StartJobRequest + `db/migrate.py` extraction_jobs + `repositories/extraction_jobs.py`.

## Scope (IN)
- **Additive contract:** add `targets: list[Literal[entities|relations|events|facts|summaries]] | None = None` and `concurrency_level: int | None = None` to knowledge-service `StartJobRequest`.
- **Migration:** `extraction_jobs ADD COLUMN targets TEXT[] NOT NULL DEFAULT ARRAY['entities','relations','events','facts','summaries']` (null/empty request ⇒ default all).
- **Repository threading:** thread `targets` through `ExtractionJobCreate` / `ExtractionJob` / select-cols / INSERT.
- **SDK (`loreweave_extraction` pass2):** `extract_pass2(..., targets: set | None = None)` — wrap entity extraction in a target check; build the relations/events/facts gather task-list **conditionally** and zip results back. Extractor internals unchanged.
- **Orchestrator:** thread `targets` through `_run_pipeline` / `extract_pass2_chapter`; apply the same conditional pattern at the orchestrator gather; gate the no-entity short-circuit; gate the **summaries** enqueue condition with `and "summaries" in targets`.
- **worker-ai runner:** read `targets` from the job row → pass to `extract_pass2` (strip `summaries`, which is orchestrator-gated not an SDK op).
- **Decoupled trio:** `new_extract_state` stores `targets`; `apply_entity_result` advances to TRIO only if any of R/E/F is in targets; `assemble_trio_submits` builds the submit-dict conditionally (trio fan-in already tolerates a partial op set — no state-machine change).
- **Validation locks:** dependent-target auto-include (`{relations|events|facts}` ⇒ force `entities` in, silently, in StartJobRequest validation + an SDK guard); recovery/precision-filter auto-disable when `entities ∉ targets`.
- **FE:** 3-step build-wizard **shell** (target picker / pinning placeholder / budget) + **Step-1 target picker** posting `targets[]` + `concurrency_level`. FE label "events·timeline" ⇒ the `events` op; "lore/wiki" ⇒ wiki-stub path.
- `scripts/raid/verify-cycle-12.sh` (acceptance gate; runner creates it) + Playwright screenshot of the Step-1 target picker.

## Scope (OUT — explicitly)
- **NO pinning** — `pinned_glossary_entity_ids`, the Step-2 dual-list, `fetch_entities_by_ids`, the glossary stats endpoint, the pinned-cost line are all **C13**.
- **NO extractor-internals rewrite** — entity/relation/event/fact extractor bodies are untouched; only the gather task-list is built conditionally.
- **NO break to other SDK consumers** — translation-service and any other `loreweave_extraction` caller MUST be unaffected (`targets=None` ⇒ current behavior).
- No timeline importance/narrative-order (C14); no graph canvas; no new provider wiring.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass:
  - SDK unit: `targets={entities}` → only entities; `{entities,events}` → entities+events, no relations/facts; `{relations}` → auto-includes entities; empty/`None` → all.
  - Orchestrator unit: summaries enqueue gated by `summaries ∈ targets`; recovery/precision-filter disabled when `entities ∉ targets`.
  - Repository/migration unit: `targets` round-trips; default-all on null.
- Lints pass: ruff/black on knowledge-service + worker-ai + SDK; `python scripts/ai-provider-gate.py` green (no hardcoded model names — extraction LLM/embedding resolve via provider-registry).
- **Live smoke (REQUIRED — cross-service):** evidence string contains `live smoke: targets=["events"] build → only the event pass runs`. Start a job with `targets=["events"]` on a real project → assert via job logs that only the event pass ran and the relations/facts tables are untouched. If full stack un-bootable: `live infra unavailable: <reason>` is the only substitute.
- Playwright screenshot: Step-1 target picker renders + a target can be toggled.

## DPS parallelism plan
- DPS 1 (BE contract/storage): StartJobRequest fields + migration + repository threading + dependent-auto-include validation (return budget: 1500 tokens summary)
- DPS 2 (SDK + orchestrator): conditional gather in `pass2` + orchestrator gather + summaries gate + recovery/filter auto-disable
- DPS 3 (worker-ai): runner reads `targets` → strips summaries → `extract_pass2`; decoupled-extract stores+honors targets in trio assembly
- DPS 4 (FE): 3-step wizard shell + Step-1 target picker + post; Playwright shot
- **Serial tail (Raid Leader):** rebuild touched images → `targets=["events"]` live smoke → `verify-cycle-12.sh`

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **SDK back-compat break:** any code path where `targets=None` no longer runs all passes → breaks translation-service + other consumers. Confirm the `None`/empty ⇒ all default holds at every layer (request, column, SDK, orchestrator).
- **Dependent-target silent-include missed:** `{relations}` alone must auto-add `entities` (R/E/F anchor to entity names) — a missing auto-include yields empty relations, not an error.
- **Recovery/filter not disabled:** entity_recovery/precision_filter are no-ops with no entity set — left enabled they waste an LLM call or crash on empty input.
- **Mock-only false-green:** unit suite green but no real `targets=["events"]` job ran → confirm the live-smoke token reflects a genuine job, and relations/facts tables were verified untouched.
- **Hardcoded model name:** any literal extraction LLM/embedding string instead of provider-registry resolution.
- **Decoupled trio state drift:** trio advanced when no R/E/F requested, or submit-dict built for a skipped op.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (contract + migration + SDK + orchestrator + worker-ai + decoupled + FE wizard shell + Step-1 picker)
- No OUT items touched (no pinning, no extractor-internals rewrite, no C14)
- All acceptance criteria met (units + provider-gate + live-smoke token + Playwright shot)
- Cross-cycle invariants not violated (SDK stays backward-compatible; provider invariant held)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Detailed design: [DESIGN_C12_C13.md](../../plans/2026-06-13-creation-unblock/DESIGN_C12_C13.md) — C12 section (touch-points + 4 logic sites + locks).
- Cycle row: [CYCLE_DECOMPOSITION.md](../../plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md) — C12 row + "Build wizard is C12+C13 (split)" note.
- LOCKED decisions: [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md) — §Architecture-review locks "C12 = L (DESIGNED, de-risked from XL)"; §Knowledge cycle design "C12 target taxonomy".
- Backend audit: [2026-06-13-knowledge-design-vs-impl-gap.md](../../specs/2026-06-13-knowledge-design-vs-impl-gap.md).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** `targets` stored `TEXT[]` default all; `targets=None`/empty ⇒ all → **SDK change MUST stay backward-compatible** (translation-service + other consumers unaffected).
- 🔴 **Top LOCKED 2:** dependent targets auto-include `entities` — requesting any of {relations,events,facts} silently forces `entities` in (don't error).
- 🔴 **Top LOCKED 3:** recovery/precision-filter auto-disable when `entities ∉ targets` (they no-op with no entity set).
- 🔴 **Acceptance MUST include:** the cross-service live-smoke token `live smoke: targets=["events"] build → only the event pass runs` — mock-only is a false-green and fails review.
- 🔴 **Do NOT touch:** pinning (C13: dual-list, `fetch_entities_by_ids`, glossary stats endpoint, pinned-cost line) or extractor internals — only the gather task-list is conditional.
- 🔴 **Fresh session reminder:** this is a new `/raid 12` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
