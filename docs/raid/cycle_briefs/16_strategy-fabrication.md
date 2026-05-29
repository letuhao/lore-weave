# Cycle 16: Strategy (c) fabrication

## 🎯 TL;DR (30 seconds — TOP critical info)
- **What:** Add the **P2 `fabrication` strategy** — canon-grounded fabrication of new location detail — as a pluggable `EnrichmentStrategy`, registered but **gated OFF** until the C15 eval gate clears.
- **Why P2 ≠ active:** Fabrication is higher-cost/higher-risk than P1 (template/retrieval). It only goes "active" (selectable for jobs) once `scripts/enrichment_eval.py` shows it clears the C15 threshold vs baseline. **Cost discipline is LOCKED: no fabrication runs before the gate passes.**
- **H0 is non-negotiable:** every fabricated fact is `origin='enriched'`, `technique='fabrication'` (`source_type='enriched:fabrication'`), `pending_validation=true`, `confidence<1.0`, **quarantined**. NEVER canon. Reuses the C11 tagging + C12 canon-verify + C13 write-back path — this cycle adds the **generator strategy only**, not a new write path.
- **Output language = Chinese** (源文一致, 封神演义 tone). Model resolved via **provider-registry** (Qwen 3.6 / bge-m3) — **NO hardcoded model names**.
- **Acceptance gate:** `scripts/raid/verify-cycle-16.sh` exits 0 (created by this cycle's runner). It asserts: strategy registers, is **flag-default-OFF**, fabricated facts carry H0 origin tags, and the eval-gate read blocks activation below threshold.

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C15
- C15 ships the eval framework + gate (`scripts/enrichment_eval.py`, `eval/enrichment-eval-suite.toml`, `eval/baselines/enrichment-vX.json`, `enrichment_eval_runs` persist, judge-ensemble). C16 **consumes** that gate to decide whether fabrication may activate. C15 transitively guarantees C8 (strategy core/registry/feature-flags/cost-cap), C11 (origin tagging), C12 (canon-verify), C13/C14 (write-back + job runner) are DONE.
- Do not start C16 until CYCLE_LOG.md marks **C15 = DONE**.

## Scope (IN)
- New strategy class implementing the **C8 `EnrichmentStrategy` interface**: `app/strategies/fabrication.py` (mirror C9 template / C10 retrieval strategy shape).
- Register it in the C8 **strategy registry** under `technique='fabrication'`, behind a **feature flag default-OFF** (`ENRICHMENT_FABRICATION_ENABLED=false`).
- **Grounding contract:** fabrication is *canon-grounded* — it MUST consume the same inputs P1 uses (C7 gap, C10 `cultural_grounding_ref` retrieval results, KG-read-port neighborhood) and emit facts that cite those `source_refs_json`. Fabrication fills gaps the retrieval cannot, but stays anchored to retrieved grounding (no free invention).
- **Gate-aware activation:** a guard that reads the latest persisted `enrichment_eval_runs` / baseline-diff for `technique='fabrication'` and **refuses to mark the technique active** (and refuses job selection) unless the score clears the C15 threshold. Below threshold → strategy stays inert + escalates per RAID cost-control.
- Per-job **cost guardrail** integration: fabrication declares a higher cost estimate so the C8 cost-cap can pause/escalate.
- LLM + embedding access **only** via the C1 KG-read port / provider-registry-resolved client (model by id, tolerate JIT load latency).
- Unit tests: (a) registry selects fabrication when flag ON; (b) flag default-OFF → not selectable; (c) every fabricated fact carries `origin='enriched'` + `technique='fabrication'` + `confidence<1.0` + `pending_validation=true`; (d) gate-guard blocks activation when eval below threshold; (e) fabricated facts include `source_refs_json` to grounding.
- `scripts/raid/verify-cycle-16.sh`.

## Scope (OUT — explicitly)
- **NOT** technique (d) re-cook (that is C17, real history/news + licensing).
- **NOT** a new write-back path, proposal store, or KG writer — reuse C11/C12/C13 unchanged.
- **NOT** editing the eval framework files (C15 owns `scripts/enrichment_eval.py`, `eval/enrichment-eval-suite.toml`, baselines). C16 only **reads** persisted results / calls the gate.
- **NOT** editing climate/geo eval files (`scripts/climate_eval.py`, geo `*-suite.toml`) — isolation locked.
- **NOT** modifying `world-service` / `game-server` / `tilemap` / `infra/existing-prod/`.
- **NOT** building a RAG framework or adding langchain/llamaindex — retrieval is C10's reuse of knowledge-service `/internal/embed`.
- **NOT** hardcoding model names, web/internet search, or English output.
- **NOT** flipping the flag ON in committed config — activation is gate-driven at runtime.

## Acceptance criteria (CI gates — exit code 0 = pass)
- `scripts/raid/verify-cycle-16.sh` exits 0.
- Unit suite green: registry select, flag-default-OFF, H0 tagging on every fabricated fact, gate-guard blocks below threshold, grounding `source_refs_json` present.
- Grep gate: no hardcoded model-name literals in `app/strategies/fabrication.py` (model id comes from provider-registry/port).
- Isolation gate: `git diff --name-only` touches **no** climate/geo eval files, no `world-service`/`game-server`/`infra/existing-prod/`.
- Flag-default-OFF asserted: with default config, fabrication is registered but **not** in the selectable-active set.
- **Cross-service: NO.** This cycle is in-service (lore-enrichment-service only) — no live-smoke token required. If the runner discovers it must touch glossary/knowledge-service, STOP and reclassify (that would make it cross-service per CLAUDE.md VERIFY rule).

## DPS parallelism plan
- **DPS 2–3 (low, locked cost posture).** Small surface: one strategy file + registry wiring + gate-guard + tests.
- Lane A: `app/strategies/fabrication.py` (generator + grounding prompt assembly, Chinese output).
- Lane B: gate-guard module (read `enrichment_eval_runs`, compare to baseline threshold) + registry/feature-flag wiring.
- Lane C: unit tests + `verify-cycle-16.sh`.
- Sync point: tests in C depend on A+B signatures — freeze the `EnrichmentStrategy` method signatures (inherited from C8) before C lands.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **H0 leak:** can any fabricated fact reach the KG/glossary as `source_type='glossary'` or `confidence=1.0`? Confirm every emitted fact is `origin='enriched'` + `technique='fabrication'` + quarantined + `confidence<1.0`. This is the highest-risk pitfall for a *fabrication* technique — it invents content, so a tagging miss = pure hallucination entering as canon.
- **Gate bypass:** is activation truly gated? Try: flag forced ON in config, missing/stale `enrichment_eval_runs`, eval row below threshold — fabrication must stay inert and escalate, never silently activate. Check default-OFF is the committed state.
- **Ungrounded invention:** does "fabrication" degrade into free hallucination? Verify it cites `source_refs_json` from C10 grounding / KG neighborhood and does not fabricate beyond retrieved anchors.
- **Hardcoded model name:** grep for any literal model id (`qwen...`, `bge-m3`, etc.) in the strategy — must resolve via provider-registry/port.
- **Scope creep into C17:** any history/news/licensing logic = wrong cycle.
- **Eval-file mutation / isolation:** confirm no edits to C15 eval files, climate/geo eval, world-service/game-server, infra/existing-prod.
- **Output language:** confirm prompts/output are Chinese, not English.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR only if ALL hold:
- Diff limited to lore-enrichment-service strategy/registry/gate-guard/tests + `scripts/raid/verify-cycle-16.sh`.
- No new write path; reuses C11/C12/C13.
- No edits to eval files (C15), climate/geo eval, world-service, game-server, infra/existing-prod.
- Feature flag default-OFF committed; activation gate-driven.
- No hardcoded model names; Chinese output.
- `scripts/raid/verify-cycle-16.sh` exits 0.
Else BLOCKED with the offending file/line.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- `docs/plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md` — C16 row + C15 gate + cost-discipline note (P1 before P2/P3; gate must exist before fabrication).
- `docs/plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md` — H0 invariant; Q-R2 (phased P1→P2→P3, gate promotes each tier); execution decisions (Chinese output, provider-registry models, eval auto-blocks C16 on failure + escalates).
- `docs/03_planning/lore-enrichment/PLAN.md` — strategy/technique architecture + cost posture.
- `docs/03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md` — code-verified seams (strategy interface, eval framework, provider-registry).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **H0 (CORE):** every fabricated fact = `origin='enriched'` + `technique='fabrication'` (`source_type='enriched:fabrication'`) + `pending_validation=true` + `confidence<1.0`, quarantined. NEVER canon. Only the author's explicit promote canonizes — and the permanent origin marker survives promotion. A fabrication tagging miss is the single worst failure here.
- 🔴 **Cost gate (LOCKED Q-R2):** fabrication ships **flag-default-OFF** and only activates when `scripts/enrichment_eval.py` (C15) shows it clears threshold vs baseline. No fabrication job runs before the gate passes; below threshold → inert + escalate. **Acceptance gate = `scripts/raid/verify-cycle-16.sh` exits 0.**
- 🔴 **DO NOT TOUCH:** C15 eval files / climate-geo eval files / `world-service` / `game-server` / `tilemap` / `infra/existing-prod/`. No new write path (reuse C11/C12/C13). No hardcoded model names (provider-registry only). Output = Chinese. This is in-service — no cross-service edits (would force reclassify + live-smoke).
