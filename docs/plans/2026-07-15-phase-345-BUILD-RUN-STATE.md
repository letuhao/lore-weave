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

### PRE-P3 · Wiki/entity privacy fix (SD-1) — the FIRST milestone
| Slice | Status | Evidence / note |
|---|---|---|
| **PP-1** verify the existing `wiki_settings` PATCH guard + add a regression test | ⬜ | server.go:1073 EGRESS GUARD #3 already blocks it — VERIFY + test, do not rebuild |
| **PP-2** projection chokepoint: add `Kind` to glossary `bookProjection`; `fetchBookProjection` nulls `WikiSettings`/community_mode for a diary | ⬜ | closes checkWikiPublic + listUserWikiContributions + submitWikiSuggestion + residual blobs at once |
| **PP-3** `generateWikiStubs` + `internalUpsertEnrichments` consult projection `Kind` → refuse a diary | ⬜ | network read of the projection; no wiki_article/enrichment for a diary |
| **PP-4** entity-level guard: block wiki/enrichment/share for `is_self=false ∧ kind.code='colleague'` (mind `org` over-block) | ⬜ | novel character unaffected |
| **PP-5** pass2: thread diary-flag + self-anchor → coerce third-party `preference→statement` (diary-scoped ∧ subject≠self) | ⬜ | novel `preference` untouched |

### P3 · Scheduler + proactive (see the phase-3 plan; opens sealed)
| Slice | Status | Evidence / note |
|---|---|---|
| **WS-3.0** server-side distill-context resolution (book+BYOK-model+tz+lang) | ⬜ | 🆕 prereq; the real "Q8 follow-up" |
| **WS-3.1** Go `scheduler-service` (table+lease+scaffold) | ⬜ | re-impl mirroring usage-billing sweeper.go; language-rule.yaml row + own DB + compose |
| **WS-3.2** auto-EOD via the HTTP trigger | ⬜ | not a raw XADD |
| **WS-3.3** catch-up sweep (spend-capped) · **WS-3.4** away marker (nudge exclusion only) · **WS-3.6** content-free nudges · **WS-3.7** costed weekly rollup | ⬜ | |
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
SD-1..7 + P3-D1..6 + P4-D1..6 + P5-D1..12 — all in [`2026-07-15-phase-345-clean-seal.md`](2026-07-15-phase-345-clean-seal.md) §3/§7. Ordinary build-time calls get appended here as they're made.

## 5 · Parked (blocked ≠ stopped)
- **P-12** (diary encryption + backup-resistant crypto-shred) — human-owned separate goal (D-R24). Orthogonal.
- **Human-rating milestones** — P5 safety-eval + numeric-eval clearance (SD-7). Not code.

## 6 · Drift log (record the near-misses — an empty drift log is dishonest)
- *(build has not started; the 4-reviewer cold pass already caught 4 of my wrong plan claims — logged in the clean-seal §7)*

## 7 · Debt carried in (relevant to this build)
- **DBT-15** distiller uses the session model — a reasoning model silently empties the diary. Q8 dedicated non-reasoning distill model resolves this; WS-3.0 is its natural home.
- **DBT-12** char-based chunk sizing (CJK under-counts) — switch to the token estimator when the distiller job is wired.
- **Voice deferral** `D-CHATAI-VOICE-TWO-STORES` (settings vocab) — WS-4.0.
