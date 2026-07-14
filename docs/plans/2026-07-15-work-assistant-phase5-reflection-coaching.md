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

### Gate 1 — the commitment/thread SCHEMA (R3)

| Deliverable | Shape | Why |
|---|---|---|
| **WS-5.7** `commitment` fact type | new fact type + **`due_date`** + a **stable `commitment_id`** (content-keying breaks the moment a date moves — the prior version becomes an unlinked node) + slippage history | "a date that moved K times" is literally unrecoverable today; this makes commitment-slippage a real detector. CHECK-backfill discipline (D5): the new enum value must backfill ALL historical CHECK blocks. |
| **WS-5.8** thread/open-item | a thread entity with `open|resolved` status | unresolved-thread-age has no substrate today. |
| **WS-5.9** maintain_chain guard | the assistant path **never** passes `maintain_chain=True` (P5-D4) — its (subject, fact_type) scope collapses every `decision` about Alice into one chain (facts.py) | state it; test it. |

### Gate 2 — judge ≠ actor (Q6)

**WS-5.10.** Today `evaluate.py` reads `model_source`/`model_ref` **straight off the `chat_sessions` row** — *the model that played the roleplay partner scores its own performance.* `ModelRole.CRITIC` exists (`settings_resolution.py`) but `evaluate.py` **has never used it**. Fix: resolve the judge via `resolve_model_role(ModelRole.CRITIC, …)` and **assert `judge_model_ref != session.model_ref` — refuse to score if equal**, with a test. (`temperature=0.0` is already correct.)

### Gate 3 — the platform SAFETY layer (R8) — the repo has NOTHING here

Verified: `self-harm|suicid|crisis|distress|safeguard|helpline` → **zero** substantive hits across `services/` and `docs/standards/`. This is the first feature that reads a person's emotional life. A non-goal is not a control.

| Slice | Scope |
|---|---|
| **WS-5.11** | A **safety classifier** runs BEFORE any pattern is surfaced. On a trip (distress / harassment-or-abuse disclosure / self-harm indicators) the weekly pipeline **short-circuits**: no patterns, no OIS, no score. **Fail closed** (reuse D7). |
| **WS-5.12** | On a trip, surface a plain, non-clinical, non-judgmental acknowledgement + locale-appropriate resources — **once**, dismissible, never repeated, **never written into the KG as a fact about the user**. |
| **WS-5.13** | **Never roleplay a disclosed harassment/abuse scenario** — practice templates refuse when the classifier trips on the source material. |
| **WS-5.14** | A **deny-list guard on the phrasing step's output** for clinical/diagnostic vocabulary — a pattern whose text trips it is **dropped, not softened**. |
| **WS-5.15** | A **safety eval set** (distress diaries) asserting short-circuit behavior — **a release gate**. More load-bearing than any accuracy number. |

### Gate 4 — the numeric EVAL bar (Q9) — v1's 93.75% was retracted by our own repo

The repo's own canon-check eval withdrew a 93.75% point-estimate that re-ran at **68.75% / 33% recall**, and concluded: *report a RANGE from repeated runs, not a point estimate.* Adopt it:

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
| **WS-5.21** | `Scorecard` **generalization** — today it's interview-shaped (`star_coverage`, `filler` — STAR constructs). Generalizing to N rubric dimensions is a model + prompt + coercion change (not "reuse ChatOutput"). The scored subject is **always the user's own utterances** (`role='user'`), enforced in `coerce_scorecard`. |
| **WS-5.22** | The pipeline (once gated): **Aggregate** (SQL/graph) → **Detect** (deterministic, evidence refs, no refs ⇒ drop) → **Phrase** (LLM writes Observation→Impact→Suggestion, may not invent, carries refs, checked against the closed detector enum) → **Bound** (≤2 patterns/week). |
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
A (reflection, ungated)  →  Gate 1 schema  →  Gate 2 judge≠actor  →  Gate 3 safety  →  Gate 4 eval
                                                                          │
                              (safety + eval are the longest poles) ──────┘
                                                                          ▼
                                                          scorer (quarantine-tier until eval clears)
```

**Reflection ships first and stands alone.** The scorer is the LAST thing to light up, and only shown-never-trended until QWK ≥ X — because a coach that can't be trusted or kept safe should not exist.
