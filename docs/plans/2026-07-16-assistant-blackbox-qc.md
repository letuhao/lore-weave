# PLAN — Personal Assistant: blackbox QC (production-readiness)

Status: **PLAN ONLY.** This doc designs the QC campaign; building/running Playwright/CV is a SEPARATE later
goal. Prereq: Track A (production-ready close-out) is ✅ — see
[`2026-07-16-assistant-prod-ready-RUN-STATE.md`](./2026-07-16-assistant-prod-ready-RUN-STATE.md).

Goal of the campaign: prove the assistant **serves real daily needs**, from **multiple perspectives**, on
**both form factors + multi-device**, including **data-rights + tenancy** — not just the happy path. QC exits
"production-ready" only when every P0 scenario passes on the deployed stack and the tenancy gate is green.

---

## 1 · Personas (perspectives to test from)
| ID | Persona | Cares about |
|---|---|---|
| **P1** | Daily journaler | Talk through the day → end day → review → keep. Low friction. |
| **P2** | Busy PM | Track people/projects; recall "who did I meet about X"; fix a wrong note. |
| **P3** | Interview practicer | Run Practice; wrap at Q5 / at time budget; read the scorecard. |
| **P4** | Privacy / data-rights user | Capture OFF until opt-in; forget a person; erase everything (incl. archived epoch); changed-jobs isolation; verify data is truly gone. |
| **P5** | Multi-device user | Do X on PC, see it on mobile (and vice-versa); prefs/first-run/tz sync. |
| **P6** | First-run newcomer | Safe defaults stated plainly; consent OFF; tz; "start my first day". |
| **P7** | Autonomy opt-in user | Turn on auto-journal/reflection; it actually fires; OFF → nothing spends. |

---

## 2 · Scenario × persona matrix (each with measurable acceptance)
Priority: **P0** = production-blocker (must pass to ship), **P1** = important, **P2** = polish.

| # | Scenario | Persona | Priority | Acceptance (measurable) |
|---|---|---|---|---|
| **S1** | End-of-day loop | P1 | P0 | capture rail shows ≥1 noticed item → `dock-end-day`/`assistant-end-day` → `assistant-distilling` → a draft in `assistant-review` → `assistant-keep-entry` → the entry appears in the Journal sheet (`mobile-journal-list`). |
| **S2** | Ask-my-memory (recall) | P2 | P0 | open Memory (`assistant-open-memory`) → `memory-search` a known name → the entity row appears in `memory-list`; an unknown term → honest empty state. |
| **S3** | Correct a memory | P2 | P1 | open a past Journal day → edit → submit; a re-distill supersedes the old facts, the corrected text shows on reload. |
| **S4** | Forget a person | P4 | P0 | `memory-forget-<id>` → worded confirm (`memory-forget-confirm-<id>`) → `memory-forget-do-<id>` → the person leaves `memory-list` AND a recall search no longer returns them. |
| **S5** | Erase everything (incl. archived) | P4 | P0 | seed an archived epoch (via S8 first) → `memory-erase-all-open` → `memory-erase-all-do` → all diary/knowledge gone **including the archived epoch** (verify server-side: 0 assistant projects); re-provision yields an empty diary. |
| **S6** | Weekly reflection + dismiss | P1 | P1 | `reflection-card` renders with `reflection-pattern` chips → `dismiss-pattern` → the pattern never resurfaces on reload. |
| **S7** | Practice interview wrap | P3 | P0 | `assistant-practice-link` → Practice → drive to Q5 → `practice-wrapping` (the "final question" directive) shows; the anchor wraps at 5 / at time budget; `/evaluate` yields a `coaching-scorecard` with a `quarantine-badge` when applicable. |
| **S8** | Changed jobs (new epoch) | P4 | P1 | `memory-new-epoch-open` → `memory-new-epoch-do` → the old epoch's facts leave default recall; a fresh (empty) epoch is active; the old epoch is still erasable (feeds S5). |
| **S9** | Consent fail-closed | P4/P6 | P0 | fresh account: `first-run-consent` and `assistant-consent-toggle` are OFF by default; with capture OFF, nothing is noticed (empty `capture-rail`); turning it ON begins capture. |
| **S10** | Autonomous opt-in | P7 | P0 | `autonomous-settings`: every `autonomous-toggle-<kind>` OFF by default; toggle `eod_distill` ON → the server row is armed (GET reflects it) → on the scheduled tick the job fires; toggle OFF → nothing fires / spends. |
| **S11** | Multi-device sync | P5 | P1 | set tz / complete first-run / arm an autonomous toggle on device A → device B (fresh session, same account) reflects it (server-SSOT, not localStorage). |
| **S12** | Desktop parity | P1–P4 | P0 | every P0 scenario (S1,S2,S4,S5,S9) is completable on a **desktop** viewport too — the A2 fix; regression-guard it (`desktop-strip` present, `assistant-open-memory`/`assistant-open-journal` reachable). |
| **S13** | First-run once | P6 | P1 | a never-onboarded account shows `assistant-first-run` on mobile once → `first-run-start` → never shown again (server-gated); a returning account never sees it. |

---

## 3 · Tenancy adversarial gate (production-safety — 2 users, not a happy path)
| # | Check | Acceptance |
|---|---|---|
| **T1** | Cross-user recall | User A's `memory-search` / recall never returns user B's entities/facts. |
| **T2** | Cross-user forget/erase isolation | A's forget/erase/new-epoch never touch B's data (verify B's rows intact after A's destructive ops). |
| **T3** | Forged identity rejected | An internal-route call with a forged `user_id` in the body is ignored — the JWT `sub` wins (already unit-guarded in the gateway spec A1.3; re-assert at the live edge). |
| **T4** | Autonomous scope | A's armed schedule never fires B's jobs; `GET /v1/assistant/schedule` returns only the caller's rows. |

T1–T4 are a **blocking gate**: any failure is a ship-stopper regardless of scenario coverage.

---

## 4 · Scenario → tool-layer mapping
Three layers, each doing what it's best at (the user's framing):

| Layer | What it owns | Scenarios |
|---|---|---|
| **Playwright CLI scripts** (deterministic regression backbone; `data-testid` selectors; CI-able) | The stable, repeatable core + edge/negative + the tenancy gate. *The certainty layer.* | S1, S2, S4, S5, S8, S9, S10, S12, S13 + **T1–T4** |
| **Playwright MCP** (agent-driven, goal-directed exploration) | Open/fuzzy flows + discoverability; catches states rigid scripts miss. | S3 (free-form correction), S6 (reflection variety), S7 (interview dialogue), plus an exploratory "find a way to erase your data" discoverability run. |
| **CV agent** (interacts like a human; verify-by-effect on the real UI) | Confirms the *effect* is really visible: the distilled entry appears, the wrap shows at Q5, erased data is visibly gone. "Live browser smoke, not raw-stream." | S1 (distill visibly appears), S5 (visibly gone), S7 (wrap visibly at Q5), S10 (a fired job's visible result). |

Cross-service seams a script alone can't prove (verify these on a stack-up, not mocked): S1/S3 distiller (chat↔book↔knowledge), S5 erase (gateway↔chat↔knowledge↔book↔glossary), S7 interview (roleplay↔chat↔knowledge), S10 autonomous (scheduler↔chat).

---

## 5 · data-testid inventory (grounded — selectors the scripts bind to)
Stable ids present in the code today (extend as gaps surface; a NEW flow needs a `data-testid` before its script):

- **Surface / layout:** `assistant-page` · `assistant-greeting` · `desktop-strip` · `mobile-assistant-dock` · `mobile-dock` · `mobile-tab-bar` · `mobile-nav` · `mobile-header` · `chat-surface` · `assistant-loading` / `assistant-error` / `assistant-first-run-loading`
- **Sheets (addressable `?sheet=`):** `today` · `journal` · `memory` · `apps` — buttons `dock-today` · `dock-end-day` · `assistant-open-journal` · `assistant-open-memory`
- **End-of-day:** `assistant-end-day` / `dock-end-day` · `assistant-distilling` · `assistant-review` · `assistant-entry` / `assistant-entry-body` / `assistant-entry-date` · `assistant-keep-entry`
- **Capture + consent:** `assistant-capture-rail` / `capture-entity` / `capture-rail-empty` · `assistant-consent-toggle` · `first-run-consent`
- **Memory + data-rights:** `memory-sheet` · `memory-search` · `memory-list` · `memory-forget-<id>` / `memory-forget-confirm-<id>` / `memory-forget-do-<id>` / `memory-forget-keep-<id>` · `memory-erase-all` / `-open` / `-confirm` / `-do` / `-cancel` · `memory-new-epoch` / `-open` / `-confirm` / `-do` / `-cancel`
- **Autonomous (A3):** `autonomous-settings` · `autonomous-toggle-eod_distill` / `-weekly_reflection` / `-weekly_rollup` / `-nudge`
- **Fact inbox / reflection / scorecard:** `diary-fact-inbox` / `diary-fact-row` / `diary-fact-confirm` / `diary-fact-reject` · `reflection-card` / `reflection-pattern` / `dismiss-pattern` · `coaching-scorecard` / `scorecard-overall` / `dimension-score` / `quarantine-badge`
- **First-run / tz:** `assistant-first-run` / `first-run-privacy` / `first-run-consent` / `first-run-start` · `timezone-confirm` / `tz-detected` / `tz-use-detected` / `tz-select`
- **Practice (A5 + prior):** `assistant-practice-link` · `practice-progress` / `practice-qcount` / `practice-timer` / `practice-wrapping`

Dynamic ids interpolate an entity/chapter id (`memory-forget-<entity_id>`) — scripts read the id from the row.

---

## 5b · Harness status (built + green)
Started the Track-B execution against the EXISTING Playwright framework (`frontend/tests/e2e/`, PoM +
`TEST_USER`/`TEST_USER_B` + `PLAYWRIGHT_BASE_URL`). Shipped so far:
- **`pages/AssistantPage.ts`** — PoM for the assistant surface (strip, sheets, data-rights + autonomous controls).
- **`specs/assistant-data-rights.spec.ts`** (S2/S4/S5/S8/S9/S12) + **`specs/assistant-autonomous.spec.ts`** (S10)
  — **6 tests GREEN** on the built image (:5185): consent fail-closed, Memory/Journal reachable on desktop,
  erase two-step confirm (cancel), new-epoch confirm (cancel), Practice→/roleplay, every autonomous toggle OFF.

**Run recipe (BUILT image on a free port — never `vite dev`, which a parallel session can shadow):**
```sh
cd infra && docker compose build frontend                 # rebuild the bundle after ANY FE source change
docker rm -f qc-frontend 2>/dev/null; \
docker run -d --name qc-frontend --network infra_default -p 5185:80 infra-frontend   # dedicated, isolated
cd ../frontend && PLAYWRIGHT_BASE_URL="http://localhost:5185" npx playwright test assistant-*.spec.ts
```
**FINDING (F-QC-1, flagged not fixed):** on `/assistant` the chat surface auto-opens a full-screen
`NewChatDialog` (generic "new chat" + model picker) that covers the assistant home. It persists for the test
account because it has **no default model** (`user_default_models` empty) → the assistant session can't
auto-create. A production user with a default model wouldn't see it persistently, but a diary assistant
greeting you with a "pick a model for a new chat" modal is worth a UX review. The harness dismisses it
(`new-chat-dismiss` testid, added) before strip interactions.

## 6 · Infra + accounts (setup the scripts assume)
- **Frontend under test:** `vite dev` on **:5199** (a free port; NEVER shadow the baked prod nginx `:5174`), OR a
  built image on a free port for the prod-parity pass. FE talks to the gateway via relative `/v1`.
- **Gateway:** `:3123` (dev). Full stack up via `infra/docker-compose.yml`.
- **Accounts:** the test account `claude-test@loreweave.dev` drives real flows; it has ~15 BYOK **local**
  models ($0 spend) — prefer a local chat model for S7's real LLM turns. For the **tenancy gate (T1–T4)**
  provision a SECOND throwaway account so A-vs-B isolation is real.
- **Autonomous (S10):** the scheduler tick is 1 min; a script arms a toggle, forces the row due
  (`next_fire_at` past), and asserts the live scheduler claims + fires it (as the A3 live-smoke did).
- **Reset between runs:** the shared dev DB carries state — a script must create its own fixtures and not
  assume a clean DB (the "shared dev DB dirty" hazard); the erase/new-epoch scenarios are self-cleaning.

---

## 7 · Run sequencing (build + execute order for the later goal)
1. **Author the `data-testid` gaps first** — any scenario whose selector is missing gets its `data-testid`
   added (small FE commits) before its script.
2. **Layer 1 — script the P0 core** (S1, S2, S4, S5, S9, S10, S12) happy paths → green in CI.
3. **Layer 1 — edge/negative** (empty states, failure toasts, fail-closed defaults, S13).
4. **The tenancy gate (T1–T4)** — the 2-user adversarial scripts. Ship-blocking.
5. **Layer 2 — Playwright MCP** exploratory for S3/S6/S7 + a discoverability sweep.
6. **Layer 3 — CV agent** verify-by-effect on S1/S5/S7/S10 (the seams where "green unit test ≠ visibly works").
7. **Define the exit bar:** production-ready ⇔ every P0 scenario green on the deployed stack (built image, not
   just `vite dev`) **and** T1–T4 green. P1/P2 tracked, not blocking.

---

## 8 · Notes that shape QC scope
- **Proactive check-ins** are now EXPOSED + wired (D-A3-PROACTIVE-SETTING cleared): add a scenario —
  `autonomous-toggle-proactive_nudge` ON sets BOTH the chat opt-in AND the schedule; the fired turn persists
  a GROUNDED check-in (references recent work) with a non-reasoning model, or a safe static line otherwise.
  Verify by effect: the assistant_proactive message appears; OFF → no turn / no spend.
- **Desktop sheet** (D-A2-DESKTOP-SHEET-STYLE cleared): the Journal/Memory sheets now open as a centered
  dialog on desktop (`data-variant="center"`) — S12 can assert the variant, but reachability remains the bar.
- Scenarios must **verify by effect** (visible UI + server-side row checks), never raw stream / unit-mock —
  the whole reason this campaign exists on top of the unit suites.
