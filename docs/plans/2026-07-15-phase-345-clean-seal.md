# Work Assistant — Phase 3/4/5 CLEAN + SEAL (the master decision register)

**Date:** 2026-07-15 · **Track:** Work Assistant · **Status:** SEALING (pre-build) ·
**Goal owner:** human-directed ("clean phase 3, 4, 5" + "unblock phase 5") ·
**Deliverable:** sealed decisions + a ready-to-build plan per phase — **NO CODE this run**; the human reviews the sealed plans, then greenlights the build as a separate run.

> Companion detailed plans (this doc is the index + the sealed register):
> - Pre-P3 security: [§2 wiki/entity privacy fix](#2--pre-phase-3-the-live-wikientity-privacy-hole-r5r6r7) (small — inline here)
> - Phase 3: [`2026-07-13-work-assistant-phase3-scheduler-proactive.md`](2026-07-13-work-assistant-phase3-scheduler-proactive.md) (exists; opens sealed below)
> - Phase 4: [`2026-07-15-work-assistant-phase4-voice.md`](2026-07-15-work-assistant-phase4-voice.md)
> - Phase 5: [`2026-07-15-work-assistant-phase5-reflection-coaching.md`](2026-07-15-work-assistant-phase5-reflection-coaching.md)

---

## 0. Where we are (the pre-condition)

**Phase 2 is COMPLETE** — WS-2.1→2.10 built + committed + proven vs live Neo4j/PG, incl. the full D17 memory-amendment (all 4 verbs) and the employment epoch. The scoped-erasure primitive exists at 3 scopes (entity/epoch/account). The only Phase-2 remainder is **P-12** (diary at-rest encryption + backup-resistant crypto-shred), which the human sealed as its own dedicated goal (D-R24) — the immediate row-cascade is done, only the crypto-shred hardening is parked. Nothing else blocks Phase 3.

**One live hole surfaced during this clean pass** (not Phase-2, exploitable today) → §2.

---

## 1. The GOAL (this run)

> **Clean, clarify, and SEAL every open decision across: the pre-Phase-3 wiki/entity privacy fix, Phase 3 (scheduler/proactive), Phase 4 (voice), and Phase 5 (reflection + coaching). Produce a ready-to-build plan per phase. Stop at sealed-plans; do not build.**

**Autonomy contract for the clean/seal work:** I seal ORDINARY tech decisions myself and record them here (§3). The three FORKS the human already decided are SD-1/2/3. A sealed decision may not be overridden without the human.

---

## 2 · Pre-Phase-3: the wiki/entity privacy hole (R5/R6/R7) — RE-SCOPED after cold review

**Human decision (SD-1): fix this BEFORE Phase 3, inside this upcoming goal.**

**⚠️ CORRECTION (cold review, 2026-07-15): the primary exploit is ALREADY CLOSED.** My first pass overstated this as a "live one-click hole." Verified against code: `book-service server.go:1073` ("EGRESS GUARD #3") already **rejects a `wiki_settings` PATCH on a `kind='diary'` book** (`403 BOOK_DIARY_NO_WIKI`). So the *mutation* path is shut. The genuine residual is narrower but real:
- **Legacy/residual blobs**: any diary whose `wiki_settings.visibility` was set to `public` **before** the guard landed — the guard blocks new mutations, not existing rows.
- **Two glossary-side READERS bypass `checkWikiPublic`** and read `wiki_settings.visibility` directly: `listUserWikiContributions` (`wiki_contributions_handler.go:100`, **anonymous, cross-book** public profile) and `submitWikiSuggestion` (`wiki_handler.go:1729`, `community_mode` public edit). Neither has a `kind` guard.
- **The auto-writers** (`generateWikiStubs` `wiki_handler.go:1181`; `internalUpsertEnrichments` `enrichment_handler.go:70`) manufacture AI prose about a diary colleague with no diary check.

**The fix — ONE chokepoint, not seven one-off patches.** glossary-service's `bookProjection` struct (`book_client.go:29`) has **no `Kind` field**, even though book-service's projection already emits `kind` (`server.go:3084`, "the diary taint; consumers guard on it"). So:

| Slice | Guard | Where | Test |
|---|---|---|---|
| **PP-1** ✅ verify-only | The `wiki_settings` PATCH guard on a diary — **already built** (EGRESS GUARD #3). | book-service `server.go:1073` | add a REGRESSION test (a diary `wiki_settings` PATCH → 403); do NOT rebuild. |
| **PP-2** 🔴 the real fix | Add `Kind` to glossary `bookProjection`; **`fetchBookProjection` nulls `WikiSettings` (and community_mode) when `kind=='diary'`.** This is the SINGLE chokepoint — it closes `checkWikiPublic`, `listUserWikiContributions` (H1), and `submitWikiSuggestion` (M2) at once, INCLUDING the residual-blob case. | glossary `book_client.go:29,43` | a diary with `visibility=public` forced in the blob → 404 on the public read AND absent from the public profile AND rejected on suggest. |
| **PP-3** | `generateWikiStubs` + `internalUpsertEnrichments` consult the projection `Kind` (a network read — they don't hold book kind locally) and **refuse** a diary book. | glossary `wiki_handler.go:1181`, `enrichment_handler.go:70` | no wiki_article / enrichment row is manufactured for a diary entity. |
| **PP-4** | **Entity-level guard (R6)** with a PRECISE predicate: a real person = `glossary_entities.is_self=false AND kind.code IN (the seeded work kinds: colleague/project/meeting/decision/task/jargon/org)`. Block wiki + enrichment + share at the entity level. **Watch the over-block:** `org` and mis-kinded entities — scope the block to `colleague` (+ a `third_party` marker if one is added) rather than all work kinds, so a legitimately-public `org` page isn't caught. | glossary entity | a colleague entity is wiki/enrichment-blocked; a novel character is not. |
| **PP-5** | **Forbid `preference`-type facts about a third-party entity (R7)** — coerce to `statement`. **Requires plumbing** (H2): `pass2_writer.write_pass2_extraction` has no diary/self signal today (subjects resolve by name to a graph id; `is_self` lives in glossary Postgres, not Neo4j). Thread a `diary`/`work_mode` flag + the self-entity anchor id into the writer; coerce `preference→statement` **only when diary-scoped AND subject ≠ self**, so a novel `preference` ("Kai always carries a sword") is untouched. | knowledge `pass2_writer.py:916` | a third-party diary `preference` → coerced to `statement`; a novel `preference` unaffected. |

**Dropped:** the old PP-7 "export" slice — the real export paths (`exportGlossary` etc.) are owner/grantee-scoped and don't emit wiki/enrichment; diaries aren't grant-shareable. No non-owner publication surface there. (Covered by "verify no export bypasses the projection guard" in PP-2's test.)

**Size:** M (glossary + knowledge; book-service is verify-only). The projection chokepoint (PP-2) is the whole game — it converts "enumerate every reader" into "neutralize the taint at the one place every reader already reads." All guards fail-closed + consumed-by-effect.

---

## 3 · The SEALED DECISION REGISTER (every open question, resolved)

### Human forks (decided this turn)

| # | Decision | Rationale |
|---|---|---|
| **SD-1** | The wiki/entity privacy guards (R5/R6/R7) are **fixed BEFORE Phase 3**, folded into this goal. | Live hole leaking real people's data; not gated on coaching; cheap fail-closed guards. |
| **SD-2** | **Phase 5 is built in FULL** — the ungated reflection half AND all 4 coaching gates (commitment/thread schema · judge≠actor · platform safety layer · numeric eval bar). | Human chose the ambitious path; coaching scores can't ship trustworthy/safe without the 4 gates, so they're in-scope, not deferred. |
| **SD-3** | Deliverable for THIS goal = **sealed decisions + ready-to-build plans**; no code. Human reviews, then greenlights the build. | Matches the Phase-3 plan precedent; keeps the human in the loop before a large multi-phase build. |

### Phase 3 — ordinary seals (I decide + record)

| # | Open | SEAL |
|---|---|---|
| P3-D1 | Q-open-1 scheduler home | **New Go `scheduler-service`** (D-R28, already sealed). One home for the clock; worker-ai stays a pure executor. Language rule: meta/domain infra ⇒ Go. |
| P3-D2 | Q-open-2 auto-EOD default | **OFF / opt-in** (D-R29, already sealed). SET-* user setting; revisit after reflection ships. |
| P3-D3 | Q-open-3 reflection surface | **Pull-only weekly DRAFT for v1** (the user opens it); upgrade to a proactive turn only once the WS-3.5 seam is live-proven. Avoids the agent-initiated-message risk on day one. |
| P3-D4 | Away marker | **`assistant_away_periods` table**; detectors + nudges exclude declared-away days; a gap detector never fires on a declining-engagement trend without asking why. An empty week is a valid, good output. |
| P3-D5 | Notification content | **Content-free, enforced by a test** (T26/D16): diary-sourced notifications carry zero content ("You have an unfinished entry"); the content lives only behind auth. |
| P3-D6 | Unattended writes | **Draft-into-inbox or pre-allowlisted only** (D4/Q4): a scheduled distill produces a DRAFT the user confirms, never auto-canon. |

### Phase 4 — ordinary seals

| # | Open | SEAL |
|---|---|---|
| P4-D1 | Prerequisite ordering | The **`D-CHATAI-VOICE-TWO-STORES-ENUM`** settings-store reconcile lands **FIRST** — building voice on a mid-migration settings store forks it further (spec 12 Q3#4). |
| P4-D2 | Transcript routing | Route the voice transcript through the **existing text agent loop** (`stream_response`), not a duplicate path — voice inherits tools, skills, capture, and context-budget frames (~70% already shared). |
| P4-D3 | Billing | **Real usage accounting** — STT + LLM + TTS metered into the assistant lane (fix the verified `input_tokens=0, output_tokens=0`), so the spend lane + daily cap see voice. |
| P4-D4 | Audio retention default | **Short default = 7 days**, user-settable from **0 (delete audio the moment its transcript is written)** up to a bounded max. Audio segments join the erasure copy-set AND "delete my day" (MinIO objects, never purged today). |
| P4-D5 | Affordance gating | Voice input **hidden/disabled for assistant-bound sessions in P1–P3**; if ever reachable it must at minimum log a capture decision `reason='voice_path_unsupported'`. |
| P4-D6 | Non-goal (LOCKED) | **Never ambient/always-listening** (D2). Push-to-talk-shaped; the user talking to the assistant, never open-mic capture of a room/meeting/colleague. |

### Phase 5 — ordinary seals (coaching gates are IN per SD-2)

| # | Open | SEAL |
|---|---|---|
| P5-D1 | Reflection vs coaching split | **Reflection ships ungated** (no truth guarantee needed); **coaching/scoring ships only behind its 4 gates** — but all 4 are IN-SCOPE this effort (SD-2). |
| P5-D2 | The 4 coaching gates | (1) **commitment/thread schema** (R3): `reflection_notes` (P1) + `commitment` fact type with `due_date` + a **stable `commitment_id`** (content-keying breaks on date change) + slippage history + a thread entity with `open|resolved`; (2) **judge≠actor** (Q6): resolve the judge via `resolve_model_role(ModelRole.CRITIC,…)` and **refuse to score if `judge_model_ref == session.model_ref`**, with a test; (3) **safety layer** (R8): a classifier runs BEFORE any pattern, short-circuits the pipeline on distress/harassment/self-harm (fail-closed), offers non-clinical resources once, never roleplays a disclosed abuse scenario, deny-list guard on the phrasing output, + a **safety eval set** as a release gate; (4) **numeric eval bar** (Q9): report a RANGE over ≥3 runs, IRR (≥2 human raters, QWK vs consensus), N≥50 transcripts, **quarantine-tier until QWK≥X clears**; a weak/local judge ⇒ NO score, not a noisy one. |
| P5-D3 | Detector integrity | `reflection_patterns.detector_code` is a **closed enum of shipped detectors**; the phrasing LLM's output is **rejected** if it names a pattern whose `detector_code` isn't in the candidate set it was handed. Cite-or-drop. Enforcement, not a prompt. |
| P5-D4 | maintain_chain | The **assistant path NEVER passes `maintain_chain=True`** (its (subject, fact_type) scope would collapse every `decision` about Alice into one chain) — or the scope key gains a topic dimension. State it; test it. |
| P5-D5 | Rubric provenance (Q15.2) | RULE: **an adapted rubric inherits the source's structure, not its validation** — our rubric is validated by our own eval (P5-D2#4) or it is not validated. **Check the license** before embedding. Do NOT transplant Advocacy-Inquiry (healthcare-sim, trained raters) and inherit its name's credibility. A coach session with no resolvable **System-tier** rubric **refuses to score**. |
| P5-D6 | User-editable rubric (Q15.3) | Clone ⇒ a **new `code`**; trends never cross codes. |
| P5-D7 | Retention (Q15.4) | Coach transcripts + scorecards + `reflection_patterns` are **added to the erasure copy-set** (the most sensitive artifacts in the feature). |
| P5-D8 | Dismiss-rate (Q9.5) | **Demoted to an operational signal** (noise ⇒ self-disarm a detector), NOT a validity metric (it selects for flattery). Quality = **precision against a hand-labeled set** (is the observation true given its evidence refs?). Split user signal into 3 questions: accurate? / useful? / dismiss. |
| P5-D9 | Practice scenarios (Q15.1) | Start with **3**: "deliver critical feedback", "say no to scope creep", "raise a blocker early". Reuse `session_templates`; the coaching KB is a `kind='lore'` book. |
| P5-D10 | coaching_enabled | **NET-NEW setting, default OFF** (spends tokens AND judges a person ⇒ the spend-causing-toggle rule mandates off). i18n: rubric anchors, OIS phrasing, reflection prompts all resolve the user's language. |
| P5-D11 | Detector self-disarm threshold (Q15.5) | A detector self-disarms when its **dismiss-rate exceeds 0.6 over ≥5 surfaced patterns** (operational; tunable). |
| P5-D12 | Longitudinal (P5-internal) | Trends only AFTER the numeric gate clears; add the `(user_id, type)` index; every longitudinal query date-windowed (`list_facts_by_type` is a full label scan today). |

---

## 4 · BUILD ORDER (dependency-correct — for the FUTURE build run, not this one)

```
PRE-P3  Wiki/entity privacy fix (PP-1..7)         ── SD-1: security first, unblocks everything
  │
  ▼
P3      Scheduler + proactive (WS-3.1..3.8)        ── the platform's one true hole
  │      (scheduler-service · auto-EOD · catch-up sweep · away marker · proactive seam ·
  │       content-free nudges · costed weekly rollup · weekly reflection DRAFT)
  ▼
P4      Voice parity (two-stores reconcile → route-via-text-loop → 0/0 billing → audio retention)
  │      (shares the proactive-turn seam + the spend lane with P3)
  ▼
P5      Reflection (ungated) → the 4 coaching gates → coaching scorer (quarantine-tier until eval clears)
         (commitment/thread schema · judge≠actor · safety layer · eval harness · Scorecard generalization)
```

**Why this order:** PP-* is a live leak (fix first). P3's scheduler is the substrate P5's weekly reflection + P4's shared seam ride on. P4 and P5-reflection can parallelize after P3 if desired; P5-coaching's safety layer + eval bar are the longest poles and gate the scorer.

---

## 5 · What this clean/seal pass deliberately did NOT decide

- **P-12** (diary encryption + backup-resistant crypto-shred) stays its own human-owned goal (D-R24) — orthogonal to 3/4/5.
- **Exact eval QWK threshold `X`** (P5-D2#4) — set empirically from the human-rater ceiling once the eval set exists; a design-time guess would be dishonest.
- **The coaching KB's specific frameworks** — each cited reference must individually resolve before sign-off (spec 08 Q4 R3-cite); any that doesn't resolve is dropped.

---

## 6 · Register (this doc's own audit)

- **Decisions sealed:** SD-1/2/3 (human) + P3-D1..6 + P4-D1..6 + P5-D1..12 (ordinary, recorded above) + the §7 review-driven seals below.
- **Parked (unchanged):** P-12 (D-R24).
- **Open-for-the-human-at-build-time:** the eval threshold X, the KB framework list (both genuinely empirical/external, not clean-pass decidable).

---

## 7 · COLD-REVIEW FINDINGS & RESOLUTIONS (4 independent adversarial reviewers, 2026-07-15)

Each plan was cold-reviewed by an independent agent against the spec + the ACTUAL code. The review **corrected several of my own wrong claims** (marked ⚠️) and re-scoped the under/over-sized slices. Every finding is resolved below; the per-phase plans are patched to match.

### Cross-plan seams (found by me, the only view that spans all 4 plans)

| # | Finding | RESOLUTION (sealed) |
|---|---|---|
| **X-1** | Weekly reflection draft double-owned (`WS-3.8` ∧ `WS-5.3`). | Phase 5 owns the **content** (detectors+phrasing); the v1 reflection is **pull-only, user-invoked** (P3-D3) so it needs NO Phase-3 scheduler. `WS-3.8` is redefined as the *later* scheduled/proactive upgrade only — deferred with `WS-3.5` (see R2-M3). No parallel build. |
| **X-2** | Safety layer (Gate 3) must gate any content-bearing reflection, not just scored coaching — the weekly reflection draft carries emotional content. | **SEAL: Gate 3 is a prerequisite for the reflection PATTERN-SURFACING step (WS-5.2/5.3), not only the scorer.** Reflection over the user's OWN notes (WS-5.1) is fine; the moment a *detector* surfaces a pattern about their emotional life, the safety classifier gates it. Re-sequenced in the Phase-5 plan: safety floor before pattern-surfacing. |
| **X-3** | R7 double-listed (PP-5 pre-P3 ∧ Phase-5 §D). | It lives in the **pre-P3 fix (PP-5)** — a live `pass2_writer` hygiene hole. Phase 5 only references it. Deduped. |
| **X-4** | Gate 4 eval needs ≥2 human raters × N≥50 — not code-completable. | **SEAL: the code run builds the eval HARNESS + fixtures + QWK computation ONLY; the numeric gate CANNOT be marked cleared inside a code run.** The scorer ships quarantine-tier and stays there until a separate human-rating milestone. This is a hard exit-condition rule for the build goal (§8). |
| **X-5** | Safety-classifier model choice fights the $0-capable ethos. | **SEAL: the safety FLOOR is deterministic (fail-closed curated distress lexicon + paraphrase patterns), never solely an LLM** — a model miss can't silently pass distress. An LLM refinement may *widen* the net, never *narrow* the floor. |

### Wiki-fix (Reviewer 1) — see the re-scoped §2

| # | Finding | RESOLUTION |
|---|---|---|
| ⚠️ R1-M1 | PP-1 (the `wiki_settings` PATCH guard) is **already built** (EGRESS GUARD #3, `server.go:1073`). My "live one-click hole" was overstated. | §2 re-scoped: PP-1 = verify+regression-test; the real residual is legacy blobs + the glossary readers. |
| R1-H1/M2 | `listUserWikiContributions` (anon, cross-book) + `submitWikiSuggestion` bypass `checkWikiPublic`. | The **projection chokepoint (PP-2)** — null `WikiSettings` for a diary in `fetchBookProjection` — closes all readers at once, incl. residual blobs. |
| R1-H2/H3 | PP-5/6 (pass2 preference-guard) unbuildable as written (no diary/self signal in the writer; over-blocks novels); glossary guards need the book kind they don't hold locally. | §2 PP-3/4/5 rewritten: consult projection `Kind`; thread a diary-flag + self-anchor into pass2; coerce only diary-scoped ∧ subject≠self. |
| R1-M3/L1 | PP-5 predicate hand-wavy; PP-7 export moot. | Predicate pinned (`is_self=false ∧ kind.code='colleague'`); PP-7 dropped. |

### Phase 3 (Reviewer 2)

| # | Finding | RESOLUTION |
|---|---|---|
| R2-H1 | Auto-EOD (WS-3.2) needs server-side **book+model(BYOK)+tz+lang resolution** that doesn't exist (today client-supplied); collides with the empty `user_default_models`. | **NEW prereq slice WS-3.0** (server-side distill-context resolution) added; WS-3.2 gated on it. This is the "Q8 follow-up" made real. |
| R2-H2 | Away-marker acceptance references Phase-5 detectors that don't exist. | WS-3.4 scoped to "away column + **nudge** exclusion"; the detector-exclusion + "no gap patterns" acceptance moves to Phase 5. |
| R2-M3 | Proactive seam WS-3.5 has no v1 consumer (contradicts pull-only seal P3-D3). | **WS-3.5 + proactive-WS-3.8 DEFERRED** to the phase that enables them; v1 ships nudges-as-notifications + reflection-as-pull-draft. |
| R2-M4/M5 | "Copy the authoring-run driver" is Python; a raw Go→Redis XADD is a 3rd copy of the stream field-list. | Re-impl the lease/breaker in Go mirroring `usage-billing sweeper.go`/`publisher poll_loop`; **enqueue via the existing `POST /internal/chat/assistant/distill` HTTP trigger**, not a raw XADD. |
| R2-M6/L7/L8 | Headless `stream_response` ripple; SKIP-LOCKED≠fairness; scheduler-service scaffolding under-weighted. | Folded into the deferred WS-3.5; fairness attributed downstream; WS-3.1 gains the scaffold subtasks (language-rule.yaml row, own DB, migrations, compose, the opt-in write path). |

### Phase 4 (Reviewer 3)

| # | Finding | RESOLUTION |
|---|---|---|
| ⚠️ R3-H2 | The spend **`lane` column is NOT built** (T-8 unbuilt; only the daily-cap degrade WS-2.8 shipped; `log_usage` hardcodes `purpose='chat'`). My "assistant lane (built)" was wrong. | WS-4.2 dependency corrected: either build the `lane` column ×3 tables first, or scope WS-4.2 to LLM-token billing on the existing global cap. |
| R3-H1 | STT/TTS usage is **uncapturable at the call site** (`SttResult` has no tokens; `stream_tts` discards `UsageEvent`); STT bills by minutes, TTS by chars, not tokens. | WS-4.2 split: (a) LLM-token fix (easy — voice discards the `UsageEvent` it already receives; thread it in), (b) a tracked STT/TTS-usage-plumbing item (provider-registry adapters emit usage → SDK surfaces it → voice logs it). Acceptance corrected: not "tokens" for STT/TTS. |
| R3-H3 | WS-4.1 mis-locates the seam — `stream_response` is the wrong layer (serialized SSE, double-persist); `_stream_with_tools` yields `tool_call`/`suspend` chunks voice KeyErrors on; capture is in yet another layer. | WS-4.1 re-scoped to **extract a shared inner generator** both `_emit_chat_turn` and voice consume (voice keeps its TTS interception), + handle non-content chunks, + decide frontend-tool (`suspend`) applicability for voice. Real refactor, not a swap. |
| ⚠️ R3-M1/M2/M3 | The audio sweeper + MinIO delete **already exist** (`main.py _audio_cleanup_loop`, `voice.py /cleanup`); spec 12's "never purged" is stale. The D-R27 erase DOES orphan MinIO objects (real bug). | WS-4.3 re-scoped to "global `AUDIO_TTL_HOURS` env → **per-user setting**"; **P4-D4 default corrected: 48h stays the ceiling, do NOT lengthen to 7d** (that weakens a privacy feature) — user-settable 0..48h. WS-4.4 = apply the existing `RETURNING object_key→delete_object` pattern to the D-R27 cascade (SELECT keys BEFORE the cascade). |
| R3-L1/L2/L3 | Voice is **NOT gated for assistant sessions today** (live uncaptured/unbilled bug, not "hidden"); deferral-ID drift; WS-4.0 only blocks WS-4.3. | WS-4.5 reframed: the P1-P3 gate is a real FIX to add now (the bug is live), not a formality. ID reconciled to `D-CHATAI-VOICE-TWO-STORES`. WS-4.0 re-ordered as a prereq for WS-4.3 only. |

### Phase 5 (Reviewer 4)

| # | Finding | RESOLUTION |
|---|---|---|
| R4-M1 | Gate 1 over-engineers commitment identity — **the WS-2.6b supersession primitive already tracks "a date that moved"** (content date-free + `due_date` + the s/p/o trio + `group_supersessions()`). | **Gate 1 collapses to: a `due_date` field + an overdue detector**, reusing WS-2.6b. No new `commitment_id` identity model. Big simplification. |
| R4-M2 | Adding a `commitment` fact type touches **3 registries** (the `FactType` Literal `facts.py:63`, `knowledge_pending_facts` CHECK ×2 `migrate.py:732,746`, the `kg_fact_types` ontology) — D5 named one → a 500-at-merge if missed. | P5-D2 rewritten to enumerate all 3; decide `commitment` = hardcoded Literal member (pragmatic, matches the closed set). |
| R4-H3 | Gate 2 judge≠actor has a **silent-universal-refusal** hole: a single-model user (empty `user_default_models`) → critic resolves to the same model → refuses ALL scoring. | Add an explicit degraded path: require a distinct critic model with a "configure a second model for coaching" message, OR allow same-model with a disclosed caveat. Not silent refusal. |
| R4-H2 | Gate 3 safety = intent, not mechanism (the riskiest slice). Deterministic list fails open on paraphrase; LLM is an unvalidated judge; the 2nd placement (practice) is unspecified. | Committed mechanism (X-5): deterministic fail-closed FLOOR + optional LLM widener; classifier placed at BOTH the weekly-pattern node AND practice source-material/start; the safety eval set is a **human-labeled release gate a code run cannot self-certify**. |
| R4-H1 | Gate 4 eval slices are a human-data project mislabeled as code. | (X-4) split harness-vs-human-rating; forbid a committed QWK from a single self-run; scorer quarantine-tier until the out-of-band human pass. |
| R4-M3/M4 | Scorecard generalization touches ~4-6 sites (not 3); "quarantine-tier for scores" is net-new plumbing (canon-check's quarantine is fact-validation, no tier on `Scorecard`). | WS-5.21 re-scoped to the real site list (model + prompt template + `coerce_scorecard` + 2 render sites + FE, rubric-driven server-authoritative dims); WS-5.22 adds a real `quarantine` tier column + FE gate. |
| ✅ R4-sound | `maintain_chain=False` already holds on the diary path (`pending_facts.py:172`); `reflection_notes` genuinely absent; the 2 detectors' substrate exists. | WS-5.9 test extended to the NEW commitment/thread writers; WS-5.2 must VERIFY diary chapters actually have entity links populated, not assert it. |

### The seals this review ADDS

- **SD-4** — the wiki fix is a **single projection chokepoint** (PP-2), not seven patches; PP-1 is verify-only.
- **SD-5** — Phase 3 gets a **WS-3.0 server-side distill-context resolution** prereq; the **proactive seam (WS-3.5) is deferred** out of v1; enqueue via the HTTP trigger.
- **SD-6** — Phase 4's **spend `lane` is unbuilt** (a real dependency, not "done"); **audio retention stays ≤48h** (never lengthened); the sweeper + MinIO delete already exist (reuse, don't rebuild).
- **SD-7** — Phase 5 **Gate 1 reuses the WS-2.6b supersession primitive**; **Gate 3 (safety) and Gate 4 (eval) CANNOT be cleared inside an autonomous code run** — the run builds the mechanism + harness; clearance is a human-gated milestone. The coaching scorer ships **quarantine-tier, permanently, until that human milestone runs**.

---

## 8 · Implications for the upcoming BUILD goal (the human sets this next)

The build is a LONG autonomous run and MUST bake in these guardrails (per the human's ask for review-impl / fix-bugs / live-test):

1. **Per-milestone `/review-impl`** (adversarial, cold-start) — the wiki fix, the scheduler substrate, the proactive/voice seams, and EVERY Phase-5 safety/eval slice are load-bearing; each gets a cold review before its commit.
2. **Live-test gate** — cross-service milestones (wiki chokepoint, auto-EOD, voice billing, the reflection pipeline) prove on a real stack, not mocks (the repo's repeated cross-service lesson).
3. **The two human-gated carve-outs (SD-7):** the goal's exit condition is *"the safety mechanism + the eval harness are BUILT and the scorer is wired quarantine-tier"* — **NOT** *"the eval passes"* or *"safety is certified."* A build agent claiming a QWK number or a safety pass from a self-run is a drift violation (the retracted-93.75% failure mode). Those two clear only in a later human-rating pass.
4. **Fix-bugs loop** — findings from each `/review-impl` are fixed + re-verified before the milestone commits; the drift log records the near-misses.
