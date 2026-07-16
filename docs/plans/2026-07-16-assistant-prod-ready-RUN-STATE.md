# RUN-STATE — Assistant production-ready close-out (Track A) + Track-B QC plan

Plan (detailed slice specs): [`2026-07-16-assistant-production-ready-and-qc.md`](./2026-07-16-assistant-production-ready-and-qc.md).
Gap source: 3-agent disjoint completeness audit (FE/mobile · BFF+chat · knowledge), 2026-07-16.

## 0 · Resuming after a compaction — do THIS first
Re-READ this file, then `git log --oneline -12`, then the plan doc §1 (slice specs) + §0 (finish line).
Re-verify each audit `file:line` against code before building a slice — the audit is PLAUSIBLE, not gospel.
Never re-litigate a sealed decision (below) from memory — re-read it here.

## 1 · The commitment (owner-sealed 2026-07-16)
Scope = **FULL**: manual assistant + **desktop parity** + **erase-completeness** + **arm the autonomous layer**.
Order = **fix the blocking gaps (Track A) FIRST**, then write the **Track-B blackbox QC plan doc** (plan only —
NO Playwright/CV build or run in this goal). Finish line = plan §0.

## 2 · Standing invariants (never lower silently)
- **Autonomous = fail-closed OFF, per-user setting** (A3). NOT seeded-on at provision, NOT an env flag. It causes
  background token spend ⇒ Settings-and-Config SET-1..8 + "spend-causing setting fails closed";
  `effective = AND(deploy_allows, user_enabled)`. Default-on is a DEFECT.
- **Tenancy** — every assistant read/write owner-scoped (JWT `sub`→`user_id`); no shared/global mutation; erase/
  forget never touch another user. A missing scope key is a HIGH finding.
- **Data-rights complete** — erase covers archived epochs; forget clears `:Passage` search too (not just `:Entity`).
- **Provider gateway / no hardcoded model** — A4.2 proactive LLM copy resolves via provider-registry; agentic ⇒ MCP.
- **Server-SSOT persistence** — settings/prefs via `/v1/me/preferences` or a server row, never localStorage for user data.
- **Verify by EFFECT** — cross-service slices live-smoke on a stack-up; unit-green alone is insufficient.

## 3 · SLICE BOARD (done = a pasted evidence string, NOT a checkmark)
| Slice | Deliverable | Sev | Cross-svc | Status | Evidence |
|---|---|---|---|---|---|
| **A1** ✅ | knowledge account-erase includes ARCHIVED epochs (right-to-erasure hole) via `list_all_assistant_project_ids` (archived-inclusive; recall keeps active-only). A1.2 (forget `:Passage`) = NON-ISSUE (diary never passage-indexed). A1.3 SEC-1 forged-`user_id` guard added. (c3f25b306) | HIGH | Y | ✅ | **EVIDENCE (pasted, committed c3f25b306):** knowledge **59 passed** on real PG :5555 (test_projects_repo incl. 2 new: erase-resolver-includes-archived + is-user-scoped; test_internal_admin unit); gateway assistant spec **43 passed** (incl. the A1.3 adversarial "forged user_id ignored → JWT sub wins"). **LIVE-SMOKE (rebuilt knowledge image):** seeded 1 archived + 1 active assistant epoch + a pending fact in the archived → `DELETE /internal/admin/assistant/erase?user_id=U` (no project_id) → `{projects_erased:2, pending_facts_deleted:1}` (archived INCLUDED — pre-fix would be 1), asserts projects_left=0/archived_left=0/pending_left=0. **/review-impl:** standards clean (resolver user-scoped; no provider/model/secret/table); no HIGH/MED; 2 LOW accepted (smoke seeded PG-only for archived — Neo4j cascade is per-project archived-agnostic + D-R27-tested; A1.2 rests on "diary never indexes" invariant — §6). |
| **A2** ✅ | desktop parity — extracted `useAssistantMemory` (shared controller: journal/memory/correct/forget/erase + refetch handlers), consumed by BOTH the mobile dock and the desktop `AssistantHomeStrip`; strip gains Journal + Memory buttons opening the reused addressable sheets (incl. forget + erase danger-zone). (81f774c09) | HIGH | N | ✅ | **EVIDENCE (pasted, committed 81f774c09):** assistant suite **21 files / 85 passed**; **tsc 0**. New: `AssistantHomeStrip.desktop-parity` 3 (Journal+Memory reachable; forget + erase controls OPEN on desktop; erase two-step confirm→handler) + `useAssistantMemory` 3 (refetch-on-success-only; erase re-provisions+refreshes; correct gated on amended). Dock refactor regression-free (mutually-exclusive with strip → no double sheet mount). **/review-impl:** FE-only, standards clean (MVC hook owns logic; server-SSOT; no conditional unmount; no provider/model/secret/table); no HIGH/MED; LOW (handler coverage) CLOSED with the shared-hook test; 1 COSMETIC → D-A2-DESKTOP-SHEET-STYLE. |
| **A3** ✅ | arm autonomous — scheduler `ListSchedules`+`GET /internal/schedules`; gateway `GET /v1/assistant/schedule` + full-set enum; FE `useAssistantSchedule` (fail-closed effective state) + `AutonomousSettings` on desktop strip + mobile Today sheet. **CONFIG FIX:** scheduler→chat wrong hostname (`chat`→`chat-service`) that made arming hollow. (ca372d6eb) | HIGH | Y | ✅ | **EVIDENCE (pasted, committed ca372d6eb):** scheduler Go — ListSchedules real-DB owner-scoped + GET auth/validation + upsert/nudge pass (pre-existing `TestReArm` unrelated, reproduced on fully-stashed clean tree); gateway assistant spec **48 passed** (5 new: GET proxy + server-derived id + full enum + fail-closed); FE **23 files / 93 passed**, tsc 0. **LIVE-SMOKE:** enable eod_distill via gateway→armed; GET reflects enabled+armed; forced due → LIVE scheduler **claimed + FIRED** (log `fired count=1`, `last_fired_at` set, re-armed 21:00, breaker clean → enqueue to chat SUCCEEDED); toggle OFF→enabled=false. **/review-impl:** SET-1..8 compliant; MED (proactive_nudge silent-no-op via separate default-OFF `proactive_enabled`) FIXED — not exposed, deferred D-A3-PROACTIVE-SETTING; 2 LOW accepted (enum arrays not machine-synced=fail-safe reject; nudge notification path not smoked). |
| **A4** ✅ | new-epoch FE (changed-jobs confidential-fact isolation): `useNewEpoch` → shared `useAssistantMemory` → worded confirm control in the memory sheet (desktop + mobile). A4.2 proactive-LLM FOLDED into D-A3-PROACTIVE-SETTING (proactive gated off = no reachable consumer). (c728a1f4c) | MED | Y | ✅ | **EVIDENCE (pasted, committed c728a1f4c):** assistant suite **24 files / 99 passed**; tsc 0. New: `useNewEpoch` 3 (token+bookId guard, error-swallow), MemorySheet new-epoch 2 (worded two-step confirm; absent w/o handler), `useAssistantMemory` handleNewEpoch (reprovision+refresh on close only). **LIVE-SMOKE (FE→gateway→knowledge):** new-epoch on the test account → `epoch_closed=true`, prev-active project ARCHIVED, fresh project active (active=1) — changed-jobs isolation works E2E (and the archived epoch stays erasable per A1). **/review-impl:** FE MVC + tenancy clean (new-epoch user-scoped via JWT); no HIGH/MED; 1 LOW (book_id from client body vs erase's server-resolve — safe, close-epoch is user-scoped) accepted. |
| **A5** ✅ | Practice interview nav — "Practice interview" link (→ /roleplay) added to the desktop home strip + mobile Today sheet (next to the scorecard). Audit's "unreachable on mobile" was overstated — `AllAppsDrawer→Coaching` (on Home + You) already reached it; the real gap was discoverability from the assistant. (22ec90868) | LOW | N | ✅ | **EVIDENCE (pasted, committed 22ec90868):** assistant suite **24 files / 100 passed**; tsc 0. Test asserts the desktop entry links to `/roleplay`. **/review-impl:** FE-only nav to an auth-gated route; no provider/model/secret/tenancy surface; no HIGH/MED. |
| **B-PLAN** ✅ | `docs/plans/2026-07-16-assistant-blackbox-qc.md` — 7 personas × 13 scenarios (measurable acceptance) + blocking 2-user tenancy gate (T1–T4) + scenario→tool-layer map (CLI scripts · MCP · CV) + grounded data-testid inventory + run sequencing + exit bar. PLAN ONLY. (2388eaaab) | — | N | ✅ | committed **2388eaaab**; contains all four required elements (matrix, tool-layer map, testid inventory, sequencing). |

**🏁 GOAL COMPLETE 2026-07-16 — all 5 Track-A slices ✅ + the Track-B QC plan committed.** A1 c3f25b306 · A2 81f774c09 · A3 ca372d6eb · A4 c728a1f4c · A5 22ec90868 · B-PLAN 2388eaaab. Each Track-A slice: pasted fresh green test output + /review-impl (HIGH/MED fixed + re-verified) + commit hash; A1/A3/A4 cross-service live-smoked (A2/A5 FE-only). A3 additionally found + fixed + live-proved a real production-blocker (scheduler→chat hostname). Standing deferrals: D-A3-PROACTIVE-SETTING (incl. A4.2), D-A2-DESKTOP-SHEET-STYLE. Pre-existing (not ours): scheduler `TestReArm`.

Sequence: A1 → A2 → A3 → A4 → A5 → B-PLAN. (A2/A5 FE-only; A1/A3/A4 live-smoke or waiver.)

## 4 · Decisions register (append sealed calls)
- 2026-07-16 · Scope FULL incl. arming autonomous (owner). · Order fix-first then QC-plan (owner).
- 2026-07-16 · Autonomous is a fail-closed OFF per-user setting, no auto-seed (repo law — sealed).
- 2026-07-16 · Track B is PLAN-ONLY in this goal; Playwright/CV build+run is a SEPARATE later goal.

## 5 · Parked register (gate each)
- ~~**D-A3-PROACTIVE-SETTING**~~ **CLEARED 2026-07-16 (4f5fc6b24)** — proactive fully wired + exposed:
  `useProactiveSetting` sets BOTH the chat opt-in AND the `proactive_nudge` schedule (ordered so a partial
  failure can't leave the gate ON with no trigger), surfaced as a dedicated "Proactive check-ins" row on
  desktop + mobile. A4.2 done: grounded LLM check-in via provider-registry (recent-turns grounding + scaffold
  cleanup + static fail-safe). **LIVE-SMOKE:** a clean grounded message referencing the user's recent work;
  reasoning-model → safe static fallback. Also fixed a latent `logger` NameError in internal.py.
- ~~**D-A2-DESKTOP-SHEET-STYLE**~~ **CLEARED 2026-07-16 (bb3b074a0)** — the shared `Sheet` gained a `variant`
  prop; the assistant's Journal/Memory sheets open as a centered dialog on desktop, bottom-sheet on mobile.
  Default `'bottom'` keeps every other Sheet consumer unchanged.
- **D-A3 remaining note (not blocking):** nudge's notification-service path still wasn't live-smoked (only
  eod_distill + proactive fired live); `NOTIFICATION_SERVICE_INTERNAL_URL` (:8091) matches every other
  service's addressing. Left as a QC-scenario check (S10), not a code gap.

## 6 · Debt / drift log (append as you go — an empty drift log at the end is dishonest)
- **A1.2 near-miss (audit said MED, proved NON-ISSUE):** forget was flagged for leaving KS-owned `:Passage`
  prose searchable. Traced the code: diary books **never publish/index** (`book-service kg_index.go:10`), and
  the distiller only `write_diary_entry` + `queue_diary_facts` (no chapter index) — so diary prose is NEVER
  ingested as `:Passage`. Forget has no passage residue. **ASSUMPTION to revisit:** if diary passage-indexing
  is ever added (for richer prose recall), forget MUST also re-index/redact those passages — re-open A1.2 then.
- **A1 live-smoke scope:** the archived-epoch smoke seeded PG rows only (passages/kg=0), so the archived
  project's Neo4j cascade wasn't exercised end-to-end. Accepted: the A1 change is the RESOLVER only; the
  per-project cascade is unconditional on `is_archived` and covered by D-R27 tests.
- **A3 real config bug found + fixed:** scheduler enqueued to `http://chat:8090`, but the service hostname is
  `chat-service` (no `chat` alias) — DNS "no such host", so EVERY armed autonomous job silently breaker-looped
  and never reached chat. Arming would have been hollow. Fixed compose env + config.go default + the missing
  notification URL. Live-proven: post-fix, eod_distill fired with a clean breaker.
- **A3 pre-existing failure (NOT mine):** `TestReArm_UsesLocalFireTime_NotRawInterval` fails on a
  fully-stashed clean scheduler tree (re-arm lands at ~claim time, not the next 21:00). My A3 changes don't
  touch `recordSuccess`/`ComputeNextFireAt`; it belongs to the concurrent scheduler track. Recorded for honesty.
- **Debt-clear latent bug found + fixed:** `internal.py` used `logger` (proactive-notification warn paths,
  lines ~740/743) with NO module-level `logger` defined — a real notification failure would have raised
  NameError → 500. Never hit in tests (those paths were mocked/happy). My grounded-content fallback path
  exposed it; fixed by defining the module logger.
- **Debt-clear model-quality finding (fail-safe, not a bug):** a local REASONING model (gemma-4-26b-a4b-qat)
  emitted planning/scaffolding (or empty content) for the proactive check-in; the scaffold-cleanup then the
  static fallback kept the output safe. A non-reasoning instruct model (qwen2.5-7b-instruct) produced a
  clean grounded message. So proactive content quality depends on the user's model — correct + fail-safe.

## 7 · Checkpoints
- Owner checkpoint after each cross-service slice (A1, A3) and at B-PLAN. Commit per slice with pasted evidence.
- Standing deferrals carried in: this file's §5/§6 + SESSION_HANDOFF Deferred Items.
