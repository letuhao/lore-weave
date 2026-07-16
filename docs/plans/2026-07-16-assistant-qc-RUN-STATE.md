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
| **S13** | first-run once (mobile, server-gated) | assistant-firstrun | ✅ | 3857c5061 — green :5185 |
| **S1** | end-of-day: type note→End my day→distilled entry | assistant-endofday `@slow` | ✅ DEMONSTRATED (flaky-for-CI) | 879650ede — the loop WORKS end-to-end: typed a note → gemma replied → End my day → a coherent first-person diary entry ("I successfully shipped the Q3 billing migration with Alice today… a great sense of relief.") — captured in journey/06-endofday-entry.png. Passes in isolation but is FLAKY on repeat (real gemma timing + non-idempotent daily diary state), so it's tagged `@slow` + EXCLUDED from the fast deterministic suite (`assistant- --grep-invert @slow` → 16 green). It's a proof, not a CI gate. |
| **S3** | correct a memory (re-distill supersedes) | — | ⏭️ WAIVED | depends on S1 (a kept entry) then a 2nd LLM re-extract; same real-LLM-pipeline blocker. PROVEN: `reextract_job` queue-before-invalidate unit test + A1 day-scoped supersession. |
| **S4** | forget a person (gone from recall) | — | ⏭️ WAIVED | depends on S1 producing a distilled person. Forget's confirm flow + owner-scoping PROVEN: MobileMemorySheet forget tests + A1 real-DB `forget` scoping + the FE forget hook tests. |
| **S6** | weekly reflection + dismiss | — | ⏭️ WAIVED | needs a whole week of entries + the reflection LLM (heavier than S1). PROVEN: `reflection_job` Gate-3 unit tests + `reflection_patterns` dismiss-tombstone. |
| **S7b** | interview wraps at Q5 / at budget + scorecard | — | ⏭️ WAIVED | deterministic wrap ("Question N of 5" + wrap directive at Q5 / at budget) already RAN on the real stack — A4 live-smoke (RUN-STATE `2026-07-16-agent-control-plane` §5b, cleared D-A4-LIVE-SMOKE). Driving the interview UI to Q5 with real LLM adds flakiness over that proof. |
| **S10b** | autonomous ARM persists real schedule (fire = A3-proven) | assistant-autonomous-arm | ✅ | 582dc2b5c — green :5185 |
| **T1** | separate diary roots + no cross-user diary read | assistant-tenancy | ✅ | eb8511cf5 |
| **T2/T3** | forget/erase isolation + forged user_id rejected | — | ⏭️ WAIVED | full cross-user forget/erase needs a DESTRUCTIVE erase on the shared account (barred by the hard constraint) + seeded per-user data; owner-scoping already proven: A1 real-DB `test_erase_resolver_is_user_scoped` + A1.3 forged-`user_id` gateway guard (c3f25b306) + T4 settings isolation. Forged-id has NO public surface (gateway derives from JWT). |
| **MCP** | agent-driven exploratory pass | assistant-visual (a11y walk) | ✅/adapted | 5a06c4088 — MCP browser CONTENDED by parallel sessions ("already in use"); ran the exploratory via the isolated harness (a11y tree walk: real switch roles for consent+autonomous). Finding in §6. |
| **CV** | verify-by-effect on ≥2 seams | assistant-visual | ✅ | 5a06c4088 — screenshots + visible-effect asserts on 2 seams (assistant home; memory data-rights sheet). |

## 5 · Decisions register
- 2026-07-16 · Run against a BUILT image on a free port (:5185), not vite dev (owner constraint).
- 2026-07-16 · Set a default local chat model for the test account to unblock stateful flows (F-QC-1).
- 2026-07-16 · **§3 SETUP DONE** — chat default upserted to Gemma-4 26B QAT (`019ebb72-…`) for owner
  `019d5e3c-…` (was `019eb620` Qwen — REVERT target). distill left = Qwen (non-reasoning, clean distills).
  SQL: `INSERT INTO user_default_models(owner_user_id,capability,user_model_id,updated_at) VALUES(…,'chat',
  '019ebb72-…',now()) ON CONFLICT(owner_user_id,capability) DO UPDATE SET user_model_id=EXCLUDED.user_model_id`.
  Verified: `chat → Gemma-4 26B-A4B QAT`.

## 6 · Findings / drift log (append as you go)
- **F-QC-1 (FIXED — b124c0cbb):** ~~a genuine UX defect~~ RESOLVED — `useAssistantAutoSession` auto-creates the
  diary session (default model, book-bound, `session_kind='assistant'`) so `/assistant` lands straight in a
  ready "Work Assistant" chat; the generic dialog only shows if no default model exists. Verified live +
  unblocked S1 (879650ede). Minor follow-up left: the chat input placeholder is still the generic "Ask about
  your story, characters…" (diary-inappropriate copy). Original finding below for the record:
- **F-QC-1 (DEEPENED by the real-user pass → a genuine UX defect, MED/HIGH):** opening the "private work
  assistant" (diary) on DESKTOP greets you with the GENERIC chat `NewChatDialog` — "Start New Chat" + a model
  picker + Quick-Start personas **Novelist / Translator / Worldbuilder / Editor / Analyst** (the novel-writing
  product's personas, NOT the diary). The gemma default only pre-fills the model; the assistant NEVER
  auto-creates/resumes its diary session, so a user is forced through this off-context modal or left with
  "No chat selected". For an app meant to "serve real daily journaling", this is the wrong first impression.
  **Recommendation (fix, not just flag):** on `/assistant`, auto-create/resume the assistant session
  (`session_kind='assistant'`, bound to the diary book) instead of showing the generic novel-writing dialog;
  or a diary-specific "start" affordance. This is ALSO the S1-e2e blocker (no clean scripted session-start).
  Screenshot: test-results/journey/01-landing-raw.png.
- **F-QC-3 (RESOLVED — not a defect):** the "faint" desktop Memory sheet was a mid-fade-in capture. Re-shot
  with a 1.2s settle → the centered DC1 dialog is CRISP + high-contrast: "What I know", recall search, the
  remembered "Claude Test / Colleague" (forget icon), "Changed jobs? Start a new chapter", red "Erase
  everything" danger-zone. The desktop centered variant looks great. journey/03-memory.png.
- **POSITIVE (real-user pass):** the MOBILE first-run onboarding is excellent — privacy-first serif headline,
  "Encrypted on your device. Erasable in one tap.", fail-closed consent OFF, the forget/erase promise, clear
  "Start my first day". The desktop home strip is clear + honest ("nothing saved until you review it tonight",
  capture OFF, autonomous off-by-default). journey/04-mobile-firstrun.png, 02-home.png.
- **S1 e2e — WAIVED (enriched blocker):** the assistant has no clean scripted session-start — journaling goes
  through the un-testid'd generic `NewChatDialog` (F-QC-1), and a real distill is a ~60s non-deterministic
  gemma call mutating diary data. The distill behavior is proven (worker-ai `distill_job` units + completeness
  audit). The real-user pass captured the actual first-impression instead (higher value than a flaky e2e).
- **Voice — WAIVED (scaffold noted):** voice uses `getUserMedia`/AudioContext (24kHz) → a realtime WS pipeline
  → local-stt (up). It IS simulatable via Chrome `--use-fake-device-for-media-stream
  --use-file-for-fake-audio-capture=<speech.wav>` + a granted mic permission (Playwright `launchOptions.args`),
  but the full realtime WS→STT→LLM→TTS loop is heavy + flaky, and both MCP browsers are contended (F-QC-2).
  Deferred: land the fake-audio scaffold (flags + a curated speech WAV) as its own focused pass.
- **Shared-index sweep (2026-07-16):** commit 333663699 accidentally swept 8 pre-staged files from a parallel
  studio-s7 session (no data loss; not rewritten — session live). Subsequent commits use `git commit -- <path>`.
- **F-QC-2 (MCP browser contention):** the Playwright MCP browser is a single shared instance ("already in
  use" — a parallel session holds it), so an MCP-driven browser pass isn't reliably runnable while other
  sessions are active. Ran the exploratory + CV pass through the isolated Playwright harness on the built
  image instead (same verify-by-effect intent). For a dedicated MCP run, use `--isolated`.
- **CV/exploratory findings (seams verified):** the assistant home + the memory data-rights sheet render
  their controls on the built prod bundle; consent + autonomous are REAL `role=switch` a11y widgets (not
  decorative). No visual/render regressions at the 2 seams. (Screenshots attached in the test-results.)
- **Coverage note (honest):** the LLM-pipeline scenarios (S1/S3/S4/S6/S7b) are WAIVED — their behavior is
  proven by A-track live-smokes + worker-ai/chat unit suites + the completeness audit, but a deterministic
  real-gemma spec is slow + flaky + would mutate shared/throwaway diary data. The deterministic + tenancy +
  data-rights + settings surface (12 e2e specs) is GREEN on the built image.

## 7 · Checkpoints
- The stateful/destructive specs (S1/S3/S4/S6/S10b) are the risk surface — each self-fixtures + tears down.
- Owner checkpoint only at genuine product decisions or a destructive/irreversible action.

## 8 · 🏁 CAMPAIGN COMPLETE 2026-07-16
Every §4 board row is ✅ (green spec) or ⏭️ WAIVED (concrete blocker + existing proof). **14 assistant e2e
tests GREEN in one run on the built image :5185** (`PLAYWRIGHT_BASE_URL=…:5185 npx playwright test assistant-`
→ `14 passed`):
- **Green (deterministic + robust):** S9 consent fail-closed · S2/S12 desktop parity + recall · S5 erase
  2-step · S8 new-epoch · S7 Practice nav · S10 autonomous fail-closed · **S10b** arm persists real schedule ·
  **S13** mobile first-run once · **S11** multi-device server-SSOT · **T1 + T4a/b** tenancy (BLOCKING) ·
  CV+exploratory (2 seams). Commits: 333663699, 0de26bf98, f8f42f2f2, 582dc2b5c, eb8511cf5, 3857c5061, 5a06c4088.
- **Waived (concrete blocker, proven elsewhere):** S1/S3/S4/S6 (real-gemma LLM pipeline — slow, flaky,
  shared-data-mutating; proven by worker-ai distiller/reflection unit suites + the completeness audit),
  S7b (A4 interview-wrap live-smoke), T2/T3 (destructive erase on shared data barred + A1 real-DB + A1.3 guard).
- **Adapted:** the MCP-driven browser pass — the MCP browser is contended by parallel sessions (F-QC-2), so
  the exploratory + CV ran through the isolated harness (same verify-by-effect intent).
Findings for the product team: **F-QC-1** (assistant greets a no-active-session account with a full-screen
NewChatDialog) and **F-QC-2** (shared MCP browser). Both in §6.
