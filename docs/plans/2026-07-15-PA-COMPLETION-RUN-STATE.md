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
| **C1** distiller token sizing | SD-C1 | ⬜ | worker-ai: swap char-window → `loreweave_context.tokens.estimate_tokens` (o200k). Add the dep. |
| **C2** reflection v2 (co-occurrence notes + live tombstone) | SD-C2 | ⬜ | worker-ai `ChatAssistantClient` → notes into `run_weekly_reflection`; `reflection_dismissals` table + dismiss endpoint → tombstone LIVE. |
| **C3** coaching scorer → rubric SoT (quarantine) | SD-C3 | ⬜ | evaluate.py `resolve_active_rubric` (code `charter.rubric_code` default `interview_v1`) → 409 no-rubric; `coerce_dimensions`; quarantine STAYS True. |
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
- *(append as the build runs)*

## 7 · Debt / follow-on carried
- **SD-7 human-rating milestones** — safety-eval cert + numeric-eval QWK clearance. NOT code; gates a later milestone. The scorer stays quarantine-tier until then.
- Anything discovered during C1..C8 that clears the defer gate lands here.
