# Personal Assistant COMPLETION — BUILD RUN-STATE (the durable commitment)

## 0 · Resuming after a compaction — do THIS first
Re-read THIS file, then `git log --oneline -20`, then continue. Never re-litigate a sealed
decision (SD-C1..8, H1..4) from memory — re-read [`2026-07-15-personal-assistant-completion-seal.md`](2026-07-15-personal-assistant-completion-seal.md).

## 1 · The GOAL
Clear EVERY code-doable Personal-Assistant remainder (C1..C8 below) so the feature is complete.
A serious QC phase runs AFTER. **Autonomous exit** = every §3 slice ✅-with-evidence, each
milestone `/review-impl`'d + live-smoked, commits pushed. **NOT in this phase (SD-7):** the
coaching safety-eval + numeric-eval CLEARANCE — human milestones; the scorer ships quarantine-tier.

## 2 · Standing invariants (the bar — never lower silently)
- Never `git add -A` (shared checkout — explicit pathspec per slice). Commit each slice promptly.
- Per milestone: PASTED green tests + a PASTED cross-service live-smoke (where it crosses services)
  + a cold-start `/review-impl` with findings fixed + re-verified.
- Ordinary tech decisions: make them + record in §4. A SEALED decision (SD-C1..8, H1..4) may NOT be
  overridden without the human — if one looks wrong, park + flag.
- **SD-7:** the coaching SCORE stays quarantine-tier; a committed QWK / "safety passing" is a DRIFT
  VIOLATION. Wiring the rubric (C3) is SD-7-safe.
- Settings & Config Boundary: `proactive_enabled`, encryption toggles, retention — per-user, fail
  closed, effective-value-visible. Provider-gateway: STT/TTS pricing resolves from provider-registry,
  never hardcoded. Tenancy: every new table carries an owner/scope key.
- Stop + ask ONLY if a sealed decision turns out wrong, an action is destructive/irreversible/risks
  real user data (esp. C5 encryption — a wrong DEK migration is data-loss), or you reach the SD-7
  human boundary. Otherwise keep going.

## 3 · SLICE BOARD (evidence string, not a checkmark)
| Slice | SD | Status | Evidence / note |
|---|---|---|---|
| **C1** distiller token sizing | SD-C1 | ✅ | worker-ai `distiller.py` windows in TOKENS via `loreweave_context.estimate_tokens` + NEW `split_to_token_budget` (single home in the SDK, not duplicated). `WINDOW_CHARS`→`WINDOW_TOKENS`(12k), `GIANT_PASTE_CHARS`→`GIANT_PASTE_TOKENS`(40k). **Tests:** SDK 7 passed + worker-ai distiller/job/reextract 55 passed (pasted). **Smoke:** real-import — a 20k-char CJK day: OLD char-window let a chunk reach ~12.6k tok (overflows small models); NEW caps every chunk ≤12k tok (worst 11999); same-size Latin day now 1 chunk vs 2. **Cold review:** cold agent, no HIGH, standards clean, `split_to_token_budget` lossless (2000-string stress); 2 LOW test-strengthenings fixed + re-green; 1 MED → debt D-DISTILL-WINDOW-MODEL-AWARE (§7). Single service — no cross-service seam. |
| **C2** reflection v2 (co-occurrence notes + live tombstone) | SD-C2 | ✅ | worker-ai `ChatAssistantClient` fetches the week's notes (→ co-occurrence fires) + dismissed pattern_keys (→ tombstone) and threads them into `run_weekly_reflection`. New chat `reflection_dismissals` table (owner-scoped, `UNIQUE(owner,pattern_key)`) + `PUT /assistant/reflection-dismiss` (idempotent) + `GET /assistant/reflection-dismissals`. **Tests:** worker reflection 21 + job; chat dismiss-router 4 + dismissals-db 2 (real PG). **Live-smoke (PASTED):** worker-ai real `ChatAssistantClient` → running chat-service :8212 → seed 2 notes → co-occurrence `co_occurrence:migration` surfaced; dismiss (idempotent 2×) → fetched back → pattern tombstoned (empty). **Cold review:** 1 MED (notes feed the fail-CLOSED Gate-3 safety screen but were swallowed on transport error) → FIXED: `list_reflection_notes` now raises `ChatAssistantUnavailable` → consumer un-ACKs/retries (re-smoked: down-endpoint raises); LOW-3 router param-assert added; LOW-2 (dismiss-WRITE producer) = C8's FE. Debt: D-REFLECTION-FACTS-RECALL-FAIL-CLOSED (§7). |
| **C3** coaching scorer → rubric SoT (quarantine) | SD-C3 | ✅ | evaluate.py resolves the SoT `coaching_rubrics` standard (`charter.rubric_code` default `interview_v1`) → **409 refuse-to-score** if none (before any LLM spend/persist); `coerce_dimensions` rebuilds the N-dim score server-authoritatively; the rubric's dims are threaded into the judge prompt. **quarantine STAYS True (SD-7)** — verified by cold review; `rubric.tier` deliberately unread. **Tests:** evaluate 42 (unit + router C3 class: 409, invented-dropped/omitted→None/clamp, quarantine-true, dims-reach-prompt). **Live-check (PASTED):** real seeded `interview_v1` resolves w/ 3 dims tier=quarantine; bogus code→None (409 path); coercion server-authoritative. **Cold review:** SD-7 VERIFIED INTACT (no drift); 1 MED (NaN/Infinity score → int() raise outside try → 500) FIXED (math.isfinite guard + test); LOW-2 empty-dims→None test + LOW-3 tier-independence comment added. Single service (chat) — the judge-LLM hop via provider-registry is pre-existing infra, unchanged. |
| **C4** wiki `is_person` structural flag | SD-C4 | ⬜ | glossary `book_kinds.is_person`; seed colleague+character; migrate/backfill; 4 filters → is_person; seed-drift test. |
| **C5** diary encryption + crypto-shred | SD-C5 | ⬜ | book diary chapters encrypted at rest (per-user DEK via `loreweave_crypto`); D-R27 erase DESTROYS the DEK (backup-resistant). Dedicated key ≠ JWT_SECRET. |
| **C6** billing STT/TTS cost-model + spend lane | SD-C6 | ⬜ | usage-billing `lane` ×3 (T-8) + STT(per-min)/TTS(per-char) pricing from provider-registry; price the voice_stt/voice_tts records. |
| **C7** proactive-turn seam (WS-3.5/3.8) | SD-C7 | ⬜ | `chat_messages.initiated_by`; headless proactive entrypoint; `proactive_enabled` per-user OFF; scheduler `weekly_reflection`/`proactive_nudge` job_kinds; away-gated. |
| **C8** FE surfaces | SD-C8 | ⬜ | reflection card + dismiss; coaching scorecard + quarantine badge (no trend); capture-status strip verify. |

## 4 · Decision register (sealed — do not override without the human)
H1..H4 + SD-C1..C8 — all in [`2026-07-15-personal-assistant-completion-seal.md`](2026-07-15-personal-assistant-completion-seal.md) §1/§2. Ordinary build-time calls appended here as the build runs.

## 5 · Parked (blocked ≠ stopped)
- *(none yet)*

## 6 · Drift log (record the near-misses — an empty drift log is dishonest)
- **C1 near-miss (accepted):** re-interpreting the sealed budget number 12_000 as TOKENS (was chars)
  QUADRUPLES the Latin/English window (3k→12k tok). Cold review flagged this would overflow a
  hypothetical 8k-context model (and it's a Latin regression there). Accepted, NOT reverted: the seal
  is explicit ("same number, now tokens"), and the deployed distill model (Gemma-4 26B QAT) runs at
  **200K context** — 12k is trivially safe. For CJK the change is strictly SAFER (12k tok cap vs the
  old ~12.6k). Tracked as D-DISTILL-WINDOW-MODEL-AWARE for robustness against a future small-context
  BYOK model. Two LOW test gaps the review found (lone-char-over-budget; CJK giant-paste) were fixed
  in-slice, not deferred.

- **C2 near-miss (fixed):** the reflection_notes fetch was first written best-effort (swallow → `[]`),
  which would have silently DOWNGRADED the fail-closed Gate-3 safety screen on a chat-service blip
  (a note-borne-distress week could be written as an upbeat reflection, terminal, never retried).
  Cold review caught it; fixed to raise → retry. The review's premise that `recall_facts_range`
  already "propagates" was WRONG (it also swallows) — so the facts path has the same latent gap,
  tracked as D-REFLECTION-FACTS-RECALL-FAIL-CLOSED rather than assumed-safe.

- **C3 near-miss (fixed):** the SD-7 quarantine held (defaulted True, never derived from rubric.tier)
  — cold review confirmed intact. Separately, the new dimension path had a NaN/Infinity → 500 crash
  (json.loads accepts those bare tokens; `int(nan)` raises, outside evaluate's try/except). The sibling
  `_clamp_score` already caught it; the new path didn't. Fixed with a `math.isfinite` guard + test.
  The `rubric.tier=='validated'` field is the seam a future author could grab to wrongly clear
  quarantine — commented at the write site as an SD-7 tripwire.

## 7 · Debt / follow-on carried
- **SD-7 human-rating milestones** — safety-eval cert + numeric-eval QWK clearance. NOT code; gates a later milestone. The scorer stays quarantine-tier until then.
- **D-DISTILL-WINDOW-MODEL-AWARE** (from C1 cold review, MED) — the distiller's `window` default is a
  fixed 12k tokens (per SD-C1). The mechanism to pass a smaller window already exists (it's a param);
  what's missing is wiring it to the *resolved target model's* context length so a small-context BYOK
  model gets `window = min(12_000, ctx − prompt_overhead − output_reserve)` instead of a fixed 12k.
  Gate #2 (needs the distill job to resolve the model's context length — a real feature, not a quick
  edit). NOT urgent: the deployed model is 200K-context. Trigger: a user configures an ≤8k BYOK distill
  model. Default stays 12k per the seal.
- **D-REFLECTION-FACTS-RECALL-FAIL-CLOSED** (from C2 cold review, LOW/MED-adjacent) — `KnowledgeClient.
  recall_facts_range` swallows a transport/non-200 to `[]` (best-effort), same as the notes fetch did
  before the C2 fix. The diary FACTS are the dominant input to the fail-closed Gate-3 safety screen, so
  on a knowledge-service blip a reflection can still be written having screened fewer facts. C2 fixed
  the NEW input (notes); making `recall_facts_range` distinguish transport-error from genuine-empty is a
  SHARED-contract change (it's also used by `roll_up_week`, where empty-on-error is currently the
  intended "nothing to summarize" degrade) — gate #2 (structural, needs a per-caller retryable variant).
  Trigger: harden the reflection safety path fully. NOT urgent (facts-only distress + a concurrent blip).
- Anything discovered during C1..C8 that clears the defer gate lands here.
