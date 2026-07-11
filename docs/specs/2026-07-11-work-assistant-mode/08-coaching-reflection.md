# 08 · Self-Reflection & Coaching — detailed design

**Date:** 2026-07-11 · **Status:** DESIGN **v2** — v1 was red-teamed and **failed** ("not ready"): its central
engineering claim (*deterministic detectors are the backbone; the LLM never originates a pattern*) **did not
survive contact with the schema** — 3 of its 4 detectors had no data to run on. v2 re-scopes honestly (§R4),
adds the safety layer v1 lacked entirely, and fixes a privacy hole that reached **outside** this feature.
Review record: §Q14.

> **Method — the self-ask loop.** Written as a chain of *questions we must answer before building*, each
> answered concretely. Anything unanswerable becomes an explicit open decision, never a silent assumption.
> **v2's lesson: also ask "does the data to do this actually exist?"** — v1 didn't, and designed an engine
> with no fuel.

---

## Q1. What *is* this? (Three things — conflating them is the first bug.)

| | What | Who thinks | Truth requirement |
|---|---|---|---|
| **(a) Recall** | "What happened Tuesday?" | Neither — retrieval | The user's record |
| **(b) Reflection** | The user makes meaning; we *scaffold* with good questions | **The user** | **None** — the user is the sole authority on their own experience |
| **(c) Coaching** | An external standard is applied to their behavior → assessment | **We** | **High** — needs a standard, evidence, citations |

**R1 — split them.** Most AI coaches fail by doing **(c)** with **(b)**'s rigor. *v1 of this doc was set up to
do exactly that* — see R4.

---

## Q2. What data — and what may we never claim?

| Layer | Source | Trust | Status |
|---|---|---|---|
| L0 | Confirmed diary entries | Highest | ✅ exists |
| L1 | Confirmed KG facts | High | ⚠️ **thinner than v1 assumed** (Q3) |
| L2 | Raw chat transcript | Medium (it's the user's *account*) | ✅ exists |
| L3 | User's went-well / to-improve notes | High | ❌ **no table exists** — net-new (Q3) |
| L4 | Practice-session transcripts | **Highest for behavior** — the only place we *observe* the user | ✅ roleplay exists |

**R2 — the honesty constraint (LOCKED).** Per D2 we never record real meetings; we only see the user's
*account*. Therefore:
- ❌ Never claim to assess how the user communicated in a real meeting. **We weren't there.**
- ✅ May assess the **practice session** (L4 — observed behavior).
- ✅ May surface patterns in what they *report* — phrased as such ("you **mentioned**…", never "you **are**…").

**Enforcement (v1 had none — it was a prompt hope):**
1. **Structural (already true, now stated):** the scorecard route *refuses* a session with no interview
   charter (`evaluate.py:158`), and D13 says the main all-day session carries **no charter** → **the main
   session is structurally unscoreable.** This is our best existing asset.
2. **Prose path (net-new):** a refusal-and-redirect rule *plus* an **output guard with a test** — an
   assistant turn making an evaluative claim about an unobserved event is a contract violation. (A prompt
   line with no test is the silent-no-op class this repo has shipped twice.)
3. **The scored subject is always the user's own utterances** (`role='user'`), never a quoted third party.
   Enforce in `coerce_scorecard` (which already server-rebuilds the checklist — extend that safe-when-wrong
   pattern to reject any dimension naming a non-user subject).

---

## Q3. What is the algorithm — and **does the data exist?** (v1's fatal gap)

v1 claimed four "deterministic detectors, zero LLM." The schema says otherwise:

| Detector | Substrate | Verdict |
|---|---|---|
| **Entity co-occurrence** | `chapter_entity_links(entity_id, chapter_id)` self-join (glossary migrate.go:85-96) + `(:Fact)-[:ABOUT]->(:Entity)` | ✅ **feasible today** |
| **Journaling gaps** | `chapters.entry_date` | ✅ **feasible today** |
| **Unresolved-thread age** | **No thread entity, no open/resolved status anywhere.** `:Fact` has no `status`; `knowledge_pending_facts` is 7 columns | ❌ **no substrate** |
| **Commitment slippage** | **`task`/`commitment` are not fact types** (closed set: `decision · preference · milestone · negation`, +`statement` per D5). **No due-date field.** Worse: `fact_id()` is **content-keyed** — a commitment with a moved date becomes a *different node* with **no link to its prior version**. "A date that moved K times" is literally unrecoverable | ❌ **no substrate** |
| **Recurring note themes (L3)** | **No table.** `went_well`/`to_improve` → zero hits repo-wide | ❌ **no substrate, no home** |

**Why this is a P0, not a detail.** With only co-occurrence + gaps, the "engine" produces *"you mentioned
Alice and Q3-budget together 4 times"* and *"you skipped Thursday."* That is not coaching. The pressure to
feel valuable then lands on the LLM "phrasing" step — and it starts **inventing** the patterns it was told it
could only phrase. "Cite or drop" does **not** save us: evidence refs attach happily to an LLM-invented
narrative *about* a real cluster ("you're avoiding conflict with Alice" — refs: 4 entry IDs). **The integrity
story inverts.**

### R3 — Kill or build. Each detector names the exact column/edge it reads, or it is a **schema deliverable**.

| Deliverable | Shape | Phase |
|---|---|---|
| `reflection_notes` | `owner_user_id, entry_date, went_well, to_improve` | **P1** (L3 has no home today) |
| `commitment` fact type | new fact type + **`due_date`** + a **stable `commitment_id`** (content-keying breaks on date change) + slippage history | **P2** (CHECK-backfill discipline per D5) |
| thread/open-item | a thread entity with `open|resolved` status | **P2** |

**Hard invariant + test:** `reflection_patterns.detector_code` is a **closed enum of shipped detectors**; the
phrasing LLM's output is **rejected** if it names a pattern whose `detector_code` isn't in the candidate set
it was handed. *That is enforcement, not a prompt.*

### R4 — Re-scope (the honest conclusion)

- **P1 ships reflection (R1b), NOT coaching (R1c).** Recall + the end-of-day capture (with a real L3 table) +
  journaling-gap and co-occurrence surfacing + reflection scaffolding. **This needs no truth guarantee at all,
  and it is where the honest value is.**
- **Coaching (R1c) is gated behind four prerequisites:** the commitment/thread schema (R3), the judge/actor
  split (Q6), the safety layer (Q13), and an eval with a numeric bar (Q9).
- **An empty week is a valid, good output** ("nothing worth surfacing"). The UI treats it as success.

### The pipeline (once gated)

1. **Aggregate** — SQL/graph. 2. **Detect** — deterministic detectors emit candidates **with evidence refs**;
no refs ⇒ dropped. 3. **Phrase** — LLM writes **Observation → Impact → Suggestion**, may not invent, must
carry refs through, output checked against the closed detector enum. 4. **Bound** — ≤2 patterns/week.

---

## Q4. Where does the "true knowledge" come from? *(The sharpest question — v1's answer survives.)*

| Need | Source of truth | LLM's role |
|---|---|---|
| **What happened** | The user's own diary/KG/transcripts. Nothing external | Extract & quote only — inventing here is a data bug |
| **What "good" looks like** | A **versioned rubric stored as data**, from published frameworks — **never** improvised per-run from model memory | *Apply* it; cite the evidence span per score |
| **Technique advice** | A **curated, cited coaching KB** (+ `web_search`) | Retrieve → synthesize **with citations** |

**Can a strong model be the teacher? Yes — bounded.** ✅ Reasoning/language (phrasing, Socratic prompts,
applying a rubric to evidence) — *grounding doesn't fix reasoning gaps, and these are reasoning gaps.*
⚠️ Generic advice — allowed, **labeled as opinion**. ❌ Never: inventing the standard; asserting a factual
claim without citation; judging what it never observed (R2).

**The coaching KB is just a book** — `kind='lore'`, chapters = curated cited frameworks, indexed via
[publish-independent-kg-indexing](../2026-07-11-publish-independent-kg-indexing.md) → cited retrieval is free
existing infrastructure.

**⚠️ This doc must pass its own gate (R3-cite).** The literature references below came from a search scan and
are **not yet resolved**: they must be individually verified before sign-off, and any that doesn't resolve is
**dropped** — exactly as this doc's own rule demands of the product.

---

## Q5. Detecting problems without being wrong or harmful

Deterministic detectors first (they can't hallucinate) · **cite or drop** · self-report framing (R2) ·
**dismissible with a tombstone** · never shared (tenancy law).

**Tombstone fix (v1 was broken):** keying on `(period, detector_code)` means the same pattern **resurfaces
next period as a new row**. Key on a **period-independent `pattern_key`** (`detector_code` + normalized
subject/theme hash): `UNIQUE(owner_user_id, pattern_key) WHERE status='dismissed'`, checked **at detection
time** (drop the candidate before it reaches the LLM), not at render time.

---

## Q6. Keeping the judge honest — *the judge IS the actor today*

**v1 asserted a reuse that does not exist.** `evaluate.py:149-150` reads `model_source`/`model_ref` **straight
off the `chat_sessions` row** — i.e. **the model that just played the roleplay partner scores its own
performance**. `ModelRole.CRITIC` exists (`settings_resolution.py:39`) but `evaluate.py` **has never used it**.
Self-preference bias is live in the code v1 said it was reusing.

**Net-new work item (not a reuse):** resolve the judge via `resolve_model_role(ModelRole.CRITIC, …)` and
**assert `judge_model_ref != session.model_ref`** — *refuse to score if they're equal*. With a test.
*(Credit where due: `temperature=0.0` is already correct — `evaluate.py:108`.)*

---

## Q7. Data model

| Store | Notes |
|---|---|
| `reflection_notes` | **NET-NEW (P1)** — L3 has no home today |
| `coaching_rubrics` | `code, version, dimensions[] (anchors 1-5), source_citation, license, tier`. **Replaces** `SessionTemplate.rubric`, which is today **free-form `dict[str, Any]`, no schema, no version** (models.py:73) — i.e. **"improvised standards" already ship**, contradicting Q10. A coach session with no resolvable **System-tier** rubric **refuses to score** |
| `reflection_patterns` | `owner_user_id, pattern_key, detector_code (closed enum), observation, impact, suggestion, evidence_refs[], citations[], status, …` |
| Scorecards | ⚠️ `Scorecard` is **interview-shaped** (`star_coverage`, `filler` — STAR constructs, models.py:119-122). Generalizing to N rubric dimensions is a **model + prompt + coercion change**, not "reuse ChatOutput" |
| Practice scenarios | Reuse `session_templates` ✅ |
| Coaching KB | Reuse a `lore` book + KG ✅ |

**⚠️ `maintain_chain` would corrupt a work KG.** `MAINTAIN_FACT_CHAIN_CYPHER` scopes the supersession chain on
**(subject, fact_type)** (facts.py:357-365). In a novel that's fine. In a work KG, **every `decision` about
Alice is one chain** — "Alice decided to delay the launch" (Jan) gets closed out by "Alice decided to hire a
contractor" (Feb) as if it superseded it. **Rule: the assistant path never passes `maintain_chain=True`** (or
the scope key gains a topic dimension). State it; test it.

---

## Q8. Cost

Aggregation ~0 LLM (⚠️ except near-dup theme clustering, which needs **embeddings** — not free) · phrasing 1–2
calls/week · advice retrieval 1 embed + rerank + 1 synthesis · practice = roleplay turns + **1 judge call**.
**Scale caveat:** `list_facts_by_type` is a **full label scan with no `(user_id, type)` index** (facts.py:409-413
says so verbatim) — sized for a novel, not 3 years of work facts. **Every longitudinal query must be bounded by
a date window**; the index is a P5 deliverable.

---

## Q9. How do we know it works? (v1's evidence was retracted by our own repo)

**v1 cited "Gemma-4 26B scored 93.75%" as validation. That number is withdrawn.**
[`docs/eval/canon-check-judge-2026-07-06.md:98-120`](../../eval/canon-check-judge-2026-07-06.md) — same doc,
same day — reports re-runs at **68.75% accuracy / 33% recall** at `temperature=0.0`, and concludes: *"a single
eval run is not sufficient evidence of this model's true reliability; **report a RANGE from repeated runs, not
a point estimate**."* Its operational landing: canon-check shipped as **`quarantine` (log-and-flag), never a
hard block**, *precisely because* precision/recall couldn't be trusted.

**Adopt that as the rule here:**
1. **Report a range over ≥3 repeated runs.** Never a point estimate.
2. **The canon-check precedent doesn't transfer anyway** — it's 16 fixtures, **binary**, with **objective**
   ground truth. A rubric is **multi-dimensional, ordinal, subjective**. The right instrument is **inter-rater
   reliability**: ≥2 independent human raters, report human–human agreement (Krippendorff's α / QWK) as the
   **ceiling**, and compare the LLM-judge against the human *consensus* — not against one annotator.
3. **Numeric gate:** N ≥ 50 transcripts · ≥2 raters · LLM-judge QWK ≥ *X* vs consensus. **Until it clears,
   scores are `quarantine`-tier: shown, never trended.** (Mirror canon-check's own landing.)
4. **Weak/local judge ⇒ NO score, not a noisy score.** The repo's own finding: a $0 quantized model's verdict
   can contradict its own stated reasoning.
5. **Dismiss-rate is NOT a validity metric (v1 was wrong).** It's *negatively* correlated with truth: an
   accurate, uncomfortable observation gets dismissed; a flattering, wrong one gets accepted — optimizing
   acceptance **selects for flattery**, the exact reward-hacking dynamic Q4 warns about. And with ≤2
   patterns/week, one dismissal flips a 60% bar — n is meaningless.
   → **Demote dismiss-rate to an operational signal** (noise ⇒ self-disarm a detector). The **quality** metric
   is **precision against a hand-labeled set**: *is the observation factually true given its evidence refs?*
   Objective, checkable. And split the user signal into **three different questions**: "was this **accurate**?"
   (truth) · "was this **useful**?" (value) · "dismiss" (noise). Conflating them is the bug.
6. **A safety eval set** (Q13) — more load-bearing than any accuracy number.

---

## Q10. Non-goals (LOCKED)

- Diagnosing mental health, personality, or performance-rating (see Q13 for the *mechanism*).
- Assessing real, unobserved meetings (R2).
- Cross-user comparison/benchmarking; manager/HR visibility of any artifact.
- Improvised standards — **no rubric, no score**.
- **No inferred trait/behavioral facts about a third party** (Q12).
- **No derived profile artifact about anyone other than the user** — never generated, rendered as prose, or
  reachable by a non-owner principal (Q11).

---

## Q11. 🔴 Third parties are data subjects — and the **wiki** is an unguarded publication surface

**D10 pins the diary's privacy lock on two paths (collaborator grants; sharing-service `patchSharingPolicy`).
It misses at least three. The wiki is the worst.**

Verified: the public wiki gate reads **`books.wiki_settings.visibility == "public"`** (wiki_handler.go:1459) —
a **JSONB blob PATCHable on the book** (`PATCH /v1/books/:id`, server.go:887-893), keyed on **nothing about
`kind`**. Sharing-service's check never runs on this path. `wiki_articles` is **one article per entity**
(`UNIQUE(entity_id)`, glossary migrate.go:643-652), `generateWikiStubs` **auto-writes prose** from the KG
(revision summary literally *"Auto-generated from KG"*), unauthenticated readers can list/read
(wiki_handler.go:1468, :1595), and `community_mode` lets **the public submit edit suggestions**. There is also
a second engine — `entity_enrichments` (migrate.go:1473-1493) — that manufactures confidence-scored,
AI-authored "dimensions" about an entity.

**Because D14 reuses the book GUI**, the diary user gets a one-click path to: generate an **AI-written
biography of every colleague** in their diary → flip `wiki_settings.visibility='public'` → serve those
biographies **to the open internet** → open them to public suggestions. **A real person who never consented,
profiled and published.** D10's "un-shareable on every path" is **false as written**.

### R5 — Amend D10 to enumerate **every** publication surface, keyed on immutable `kind='diary'`, each with a consumed-by-effect test

(a) collaborator grants ✅ already · (b) sharing-service `patchSharingPolicy` ✅ already ·
(c) **`PATCH /v1/books/:id` must reject any `wiki_settings` mutation** on a diary ·
(d) **`generateWikiStubs` must reject** diary books · (e) **`entity_enrichments` must reject** them ·
(f) **`checkWikiPublic` fails closed on `kind='diary'`** even if the flag somehow got set (defense in depth —
the flag is a legacy JSONB blob; assume drift) · (g) export.

### R6 — Guard at the **entity** level, not just the book level

Entities can be merged, moved, or referenced from a non-diary book. Mark real people
(`kind='colleague'` / a `third_party` predicate) and **block wiki + enrichment + share at the entity level**.

### R7 — Only stated, dated, attributed facts about third parties

`preference` is defined as *"Kai always carries a sword"* — mapped to work, that becomes **"Minh always pushes
back"**: a durable, queryable **behavioral trait claim about a real person**, derived from one person's
account. **Forbid `preference`-type facts whose subject is a third-party entity**; restrict them to the
`statement` type (what the user reports X said, on a date). Enforce in `pass2_writer.py`, with a test.

---

## Q12. 🔴 Q13. Distress & safety (LOCKED) — v1 had *nothing*, and the repo has *nothing*

Verified: `self-harm|suicid|crisis|distress|safeguard|helpline` → **zero** substantive hits across `services/`
and `docs/standards/`. There is **no safety layer anywhere in the platform** — and this is the first feature
that reads a person's emotional life and explicitly looks for "stress patterns."

**A non-goal is not a control.** Without a mechanism, the pipeline has *no branch* for a diary that reads
*"another 11pm push" · "Minh humiliated me in front of the team again" · "I don't know how much longer I can
do this."* Best case it answers with a glib productivity tip; worse, it offers to **roleplay the harassment**,
or scores the user's account of being harassed against a communication rubric and tells them their advocacy
was weak.

### R8 — A mechanism, not a prompt

1. **A safety classifier runs BEFORE any pattern is surfaced.** If it trips (distress, harassment/abuse
   disclosure, self-harm indicators) the weekly-reflection pipeline **short-circuits**: no patterns, no OIS,
   no score, no suggestion. **Fail closed** (reuse D7's fail-closed pattern).
2. **Instead:** a plain, non-clinical, non-judgmental acknowledgement + locale-appropriate resources —
   surfaced once, dismissible, never repeated, **never written into the KG as a fact about the user**.
3. **Never roleplay a disclosed harassment/abuse scenario.** Practice templates refuse when the classifier
   trips on the source material.
4. **Deny-list guard on the phrasing step's output** for clinical/diagnostic vocabulary — a pattern whose text
   trips it is **dropped, not softened**. With an eval case.
5. **A safety eval set** (distress diaries) asserting short-circuit behavior — a release gate.

---

## Q13. Settings & i18n

- **`assistant.coaching_enabled` — NET-NEW, default OFF.** v1 had no switch: a user who wants the diary but
  does not want to be *judged* had no way out. It spends tokens **and** it judges a person ⇒ per the
  spend-causing-toggle rule, **off** is the only defensible default.
- **i18n:** rubric anchors, OIS phrasing, and reflection prompts are all user-facing prose. The distiller
  already resolves the user's language; coaching must too. A Vietnamese user getting an English rubric anchor
  is a shipped bug.

## Q14. Phasing (re-scoped)

| Phase | Scope |
|---|---|
| **P1 — Reflection only (R4)** | `reflection_notes` table + end-of-day capture; journaling-gap + co-occurrence surfacing; reflection scaffolding; `assistant.coaching_enabled` (off); **R5/R6/R7 privacy guards** (they block a live hole *today*); i18n |
| **P2 — Coaching, gated** | commitment/thread schema (R3); `coaching_rubrics` replacing free-form rubrics; judge/actor split (Q6); **safety layer (R8)**; coaching KB + cited advice; `Scorecard` generalization |
| **P5 — Longitudinal** | trends (only after the Q9 numeric gate clears); `(user_id, type)` index; date-windowed queries |

## Q15. Open decisions

1. Which 2–3 practice scenarios first?
2. **Rubric provenance (upgraded to a real risk):** v1 proposed adapting **Advocacy-Inquiry** — but that
   instrument is from **healthcare-simulation debriefing**, validated *for that context with trained raters*.
   Transplanting it to workplace communication scored by a quantized local LLM **inherits none of its
   validity** and risks **laundering** unvalidated judgment behind a validated name. Also: **check the
   license** before embedding. **Rule to adopt:** *an adapted rubric inherits the source's structure, not its
   validation — our rubric is validated by our own eval (Q9), or it is not validated.*
3. User-editable rubric? (clone ⇒ **new `code`**; trends never cross codes.)
4. Retention: coach transcripts + scorecards + `reflection_patterns` must be **added to the §7 erasure
   inventory** (v1 omitted the most sensitive artifact in the feature).
5. Detector self-disarm threshold.

## Q16. Review record (v1 → v2)

| # | Finding | Fix |
|---|---|---|
| **P0-1** | **3 of 4 detectors have no data substrate** (`task`/`commitment` aren't fact types; no thread status; no L3 table) → the LLM would originate patterns and the integrity story inverts | Q3 (kill-or-build + closed detector enum + **R4 re-scope: P1 = reflection, not coaching**) |
| **P0-2** | **The wiki** — an unguarded 3rd publication surface; diary colleagues become AI-written, publicly-servable profile pages | Q11 (R5/R6/R7; **amends D10**) |
| **P0-3** | **No distress/safety handling exists anywhere**, and this feature reads emotional life | Q12 (R8 — classifier, short-circuit, resources, deny-list, eval) |
| **P0-4** | **The judge IS the actor** (`evaluate.py` uses the session's own model); and the **93.75% eval number is retracted** by our own doc (68.75% on re-runs) | Q6 (CRITIC role + assert ≠); Q9 (range-not-point-estimate; IRR; quarantine-tier) |
| **P1** | Free-form `SessionTemplate.rubric` = improvised standards already ship; `maintain_chain` would corrupt the work KG; trait facts about third parties; dismiss-rate selects for flattery; tombstone resurfaces each period; coach transcripts absent from erasure; `Scorecard` is interview-shaped | Q5, Q7, Q9.5, Q15.4 |
| **P2** | No coaching-off setting; no i18n; unindexed full-label scans; empty-week behavior undefined | Q8, Q13, Q3 (R4) |
