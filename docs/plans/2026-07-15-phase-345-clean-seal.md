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

## 2 · Pre-Phase-3: the LIVE wiki/entity privacy hole (R5/R6/R7)

**Human decision (SD-1): fix this BEFORE Phase 3, inside this upcoming goal.**

**The hole (re-verified 2026-07-15, still open):** a diary reuses the book GUI (D14), so a diary user has a one-click path to publish **AI-written biographies of every colleague in their diary** to the open internet. `checkWikiPublic` (`glossary wiki_handler.go:1447`) reads `books.wiki_settings.visibility=='public'` **with no `kind='diary'` guard**; `PATCH /v1/books/:id` does not reject a `wiki_settings` mutation on a diary; `generateWikiStubs` auto-writes prose from the KG; `entity_enrichments` manufactures AI "dimensions" about an entity; unauthenticated readers can list/read; `community_mode` invites public edit suggestions. D10's "un-shareable on every path" is **false as written** — the wiki/enrichment paths were missed.

**The fix — enumerate EVERY publication surface, key on immutable `kind='diary'`, each with a consumed-by-EFFECT test** (spec 08 R5/R6/R7):

| Slice | Guard | Where | Test |
|---|---|---|---|
| PP-1 | `PATCH /v1/books/:id` **rejects any `wiki_settings` mutation** on a `kind='diary'` book | book-service `server.go:887` | a diary PATCH with `wiki_settings` → 4xx; a novel unaffected |
| PP-2 | `generateWikiStubs` **refuses** diary books | glossary wiki | no wiki_article rows for a diary entity |
| PP-3 | `entity_enrichments` **refuses** diary/colleague entities | glossary enrichment | no enrichment row manufactured for a diary colleague |
| PP-4 | `checkWikiPublic` **fails closed on `kind='diary'`** even if the JSONB flag somehow got set (defense-in-depth — treat the legacy blob as untrusted) | glossary wiki_handler.go:1447 | a diary with `visibility=public` forced in the blob → still 404 on the public wiki read |
| PP-5 | **Entity-level guard (R6):** mark real people (`kind='colleague'` / a `third_party` predicate) and block wiki + enrichment + share at the ENTITY level (entities can be merged/moved/referenced from a non-diary book) | glossary entity | a colleague entity referenced from a novel is still wiki/enrichment-blocked |
| PP-6 | **Forbid `preference`-type facts whose subject is a third-party entity (R7)** — restrict to `statement` (what the user reports X said, on a date); a `preference` about a real person is a durable behavioral-trait claim derived from one account | knowledge `pass2_writer.py` | a third-party `preference` fact is rejected/coerced to `statement`, with a test |
| PP-7 | **Export** path honors the same guards | export surface | a diary export never emits a colleague wiki/enrichment artifact |

**Size:** M (cross-service: book + glossary + knowledge), risk floor = privacy. All guards are fail-closed + consumed-by-effect. This is the security slice that lets everything after it proceed safely.

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

- **Decisions sealed:** SD-1/2/3 (human) + P3-D1..6 + P4-D1..6 + P5-D1..12 (ordinary, recorded above).
- **Parked (unchanged):** P-12 (D-R24).
- **Open-for-the-human-at-build-time:** the eval threshold X, the KB framework list (both genuinely empirical/external, not clean-pass decidable).
