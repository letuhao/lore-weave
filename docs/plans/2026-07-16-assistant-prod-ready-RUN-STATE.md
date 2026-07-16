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
| **A3** | arm autonomous — fail-closed per-user schedule setting → `POST /v1/assistant/schedule`; toggle ON makes a job fire | HIGH | Y | ⬜ | |
| **A4** | new-epoch FE (changed-jobs isolation) + proactive LLM content via provider-registry | MED | Y | ⬜ | |
| **A5** | Practice interview nav — entry from assistant + mobile path | LOW | N | ⬜ | |
| **B-PLAN** | `docs/plans/2026-07-16-assistant-blackbox-qc.md` — persona×scenario matrix, scenario→tool-layer map, data-testid inventory, run sequencing (PLAN ONLY) | — | N | ⬜ | committed hash |

Sequence: A1 → A2 → A3 → A4 → A5 → B-PLAN. (A2/A5 FE-only; A1/A3/A4 live-smoke or waiver.)

## 4 · Decisions register (append sealed calls)
- 2026-07-16 · Scope FULL incl. arming autonomous (owner). · Order fix-first then QC-plan (owner).
- 2026-07-16 · Autonomous is a fail-closed OFF per-user setting, no auto-seed (repo law — sealed).
- 2026-07-16 · Track B is PLAN-ONLY in this goal; Playwright/CV build+run is a SEPARATE later goal.

## 5 · Parked register (gate each)
- **D-A2-DESKTOP-SHEET-STYLE** (A2 COSMETIC) — the desktop strip reuses the mobile `Sheet` (Radix Dialog
  styled as a bottom-sheet), so on a wide desktop the Journal/Memory panels open bottom-anchored. Functional
  + accessible (focus-trap, Escape, aria). **Gate:** a desktop-shaped panel/side-drawer is a polish pass, not
  a reachability blocker — do it if the QC personas flag the bottom-sheet-on-desktop as jarring.

## 6 · Debt / drift log (append as you go — an empty drift log at the end is dishonest)
- **A1.2 near-miss (audit said MED, proved NON-ISSUE):** forget was flagged for leaving KS-owned `:Passage`
  prose searchable. Traced the code: diary books **never publish/index** (`book-service kg_index.go:10`), and
  the distiller only `write_diary_entry` + `queue_diary_facts` (no chapter index) — so diary prose is NEVER
  ingested as `:Passage`. Forget has no passage residue. **ASSUMPTION to revisit:** if diary passage-indexing
  is ever added (for richer prose recall), forget MUST also re-index/redact those passages — re-open A1.2 then.
- **A1 live-smoke scope:** the archived-epoch smoke seeded PG rows only (passages/kg=0), so the archived
  project's Neo4j cascade wasn't exercised end-to-end. Accepted: the A1 change is the RESOLVER only; the
  per-project cascade is unconditional on `is_archived` and covered by D-R27 tests.

## 7 · Checkpoints
- Owner checkpoint after each cross-service slice (A1, A3) and at B-PLAN. Commit per slice with pasted evidence.
- Standing deferrals carried in: this file's §5/§6 + SESSION_HANDOFF Deferred Items.
