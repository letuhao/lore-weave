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
| **A1** | knowledge erase includes archived epochs + forget clears `:Passage` index + internal-token JWT-bind assert | HIGH | Y | ⬜ | |
| **A2** | desktop parity — Memory/recall + Journal + Correct + Forget + Erase in the desktop `/assistant` (reuse hooks/sheets) | HIGH | N | ⬜ | |
| **A3** | arm autonomous — fail-closed per-user schedule setting → `POST /v1/assistant/schedule`; toggle ON makes a job fire | HIGH | Y | ⬜ | |
| **A4** | new-epoch FE (changed-jobs isolation) + proactive LLM content via provider-registry | MED | Y | ⬜ | |
| **A5** | Practice interview nav — entry from assistant + mobile path | LOW | N | ⬜ | |
| **B-PLAN** | `docs/plans/2026-07-16-assistant-blackbox-qc.md` — persona×scenario matrix, scenario→tool-layer map, data-testid inventory, run sequencing (PLAN ONLY) | — | N | ⬜ | committed hash |

Sequence: A1 → A2 → A3 → A4 → A5 → B-PLAN. (A2/A5 FE-only; A1/A3/A4 live-smoke or waiver.)

## 4 · Decisions register (append sealed calls)
- 2026-07-16 · Scope FULL incl. arming autonomous (owner). · Order fix-first then QC-plan (owner).
- 2026-07-16 · Autonomous is a fail-closed OFF per-user setting, no auto-seed (repo law — sealed).
- 2026-07-16 · Track B is PLAN-ONLY in this goal; Playwright/CV build+run is a SEPARATE later goal.

## 5 · Parked register (gate each) — none yet.

## 6 · Debt / drift log (append as you go — an empty drift log at the end is dishonest) — none yet.

## 7 · Checkpoints
- Owner checkpoint after each cross-service slice (A1, A3) and at B-PLAN. Commit per slice with pasted evidence.
- Standing deferrals carried in: this file's §5/§6 + SESSION_HANDOFF Deferred Items.
