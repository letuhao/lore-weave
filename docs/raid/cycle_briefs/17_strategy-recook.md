# Cycle 17: Strategy (d) re-cook

## 🎯 TL;DR (30 seconds — TOP critical info)
- **What:** Add the **P3 `recook` strategy** — re-cook real history/news/reference material into 封神演义 location lore — as a pluggable `EnrichmentStrategy`, registered but **gated OFF** until the C15 eval gate clears AND a **licensing check** passes.
- **Two gates, not one:** (1) the C15 eval-gate (same cost-discipline guard C16 uses); (2) a **source-licensing check** that admits ONLY licensed / public-domain material into the re-cook corpus. Both must pass before re-cook may activate. **Cost discipline is LOCKED: P3 is last, after P1 (C9/C10) and P2 (C16); no re-cook run before the gate passes.**
- **H0 is non-negotiable:** every re-cooked fact is `origin='enriched'`, `technique='recook'` (`source_type='enriched:recook'`), `pending_validation=true`, `confidence<1.0`, **quarantined**. NEVER canon. Reuses the C11 tagging + C12 canon-verify + C13 write-back path — this cycle adds the **generator strategy + licensing gate only**, not a new write path.
- **Output language = Chinese** (源文一致, 封神演义 tone). Model resolved via **provider-registry** (Qwen 3.6 / bge-m3) — **NO hardcoded model names**.
- **Acceptance gate:** `scripts/raid/verify-cycle-17.sh` exits 0 (created by this cycle's runner). It asserts: strategy registers, is **flag-default-OFF**, re-cooked facts carry H0 origin tags + `source_refs_json` to licensed sources, the eval-gate read blocks activation below threshold, and the licensing check rejects any non-licensed/non-public-domain source.

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C15, C16
- C15 ships the eval framework + gate (`scripts/enrichment_eval.py`, `eval/enrichment-eval-suite.toml`, `eval/baselines/`, `enrichment_eval_runs` persist, judge-ensemble). C17 **consumes** that gate. C16 ships the P2 fabrication strategy + the gate-aware activation guard pattern that C17 mirrors for re-cook. C15+C16 transitively guarantee C8 (strategy core/registry/feature-flags/cost-cap), C11 (origin tagging), C12 (canon-verify), C13/C14 (write-back + job runner) are DONE.
- Do not start C17 until CYCLE_LOG.md marks **C15 = DONE** and **C16 = DONE**.

## Scope (IN)
- New strategy class implementing the **C8 `EnrichmentStrategy` interface**: `app/strategies/recook.py` (mirror C9 template / C10 retrieval / C16 fabrication strategy shape).
- Register it in the C8 **strategy registry** under `technique='recook'`, behind a **feature flag default-OFF** (`ENRICHMENT_RECOOK_ENABLED=false`).
- **Re-cook contract:** take real, attributable reference material (history/news/encyclopedic text on the four locations 玉虛宮 / 碧遊宮·金鰲島 / 蓬萊 / 陳塘關 along 历史/地理/文化/features/inhabitants) and re-cast it into source-faithful 封神演义 lore. Output MUST cite the originating source in `source_refs_json` (source id + license tag).
- **Licensing gate (NEW, this cycle's distinguishing surface):** a `licensing_check` module that admits a source ONLY if its license is `public-domain` or an explicit `licensed` allowlist value. Anything else (`unknown`, `copyrighted`, `restricted`, missing license) → **rejected**, source excluded from corpus, re-cook of that source refused + escalated. License metadata travels with each source record; the check runs at corpus-admission AND at fact-emit (defence in depth).
- **Gate-aware activation:** a guard that reads the latest persisted `enrichment_eval_runs` / baseline-diff for `technique='recook'` and **refuses to mark the technique active** (and refuses job selection) unless the score clears the C15 threshold. Below threshold → inert + escalate. Activation requires eval-gate PASS **and** licensing-check PASS.
- Per-job **cost guardrail** integration: re-cook declares its cost estimate so the C8 cost-cap can pause/escalate.
- LLM + embedding access **only** via the C1 KG-read port / provider-registry-resolved client (model by id, tolerate JIT load latency).
- Unit tests: (a) registry selects recook when flag ON; (b) flag default-OFF → not selectable; (c) every re-cooked fact carries `origin='enriched'` + `technique='recook'` + `confidence<1.0` + `pending_validation=true`; (d) gate-guard blocks activation when eval below threshold; (e) licensing-check ADMITS public-domain/licensed and REJECTS unknown/copyrighted/missing-license; (f) re-cooked facts include `source_refs_json` with source id + license tag.
- `scripts/raid/verify-cycle-17.sh`.

## Scope (OUT — explicitly)
- **NOT** technique (c) fabrication (that is C16) or P1 template/retrieval (C9/C10).
- **NOT** a web crawler / internet search / live news fetch. The re-cook corpus is a curated, license-tagged input set; sourcing/crawling is out of scope (and would be a licensing liability). No langchain/llamaindex, no new RAG framework — retrieval reuses knowledge-service `/internal/embed` per C10.
- **NOT** a new write-back path, proposal store, or KG writer — reuse C11/C12/C13 unchanged.
- **NOT** editing the eval framework files (C15 owns `scripts/enrichment_eval.py`, `eval/enrichment-eval-suite.toml`, baselines). C17 only **reads** persisted results / calls the gate.
- **NOT** editing climate/geo eval files (`scripts/climate_eval.py`, geo `*-suite.toml`) — isolation locked.
- **NOT** modifying `world-service` / `game-server` / `tilemap` / `infra/existing-prod/`.
- **NOT** hardcoding model names or emitting English output.
- **NOT** flipping the flag ON in committed config — activation is gate-driven at runtime.

## Acceptance criteria (CI gates — exit code 0 = pass)
- `scripts/raid/verify-cycle-17.sh` exits 0.
- Unit suite green: registry select, flag-default-OFF, H0 tagging on every re-cooked fact, gate-guard blocks below threshold, **licensing-check admits licensed/public-domain only**, grounding `source_refs_json` (source id + license) present.
- **Eval clears:** the C15 eval read for `technique='recook'` clears the persisted baseline threshold (or activation stays inert + escalates).
- **Licensed sources only:** every source admitted into the re-cook corpus carries license ∈ {`public-domain`, `licensed`}; a fixture source with `unknown`/`copyrighted`/missing license is rejected (test-asserted).
- Grep gate: no hardcoded model-name literals in `app/strategies/recook.py` (model id comes from provider-registry/port).
- Isolation gate: `git diff --name-only` touches **no** C15 eval files, no climate/geo eval files, no `world-service`/`game-server`/`tilemap`/`infra/existing-prod/`.
- Flag-default-OFF asserted: with default config, recook is registered but **not** in the selectable-active set.
- **Cross-service: NO.** In-service (lore-enrichment-service only) — no live-smoke token required. If the runner discovers it must touch glossary/knowledge-service, STOP and reclassify (cross-service per CLAUDE.md VERIFY rule).

## DPS parallelism plan
- **DPS 2–3 (low, locked cost posture).** Small surface: one strategy file + licensing module + registry wiring + gate-guard + tests.
- Lane A: `app/strategies/recook.py` (re-cook generator + grounding prompt assembly from license-tagged sources, Chinese output).
- Lane B: `licensing_check` module + gate-guard (read `enrichment_eval_runs`, compare to baseline threshold) + registry/feature-flag wiring.
- Lane C: unit tests + `verify-cycle-17.sh`.
- Sync point: tests in C depend on A+B signatures — freeze the `EnrichmentStrategy` method signatures (inherited from C8) and the `licensing_check` interface before C lands.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **H0 leak:** can any re-cooked fact reach the KG/glossary as `source_type='glossary'` or `confidence=1.0`? Confirm every emitted fact is `origin='enriched'` + `technique='recook'` + quarantined + `confidence<1.0`. Re-cook ingests external text, so a tagging miss = third-party material entering as canon.
- **Licensing bypass:** is the licensing check truly enforced at BOTH corpus-admission and fact-emit? Try: source with missing license, `unknown`, `copyrighted`, `restricted` — re-cook must refuse and escalate, never silently include. Confirm the allowlist is conservative (default-deny), not an allow-by-absence.
- **Gate bypass:** is activation truly gated? Try: flag forced ON in config, missing/stale `enrichment_eval_runs`, eval row below threshold — recook must stay inert + escalate, never silently activate. Default-OFF must be the committed state.
- **Ungrounded / unattributed output:** does a re-cooked fact ever lack `source_refs_json` (source id + license)? Re-cook MUST be attributable to a specific licensed source; verbatim copying vs. transformative re-cook should be sane.
- **Hardcoded model name:** grep for any literal model id (`qwen...`, `bge-m3`, etc.) in the strategy — must resolve via provider-registry/port.
- **Scope creep:** any web crawler / live news fetch / internet search = wrong scope (licensing liability). Any fabrication (C16) or template/retrieval (C9/C10) logic = wrong cycle.
- **Eval-file mutation / isolation:** confirm no edits to C15 eval files, climate/geo eval, world-service/game-server, infra/existing-prod.
- **Output language:** confirm prompts/output are Chinese, not English.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
CLEAR only if ALL hold:
- Diff limited to lore-enrichment-service strategy/licensing/registry/gate-guard/tests + `scripts/raid/verify-cycle-17.sh`.
- Licensing check is default-deny; only `public-domain`/`licensed` sources admitted (test-asserted reject of unknown/copyrighted/missing).
- No new write path; reuses C11/C12/C13. No web crawler / internet fetch.
- No edits to eval files (C15), climate/geo eval, world-service, game-server, tilemap, infra/existing-prod.
- Feature flag default-OFF committed; activation gate-driven (eval + licensing).
- No hardcoded model names; Chinese output.
- `scripts/raid/verify-cycle-17.sh` exits 0.
Else BLOCKED with the offending file/line.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- `docs/plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md` — C17 row + C15 gate + cost-discipline note (P1 → P2 → P3; gate must exist before re-cook; {C16,C17} after C15).
- `docs/plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md` — H0 invariant; Q-R2 (phased P1→P2→P3, gate promotes each tier); execution decisions (Chinese output, provider-registry models, eval auto-blocks tier on failure + escalates).
- `docs/03_planning/lore-enrichment/PLAN.md` — strategy/technique architecture, re-cook tier + cost posture.
- `docs/03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md` — code-verified seams (strategy interface, eval framework, provider-registry, knowledge-service `/internal/embed`).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **H0 (CORE):** every re-cooked fact = `origin='enriched'` + `technique='recook'` (`source_type='enriched:recook'`) + `pending_validation=true` + `confidence<1.0`, quarantined. NEVER canon. Only the author's explicit promote canonizes — and the permanent origin marker survives promotion. Re-cook ingests external text, so a tagging miss admits third-party material as canon — the single worst failure here.
- 🔴 **Two gates LOCKED:** re-cook ships **flag-default-OFF** and activates ONLY when (1) `scripts/enrichment_eval.py` (C15) shows it clears threshold vs baseline AND (2) the **licensing check passes — licensed / public-domain sources ONLY** (default-deny; reject unknown/copyrighted/missing). No re-cook run before the gates pass; below threshold or unlicensed → inert + escalate. **Acceptance gate = `scripts/raid/verify-cycle-17.sh` exits 0.**
- 🔴 **DO NOT TOUCH:** C15 eval files / climate-geo eval files / `world-service` / `game-server` / `tilemap` / `infra/existing-prod/`. No new write path (reuse C11/C12/C13). No web crawler / internet search. No hardcoded model names (provider-registry only). Output = Chinese. In-service only — no cross-service edits (would force reclassify + live-smoke).
