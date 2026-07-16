# RUN-STATE — Assistant blackbox QC campaign (Track-B execution)

Plan: [`2026-07-16-assistant-blackbox-qc.md`](./2026-07-16-assistant-blackbox-qc.md). Framework:
`frontend/tests/e2e/` (Playwright PoM + helpers + `TEST_USER`/`TEST_USER_B`).

## 0 · Resuming after a compaction — do THIS first
Re-READ this file, then `git log --oneline -12`, then the plan §2 (scenario matrix) + §4 (tool-layer map).
Re-run `PLAYWRIGHT_BASE_URL=http://localhost:5185 npx playwright test assistant-` to see the live board state.

## 1 · The commitment
Complete the deterministic Playwright QC for the personal assistant — every scenario S1–S13 + the tenancy
gate T1–T4 has a GREEN spec on the BUILT image (or a tracked waiver) — then one MCP-driven exploratory pass
+ one CV verify-by-effect pass on the key cross-service seams, with findings recorded.

## 2 · Standing invariants (never lower silently)
- **BUILT image only** (the user's hard constraint): run against `qc-frontend` (built `infra-frontend` on a
  free port :5185, network `infra_default`) — NEVER `vite dev`, which a parallel session can shadow into a
  wrong-target run. Rebuild the image after ANY FE source change (`docker compose build frontend` →
  `docker rm -f qc-frontend; docker run -d --name qc-frontend --network infra_default -p 5185:80 infra-frontend`).
- **Shared checkout** — commit each spec with `git add <file>` then `git commit -- <pathspec>` (commits the
  working tree for that path only, NOT the shared index). NEVER `git add -A`; NEVER rewrite history (parallel
  sessions are live). Verify each commit's file list before moving on.
- **Non-destructive by default** — reachability/fail-closed specs must be safe + self-cleaning (reset armed
  settings in a `finally`). A genuinely destructive scenario (erase/distill) creates + tears down its OWN
  fixtures; it must NOT wipe the shared account's real data.
- **Verify by EFFECT** — assert visible UI state + server-side row checks; never raw-stream/unit-mock.
- **Selectors via PoM + `data-testid`** only (repo CONVENTIONS.md). A new flow gets its testid before its spec.

## 3 · SETUP (do first — unblocks the stateful scenarios)
- **Set a default local chat model for the test account** (fixes F-QC-1): the assistant chat can't
  auto-create a session without a resolvable model, so S1/S7/S13 stall on the NewChatDialog. Owner chose
  **Gemma-4 26B-A4B QAT** — `user_model_id = 019ebb72-27a2-72f3-a42d-d2d0e0ded179` (local lm_studio, $0).
  Insert/seed the `user_default_models` row for the test account (owner `019d5e3c-…`) → this model for the
  chat capability. Record the exact SQL + a revert note here after doing it. Legitimate test-account setup
  (production users have a default). NOTE: gemma-QAT is a *reasoning* model — fine for session/distill; for
  proactive CONTENT it may hit the scaffold-cleanup → static fallback (already proven fail-safe), so S-proactive
  content-quality assertions should tolerate the fallback.

## 4 · SCENARIO BOARD (done = a pasted green `playwright test` line, NOT a checkmark)
| # | Scenario | Spec | Status | Evidence |
|---|---|---|---|---|
| S9 | consent fail-closed | assistant-data-rights | ✅ | 333663699 — green :5185 |
| S2/S12 | Memory/Journal reachable desktop + recall | assistant-data-rights | ✅ | 333663699 |
| S5 | erase two-step confirm (cancel) | assistant-data-rights | ✅ | 333663699 |
| S8 | new-epoch confirm (cancel) | assistant-data-rights | ✅ | 333663699 |
| S7 | Practice nav → /roleplay | assistant-data-rights | ✅ | 333663699 (nav only; full interview = S7b) |
| S10 | autonomous toggles OFF default | assistant-autonomous | ✅ | 333663699 |
| T4 | schedule + proactive owner-scoping (BLOCKING) | assistant-tenancy | ✅ | 0de26bf98 |
| S11 | multi-device server-SSOT | assistant-multidevice | ✅ | f8f42f2f2 |
| **S1** | end-of-day: capture→distill→review→keep→journal | assistant-endofday (TODO) | ⬜ | needs §3 model |
| **S13** | first-run once (mobile, server-gated) | assistant-firstrun (TODO) | ⬜ | mobile viewport |
| **S3** | correct a memory (re-distill supersedes) | assistant-correct (TODO) | ⬜ | needs a kept entry |
| **S4** | forget a person (gone from recall) | assistant-forget (TODO) | ⬜ | needs a remembered person |
| **S6** | weekly reflection + dismiss | assistant-reflection (TODO) | ⬜ | needs a reflection draft |
| **S7b** | interview wraps at Q5 / at budget + scorecard | assistant-interview (TODO) | ⬜ | needs §3 model |
| **S10b** | autonomous ARM → fires (eod_distill) | assistant-autonomous (extend) | ⬜ | scheduler tick + cleanup |
| **T1** | recall cross-user isolation | assistant-tenancy (extend) | ⬜ | seed A facts |
| **T2/T3** | forget/erase isolation + forged user_id rejected | assistant-tenancy (extend) | ⬜ | 2-user |
| **MCP** | agent-driven exploratory pass (discoverability) | — | ⬜ | findings recorded |
| **CV** | verify-by-effect on ≥2 seams (distill visible, wrap at Q5) | — | ⬜ | findings recorded |

## 5 · Decisions register
- 2026-07-16 · Run against a BUILT image on a free port (:5185), not vite dev (owner constraint).
- 2026-07-16 · Set a default local chat model for the test account to unblock stateful flows (F-QC-1).

## 6 · Findings / drift log (append as you go)
- **F-QC-1** — `/assistant` auto-opens a full-screen `NewChatDialog` (generic new-chat + model picker) that
  covers the home; persists for a no-default-model account. Harness dismisses it (`new-chat-dismiss`). §3
  addresses the root (default model). A diary assistant greeting with a model-picker modal = a UX review item.
- **Shared-index sweep (2026-07-16):** commit 333663699 accidentally swept 8 pre-staged files from a parallel
  studio-s7 session (no data loss; not rewritten — session live). Subsequent commits use `git commit -- <path>`.

## 7 · Checkpoints
- The stateful/destructive specs (S1/S3/S4/S6/S10b) are the risk surface — each self-fixtures + tears down.
- Owner checkpoint only at genuine product decisions or a destructive/irreversible action.
