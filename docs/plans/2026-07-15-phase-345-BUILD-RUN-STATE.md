# Phase 3/4/5 BUILD — RUN-STATE (the commitment file · re-read FIRST after any compaction)

**Created:** 2026-07-15 · **Track:** Work Assistant Phase 3/4/5 · **Mode:** **ONE long-run `/goal` for the WHOLE build** (human-directed 2026-07-15 — supersedes the earlier per-phase choice) · **HEAD at creation:** b1dcf20e3.

> This is the durable anchor (CLAUDE.md "GOAL COMMITMENT" — memory across compaction). The DESIGN lives in the sealed plans; do NOT re-litigate it from memory — re-read:
> - Sealed decisions + review resolutions: [`2026-07-15-phase-345-clean-seal.md`](2026-07-15-phase-345-clean-seal.md) (§3 register, §7 findings, §8 goal guardrails)
> - Per-phase plans: [`2026-07-13-work-assistant-phase3-scheduler-proactive.md`](2026-07-13-work-assistant-phase3-scheduler-proactive.md) · [`2026-07-15-work-assistant-phase4-voice.md`](2026-07-15-work-assistant-phase4-voice.md) · [`2026-07-15-work-assistant-phase5-reflection-coaching.md`](2026-07-15-work-assistant-phase5-reflection-coaching.md)

---

## 0 · Resuming after a compaction — do THIS first
1. Re-read this file (the slice board + registers below).
2. `git log --oneline -15`.
3. Re-read the current milestone's plan section (link above).
4. Continue at the first ⬜/🔵 slice. Never `git add -A` (concurrent sessions share this checkout — commit each slice with an explicit pathspec).

## 1 · The GOAL (ONE long-run goal for the whole build)
**Milestone order (dependency-correct):** `PRE-P3 wiki-fix` → `P3 scheduler` → `P4 voice` → `P5 reflection+gates+scorer-harness`. Run through ALL of them in one autonomous goal; the slice board (§3) is the "done" definition.
**Autonomous exit** = every §3 slice ✅-with-evidence, each milestone `/review-impl`'d + live-smoked, commits pushed. **P5's exit is "harness built + scorer quarantine-tier"** — NOT "eval passes / safety certified"; a self-run QWK or "safety passing" is a **drift violation** (those clear only in a later human-rating milestone).
**Don't stop for checkpoints** (the human prefers long uninterrupted runs). Stop-and-ask ONLY on: a sealed-decision (SD-1..7) conflict, a destructive/irreversible action, or the P5 human-rating boundary.

## 2 · Standing invariants (the bar — never lower silently)
- **Per-milestone `/review-impl`** (cold-start adversarial) before each milestone commits. Load-bearing everywhere here (privacy chokepoint, scheduler, proactive/voice seams, every P5 safety/eval slice).
- **Live-test gate**: cross-service milestones prove on a REAL stack (Neo4j :7688 / PG :5555 / a rebuilt image), not mocks — paste the output into the transcript.
- **Fix-bugs loop**: `/review-impl` findings are fixed + re-verified before the commit; the drift log (§6) records the near-misses.
- **Two human carve-outs (SD-7):** the coaching **safety eval** + **numeric eval** CANNOT be cleared by a code run. Build the mechanism + harness; the scorer ships quarantine-tier. A self-run QWK / "safety passing" is a **drift violation**.
- Tenancy/D16, provider-gateway, no-hardcoded-model, content-free-notifications — all the Phase-2 invariants still hold.

## 3 · SLICE BOARD (the only place "done" is defined — evidence string, not a checkmark)
`⬜ todo · 🔵 wip · ✅ done (evidence) · ⏸ deferred · 🅿️ parked`

### PRE-P3 · Wiki/entity privacy fix (SD-1) — ✅ **DONE (28074c2a7)** — the FIRST milestone
| Slice | Status | Evidence / note |
|---|---|---|
| **PP-1** verify the existing `wiki_settings` PATCH guard + regression test | ✅ | EGRESS GUARD #3 (server.go:1073) already blocks it; `TestDiaryEgress_WikiCannotBePublished_DB` + `TestWikiSettings_StillEditableOnANovel_DB` green |
| **PP-2** projection chokepoint (add `Kind`; null `WikiSettings` for a diary in `fetchBookProjection`) | ✅ | closes checkWikiPublic + contributions + suggest + residual blobs at ONE place; `TestFetchBookProjection_NullsWikiSettingsForADiary` green; all 3 readers nil-check (no panic) |
| **PP-3** `generateWikiStubs` refuses a diary (fail-closed `refuseDiaryWikiSurface`) | ✅ | enrichment covered by PP-4 entity-level instead (no hot-path network hop); `TestRefuseDiaryWikiSurface` green |
| **PP-4** entity-level `colleague` guard (enrichment 403 + BOTH stub query AND LLM-delegate paths) | ✅ | `TestEnrichments_RefusesAColleagueEntity_PP4` + `TestWikiGenDelegate_ExcludesColleague_PP4` green; **review H1 fix** closed the delegate leak; is_self dropped (test-DB gap; 'colleague' is the precise 3rd-party marker) |
| **PP-5** pass2 work-mode `preference→statement` coercion | ✅ | defense-in-depth (primary guard = `queue_diary_facts` forces 'statement'); `test_pp5_work_mode_coerces...` + `test_pp5_novel_mode_preserves...` green |

**Milestone VERIFY:** knowledge pass2+internal_extraction **88 passed**; glossary wiki/enrichment/chokepoint/PP4/delegate **ok**; book diary-egress **ok**. **/review-impl** (cold-start): PP-2/PP-3 solid; H1 delegate-leak FIXED+tested; H2/M1-3 documented as deliberate defense-in-depth. **LIVE-SMOKE** (glossary :8211 → book projection): diary(visibility=public)→**404**, novel(same blob)→**200** (proves the KIND guard, not book-not-found).

### P3 · Scheduler + proactive (see the phase-3 plan; opens sealed)
| Slice | Status | Evidence / note |
|---|---|---|
| **WS-3.0** server-side distill-context resolution (book+BYOK-model+tz+lang) | ✅ **DONE (b37a15ba7)** — chat trigger resolves book/model/tz server-side when omitted (posts only {user_id}); provider-registry `distill` capability (chat-validated, DBT-15); 422 when unresolvable. 2 new + 8 existing chat tests + provider default-models green. |
| **WS-3.1** Go `scheduler-service` (table+lease+scaffold) | ✅ **DONE (fcb84ae30)** — new Go service: `scheduled_agent_runs` + tick driver (SKIP-LOCKED lease/claim, re-arm, breaker; re-impl of the sweeper shape) + HTTPEnqueuer→chat trigger + full scaffold (go.mod, Dockerfile, language-rule row [lint PASS], compose :8213, own DB). 3 driver DB tests green; build+vet clean. **Opt-in WRITE path (row-on-toggle) → WS-3.2.** |
| **WS-3.2** auto-EOD via the HTTP trigger | ✅ **DONE (8a1f30133)** — `ComputeNextFireAt` (tz-aware local EOD) + `UpsertSchedule` (opt-in write path P3-D2) + `PUT /internal/schedules`; scheduler+api tests green. FE toggle proxy → DBT-14. |
| **WS-3.4** away marker · **WS-3.6** content-free nudges | ✅ **DONE (8d31985b4)** — `assistant_away_periods`+`IsAway`+`POST /internal/away`; driver SUPPRESSES a nudge on an away day (re-arms); nudge = content-free (T26), away-gated. Away-exclusion DB test green. |
| **WS-3.7** costed weekly rollup | ✅ **DONE (0b940998c core + 21d4687ca wiring)** — `roll_up_week` (recall the week's facts → `reduce_entry` → a supplement DRAFT, spend-capped) + chat trigger `/weekly-rollup` (WS-3.0 resolution, defaults the prior week) + WeeklyRollupConsumer + scheduler `weekly_rollup` enqueue. 3 worker + 1 chat test green. |
| **WS-3.3** catch-up sweep (spend-capped) | ✅ **DONE (ee3dee3c2)** — distill trigger `catchup_days` (bounded to 14) + scheduler daily eod_distill carries `catchup_days:3`. Chat catchup test green (100→15 bounded). |

**✅ P3 MILESTONE COMPLETE.** All slices WS-3.0/3.1/3.2/3.3/3.4/3.6/3.7 built + committed (WS-3.5/3.8 proactive seam deferred per the sealed plan). **Cold `/review-impl` ran → 2 HIGH + 3 MED + 1 LOW, ALL fixed + re-verified:** H1 (c20e2cf03 — the recurring re-arm used a raw interval → drift+DST; now persists tz + re-arms via `ComputeNextFireAt`), H2 (1be008500 — orphan opt-in path → added gateway `/v1/assistant/schedule` proxy), M1 (7ce0729ed — catch-up re-ran the LLM on kept days → pre-LLM kept-gate), M2 (8eede6248 — weekly rollup duplicated on redelivery → journal_kind='weekly' get-or-replace), M3 (local-day away check), L1 (job_kind enum). Review-verified-sound: no lost fire, breaker never wedges, fail-closed money/privacy resolution, content-free nudge. **LIVE-SMOKE (real stack, chat rebuilt):** WS-3.0 headless `{user_id}`→202 (resolved book+model+tz, entry_date server-computed); WS-3.3 `catchup_days:3`→days_enqueued:4; WS-3.7→202 (week 07-07..07-13). **Draft-production leg = `live infra unavailable: LM Studio` (Phase-1-proven).**
| ~~WS-3.5 / WS-3.8~~ | ⏸ DEFERRED | proactive seam — no v1 consumer under the pull-only seal |

### P4 · Voice (see the phase-4 plan)
| Slice | Status | Evidence / note |
|---|---|---|
| **WS-4.0** two-stores reconcile (prereq for WS-4.3 only) · **WS-4.1** shared-inner-generator refactor · **WS-4.2a** LLM-token billing · **WS-4.2b** STT/TTS usage plumbing (+ the unbuilt `lane` column) · **WS-4.3** retention→per-user (≤48h) · **WS-4.4** audio joins D-R27 erase · **WS-4.5** affordance gate (live bug) | ⬜ | lane column UNBUILT; sweeper EXISTS; voice NOT gated today |

### P5 · Reflection + coaching (see the phase-5 plan)
| Slice | Status | Evidence / note |
|---|---|---|
| **A** reflection: WS-5.1 notes · WS-5.2 detectors · WS-5.3 pull-draft · WS-5.4 setting/i18n · WS-5.5 closed-enum guard · WS-5.6 tombstone | ⬜ | ungated; but pattern-surfacing is safety-gated (X-2) |
| **Gate 1** WS-5.7 due_date+overdue (REUSE WS-2.6b) · WS-5.8 thread · WS-5.9 maintain_chain test | ⬜ | commitment type = 3 registries |
| **Gate 2** WS-5.10 judge≠actor + single-model degraded path | ⬜ | |
| **Gate 3** WS-5.11-15 safety: deterministic floor + LLM widener, 2 placements, eval HARNESS | ⬜ | eval CLEARANCE = human milestone |
| **Gate 4** WS-5.16-19 eval HARNESS only | ⬜ | QWK number = human milestone; never self-run |
| **Scorer** WS-5.20-23 quarantine-tier + WS-5.24 longitudinal | ⬜ | ships quarantine-tier, permanently until human eval |

## 4 · Decision register (sealed — do not override without the human)
SD-1..7 + P3-D1..6 + P4-D1..6 + P5-D1..12 — all in [`2026-07-15-phase-345-clean-seal.md`](2026-07-15-phase-345-clean-seal.md) §3/§7. Ordinary build-time calls appended here:

- **D-B1 (WS-3.0 design, sealed 2026-07-15):** the headless distill-context resolution lives IN the chat
  trigger `POST /internal/chat/assistant/distill` — its `book_id`/`model_source`/`model_ref`/`entry_zone`
  become OPTIONAL and resolve SERVER-SIDE when omitted, so the scheduler (WS-3.2) POSTs only `{user_id}`.
  Substrate (all EXISTS): book_id ← book-service `GET /internal/books/diary?user_id=`; model ← provider-
  registry `GET /internal/default-models/{capability}?user_id=` trying **`distill` then falling back to
  `chat`** (a NEW `distill` capability added to `defaultModelCapabilities`, validated against `chat` like
  `planner` — lets a user pin a dedicated NON-reasoning distill model per DBT-15/Q8, else inherits chat);
  entry_zone ← auth `/internal` profile `timezone` (DBT-11, fd4702818), default UTC; language default 'en'.
  A user with NO resolvable model → 422 (the scheduler logs + skips that user's tick; never a silent no-op).

## 5 · Parked (blocked ≠ stopped)
- **P-12** (diary encryption + backup-resistant crypto-shred) — human-owned separate goal (D-R24). Orthogonal.
- **Human-rating milestones** — P5 safety-eval + numeric-eval clearance (SD-7). Not code.

## 6 · Drift log (record the near-misses — an empty drift log is dishonest)
- *(planning) the 4-reviewer cold pass caught 4 of my wrong plan claims — logged in the clean-seal §7.*
- **PRE-P3 review H1 (caught by /review-impl):** I guarded PP-4 (`ek.code<>'colleague'`) only on the DETERMINISTIC wiki-stub query and missed the LLM DELEGATE path (`resolveWikiGenEntities` + explicit-Regenerate) — the actual AI-biography path, PP-4's stated cross-book target. The diary was still safe (PP-3 blocks both), but the cross-book colleague leak survived on the worse path. Fixed + added `TestWikiGenDelegate_ExcludesColleague_PP4`. **Same shape as the repo's recurring lesson: I guarded the path in front of me and missed the adjacent one; the cold review caught it.**
- **PRE-P3 review H2 (caught by /review-impl):** PP-5 sits on a path diary facts don't traverse (the real guard is `queue_diary_facts`). Not a leak (fails safe) — re-documented honestly as defense-in-depth rather than let it read as THE guard.
- **My "live one-click hole" framing was overstated** (planning) — EGRESS GUARD #3 already blocked the PATCH; corrected in clean-seal §2 before build.
- **WS-3.1 recordSuccess pgx type bug (caught by the driver DB test):** `$2` used both directly and in `$2 + interval` → "inconsistent types deduced for parameter" (SQLSTATE 42P08); the re-arm silently failed and next_fire_at didn't advance. Fixed with `$2::timestamptz`. **The DB test caught it — a mock would not have.**
- **P3 review H1 (caught by /review-impl):** the recurring re-arm advanced next_fire_at by a RAW +1d/+7d interval off the tick instant — so the local fire time drifted ~1 tick/day (unbounded) AND shifted ±1h across DST, never self-correcting. My WS-3.2 ComputeNextFireAt was called ONLY at upsert and abandoned on recurrence; there was no `timezone` column to recompute from. **A silently-broken design that all the unit tests passed** (they only checked "future", not "the right local time"). Fixed: persist tz + re-arm via ComputeNextFireAt.
- **P3 review M1/M2 (caught by /review-impl):** the catch-up re-ran the LLM map-reduce on already-kept days (the kept-check was only at the write seam, AFTER the LLM — silent budget waste every day); the weekly rollup wrote a 'supplement' that book-service always creates anew (duplicate weekly reviews on any redelivery). Both real bugs a green unit suite couldn't see; fixed with a pre-LLM kept-gate + a get-or-replace 'weekly' kind.
- **P3 review H2 (caught by /review-impl):** the entire opt-in write path was an ORPHAN — no gateway/FE caller, so the scheduler was dormant end-to-end (built-mounted-unreachable). Fixed with a gateway proxy (the FE toggle is DBT-14).

## 7 · Debt carried in (relevant to this build)
- **DBT-15** distiller uses the session model — a reasoning model silently empties the diary. Q8 dedicated non-reasoning distill model resolves this; WS-3.0 is its natural home.
- **DBT-12** char-based chunk sizing (CJK under-counts) — switch to the token estimator when the distiller job is wired.
- **Voice deferral** `D-CHATAI-VOICE-TWO-STORES` (settings vocab) — WS-4.0.
