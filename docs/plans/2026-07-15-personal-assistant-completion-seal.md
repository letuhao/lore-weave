# Personal Assistant — COMPLETION phase · CLARIFY + SEAL

**Goal of this phase:** clear EVERY remaining code-doable Personal-Assistant item (all defers +
debts) so the feature is complete. A serious QC phase runs AFTER. The only things this phase
does NOT clear are the two SD-7 human-rating milestones (they need human-labeled data, not a run).

Predecessor: [`2026-07-15-phase-345-BUILD-RUN-STATE.md`](2026-07-15-phase-345-BUILD-RUN-STATE.md)
(PRE-P3 · P3 · P4 · P5 all done + live-smoked + cold-reviewed). This seal covers what's left.

---

## 1 · Human decisions (asked + answered 2026-07-15)

| # | Decision | Answer (SEALED) |
|---|---|---|
| H1 | Proactive-turn seam (WS-3.5/3.8) — build or defer? | **BUILD NOW** |
| H2 | Billing STT/TTS cost-model (per-min/per-char + spend lane) — build or defer? | **BUILD NOW** |
| H3 | Diary encryption + crypto-shred (P-12/D-R24) — pull in or keep separate? | **BUILD NOW** |
| H4 | Coaching scorer wiring under SD-7 — wire now or leave dormant? | **WIRE NOW, quarantine-tier** |

**Everything is in scope.** SD-7 remains: the coaching SCORE stays quarantine-tier (shown,
never trended) until the human-rating milestone; wiring it to the real rubric is SD-7-safe and
does NOT clear the number.

## 2 · Sealed decisions (SD-C1..C8) — the how, so the build is unambiguous

- **SD-C1 · DBT-12 (distiller token sizing).** Replace the distiller's char-based windowing with
  the shared script-aware estimator `loreweave_context.tokens.estimate_tokens` (o200k; CJK/VI ≈
  1–1.7 tok/char, not the flat 4). Add `loreweave_context` to worker-ai deps; do NOT duplicate the
  estimator. The window BUDGET stays the same number, now interpreted as tokens.
- **SD-C2 · Reflection v2 (co-occurrence live + tombstone live).** (a) worker-ai gets a
  `ChatAssistantClient` that fetches `/internal/chat/assistant/reflection-notes` → threaded into
  `run_weekly_reflection` → `reflect_week(notes=…)` so the co-occurrence detector fires. (b) A new
  **`reflection_dismissals`** table (`owner_user_id, pattern_key`, UNIQUE) + an internal write
  (`/assistant/reflection-dismiss`) + read, so WS-5.6's tombstone drop is LIVE (dismissed keys
  fetched into `reflect_week`). Owner-scoped (Per-user tier).
- **SD-C3 · D-COACHING-SCORER-WIRE (H4).** `evaluate.py` resolves a rubric via
  `resolve_active_rubric(pool, code)` — code from `charter.rubric_code`, default `interview_v1`;
  **no rubric ⇒ 409 refuse-to-score** (P5-D5). It builds `Scorecard.dimensions` via
  `coerce_dimensions` (server-authoritative). `Scorecard.quarantine` STAYS True (SD-7). The legacy
  STAR fields remain for back-compat; dimensions are the forward path.
- **SD-C4 · D-WIKI-PERSON-FLAG.** Add a structural `is_person BOOLEAN` on `book_kinds`
  (glossary-service). System seed marks the person-kinds (`colleague`, `character`) `is_person=true`;
  a migration backfills them. Replace the 4 `code='colleague'` wiki-gen/enrichment filters with an
  `is_person` filter (so a renamed/custom person-kind is also excluded). A user-settable flag on
  custom kinds. + a seed-drift test asserting the System person-kinds carry the flag.
- **SD-C5 · P-12 diary encryption + crypto-shred (H3).** Diary chapter content encrypted AT REST
  with a per-user **DEK via the existing `loreweave_crypto` DEK client** (already an in-repo SDK).
  Crypto-shred = on D-R27 assistant-data erasure, DESTROY the user's diary DEK so any backup
  copy of the ciphertext is permanently unreadable (backup-resistant — the whole point of D-R24).
  Encrypt only the diary book's chapters (`kind='diary'`), not all books. A dedicated encryption
  key (never `JWT_SECRET`).
- **SD-C6 · Billing STT/TTS cost-model + spend lane (H2).** Build the spend **`lane` ×3 tables
  (T-8)** in usage-billing + **STT (per-audio-minute) / TTS (per-character)** pricing resolved
  from **provider-registry** (NO hardcoded pricing — the model's rate lives with the model). The
  WS-4.2b `voice_stt`/`voice_tts` records get priced via the lane. The lane also carries the
  assistant vs interactive spend separation the P5 scorer/reflection share.
- **SD-C7 · Proactive-turn seam WS-3.5/3.8 (H1).** Per phase-3 §4 mini-spec: `chat_messages.
  initiated_by` (enum: `user` | `assistant_proactive`), a **headless proactive entrypoint** in
  chat-service that threads a synthetic prompt through grounding, and a **`proactive_enabled`
  per-user setting (default OFF, opt-in** — a spend/interruption-causing toggle fails closed).
  WS-3.8 = the weekly reflection delivered as a proactive turn/notification (reuses the
  D-REFLECTION-WIRE consumer output). The scheduler gains `weekly_reflection` + `proactive_nudge`
  job_kinds (already have the enum pattern). Away-gated like the nudge.
- **SD-C8 · FE surfaces.** (a) The **reflection card** — render the weekly reflection draft +
  patterns, each with a **dismiss** button (→ SD-C2 dismissal). (b) The **coaching scorecard** —
  render N dimensions + a **quarantine badge**; a quarantine score is shown but **EXCLUDED from any
  trend line** (WS-5.24/5.22). (c) The **capture-status strip** already exists (WS-1.6) — verify it
  reads the persisted decision. Server is SoT; no user data in localStorage.

## 3 · SD-7 carve-out (UNCHANGED — cannot be cleared by this phase)
The coaching **safety-eval certification** (human-labeled distress corpus) and **numeric-eval
clearance** (QWK ≥ threshold, N≥50 × ≥2 human raters) are HUMAN milestones. This phase builds the
mechanism + harness + wires the scorer QUARANTINE-tier; a committed QWK / "safety passing" from a
self-run is a DRIFT VIOLATION. The scorer is shown-never-trended until a person certifies it.

## 4 · Slice board (dependency-ordered) — the "done" definition for the new goal
Each slice: committed with an explicit pathspec, marked ✅ with an evidence string, PASTED green
tests, a PASTED cross-service live-smoke where it crosses services, and a cold-start /review-impl.

| Slice | SD | Size | Services |
|---|---|---|---|
| **C1** distiller token sizing | SD-C1 | S | worker-ai |
| **C2** reflection v2 (co-occurrence notes + live tombstone) | SD-C2 | M | worker-ai + chat |
| **C3** coaching scorer → rubric SoT (quarantine) | SD-C3 | M | chat |
| **C4** wiki `is_person` structural flag | SD-C4 | M | glossary |
| **C5** diary encryption + crypto-shred | SD-C5 | L | book + chat (+ crypto SDK) |
| **C6** billing STT/TTS cost-model + spend lane | SD-C6 | L | usage-billing + provider-registry + chat |
| **C7** proactive-turn seam (WS-3.5/3.8) | SD-C7 | 🔴 L | chat + scheduler + worker-ai |
| **C8** FE surfaces (reflection card, coaching scorecard+quarantine, dismiss) | SD-C8 | M-L | frontend |

**Autonomous exit** = every slice ✅-with-evidence + review + live-smoke; commits pushed. The two
SD-7 human milestones are explicitly OUT (they gate a later human-rating milestone, not this phase).
