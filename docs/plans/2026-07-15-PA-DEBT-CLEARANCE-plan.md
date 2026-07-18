# Personal Assistant — COMPLETENESS AUDIT + DEBT-CLEARANCE plan

**Date:** 2026-07-15 · **HEAD:** 84b9dcfa4 · **Predecessors:** the whole PA build —
[`2026-07-11-work-assistant-RUN-STATE.md`](2026-07-11-work-assistant-RUN-STATE.md) (Ph0–2) ·
[`2026-07-15-phase-345-BUILD-RUN-STATE.md`](2026-07-15-phase-345-BUILD-RUN-STATE.md) (Ph3–5) ·
[`2026-07-15-PA-COMPLETION-RUN-STATE.md`](2026-07-15-PA-COMPLETION-RUN-STATE.md) (C1–C8).

This plan is the output of a **code-verified** completeness audit (5 cold subagents, one per disjoint
service cluster — not a doc re-read). It exists because a debt list overstates reality ~40–50% of the
time (repo lesson `debt-batches-list-is-stale-verify-first`); every row below was checked against the
tree with a `file:line`. **QC / acceptance is the NEXT discussion — this plan is the build-scope only.**

---

## 1 · AUDIT VERDICT

### 1a · Features — ✅ 100% built, nothing orphaned-unbuilt
Every PA feature across Phases 0–5 + the C1–C8 completion is built, tested, and (where cross-service)
live-smoked. The one thing worth re-verifying — the **Phase-2 remainder** (WS-2.6 D17 amendment +
WS-2.10 employment epoch), which older docs still show "parked gate-#2" — is in fact **fully shipped**
on HEAD in a separate track: all four D17 verbs (amend-reextract `0f51f6116`, supersede `dfaf75cba`,
forget-person+redaction `3cb7f2a08`/`06ef6cae7`, merge `365179e15`) + the epoch close/isolate/
export-purge (`f22b31b07`/`370c8adee`), each live-proven vs real Neo4j/PG. **Phase 2 is genuinely
complete** — that stale "parked" label is the only doc-drift found on the feature axis.

### 1b · The real gap — 3 shipped features are UNREACHABLE
The repo's own lesson `built-mounted-unreachable`: shipped + mounted + green can still be un-usable. Three
features are built + tested but a user cannot actually reach their value today:

| # | Feature | Built | Why unreachable | Verified |
|---|---|---|---|---|
| **G1** | Weekly-reflection **pattern dismiss** | dismiss chain FE→BFF→chat tombstone fully built+tested; detectors compute + tombstone-filter the structured patterns | `useReflection.ts:14` passes `patterns=[]` **always**; `run_weekly_reflection` renders patterns to prose and persists ONLY the prose (`reflection_job.py:293-302`) — the structured patterns are discarded, so the dismiss buttons never render live | ✅ |
| **G2** | **Coaching scorecard** (+ SD-7 quarantine/trend-exclusion) | `CoachingScorecard.tsx` + `scorecardTrend.ts` built+tested; backend persists the `scorecard` output (`evaluate.py:261`) | not imported/mounted anywhere; no `getScorecard` in `api.ts`; no gateway read route; the interview-practice result view that would host it **does not exist** | ✅ |
| **G3** | **Proactive check-in delivery** | `proactive-turn` persists a discoverable, deduped, book-bound `assistant_proactive` message | emits **no** notification/badge (unlike `nudge`, which POSTs notification-service) — an opted-in user only sees it if they happen to open the app | ✅ |

These three are the honest answer to "are all features complete?" — **the mechanisms shipped; the
last-mile reachability did not.**

### 1c · Debt — re-verified, and RECLASSIFIED
The completion-phase §7 carried 12 debt rows, most labelled "gate-#2 deferrable." **Code verification
flipped ~8 of them to BUILD-NOW** — the infra each needs already exists in-repo, so per the anti-laziness
rule ("missing infra I could write here" ≠ blocked) they are buildable, not deferrable. Two are
privacy/safety-adjacent and hit the fix-now default. The genuinely-deferrable remainder earns its gate
below. **Net: the feature is functionally complete; the residual is a real but bounded clearance list,
lighter than the docs implied on reachability and heavier on "you said defer but it's actually buildable now."**

---

## 2 · SLICE BOARD — the code-doable clearance (each: pasted tests + cross-service live-smoke where it crosses services + cold `/review-impl`)

`⬜ todo` · dependency-ordered within a group · SIZE by complexity+risk.

### Group R — Reachability (turn the 3 shipped-but-unreachable features on) — HIGHEST VALUE
| Slice | Was | Size | What it takes | Evidence bar |
|---|---|---|---|---|
| **R1** reflection patterns feed + live dismiss (G1 / D-REFLECTION-PATTERNS-FEED) | ⬜ | M | Persist the (already tombstone-filtered) structured patterns alongside the `reflection` entry (JSONB col or small table) → a read route (BFF→chat/book) → feed `useReflection.patterns`. Compute + tombstone already exist in `reflection_job.py`. | live: reflection with a co-occurrence pattern → FE renders a dismiss chip → dismiss → tombstoned → gone on refresh |
| **R2** coaching scorecard read + minimal mount (G2 / D-COACHING-SCORECARD-MOUNT) | ⬜ | M | BFF scorecard-read proxy → chat `scorecard` read → `api.getScorecard` → mount `CoachingScorecard` in a minimal interview-practice **result** panel. (The full practice *flow* is L / next-phase; the minimal result surface that makes the scorecard reachable is M.) SD-7 quarantine badge + trend-exclusion already built. | live: a real `evaluate` run → scorecard fetched → rendered with the quarantine badge; a quarantine score is NOT trended |
| **R3** proactive delivery notification (G3 / D-PROACTIVE-DELIVERY) | ⬜ | S | After the proactive message commits, emit a **content-free** notification (mirror `nudge`'s content-free pattern; notification-service is reachable). ⚠ builder note: `driver.go:251` posts to an *unregistered* `/internal/notifications/assistant-nudge` sub-route — use the registered generic sink `POST /internal/notifications/` or add the route. Optional FE badge event. | live: opted-in proactive turn → a content-free notification row lands (no content leak); opted-out → none |

### Group P — Privacy / safety / crypto (fix-now default) 
| Slice | Was | Size | What it takes | Note |
|---|---|---|---|---|
| **P1** wiki `is_person` on the USER tier (D-WIKI-PERSON-USER-TIER) | ⬜ | S | Thread `is_person` across the 3 user-tier write sites: `createUserKind` struct+INSERT, the HTTP update `setClauses`, and `createUserKindTool` (MCP). Column already migrated; adopt-clone already carries `uk.is_person`; mirror the book-tier threading. | **CONFIRMED privacy leak:** a hand-authored user-tier person kind adopted into a book yields `is_person=false` → a real person can receive an AI biography. Primary system→book path IS protected; this is the residual hole. |
| **P2** reflection facts fail-closed (D-REFLECTION-FACTS-RECALL-FAIL-CLOSED) | ⬜ | S | Add a `fail_closed=True` variant of `recall_facts_range` that raises `ChatAssistantUnavailable` on transport/non-200; call it from `reflect_week`; leave `roll_up_week` on best-effort. The consumer already un-acks on that exception. | **safety:** facts are the dominant input to the fail-closed Gate-3 distress screen; today a KG blip silently screens fewer facts. Same fix the C2 notes-fetch already got. |
| **P3** DEK hardening bundle | ⬜ | M | Three cheap crypto safeties in book/auth: (a) **multi-consumer tripwire** (D-DEK-MULTICONSUMER-TRIPWIRE, XS) — a repo-scan test that reds if a 2nd service reads `user_deks`/imports `DEKClient`, so "erase my diary" can't silently shred a future chat/knowledge consumer; (b) **shred audit row + dedicated token** (DBT-9, M) — mirror the `mcp_call_audit` precedent for a durable `dek_shred_audit` row + gate the DELETE behind a `DEK_SHRED_TOKEN` distinct from the shared internal token; (c) **generic reader decrypt** (D-DIARY-GENERIC-READERS-DECRYPT, S) — `getChapterContent` (`server.go:2164`) returns base64 ciphertext for a diary chapter; branch on `body_encrypted` to owner-gated-decrypt or 409. | diary is the SOLE DEK consumer today (verified) so no live data risk; these harden against the next consumer + give the platform's most destructive op a forensic trail. |
| **P4** diary shred durable retry (D-DIARY-SHRED-OUTBOX-RETRY) | ⬜ | M | Route `eraseDiaryBook`'s crypto-shred through the **existing** book-service transactional outbox (`outbox.go:18`) → a relay that retries auth's already-idempotent DELETE until 204, so a transient blip can't leave the DEK alive (backups decryptable). | immediate row-delete already succeeds; this closes backup-resistance on a blip. |

### Group B — Billing / correctness
| Slice | Was | Size | What it takes | Note |
|---|---|---|---|---|
| **B1** lane budget enforce + by-lane report (D-LANE-BUDGET-ENFORCE) | ⬜ | M | Thread `purpose`/`lane` into the guardrail reserve request → resolve lane via `lane_purpose_map` → add a per-lane COMMITTED+HELD cap check mirroring the existing per-`mcp_key` sub-cap block (`guardrail.go:231-257`). Additive by-lane report (`GROUP BY lane` over the existing `idx_usage_logs_owner_lane`) is an independent S that can ship first. | `user_lane_budgets` is written but never read today; the separation tag is live, enforcement is the follow-on. |
| **B2** distiller model-aware window (D-DISTILL-WINDOW-MODEL-AWARE) | ⬜ | S–M | Resolve the target model's context length in the distill consumer (`ProviderRegistryClient.get_context_length` already exists + is used on the extraction path) → `window = min(12_000, ctx − overhead − reserve)`, fall back to 12k when unknown → pass through `distill_and_write(window=…)`. | protects a future ≤8k-ctx BYOK distill model; deployed model is 200K so not urgent, but it's wiring not a new capability. |

### Group F — FE polish (DBT-14)
| Slice | Was | Size | What it takes |
|---|---|---|---|
| **F1** onboarding fifth-intent (C22) | ⬜ | XS–S | Add the assistant/work intent id + tile + route (`onboarding/types.ts` is hardcoded to exactly four). |
| **F2** FE timezone-confirm UI | ⬜ | S | The BE already expects it (`assistant.controller.ts:181` `timezone:'pending:user_confirm'`; `schedule` accepts `timezone`); add the FE confirm control so tz-aware `local_date` bucketing actually gets a zone. |
| **F3** assistant session-template seed (WS-1.7) | ⬜ | S–M | Seed the assistant session template — ⚠ must NOT stamp a working-memory charter (D13: the assistant session must not fire an executive tick); build with the session-create path, not seed-only. |

**Not in a group (mobile reachability, surfaced by the audit):** the assistant home strip is `hidden … md:block`
(`AssistantPage.tsx:48`) — desktop-only. CLAUDE.md says design for phone/tablet; a mobile reflection/home surface
is a real gap but a **product-shaped FE decision**, flagged for the QC/acceptance discussion, not auto-scoped here.

---

## 3 · PARKED — genuinely deferrable (each earns a defer-gate; do NOT force-clear)
| Item | Gate | Why it earns the defer |
|---|---|---|
| **D-PROACTIVE-LLM-CONTENT** | #2 large | grounded LLM check-in = a headless "synthetic-prompt → grounding → generate" path (spend accounting, which context, safety screen) — a real design task, not the static template's wiring. The seam (attribution/dedup/gate/**delivery once R3 lands**) is done. |
| **D-STT-METER-UNIFY** | #4 policy + #2 data | `per_second` (voice) vs `per_kchar` (async STT job) disagree; the *code* merge is S, but "which meter is canonical" is a billing-policy call + may need a pricing-dimension backfill on registered STT models. Already made observable (chat WARNs); local voice is $0 so pressure is low. |
| **DBT-7** KEK re-wrap | #2 large ops | true rotation needs a retired-KEK config list on auth + a resumable unwrap-old→reseal-new batch job + `key_ref` re-stamp. No active harm (the retired keyring IS the correctness story). Do it when rotation is first exercised in anger. |
| **DBT-10** trashed-diary restore (full UX) | blocked on product | the BE filter change (`server.go:866` `kind<>'diary'`) is trivial; the correct restore-vs-start-fresh surface is gated on the **E14 diary-lifecycle product decision**. A minimal restore is buildable once E14 is decided. |
| **DBT-2** book-service `-p 1` test deadlock | #2 structural | advisory-lock around `migrate.Up()`; workaround (`go test -p 1`) in force. Raise at a review. |
| **DBT-3** tool-liveness sweep for `book_index_chapter`/`book_chapter_set_kg_exclude` | #3 next-phase | run the real liveness sweep at the full-loop exit; absence = "unproven, not broken" (does not suppress the tool). Never hand-edit the manifest. |
| **DBT-4** `editor.json` locale keys en-only | #2 | needs a targeted key-level i18n pass + an `editorParity` test; `--force` regen would churn another track's translations. |
| **P-2** retire `raw_search` `index-drafts` endpoint | #1/#2 | redundant post publish-independent indexing but has a live FE caller — needs a deprecation path. Harmless to leave. |
| **P-4 tail** public-MCP per-resource scoping + export | #2 | small + local; a separate egress-hardening slice. Diary content stays guarded at book-service. |
| **P-11** two-Minh disambiguation | #2/#3 | latent only when work-capture writes entities (consent-gated, FE-surfaced); the correct fix is work-capture-specific (fiction should still dedup). Build with work-capture live. |

## 4 · NOT CODE — the human milestone (SD-7, unchanged)
The coaching **safety-eval certification** (human-labeled distress corpus) + **numeric-eval clearance**
(QWK ≥ threshold, N≥50 × ≥2 human raters). The scorer ships **quarantine-tier** until a person certifies
it; a self-run QWK / "safety passing" is a drift violation. R2 makes the quarantine scorecard *visible*;
it does NOT clear the number. This is the boundary of any autonomous run.

---

## 5 · Suggested execution order (if/when the build is greenlit — separate from QC)
1. **Group R** (reachability) — highest user-visible value; turns 3 dormant features on. R1→R2→R3.
2. **Group P** (privacy/safety) — P1 + P2 are the fix-now-default items (a real-person leak + a fail-closed
   safety gap); P3/P4 harden crypto. 
3. **Group B** then **Group F**.
Each slice commits with an explicit pathspec (never `git add -A` — shared checkout); each carries pasted
green tests + a cross-service live-smoke where it crosses services + a cold `/review-impl`. ~11 slices;
most S/M. The parked list (§3) stays parked with its gate; §4 stays with the human.
