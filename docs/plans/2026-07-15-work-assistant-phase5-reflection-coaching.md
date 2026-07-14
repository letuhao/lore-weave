# Work Assistant — Phase 5 (Reflection + Coaching) — ready-to-build plan

**Date:** 2026-07-15 · **Track:** Work Assistant · **Phase:** 5 · **Status:** PLAN (sealed, pre-build) ·
**Spec:** [`08-coaching-reflection.md`](../specs/2026-07-11-work-assistant-mode/08-coaching-reflection.md) (v2 — v1 red-teamed and FAILED) ·
**Sealed decisions:** [`2026-07-15-phase-345-clean-seal.md`](2026-07-15-phase-345-clean-seal.md) §3 P5-D1..12 ·
**Scope (SD-2):** build the FULL feature — ungated reflection AND all 4 coaching gates.

> **The one-line thesis the spec earns:** *"deterministic detectors are the backbone; the LLM never
> originates a pattern"* only holds if the data to run those detectors EXISTS. v1's fatal bug was designing
> an engine with no fuel (3 of 4 detectors had no substrate). This plan builds the substrate FIRST, then the
> engine, then — behind a real safety layer + a real eval bar — the scorer.

---

## 0. The three things (conflating them is the first bug — Q1/R1)

| | What | Truth requirement | Ships |
|---|---|---|---|
| **Recall** | "What happened Tuesday?" | The user's record | already (WS-2.4) |
| **Reflection** | We *scaffold* meaning-making with good questions | **None** — the user is the sole authority on their experience | **A (ungated)** |
| **Coaching** | An external standard is applied → assessment | **High** — needs a versioned rubric, evidence, citations, a safe judge | **B (gated behind 4 prereqs — all in-scope)** |

Most AI coaches fail by doing **coaching** with **reflection**'s rigor. This plan refuses to.

---

> ⚠️ **REVIEW-PATCHED 2026-07-15** (cold review R4 — see [`2026-07-15-phase-345-clean-seal.md`](2026-07-15-phase-345-clean-seal.md) §7). Load-bearing changes: **Gate 1 collapses to `due_date` + an overdue detector, reusing the WS-2.6b supersession primitive** (no new identity model); adding a `commitment` fact type touches **3 type registries** (500-at-merge if missed); **Gate 2 needs a single-model degraded path** (else it silently refuses ALL scoring); **Gate 3 safety + Gate 4 eval CANNOT be cleared inside a code run** — the run builds the mechanism/harness, clearance is a human-rating milestone; the **safety floor is deterministic** (X-5); the safety classifier ALSO gates the reflection pattern-surfacing (X-2), not just the scorer.

## A · REFLECTION (ungated — the honest value, no truth guarantee needed)

### A1 · Substrate the reflection engine needs (Q3 — "does the data exist?")

| Detector | Substrate | Verdict → action |
|---|---|---|
| Entity co-occurrence | `chapter_entity_links` self-join + `(:Fact)-[:ABOUT]->(:Entity)` | ✅ feasible today |
| Journaling gaps | `chapters.entry_date` | ✅ feasible today (+ away-marker exclusion, Phase-3 P3-D4) |
| Unresolved-thread age | no thread entity / status anywhere | ❌ build in B (schema) |
| Commitment slippage | `commitment` not a fact type; no due-date; content-keyed id can't track a moved date | ❌ build in B (schema) |
| Recurring L3 themes | **no `reflection_notes` table** (verified: zero `went_well`/`to_improve` hits repo-wide) | ❌ **build in A** (it has no home; reflection needs it) |

### A2 · Reflection slice board

| Slice | Scope | Notes |
|---|---|---|
| **WS-5.1** | `reflection_notes` table (`owner_user_id, entry_date, went_well, to_improve`) + end-of-day capture wiring | L3 has no home today; this is the reflection substrate. Owner-scoped. |
| **WS-5.2** | Journaling-gap + co-occurrence surfacing (the 2 detectors that HAVE substrate) | Deterministic; emit candidates **with evidence refs**; no refs ⇒ dropped. Away-marker excludes declared-away days. |
| **WS-5.3** | Reflection scaffolding (Socratic prompts) + the weekly reflection DRAFT | Pull-only draft for v1 (P3-D3); descriptive only — NOT a score. An empty week is a valid, good output. |
| **WS-5.4** | `assistant.coaching_enabled` setting (default OFF, P5-D10) + i18n | The switch v1 lacked; a user who wants the diary but not to be judged needs the way out. Rubric anchors/OIS/prompts resolve the user's language. |
| **WS-5.5** | Closed-detector-enum guard | `reflection_patterns.detector_code` = closed enum; the phrasing LLM's output is **rejected** if it names a pattern whose code isn't in the candidate set it was handed (P5-D3). Enforcement, not a prompt — with a test. |
| **WS-5.6** | Tombstone on a **period-independent `pattern_key`** | `UNIQUE(owner_user_id, pattern_key) WHERE status='dismissed'`, checked **at detection time** (drop before the LLM), not at render — else the same pattern resurfaces each period as a new row (Q5). |

**Reflection needs NO truth guarantee** — it surfaces what the user reported, phrased as such ("you **mentioned**…", never "you **are**…", R2), dismissible, never shared (tenancy law). This is where the honest value is.

---

## B · COACHING (the 4 gates — ALL in-scope per SD-2)

Coaching applies an external standard → it needs a standard (data), evidence, an honest judge, and a safety net. Build the 4 gates, THEN the scorer — the scorer ships **quarantine-tier** (shown, never trended) until the eval bar clears.

### Gate 1 — the commitment/thread SCHEMA (R3) — SIMPLIFIED by reusing WS-2.6b

**⚠️ Re-scoped (R4-M1): the "stable `commitment_id` + slippage history" identity model is NOT needed — WS-2.6b already tracks a claim whose value changed over time.** The spec's premise ("content-keyed `fact_id` breaks on a moved date") only holds if the date is embedded in the content string — a design choice, not a constraint.

| Deliverable | Shape | Why |
|---|---|---|
| **WS-5.7** commitment = `due_date` + reuse | Model a commitment as `content="ship the report"` (**date-free**) + a `due_date` node property + the **existing WS-2.6b s/p/o trio** (`predicate="due"`, `object=<date>`). The content-keyed `fact_id` is then **naturally stable** across date moves (MERGE updates the property), and **`group_supersessions()` (`facts.py`) ALREADY turns Friday→Tuesday→next-week into an ordered slippage chain**. So Gate 1 = a `due_date` field + an **overdue-vs-now detector** — small. **Adding a `commitment` fact type touches 3 registries (R4-M2): the `FactType` Literal (`facts.py:63` — else 500 at `merge_fact`), the `knowledge_pending_facts` CHECK ×2 (`migrate.py:732,746`), and (decide) the `kg_fact_types` ontology.** Seal: `commitment` is a hardcoded Literal member (matches the closed set; the write path validates the Literal, not the table). | reuses the primitive shipped in WS-2.6b; no parallel identity model. |
| **WS-5.8** thread/open-item | a thread entity with `open|resolved` status (buildable on the existing `:Entity` model) | unresolved-thread-age has no substrate today. |
| **WS-5.9** maintain_chain guard | ✅ **Already upheld on the diary path** (`pending_facts.py:172` passes `maintain_chain=False`, citing spec 07 §Q2). The gap: the **NEW commitment/thread writers (WS-5.7/5.8) must ALSO pass `False`** — extend the test to them, don't just re-test the diary path. | the (subject, fact_type) chain scope would collapse every `decision` about Alice into one — not live today, but the new writers must not reintroduce it. |

### Gate 2 — judge ≠ actor (Q6)

**WS-5.10.** Today **`routers/evaluate.py:149`** (the ROUTER, not `services/evaluate.py`) reads `model_source`/`model_ref` **straight off the `chat_sessions` row** — *the model that played the roleplay partner scores its own performance.* `ModelRole.CRITIC` exists (`settings_resolution.py:39`) but `evaluate.py` **has never used it**. Fix: resolve the judge via `resolve_model_role(ModelRole.CRITIC, …)` and **assert `judge_model_ref != session.model_ref` — refuse to score if equal**, with a test. (`temperature=0.0` at `:109` is already correct.)

**⚠️ The single-model hole (R4-H3, MUST fix):** `account_capability_for(CRITIC)` falls back to the `chat` capability, and the common config has an **empty `user_default_models`** — so for a single-model user the critic resolves to the SAME model → assert-equal → **"refuse to score" refuses EVERYTHING** (the silent-universal-refusal bug). Add an explicit degraded path: **hard-require a distinct critic** and surface a *"configure a second model for coaching"* message (do NOT silently refuse), OR allow same-model scoring **with a disclosed self-preference caveat**. Sealed choice: **require-a-distinct-critic + the actionable message** (coaching is off-by-default and token-spending; asking for a second model at opt-in is honest).

### Gate 3 — the platform SAFETY layer (R8) — the repo has NOTHING here

Verified: `self-harm|suicid|crisis|distress|safeguard|helpline` → **zero** substantive hits across `services/` and `docs/standards/`. This is the first feature that reads a person's emotional life. A non-goal is not a control.

**⚠️ Mechanism + placement + honesty (R4-H2, the riskiest slice — do NOT enter BUILD at intent-altitude):**
- **Mechanism (X-5, SEALED):** a **deterministic fail-closed FLOOR** — a curated distress/harassment/self-harm lexicon PLUS paraphrase patterns (the spec's own example *"I don't know how much longer I can do this"* contains NONE of the obvious keywords, so a bare keyword list fails open exactly where it must not). An LLM classifier MAY run on top to **widen** the net; it may **never narrow** the floor. A $0 quantized model is never the sole gate (it "can contradict its own reasoning" — the repo's canon-check finding).
- **Placement — TWO nodes, not one:** (1) BEFORE the weekly reflection **pattern-surfacing** step (WS-5.2/5.3 — X-2: the reflection draft carries emotional content, so it's gated too, not only the scorer), short-circuit fail-closed; (2) at **practice source-material / practice-start** (WS-5.13 — a different pipeline), refuse to roleplay a disclosed abuse scenario.
- **Cannot self-certify (X-4):** the **safety eval set (WS-5.15) needs human-labeled distress data** — a build agent CANNOT mark safety "passing" from a self-run. The code run builds the classifier + the short-circuit + the eval HARNESS; the eval **clears only in a human-rating milestone**.

| Slice | Scope |
|---|---|
| **WS-5.11** | A **safety classifier** runs BEFORE any pattern is surfaced. On a trip (distress / harassment-or-abuse disclosure / self-harm indicators) the weekly pipeline **short-circuits**: no patterns, no OIS, no score. **Fail closed** (reuse D7). |
| **WS-5.12** | On a trip, surface a plain, non-clinical, non-judgmental acknowledgement + locale-appropriate resources — **once**, dismissible, never repeated, **never written into the KG as a fact about the user**. |
| **WS-5.13** | **Never roleplay a disclosed harassment/abuse scenario** — practice templates refuse when the classifier trips on the source material. |
| **WS-5.14** | A **deny-list guard on the phrasing step's output** for clinical/diagnostic vocabulary — a pattern whose text trips it is **dropped, not softened**. |
| **WS-5.15** | A **safety eval set** (distress diaries) asserting short-circuit behavior — **a release gate**. More load-bearing than any accuracy number. |

### Gate 4 — the numeric EVAL bar (Q9) — v1's 93.75% was retracted by our own repo

The repo's own canon-check eval withdrew a 93.75% point-estimate that re-ran at **68.75% / 33% recall**, and concluded: *report a RANGE from repeated runs, not a point estimate.* Adopt it:

**⚠️ CANNOT be cleared in a code run (R4-H1 / X-4 — the single sharpest risk in this plan):** WS-5.17/5.18/5.19 demand **N≥50 transcripts × ≥2 independent HUMAN raters × QWK vs consensus** + a hand-labeled precision set. **No code produces human annotations.** A build agent handed "WS-5.18: gate QWK≥X" will do exactly what the retracted-93.75% failure did — **fabricate a point number from a single self-run.** So each eval slice is split: **(a) buildable now** = the eval harness, the fixture/labeling scaffold, the QWK computation; **(b) NOT code** = the human-rating pass that produces the number. **The numeric gate may NOT be marked cleared inside a code run**, and no QWK sourced from a self-run may be committed. The scorer ships **quarantine-tier and stays there until the human pass runs** (§F).

| Slice | Scope |
|---|---|
| **WS-5.16** | **Range over ≥3 runs**, never a point estimate. |
| **WS-5.17** | The right instrument is **inter-rater reliability**: ≥2 independent human raters, human–human agreement (Krippendorff's α / QWK) as the **ceiling**, LLM-judge compared to the human **consensus** — not one annotator. (Canon-check's binary/objective precedent does NOT transfer to a multi-dimensional ordinal subjective rubric.) |
| **WS-5.18** | **Numeric gate:** N ≥ 50 transcripts · ≥2 raters · LLM-judge **QWK ≥ X** vs consensus. **Until it clears, scores are `quarantine`-tier: shown, never trended.** A weak/local judge ⇒ **NO score, not a noisy score.** |
| **WS-5.19** | **Dismiss-rate is NOT a validity metric** (P5-D8) — it selects for flattery. Demote to an operational self-disarm signal (threshold P5-D11: dismiss-rate > 0.6 over ≥5). Quality = **precision against a hand-labeled set** (is the observation true given its refs?). Split the user signal into 3 questions: accurate? / useful? / dismiss. |

### The scorer (only after the 4 gates)

| Slice | Scope |
|---|---|
| **WS-5.20** | `coaching_rubrics` (`code, version, dimensions[] (anchors 1-5), source_citation, license, tier`) **replacing** the free-form `SessionTemplate.rubric` (today `dict[str,Any]`, no schema/version — "improvised standards already ship", contradicting Q10). A coach session with **no resolvable System-tier rubric refuses to score** (P5-D5). |
| **WS-5.21** | `Scorecard` **generalization** — interview-shaped in **~4-6 sites** (R4-M3), not "a model change": the named fields `star_coverage/clarity/filler` (`models.py:141`), `coerce_scorecard` (`evaluate.py:181`), the `EVALUATOR_SYSTEM_PROMPT` STAR text (`evaluate.py:32`), `render_summary_text` (`evaluate.py:206`), `EvaluateResponse`, + the FE renderer. Generalizing to N dimensions stays safe ONLY if the dimensions become **server-authoritative from `coaching_rubrics`** (`coerce_scorecard`'s safe-when-wrong guarantee is anchored to a fixed server-side checklist). The scored subject is **always `role='user'`**, enforced in `coerce_scorecard`. |
| **WS-5.22** | The pipeline (once gated): **Aggregate** → **Detect** (deterministic, evidence refs, no refs ⇒ drop) → **Phrase** (LLM writes Observation→Impact→Suggestion, may not invent, carries refs, checked against the closed detector enum) → **Bound** (≤2/week). **Plus a real `quarantine` tier (R4-M4):** canon-check's quarantine is FACT-validation — there is **no tier flag on `Scorecard`/`chat_outputs`** today. Add a `quarantine` column + the FE gate that shows a score but **excludes it from any trend** until Gate 4 clears (net-new plumbing, not reuse). |
| **WS-5.23** | Coaching KB = a `kind='lore'` book, chapters = curated **cited** frameworks, indexed via publish-independent-kg-indexing → cited retrieval is free existing infra. Each cited reference must **individually resolve** before sign-off (Q4 R3-cite); any that doesn't → dropped. |

---

## C · LONGITUDINAL (P5-internal — after the eval gate)

**WS-5.24.** Trends only AFTER the numeric gate clears; add the `(user_id, type)` index (`list_facts_by_type` is a full label scan today, sized for a novel not 3 years of work facts); every longitudinal query **date-windowed**.

---

## D · Privacy + retention (fold with the PRE-P3 wiki fix)

The R5/R6/R7 wiki/entity guards are pulled to the **pre-Phase-3 security slice** (SD-1, see the master doc §2). Phase 5 additionally:
- **P5-D7 retention:** coach transcripts + scorecards + `reflection_patterns` **added to the erasure copy-set** (the most sensitive artifacts).
- **R7 (also in the pre-P3 fix):** no `preference`-type facts about third parties — restricted to `statement` (what the user reports X said, on a date), enforced in `pass2_writer.py`.

---

## E · Non-goals (Q10, LOCKED)

Diagnosing mental health / personality / performance-rating · assessing real, unobserved meetings (R2 — we weren't there) · cross-user comparison or manager/HR visibility · improvised standards (no rubric ⇒ no score) · inferred trait/behavioral facts about a third party · any derived profile artifact about anyone other than the user.

---

## F · Build order within Phase 5

```
A1 reflection_notes (own notes, no detectors — safe)
   │
   ▼
Gate 3 SAFETY FLOOR (deterministic) ──┐  (X-2: the safety floor gates pattern-surfacing,
   │                                   │   so it comes BEFORE the detectors that surface
   ▼                                   │   emotional-life patterns — not just before the scorer)
A2/A3 reflection detectors + weekly pull-draft (now safety-gated)
   │
   ▼
Gate 1 schema (due_date + overdue, reusing WS-2.6b)  →  Gate 2 judge≠actor
   │
   ▼
Gate 4 eval HARNESS  ······ (numeric gate clears ONLY in a later human-rating milestone)
   │
   ▼
scorer — ships QUARANTINE-TIER and STAYS there until that human milestone runs
```

**Two things a code run builds but CANNOT clear (SD-7):** the **safety eval** (needs human-labeled distress data) and the **numeric eval** (needs ≥2 human raters × N≥50). The autonomous run builds the mechanism + the harness; **the scorer is shown-never-trended, permanently, until a human-rating pass produces a trustworthy QWK and certifies safety.** A build agent that commits a QWK or a "safety passing" from a self-run is a drift violation — the exact retracted-93.75% failure mode. **Reflection ships first and stands alone; the scorer is the last thing to light up — because a coach that can't be trusted or kept safe should not exist.**
