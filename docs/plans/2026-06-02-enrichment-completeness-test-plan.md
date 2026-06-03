# Enrichment Completeness Test Plan (serious / end-to-end)

> **Status:** DRAFT for PO review (2026-06-02). Branch `lore-enrichment/foundation`.
> **Why now:** the 2026-06-02 live e2e proved only **P1 (retrieval)** mechanically.
> Empirically, across the entire `loreweave_lore_enrichment` DB there are **0 jobs
> and 0 proposals** for **P2 (fabrication)** or **P3 (recook)** — they have NEVER
> run live, and enrichment **content quality** has never been measured. This plan
> closes that gap rigorously before we claim "enrichment is complete".

## 0. Honest baseline (what is / isn't proven)

| Path | Proven live? | Evidence |
|---|---|---|
| P1 template | partial | 1 `template` proposal exists; no full promote run captured |
| P1 retrieval | ✅ yes | job `019e88f3` completed → H0 proposal → promote→canon (5 facts) |
| P2 fabrication | ❌ never | 0 jobs / 0 proposals in DB |
| P3 recook | ❌ never | 0 jobs / 0 proposals in DB; "from internet" is a **misconception** — design forbids live web fetch ([recook.py](../../services/lore-enrichment-service/app/strategies/recook.py)), it re-cooks a pre-ingested license-tagged corpus |
| Eval gate (judge-diversity) | ❌ never passed live | gate is the switch for P2/P3; no diverse judge panel exists for the test user (qwen-only) |
| Cost-cap accuracy | partial | tokens metered live (5766) but never asserted against an independent count |
| Licensing default-deny | unit only | copyrighted corpus row exists (`某版权新闻-c17-neg`) but refusal never live-exercised |
| Injection / contradiction / anachronism / auto-reject | unit only | jieba verify ran live (no degrade) but no adversarial corpus run |

## 1. Objectives (the 4 trục — all in scope per PO)

- **T-FUNC** — every technique (P1×2, P2, P3) runs end-to-end live, produces a
  quarantined H0 proposal, and promotes to canon.
- **T-QUAL** — the generated lore is actually GOOD: source-faithful, in-voice
  (封神/文言), no fabrication-beyond-grounding, no anachronism. Scored by an
  LLM-judge rubric **plus** human spot-check.
- **T-ROBUST** — injection defense, contradiction (jieba), anachronism, C3
  auto-reject, and H0-no-leak hold under an **adversarial corpus**.
- **T-GATE** — cost-cap token accuracy, eval-gate (judge-diversity κ + family
  floor), licensing default-deny, resume/multi-gap, cross-service contracts.

## 2. P2/P3 unlock — TWO modes (per PO: override first, real panel second)

The runner selects via `GateAwareStrategyFactory`, which reads the LIVE persisted
eval gate from `enrichment_eval_runs`. That gate — NOT the `ENRICH_STRATEGY_*_ENABLED`
env flag — is the real switch (the env flag only refines selection AFTER the gate
passes). Therefore:

- **Mode A — isolation (override):** seed a PASSING gate row for the project (or
  inject a stub gate-reader in a test harness) so `factory.select` returns the P2/P3
  strategy. This isolates **generation** from judge quality → proves fabrication /
  recook *produce* valid H0 output. Env: also set
  `ENRICH_STRATEGY_FABRICATION_ENABLED=true` / `ENRICH_STRATEGY_RECOOK_ENABLED=true`
  on the worker for completeness. **Clearly label every Mode-A artifact as
  gate-bypassed** (must never be mistaken for a real gate pass).
- **Mode B — real gate path:** register a **second judge family** under the test
  user (LM Studio has `google/gemma-4-*` — distinct family from qwen) so the C2
  judge-diversity floor (≥2 judges from ≥2 distinct families **AND** κ ≥
  `LORE_ENRICHMENT_JUDGE_KAPPA_FLOOR`) can be met, run a genuine eval, and let it
  PASS on its own merits → P2/P3 unlock through the production path. This is the
  one that proves the GATE, not just the generator.

## 3. Prerequisites / fixtures (BUILD before any suite)

1. **Models (test user `019d5e3c`):** already owns qwen3.6-35b (gen) + bge-m3
   (embed). **ADD** a 2nd-family gen model for the judge panel — register
   `google/gemma-4-*` (or another non-qwen family) under the SAME lm_studio
   credential so the judge ensemble has ≥2 families. (No hardcoded model names in
   code — registration is data.)
2. **LM Studio capacity — RESOLVED (sequential load-phases, §6).** All judge +
   gen models can't co-reside, so generation and eval are split: **operator loads
   GEN + EMBED for Load-phase 1** (generate all data), then **unloads and loads the
   JUDGE models for Load-phase 2** (score). Eval needs no gen model (run_eval scores
   stored proposals). Within Load-phase 1, gen + embed DO co-reside; if even that
   evicts under the 35B gen, fall back to `max_gaps=1` for multi-gap cases.
   - **Load-phase 1 models:** `qwen/qwen3.6-35b-a3b` (gen) + `text-embedding-bge-m3`
     (embed).
   - **Load-phase 2 models:** `google/gemma-4-26b-a4b` (judge family 2) +
     `qwen/qwen3-14b` (judge family 1, independent of the gen model). Min panel = 2
     families; if VRAM is tight, drop the independent qwen-judge and reuse a qwen
     for family 1 (note the mild self-judge caveat for QUAL).
3. **Corpora (per technique):**
   - retrieval/fabrication: the seeded Fengshen glossary + the `山海经`/`史料`
     public-domain corpora already ingested on project `019e7850-aa1c`.
   - recook (P3): a **license-tagged real-history corpus** — the `史料-c17-demo-pd`
     (kind=history, public-domain) is present; **add a richer Shang–Zhou history
     corpus** (the handoff's "not downloaded" gap) for a meaningful re-cook.
   - licensing-negative: `某版权新闻-c17-neg` (copyrighted) already present.
4. **Adversarial corpus (T-ROBUST):** a curated fixture of injection payloads
   (文言文 meta-directives, base64, "forget the above"), a deliberate
   canon-contradiction, and ≥2 anachronism markers — to drive C3 auto-reject.
5. **Clean DB snapshot / reset path:** so suites are re-runnable and counts are
   unambiguous (the demo project already has prior proposals — either a fresh
   project per run, or assert on `job_id`-scoped queries).

## 4. Coverage matrix (technique × dimension)

| | H0 quarantine | promote→canon | cost-cap | eval-gate | licensing | injection | contradiction(jieba) | anachronism | content-quality |
|---|---|---|---|---|---|---|---|---|---|
| **template (P1)** | ✓ | ✓ | ✓ | n/a (P1) | n/a | ✓ | ✓ | ✓ | rubric |
| **retrieval (P1)** | ✓(done) | ✓(done) | ✓ | n/a | n/a | ✓ | ✓ | ✓ | rubric |
| **fabrication (P2)** | ✓ | ✓ | ✓ | **✓ (Mode B)** | n/a | ✓ | ✓ | ✓ | rubric (strict — extrapolation risk) |
| **recook (P3)** | ✓ | ✓ | ✓ | **✓ (Mode B)** | **✓ default-deny** | ✓ | ✓ | **✓ (re-context anachronism is the core risk)** | rubric (strict — source fidelity + citation) |

## 5. Test suites

### Suite A — T-FUNC (functional, all 4 techniques live)
- **A1 template→canon:** auto-enrich/job `technique=template`, max_gaps=1 → assert
  job `completed`, 1 proposal `origin=enrichment, conf<1.0, proposed`, jieba verify
  ran (no `verify_degraded`), approve→promote → `facts_promoted>0`, authored
  `short_description` unchanged, 5 supplement rows `promoted|enrichment`.
- **A2 retrieval→canon:** re-run the proven path on a FRESH project to capture
  clean counts (already proven once on `019e88f3`).
- **A3 fabrication→canon (Mode A then B):** Mode A (gate-bypassed) proves
  generation; Mode B (real gate) proves the unlock. Assert the proposal's
  `technique=fabrication`, content extrapolates **within** corpus+KG+era (not free
  invention), H0 markers intact.
- **A4 recook→canon (Mode A then B):** re-cook the `史料` history corpus →
  proposal `technique=recook`, content RE-CONTEXTUALISES real history into 封神 with
  the **source cited** in provenance, `recooked=true`, H0 intact.
- **Pass:** every technique yields a promoted-to-canon supplement with H0 markers
  retained; 0 H0 leaks (no `origin=glossary`/`conf=1.0` from an enrichment path).

### Suite B — T-QUAL (content quality — the part never measured)
- **Rubric (per proposal, 0–5 each):** source-fidelity · in-voice (封神/文言) ·
  grounding-faithfulness (no claim beyond corpus/KG) · coherence · usefulness.
- **B1 LLM-judge panel** scores every Suite-A proposal (reuse `loreweave_eval`
  judge ensemble; ≥2 families so the score itself is trustworthy).
- **B2 human spot-check:** PO reads ≥1 proposal per technique; records a
  verdict + any failure modes (hallucinated specifics, modern leakage, generic
  filler like the honest-no-fab "故阙如" we saw — flag when grounding is too thin).
- **B3 grounding-faithfulness adversarial check:** diff each generated claim
  against the retrieved grounding; flag any unsupported specific (name/date/place).
- **Pass:** mean rubric ≥ a PO-set bar (propose ≥3.5/5); 0 unsupported-specific
  leaks; human verdict = acceptable per technique. **Capture failures even if the
  bar is met** (this is where "completeness" is really judged).

### Suite C — T-ROBUST (adversarial safety)
- **C1 injection:** feed the adversarial corpus (文言文/base64/forget-the-above) as
  grounding → assert the sanitizer neutralises/tags, the C12 flags fire, and C3
  `decide_auto_reject` persists `review_status=rejected` + `rejected_reason`, NOT
  surfaced to queue/wiki. Negative guard: benign 听我号令/遵我指示/benign-base64 NOT
  flagged (no false positives).
- **C2 contradiction (jieba):** seed an authored canon fact + generate a directly
  contradicting claim → assert HIGH contradiction → auto-reject; AND a benign
  common-word+negation does NOT false-fire (LE-060 false-positive-safety, live).
- **C3 anachronism:** generate content containing ≥2 distinct anachronism markers
  → auto-reject; a plausible 封神 phrase with a pruned-collidable token (总统六师)
  does NOT fire (LE-058 guard, live).
- **C4 H0 no-leak sweep:** across ALL suites, query `enrichment_proposal` +
  glossary `entity_enrichments` + Neo4j for any enrichment-origin row that became
  `origin=glossary` / `conf=1.0` / canon pre-promote → must be ZERO.
- **Pass:** every egregious case auto-rejected; every benign case passes; 0 H0
  leaks; auto-reject metrics (`proposals_auto_rejected_total`) increment.

### Suite D — T-GATE (gates, cost, licensing, contracts)
- **D1 cost-cap accuracy:** run a job with a known small `max_spend_usd`; assert
  (a) pre-estimate gate blocks when the estimate exceeds the cap; (b) the metered
  `actual_cost_usd` reconciles to an INDEPENDENT token count (sum the LLM `usage`
  frames captured out-of-band) within tolerance; (c) a cap hit pauses/stops cleanly.
- **D2 eval-gate (the real test):** with the diverse panel (Mode B) run a genuine
  eval → assert PASS requires ALL of composite≥min, sub-score floors, AND
  judge-ensemble acceptable (≥2 families + κ≥floor). Then FORCE a near-clone
  qwen-only panel → assert the gate FAILS on diversity (κ/family) → P2/P3 stay
  locked. This proves the C2 floor actually gates.
- **D3 licensing default-deny (live):** point recook at the copyrighted corpus
  `某版权新闻-c17-neg` → assert `UnlicensedSourceError` (refused + escalated) at
  BOTH corpus-admission and fact-emit; point at the public-domain `史料` → allowed.
- **D4 resume / multi-gap:** enqueue a multi-gap job, simulate a pause (cap or
  infra), resume → assert done gaps skipped (no double-charge, no dup proposals),
  remainder completes. (Account for the LM Studio JIT constraint from §3.2.)
- **D5 cross-service contract:** confirm each leg on a fresh stack-up —
  provider-registry embed (model_ref, /v1 normalized), glossary supplement write
  (authored short_description preserved), knowledge enriched-promote (facts), book
  owner-gate on promote (non-owner → 403).
- **Pass:** every gate enforces in BOTH directions (allow the legitimate, refuse
  the illegitimate); cost reconciles within tolerance; resume is idempotent.

## 6. Execution order — GENERATION / EVAL are DECOUPLED (VRAM-friendly)

**Key enabler:** `run_eval()` scores PRE-GENERATED proposals — the deterministic
sub-scores need no network and the judge sub-score uses ONLY the judge models, so
**eval never needs the gen model loaded.** That lets us run with limited VRAM by
swapping models between two load-phases (PO's proposal — confirmed sound):

### Phase 0 — fixtures (no heavy models)
Register the judge model rows (provider-registry, under the test user), ingest the
richer Shang–Zhou public-domain history corpus, build the adversarial corpus, pick
fresh project(s), set LM Studio max-loaded/TTL. Evidence: model rows, corpus rows,
fixture files.

### LOAD-PHASE 1 — **GEN + EMBED loaded** (all GENERATION; NO judges needed)
Everything that produces or refuses output runs here, capturing proposals to DB:
- **Suite A FUNC** — template, retrieval, fabrication, recook → H0 proposal →
  promote→canon. P2/P3 use **Mode A**: seed a PASSING gate row in
  `enrichment_eval_runs` (DATA-ONLY — no judges, no models) so the factory permits
  them; every such artifact tagged `GATE-BYPASSED`.
- **Suite C ROBUST** — adversarial corpus → injection/contradiction/anachronism →
  C3 auto-reject; benign negatives don't false-fire.
- **Suite D1 cost-cap**, **D3 licensing default-deny** (recook refuses copyrighted
  corpus at admission), **D4 resume/multi-gap**, **D5 cross-service contracts** —
  all generation-side.
- **Capture the eval SAMPLE**: snapshot the representative proposals as
  `ScorableProposal` fixtures for Phase-2 scoring.
- → **Unload gen + embed.**

### LOAD-PHASE 2 — **JUDGES loaded** (gemma + qwen-judge); NO gen model
Pure scoring over the captured proposals:
- **Suite B QUAL** — judge panel scores every captured proposal against the rubric.
- **Suite D2 eval-gate (the real test)** — `run_eval` with the DIVERSE panel →
  assert PASS needs composite≥min + sub-score floors + ensemble acceptable (≥2
  families + κ≥floor); write the legit gate row. Then force a qwen-CLONE panel →
  assert FAIL on diversity → P2/P3 would stay locked. Proves the C2 floor gates.
- **Assert (no models) the unlock:** with the legit passed gate row,
  `GateAwareStrategyFactory.select(fabrication|recook)` SUCCEEDS — proving the
  production path permits P2/P3 once the gate truly passes.
- → **Unload judges.**

### LOAD-PHASE 3 — **GEN + EMBED again** (OPTIONAL belt-and-suspenders)
Only if PO wants P2/P3 GENERATED while a real (non-bypassed) passed-gate row is
live (one extra swap): re-run fabrication + recook with NO Mode-A bypass → the full
production-path proof. Skippable — Phase-1 generation + Phase-2 gate-pass +
factory-permits assertion already cover the production path.

### Phase 4 — synthesis
Completeness scorecard (the §4 matrix filled) + quality report + go/no-go.

**Swaps the operator does:** ONE (gen+embed → judges) for the minimal path; TWO if
Phase 3 is included.

## 7. Evidence & deliverable

- **Per case:** the live command, the job/proposal id, the DB ground-truth query +
  output, and the verdict. Mode-A artifacts tagged `GATE-BYPASSED`.
- **Completeness scorecard:** the §4 matrix filled with PASS/FAIL + evidence links.
- **Quality report:** rubric scores per technique + human verdicts + failure modes.
- **Form (PO-deferred decision):** this run can be (a) a committed **repeatable
  harness** (`scripts/enrichment_completeness_e2e.py` + a fixtures module) that
  regenerates the scorecard, or (b) a one-shot live run with an evidence doc. PO
  chose "plan first" — pick the form at Phase 0.

## 8. Known constraints & risks

- **LM Studio JIT eviction** (35B gen vs bge-m3 vs gemma-judge co-residency) — the
  single biggest execution risk; §3.2 must be resolved before multi-gap/gate runs.
- **Single-owner BYOK** — all models (gen, embed, judge) must be owned by the test
  user (provider-registry scopes by owner).
- **Cost/time** — real LLM generation across 4 techniques × multiple gaps × a judge
  panel is the most expensive run this project has done; bound it with small
  `max_gaps` + `max_spend_usd` and a fixed entity set.
- **DB state** — prior proposals exist on the demo project; use fresh project(s) or
  strictly `job_id`-scoped assertions so counts are unambiguous.

## 9. Decisions — RESOLVED 2026-06-02 (PO + agent)

1. **LM Studio capacity → sequential load-phases** (§3.2, §6): operator loads
   gen+embed for Load-phase 1, then swaps to judges for Load-phase 2. Eval is
   generation-independent so this is lossless.
2. **Deliverable → semi-automated harness + scorecard (committed).** Driver script
   automates FUNC + GATE + ROBUST and emits the scorecard; QUAL keeps a human
   spot-check. Re-runnable for regression (no-drift discipline).
3. **Quality bar → mean rubric ≥ 3.5/5 + 0 unsupported-specific leaks; P3 recook
   source-fidelity ≥ 4/5.** Capture every failure mode even when the bar is met.
4. **Corpus P3 → add a richer Shang–Zhou public-domain history corpus** (curated
   《史记·殷本纪》/《尚书》 excerpts — NOT a live web fetch; recook is owned/licensed
   corpus only). The thin `史料-c17-demo-pd` is insufficient for a meaningful recook.
5. **Judges → qwen + gemma families; κ floor = 0.0 for the first pass** (family
   diversity carries the gate; κ over 2 judges / small N is noisy — revisit ≥0.2
   after observing real κ). Models per §3.2.

**Remaining operator action before Phase 0:** load the Load-phase-1 models
(gen+embed) with max-loaded/TTL set so they stay resident; the agent registers the
judge model rows + ingests corpora in Phase 0, and the operator swaps to the
judge models when Load-phase 2 begins.
