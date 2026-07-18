# PLAN — Personal Assistant: production-ready close-out + blackbox QC

Owner decision (2026-07-16): **Scope = FULL** (manual + desktop parity + erase-completeness + **arm the
autonomous layer**). **Order = fix the blocking gaps FIRST, then blackbox QC.**

Source of the gap list: a 3-agent disjoint completeness audit (FE/mobile · BFF+chat · knowledge), 2026-07-16.
Every gap below carries `file:line` from that audit. **Verify each claim against code at BUILD start** (the
audit is PLAUSIBLE, not gospel — the repo rule is "verify against code, don't trust a handoff").

---

## 0 · Definition of "production-ready" (the finish line)
A real user, on **either PC or mobile**, across **multiple devices**, can:
1. Journal daily; End-my-day distills; review→keep; the fact-inbox confirm/reject works.
2. **Browse + search what the assistant remembers**, read **past** journal days, **correct** a memory,
   **forget a person**, and **erase everything** — on **both desktop and mobile**.
3. Erase/forget are **complete** (no archived-epoch or passage-index residue) and **tenant-safe** (user A
   can never see/mutate user B).
4. Opt IN to the **autonomous** layer (auto-distill, weekly rollup/reflection, proactive) via a **fail-closed
   per-user setting**; once ON, those jobs actually fire; once OFF, nothing spends tokens.
5. Practice interview is reachable from the assistant on both form factors.

**Done = every Track-A slice ✅ with pasted test output + /review-impl (HIGH/MED fixed) + a commit, cross-service
slices live-smoked; then Track-B QC green on the core scenarios.**

---

## 1 · TRACK A — close the gaps (fix-first)

Each slice: BUILD (TDD) → VERIFY (paste real output) → /review-impl (standards gate + coverage) → COMMIT.
Cross-service slices additionally live-smoke (≥2 services) or record an explicit waiver.

### A1 — Erase-completeness + forget passage re-index  (HIGH · backend · data-rights)
Gaps: knowledge **#3** (erase skips archived epochs — GDPR hole) + **#6** (forget leaves `:Passage` searchable).
- **A1.1** knowledge erase resolver must include archived assistant projects. Today
  `ProjectsRepo.list_assistant_project_ids` filters `WHERE user_id=$1 AND is_assistant AND NOT is_archived`
  (`db/repositories/projects.py:865-874`), but the endpoint docstring promises "ALL assistant projects"
  (`routers/internal_admin.py:98-101`). Add an archived-inclusive resolver used by the **account-erase** path
  only (close-epoch/purge keep their current filters). Test: seed an archived epoch with a passage+fact →
  account erase → assert 0 passages/facts survive for that user.
- **A1.2** forget completeness: confirm the forget orchestration (gateway → knowledge forget-entity +
  book redaction) also drives the **passage re-index** leg so the forgotten name stops surfacing in
  KS-owned `:Passage` search (`entities.py:3026-3029` defers it). If the leg is missing, build it or file
  the precise cross-service integration check at the orchestration seam. Test: forget → assert name absent
  from passage/full-text search, not just from `:Entity`/`:Fact`.
- **A1.3** LOW (accept+assert): the `require_internal_token` routes take `user_id` in the body; the gateway
  DOES bind it from JWT `sub` (audit confirmed, `controller.ts:835`). Add a contract assertion so a future
  edit can't start trusting client-supplied `user_id`.
- Services touched: knowledge + gateway (+ book). **Live-smoke:** seed→erase / forget→search on the stack.

### A2 — Desktop parity  (HIGH · FE additive, backend already exists)
Gap: FE **#1**. `AssistantHomeStrip.tsx` wires only 6/11 controller hooks; the desktop `/assistant` never
surfaces **Memory/recall, Journal timeline, Correct, Forget, Erase** — all built as mobile-only sheets.
- Surface the 5 missing capabilities in the **desktop** experience, reusing the existing presentational
  components where possible (the mobile sheets are prop-driven; a desktop rail/panel or dialog can reuse
  `MobileMemorySheet`/`MobileJournalSheet` bodies, or thin desktop wrappers over the same hooks).
- Bind `useDiaryEntries`, `useMemoryEntities`, `useDiaryCorrection`, `useForgetEntity`, `useEraseAllData`
  in the desktop tree (mirror `MobileAssistantDock`'s wiring + refetch-on-success).
- Keep the forget/erase **worded irreversible confirm** on desktop too.
- No backend work (every endpoint exists + is wired). Tests: desktop-render reachability (each capability
  present + calls its hook) + the confirm flows. **No cross-service** (FE only).

### A3 — Arm the autonomous layer  (HIGH · FE setting + wiring; fail-closed)
Gap: BFF **#1** — `POST /v1/assistant/schedule` (`controller.ts:653`, the only creator of
`scheduled_agent_runs`) has **no FE caller**, so the whole scheduled/reflection/proactive surface is dormant.
- **Design (LOCKED by repo law):** the autonomous layer is a **per-user, fail-closed OFF setting**, server-SSOT
  (`/v1/me/preferences` or a dedicated settings row), NOT seeded-on at provision, NOT an env flag — because it
  causes **background token spend** (Settings-and-Config SET-1..8 + "spend-causing setting fails closed").
  `effective = AND(deploy_allows, user_enabled)`.
- Build the FE settings control (assistant settings / a section in the home strip + mobile You/settings):
  toggle(s) for the autonomous cadence → calls `POST /v1/assistant/schedule`. Show effective value + source.
- Verify by effect: toggle ON → a `scheduled_agent_runs` row exists → the scheduler claims it → a job fires.
- Also covers BFF **LOW-1** (distill retry restart-only) becomes real once the catch-up sweep is armed.
- Services: FE + gateway + scheduler (+ chat/worker as the fired job). **Live-smoke:** toggle→row→job fires.

### A4 — new-epoch FE + proactive LLM content  (MED)
- **A4.1** BFF **MED-1**: `POST /v1/assistant/new-epoch` (`controller.ts:602`, close-epoch + fresh project)
  has no FE. Add a "Starting a new chapter / changed jobs" control (confirm-gated — it isolates the old
  epoch's confidential facts). Pairs with A1.1 (archived epochs must still be erasable).
- **A4.2** BFF **MED-2**: proactive check-in writes a hardcoded string (`internal.py:789`,
  `D-PROACTIVE-LLM-CONTENT`). Replace with grounded LLM copy **through provider-registry** (no direct SDK,
  no hardcoded model); if it's agentic, route as an MCP tool-call per the MCP-first invariant. Only matters
  once A3 arms the proactive path.

### A5 — Practice interview navigation  (LOW)
Gap: FE **#6**. `/roleplay` is linked only from the desktop sidebar; not surfaced from the assistant and no
mobile tab/entry. Add an assistant → Practice entry point + a mobile navigation path (e.g. AllApps/Coaching
drawer, mirroring A4.3's earlier mobile entry).

**Track-A sequencing:** A1 (data-rights correctness) → A2 (desktop parity) → A3 (arm autonomous) →
A4 → A5. A1/A3 are cross-service (live-smoke); A2/A5 are FE-only.

---

## 2 · TRACK B — blackbox QC (production-readiness, after Track A)

Goal: prove the app **serves real daily needs**, from **multiple perspectives**, on **both form factors +
multi-device**, including **data-rights + tenancy** — not just happy-path.

### B0 · Persona × real-life scenario matrix (design the coverage first)
Personas (perspectives):
- **P1 Daily journaler** — talks through the day, ends the day, reviews, keeps.
- **P2 Busy PM** — tracks people/projects; asks memory "who did I meet about X"; corrects a wrong note.
- **P3 Interview practicer** — runs Practice; expects wrap at Q5 / at time budget; reads the scorecard.
- **P4 Privacy / data-rights user** — capture stays OFF until opt-in; forgets a person; erases everything;
    changed jobs → isolates the old epoch; verifies data is truly gone (incl. archived + passage search).
- **P5 Multi-device user** — does X on PC, sees it on mobile (and vice-versa); prefs/first-run sync.
- **P6 First-run newcomer** — safe defaults stated plainly; consent OFF; timezone; "start my first day".

Scenario families (each → measurable acceptance criteria):
1. End-of-day: capture rail → End-my-day → distill draft → review → keep → appears in journal timeline.
2. Ask-my-memory: recall search returns the right remembered person/project; empty state honest.
3. Correct a memory: edit a day → re-extract → superseded facts gone, corrected facts present.
4. Forget a person: confirm → entity+facts gone AND name absent from recall + passage search.
5. Erase everything: confirm → all diary/knowledge/book gone, **including an archived epoch**; re-provision empty.
6. Weekly reflection: draft + dismissable patterns; dismissed pattern never resurfaces.
7. Practice interview: drive to Q5 → wrap directive; at time budget → wrap; scorecard (quarantine-aware).
8. Changed jobs: new-epoch isolates old confidential facts; new epoch is clean; old still erasable.
9. Consent fail-closed: nothing captured/saved until the toggle is ON; OFF stops capture.
10. Autonomous opt-in: schedule ON → auto-distill/reflection actually fire; OFF → nothing spends.
11. Multi-device sync: prefs, first-run-done, reading state consistent across two sessions.
12. Desktop parity: every P1–P4 scenario is completable on desktop too (the gap A2 closes — regression-guard it).

### B1 · Tenancy adversarial (production-safety, 2-user)
User A and user B: A cannot see/search/mutate B's memory; A's erase/forget never touches B; internal routes
reject a forged `user_id`. This is a gate, not a happy-path.

### B2 · Tooling layers (map each scenario → the right layer)
- **Playwright CLI scripts (deterministic)** — the regression backbone: stable flows, `data-testid` selectors,
  fast, CI-able. Owns scenarios 1–9,11,12 happy + edge. *The certain, repeatable layer.*
- **Playwright MCP (agent-driven, exploratory)** — goal-directed navigation for open scenarios; catches what
  rigid scripts miss (unexpected states, discoverability).
- **CV agent (interact like a real human)** — verify-by-effect on the real UI (distill visibly appears; wrap
  shows at Q5; erased data visibly gone). Repo rule: "live browser smoke, not raw-stream".
- Infra: `vite dev :5199` OR a built image on a free port (never shadow the baked `:5174`); FE → gateway `:3123`;
  test account `claude-test@loreweave.dev` with ~15 BYOK **local** models ($0) for real LLM flows.

### B3 · QC plan doc + sequencing
Write `docs/plans/2026-07-16-assistant-blackbox-qc.md`: the scenario matrix, scenario→layer mapping, the
`data-testid` inventory needed, and the run order: **script core happy-paths → edge/negative → tenancy
adversarial (B1) → MCP/CV exploratory**. Define measurable "production-ready" exit per scenario.

---

## 3 · Slice board (done = pasted evidence, not a checkmark)
| Slice | What | Sev | Cross-svc | Status | Evidence |
|---|---|---|---|---|---|
| A1 | erase archived epochs + forget passage re-index + internal-token assert | HIGH | Y | ⬜ | |
| A2 | desktop parity (5 caps in desktop rail) | HIGH | N | ⬜ | |
| A3 | arm autonomous (fail-closed per-user schedule setting) | HIGH | Y | ⬜ | |
| A4 | new-epoch FE + proactive LLM content | MED | Y | ⬜ | |
| A5 | Practice nav (assistant entry + mobile) | LOW | N | ⬜ | |
| B0–B3 | blackbox QC: matrix → scripts → tenancy → MCP/CV | — | Y | ⬜ | |

## 4 · Deferred / notes
- Track A is buildable now (backends for A1/A2/A4/A5 exist; A3 wires an existing route). None is "blocked".
- A3's autonomous setting MUST be fail-closed OFF (no auto-seed) — a spend-causing default-on is a defect.
- Re-verify each audit `file:line` at slice start; fix what's actually there, not what the audit assumed.
